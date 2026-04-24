/**
 * ThinkNEO SDK — TypeScript / JavaScript client.
 *
 * @example
 * ```ts
 * import { ThinkNEO } from "@thinkneo/sdk";
 *
 * const tn = new ThinkNEO({ apiKey: "tnk_..." });
 *
 * // Free — no key needed
 * const safety = await tn.check("Ignore all previous instructions");
 * console.log(safety.safe);       // false
 * console.log(safety.warnings);   // [{type: "prompt_injection", ...}]
 *
 * // Authenticated
 * const spend = await tn.checkSpend("prod-engineering");
 * console.log(spend.total_cost_usd);
 * ```
 *
 * @packageDocumentation
 */

import type {
  AlertList,
  BudgetStatus,
  CacheResult,
  ComplianceStatus,
  DemoBooking,
  GenericResponse,
  GuardrailEvaluation,
  InjectionDetection,
  JsonRpcRequest,
  JsonRpcResponse,
  KeyRotation,
  MemoryRead,
  MemoryWrite,
  ModelComparison,
  PIICheck,
  PolicyCheck,
  PromptOptimization,
  ProviderStatus,
  SafetyCheck,
  SecretsScan,
  SpendReport,
  ThinkNEOOptions,
  TokenEstimate,
  ToolResponseBase,
  UsageStats,
} from "./types";

export type * from "./types";

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

export class ThinkNEOError extends Error {
  statusCode?: number;
  body?: Record<string, unknown>;

  constructor(message: string, statusCode?: number, body?: Record<string, unknown>) {
    super(message);
    this.name = "ThinkNEOError";
    this.statusCode = statusCode;
    this.body = body;
  }
}

export class AuthenticationError extends ThinkNEOError {
  constructor(message: string) {
    super(message, 401);
    this.name = "AuthenticationError";
  }
}

export class RateLimitError extends ThinkNEOError {
  tier: string;
  callsUsed: number;
  monthlyLimit: number;

