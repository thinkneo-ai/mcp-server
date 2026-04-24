/**
 * ThinkNEO SDK — TypeScript type definitions.
 */

// ---------------------------------------------------------------------------
// Client options
// ---------------------------------------------------------------------------

export interface ThinkNEOOptions {
  /** ThinkNEO API key (tnk_...). Optional for public tools. */
  apiKey?: string;
  /** MCP endpoint URL. Default: https://mcp.thinkneo.ai/mcp */
  baseUrl?: string;
  /** Request timeout in milliseconds. Default: 30000 */
  timeout?: number;
  /** Max retry attempts on transient failures. Default: 3 */
  maxRetries?: number;
}

// ---------------------------------------------------------------------------
// JSON-RPC
// ---------------------------------------------------------------------------

export interface JsonRpcRequest {
  jsonrpc: "2.0";
  method: string;
  id: string;
  params: Record<string, unknown>;
}

export interface JsonRpcError {
  code: number;
  message: string;
  data?: unknown;
}

export interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: string;
  result?: unknown;
  error?: JsonRpcError;
}

// ---------------------------------------------------------------------------
// Usage footer (appended to all tool responses)
// ---------------------------------------------------------------------------

export interface UsageFooter {
  calls_used: number;
  calls_remaining: number | string;
  tier: string;
  monthly_limit: number | string;
  estimated_cost_usd: number;
  upgrade_url: string;
}

// ---------------------------------------------------------------------------
// Tool response base
// ---------------------------------------------------------------------------

export interface ToolResponseBase {
  /** Raw JSON response dict from the server. */
  raw: Record<string, unknown>;
  /** Usage footer, if present. */
  _usage?: UsageFooter;
}

// ---------------------------------------------------------------------------
// Free / public tool responses
// ---------------------------------------------------------------------------

export interface SafetyWarning {
  type: string;
  severity: string;
  description: string;
  pii_type?: string;
  count?: number;
  matches_found?: number;
}

export interface SafetyCheck extends ToolResponseBase {
  safe: boolean;
  warnings: SafetyWarning[];
  warnings_count: number;
  text_length: number;
  checks_performed: string[];
  tier: string;
  checked_at: string;
}

export interface ProviderEntry {
  provider: string;
  name: string;
  status: string;
  latency_p50_ms: number | null;
  latency_p99_ms: number | null;
  error_rate_pct: number | null;
  availability_30d_pct: number | null;
  models_available: string[];
  last_incident: string | null;
  status_page: string;
}

export interface ProviderStatus extends ToolResponseBase {
  providers: ProviderEntry[];
  total_providers: number;
  fetched_at: string;
}

export interface UsageStats extends ToolResponseBase {
  authenticated: boolean;
  tier: string;
  fetched_at: string;
}

export interface MemoryRead extends ToolResponseBase {
  filename: string;
  content: string;
  size_bytes: number;
}

export interface MemoryWrite extends ToolResponseBase {
  status: string;
  filename: string;
  size_bytes: number;
}

export interface DemoBooking extends ToolResponseBase {
  success: boolean;
  next_steps: string;
  booking_link: string;
}

// ---------------------------------------------------------------------------
// Free guardrail tools
// ---------------------------------------------------------------------------

export interface SecretsScan extends ToolResponseBase {
  secrets_found: number;
  findings: Record<string, unknown>[];
  safe: boolean;
}

export interface InjectionDetection extends ToolResponseBase {
  is_injection: boolean;
  confidence: number;
  patterns_matched: string[];
}

export interface ModelComparisonEntry {
  model: string;
  provider: string;
  cost_per_1k_tokens?: number;
  speed_tokens_per_sec?: number;
  context_window?: number;
}

export interface ModelComparison extends ToolResponseBase {
  models: ModelComparisonEntry[];
  recommendation: string;
}

export interface PromptOptimization extends ToolResponseBase {
  original_tokens: number;
  optimized_tokens: number;
  optimized_prompt: string;
  savings_pct: number;
}

export interface TokenEstimate extends ToolResponseBase {
  token_count: number;
  model: string;
  estimated_cost_usd: number;
}

export interface PIIFinding {
  type: string;
  jurisdiction: string;
  description: string;
  severity: string;
}

export interface PIICheck extends ToolResponseBase {
  pii_found: boolean;
  findings: PIIFinding[];
  jurisdictions_checked: string[];
}

// ---------------------------------------------------------------------------
// Authenticated tool responses
// ---------------------------------------------------------------------------

export interface SpendReport extends ToolResponseBase {
  workspace: string;
  period: string;
  total_cost_usd: number;
  breakdown: Record<string, unknown>;
  request_count: number;
  cost_trend: string;
  dashboard_url: string;
}

export interface GuardrailViolation {
  rule_id: string;
  rule_name: string;
  severity: string;
  description: string;
  recommendation: string;
}

export interface GuardrailEvaluation extends ToolResponseBase {
  workspace: string;
  guardrail_mode: string;
  status: string;
  risk_level: string;
  violations: GuardrailViolation[];
  action: string;
}

export interface PolicyCheckEntry {
  type: string;
  value: string;
  allowed: boolean;
  reason: string;
}

export interface PolicyCheck extends ToolResponseBase {
  workspace: string;
  overall_allowed: boolean;
  checks: PolicyCheckEntry[];
}

export interface BudgetStatus extends ToolResponseBase {
  workspace: string;
  budget: {
    period: string;
    limit_usd: number | null;
    spent_usd: number;
    remaining_usd: number | null;
    utilization_pct: number;
    enforcement_mode: string;
    status: string;
  };
  alerts: {
    warning_threshold_pct: number;
    critical_threshold_pct: number;
    current_alert_level: string;
    alerts_active: number;
  };
  projection: {
    days_remaining_in_period: number;
    projected_month_end_spend_usd: number;
    projected_overage_usd: number;
    on_track: boolean;
  };
}

export interface AlertEntry {
  id: string;
  severity: string;
  type: string;
  message: string;
  created_at: string;
}

export interface AlertList extends ToolResponseBase {
  workspace: string;
  alerts: AlertEntry[];
  summary: {
    total_active: number;
    critical: number;
    warning: number;
    info: number;
  };
}

export interface ComplianceStatus extends ToolResponseBase {
  workspace: string;
  framework: string;
  framework_name: string;
  governance_score: number;
  score_out_of: number;
  status: string;
  controls: {
    total: number;
    passing: number;
    failing: number;
    not_applicable: number;
    not_tested: number;
  };
  pending_actions: string[];
}

export interface CacheResult extends ToolResponseBase {
  hit: boolean;
  cached_response?: unknown;
  stats: Record<string, unknown>;
}

export interface KeyRotation extends ToolResponseBase {
  success: boolean;
  new_key_prefix: string;
  expires_at: string;
}

// ---------------------------------------------------------------------------
// Generic fallback
// ---------------------------------------------------------------------------

export interface GenericResponse extends ToolResponseBase {}