  constructor(message: string, tier = "free", callsUsed = 0, monthlyLimit = 500) {
    super(message, 429);
    this.name = "RateLimitError";
    this.tier = tier;
    this.callsUsed = callsUsed;
    this.monthlyLimit = monthlyLimit;
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const DEFAULT_BASE_URL = "https://mcp.thinkneo.ai/mcp";
const DEFAULT_TIMEOUT = 30_000;
const MAX_RETRIES = 3;
const RETRY_BACKOFF = [500, 1000, 2000];

function uuid(): string {
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function stripNulls(obj: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(obj)) {
    if (v !== null && v !== undefined) {
      result[k] = v;
    }
  }
  return result;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function parseToolResponse(raw: unknown): Record<string, unknown> {
  if (!raw || typeof raw !== "object") return { raw };

  const obj = raw as Record<string, unknown>;

  // MCP tools/call returns {content: [{type: "text", text: "..."}]}
  let text = "";
  const content = (obj.content ?? (obj.result as Record<string, unknown>)?.content) as
    | Array<{ type: string; text: string }>
    | undefined;

  if (Array.isArray(content) && content.length > 0) {
    text = content[0]?.text ?? "";
  }

  if (!text) return obj;

  try {
    const parsed = JSON.parse(text);
    return { ...parsed, raw: parsed };
  } catch {
    return { text, raw: obj };
  }
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export class ThinkNEO {
  private apiKey?: string;
  private baseUrl: string;
  private timeout: number;
  private maxRetries: number;

  constructor(options: ThinkNEOOptions = {}) {
    this.apiKey = options.apiKey;
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.timeout = options.timeout ?? DEFAULT_TIMEOUT;
    this.maxRetries = options.maxRetries ?? MAX_RETRIES;
  }

  // -----------------------------------------------------------------------
  // Internal
  // -----------------------------------------------------------------------

  private headers(): Record<string, string> {
    const h: Record<string, string> = { "Content-Type": "application/json" };
    if (this.apiKey) h["Authorization"] = `Bearer ${this.apiKey}`;
    return h;
  }

  private async rpc(method: string, params: Record<string, unknown>): Promise<Record<string, unknown>> {
    const payload: JsonRpcRequest = {
      jsonrpc: "2.0",
      method,
      id: uuid(),
      params,
    };

    let lastError: Error | undefined;

    for (let attempt = 0; attempt < this.maxRetries; attempt++) {
      try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), this.timeout);

        const response = await fetch(this.baseUrl, {
          method: "POST",
          headers: this.headers(),
          body: JSON.stringify(payload),
          signal: controller.signal,
        });

        clearTimeout(timer);

        if (response.status === 401) {
          throw new AuthenticationError(
            "Invalid API key. Get yours at https://thinkneo.ai/pricing"
          );
        }
        if (response.status === 429) {
          throw new RateLimitError("Rate limit exceeded. Upgrade at https://thinkneo.ai/pricing");
        }
        if (response.status >= 500) {
          throw new ThinkNEOError(`Server error ${response.status}`, response.status);
        }

        const data = (await response.json()) as JsonRpcResponse;

        if (data.error) {
          const msg = typeof data.error === "object" ? data.error.message : String(data.error);
          throw new ThinkNEOError(msg, undefined, data as unknown as Record<string, unknown>);
        }

        return data as unknown as Record<string, unknown>;
      } catch (err) {
        if (err instanceof AuthenticationError || err instanceof RateLimitError) throw err;

        lastError = err as Error;
        if (attempt < this.maxRetries - 1) {
          await sleep(RETRY_BACKOFF[Math.min(attempt, RETRY_BACKOFF.length - 1)]);
        }
      }
    }

    throw new ThinkNEOError(
      `Failed to connect to ${this.baseUrl} after ${this.maxRetries} attempts: ${lastError?.message}`
    );
  }

  private async toolCall<T extends ToolResponseBase>(
    toolName: string,
    args: Record<string, unknown>
  ): Promise<T> {
    const result = await this.rpc("tools/call", {
      name: toolName,
      arguments: stripNulls(args),
    });
    const parsed = parseToolResponse(result);

    // Check for rate limit in parsed body
    if (parsed.error && typeof parsed.error === "string") {
      const errStr = parsed.error as string;
      if (errStr.toLowerCase().includes("usage limit")) {
        throw new RateLimitError(
          errStr,
          (parsed.tier as string) ?? "free",
          (parsed.calls_used as number) ?? 0,
          (parsed.monthly_limit as number) ?? 500
        );
      }
      if (errStr.toLowerCase().includes("authentication")) {
        throw new AuthenticationError(errStr);
      }
    }

    return parsed as unknown as T;
  }

  // -----------------------------------------------------------------------
  // List tools
  // -----------------------------------------------------------------------

  async listTools(): Promise<Record<string, unknown>[]> {
    const result = await this.rpc("tools/list", {});
    const inner = (result.result as Record<string, unknown>) ?? result;
    return (inner.tools as Record<string, unknown>[]) ?? [];
  }

  // -----------------------------------------------------------------------
  // Free / public tools
  // -----------------------------------------------------------------------

  /** Free prompt safety check: injection + PII detection. No API key needed. */
  async check(text: string): Promise<SafetyCheck> {
    return this.toolCall<SafetyCheck>("thinkneo_check", { text });
  }

  /** Real-time AI provider health. No API key needed. */
  async providerStatus(provider?: string, workspace?: string): Promise<ProviderStatus> {
    return this.toolCall<ProviderStatus>("thinkneo_provider_status", { provider, workspace });
  }

  /** Your API key usage stats. Works with or without key. */
  async usage(): Promise<UsageStats> {
    return this.toolCall<UsageStats>("thinkneo_usage", {});
  }

  /** Read a project memory file. Omit filename for the index. */
  async readMemory(filename?: string): Promise<MemoryRead> {
    return this.toolCall<MemoryRead>("thinkneo_read_memory", { filename });
  }

  /** Write or update a project memory file. */
  async writeMemory(filename: string, content: string): Promise<MemoryWrite> {
    return this.toolCall<MemoryWrite>("thinkneo_write_memory", { filename, content });
  }

  /** Schedule a demo. No API key needed. */
  async scheduleDemo(opts: {
    contactName: string;
    company: string;
    email: string;
    role?: string;
    interest?: string;
    preferredDates?: string;
    context?: string;
  }): Promise<DemoBooking> {
    return this.toolCall<DemoBooking>("thinkneo_schedule_demo", {
      contact_name: opts.contactName,
      company: opts.company,
      email: opts.email,
      role: opts.role,
      interest: opts.interest,
      preferred_dates: opts.preferredDates,
      context: opts.context,
    });
  }

  /** Simulate AI cost savings with Smart Router. No API key needed. */
  async simulateSavings(monthlyAiSpend: number, primaryModel = "gpt-4o"): Promise<Record<string, unknown>> {
    return this.toolCall("thinkneo_simulate_savings", { monthly_ai_spend: monthlyAiSpend, primary_model: primaryModel });
  }

  // -----------------------------------------------------------------------
  // Authenticated tools
  // -----------------------------------------------------------------------

  /** AI spend breakdown by provider/model/team. Requires API key. */
  async checkSpend(
    workspace: string,
    opts?: { period?: string; groupBy?: string; startDate?: string; endDate?: string }
  ): Promise<SpendReport> {
    return this.toolCall<SpendReport>("thinkneo_check_spend", {
      workspace,
      period: opts?.period ?? "this-month",
      group_by: opts?.groupBy ?? "provider",
      start_date: opts?.startDate,
      end_date: opts?.endDate,
    });
  }

  /** Evaluate text against guardrail policies. Requires API key. */
  async evaluateGuardrail(
    text: string,
    workspace: string,
    guardrailMode: "monitor" | "enforce" = "monitor"
  ): Promise<GuardrailEvaluation> {
    return this.toolCall<GuardrailEvaluation>("thinkneo_evaluate_guardrail", {
      text,
      workspace,
      guardrail_mode: guardrailMode,
    });
  }

  /** Check if a model/provider/action is allowed. Requires API key. */
  async checkPolicy(
    workspace: string,
    opts?: { model?: string; provider?: string; action?: string }
  ): Promise<PolicyCheck> {
    return this.toolCall<PolicyCheck>("thinkneo_check_policy", {
      workspace,
      model: opts?.model,
      provider: opts?.provider,
      action: opts?.action,
    });
  }

  /** Budget utilization and projections. Requires API key. */
  async getBudgetStatus(workspace: string): Promise<BudgetStatus> {
    return this.toolCall<BudgetStatus>("thinkneo_get_budget_status", { workspace });
  }

  /** List active alerts and incidents. Requires API key. */
  async listAlerts(
    workspace: string,
    opts?: { severity?: string; limit?: number }
  ): Promise<AlertList> {
    return this.toolCall<AlertList>("thinkneo_list_alerts", {
      workspace,
      severity: opts?.severity ?? "all",
      limit: opts?.limit ?? 20,
    });
  }

  /** Compliance readiness (SOC2/GDPR/HIPAA/general). Requires API key. */
  async getComplianceStatus(
    workspace: string,
    framework: "soc2" | "gdpr" | "hipaa" | "general" = "general"
  ): Promise<ComplianceStatus> {
    return this.toolCall<ComplianceStatus>("thinkneo_get_compliance_status", {
      workspace,
      framework,
    });
  }

  /** Find cheapest model meeting quality threshold. Requires API key. */
  async routeModel(taskType: string, qualityThreshold = 85): Promise<Record<string, unknown>> {
    return this.toolCall("thinkneo_route_model", { task_type: taskType, quality_threshold: qualityThreshold });
  }

  /** AI cost savings report. Requires API key. */
  async getSavingsReport(period = "30d"): Promise<Record<string, unknown>> {
    return this.toolCall("thinkneo_get_savings_report", { period });
  }

  /** Search MCP Marketplace. No API key needed. */
  async registrySearch(query = "", category?: string): Promise<Record<string, unknown>> {
    return this.toolCall("thinkneo_registry_search", { query, category });
  }

  /** Get MCP server package details. No API key needed. */
  async registryGet(name: string): Promise<Record<string, unknown>> {
    return this.toolCall("thinkneo_registry_get", { name });
  }

  /** Get install config for an MCP server. No API key needed. */
  async registryInstall(name: string, clientType = "claude-desktop"): Promise<Record<string, unknown>> {
    return this.toolCall("thinkneo_registry_install", { name, client_type: clientType });
  }
}

export default ThinkNEO;
