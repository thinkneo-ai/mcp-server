"""
Developer Landing Page — /mcp/docs

Dark-themed HTML page showing what ThinkNEO MCP is, available tools,
free tier info, and connection instructions.
"""

from __future__ import annotations

LANDING_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ThinkNEO MCP Server — Developer Docs</title>
<meta name="description" content="ThinkNEO MCP Server — Enterprise AI Control Plane. Connect from Claude Desktop, Cursor, or ChatGPT. 500 free calls/month.">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🧠</text></svg>">
<style>
  :root {
    --bg: #0a0f1a;
    --bg2: #111827;
    --bg3: #1a2332;
    --primary: #1e50dc;
    --accent: #14b4a0;
    --text: #e2e8f0;
    --text2: #94a3b8;
    --border: #1e293b;
    --code-bg: #0d1117;
    --success: #22c55e;
    --warning: #f59e0b;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    min-height: 100vh;
  }
  .container { max-width: 960px; margin: 0 auto; padding: 0 24px; }

  /* Header */
  header {
    border-bottom: 1px solid var(--border);
    padding: 20px 0;
    background: var(--bg2);
  }
  header .container {
    display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;
  }
  .logo { display: flex; align-items: center; gap: 12px; text-decoration: none; color: var(--text); }
  .logo-icon {
    width: 40px; height: 40px; background: linear-gradient(135deg, var(--primary), var(--accent));
    border-radius: 10px; display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 18px; color: white;
  }
  .logo-text { font-size: 20px; font-weight: 700; }
  .logo-text span { color: var(--accent); }
  .badge {
    display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600;
    background: rgba(30, 80, 220, 0.15); color: var(--primary); border: 1px solid rgba(30, 80, 220, 0.3);
  }
  .header-links { display: flex; gap: 16px; }
  .header-links a { color: var(--text2); text-decoration: none; font-size: 14px; transition: color 0.2s; }
  .header-links a:hover { color: var(--accent); }

  /* Hero */
  .hero { padding: 60px 0 40px; text-align: center; }
  .hero h1 { font-size: 36px; font-weight: 800; margin-bottom: 16px; line-height: 1.2; }
  .hero h1 .accent { color: var(--accent); }
  .hero h1 .primary { color: var(--primary); }
  .hero p { font-size: 18px; color: var(--text2); max-width: 640px; margin: 0 auto 28px; }
  .hero-badges { display: flex; justify-content: center; gap: 12px; flex-wrap: wrap; }
  .hero-badge {
    padding: 6px 16px; border-radius: 8px; font-size: 13px; font-weight: 600;
    background: var(--bg3); border: 1px solid var(--border);
  }
  .hero-badge.green { border-color: rgba(34, 197, 94, 0.3); color: var(--success); }
  .hero-badge.blue { border-color: rgba(30, 80, 220, 0.3); color: var(--primary); }
  .hero-badge.teal { border-color: rgba(20, 180, 160, 0.3); color: var(--accent); }

  /* Sections */
  section { padding: 40px 0; }
  section + section { border-top: 1px solid var(--border); }
  h2 { font-size: 24px; font-weight: 700; margin-bottom: 20px; }
  h3 { font-size: 16px; font-weight: 600; margin-bottom: 8px; color: var(--accent); }

  /* Tool grid */
  .tool-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  @media (max-width: 640px) { .tool-grid { grid-template-columns: 1fr; } }
  .tool-card {
    background: var(--bg3); border: 1px solid var(--border); border-radius: 10px;
    padding: 16px; transition: border-color 0.2s;
  }
  .tool-card:hover { border-color: var(--primary); }
  .tool-name { font-family: 'SF Mono', 'Fira Code', monospace; font-size: 13px; font-weight: 600; color: var(--accent); margin-bottom: 4px; }
  .tool-desc { font-size: 13px; color: var(--text2); line-height: 1.4; }
  .tool-tag {
    display: inline-block; margin-top: 8px; padding: 2px 8px; border-radius: 4px;
    font-size: 11px; font-weight: 600;
  }
  .tool-tag.public { background: rgba(34, 197, 94, 0.12); color: var(--success); }
  .tool-tag.auth { background: rgba(245, 158, 11, 0.12); color: var(--warning); }
  .tool-tag.free { background: rgba(20, 180, 160, 0.12); color: var(--accent); }

  /* Pricing */
  .pricing-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
  @media (max-width: 640px) { .pricing-grid { grid-template-columns: 1fr; } }
  .pricing-card {
    background: var(--bg3); border: 1px solid var(--border); border-radius: 12px; padding: 24px;
    text-align: center; transition: border-color 0.2s, transform 0.2s;
  }
  .pricing-card:hover { border-color: var(--accent); transform: translateY(-2px); }
  .pricing-card.featured { border-color: var(--primary); position: relative; }
  .pricing-card.featured::before {
    content: "POPULAR"; position: absolute; top: -10px; left: 50%; transform: translateX(-50%);
    background: var(--primary); color: white; font-size: 11px; font-weight: 700;
    padding: 2px 12px; border-radius: 10px;
  }
  .pricing-tier { font-size: 14px; font-weight: 600; color: var(--text2); text-transform: uppercase; letter-spacing: 1px; }
  .pricing-price { font-size: 32px; font-weight: 800; margin: 8px 0; }
  .pricing-price span { font-size: 14px; color: var(--text2); font-weight: 400; }
  .pricing-calls { font-size: 14px; color: var(--accent); font-weight: 600; margin-bottom: 16px; }
  .pricing-features { list-style: none; text-align: left; font-size: 13px; color: var(--text2); }
  .pricing-features li { padding: 4px 0; padding-left: 20px; position: relative; }
  .pricing-features li::before { content: "\\2713"; position: absolute; left: 0; color: var(--success); font-weight: 700; }

  /* Code blocks */
  .code-tabs { display: flex; gap: 0; margin-bottom: 0; }
  .code-tab {
    padding: 8px 20px; font-size: 13px; font-weight: 600; cursor: pointer;
    background: var(--bg3); color: var(--text2); border: 1px solid var(--border);
    border-bottom: none; border-radius: 8px 8px 0 0; transition: all 0.2s;
  }
  .code-tab.active { background: var(--code-bg); color: var(--accent); border-color: var(--accent); }
  .code-block {
    background: var(--code-bg); border: 1px solid var(--border); border-radius: 0 8px 8px 8px;
    padding: 20px; overflow-x: auto; display: none; position: relative;
  }
  .code-block.active { display: block; }
  pre { font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace; font-size: 13px; line-height: 1.6; color: #c9d1d9; white-space: pre; }
  .code-comment { color: #6e7681; }
  .code-key { color: #79c0ff; }
  .code-string { color: #a5d6ff; }
  .code-url { color: #d2a8ff; }
  .copy-btn {
    position: absolute; top: 8px; right: 8px; padding: 4px 12px; font-size: 12px;
    background: var(--bg3); color: var(--text2); border: 1px solid var(--border);
    border-radius: 6px; cursor: pointer; transition: all 0.2s;
  }
  .copy-btn:hover { color: var(--accent); border-color: var(--accent); }

  /* CTA */
  .cta {
    text-align: center; padding: 48px 0; background: linear-gradient(135deg, rgba(30, 80, 220, 0.08), rgba(20, 180, 160, 0.08));
    border-radius: 16px; margin: 40px 0;
  }
  .cta h2 { margin-bottom: 12px; }
  .cta p { color: var(--text2); margin-bottom: 24px; font-size: 16px; }
  .btn {
    display: inline-block; padding: 12px 32px; border-radius: 8px; font-size: 15px;
    font-weight: 700; text-decoration: none; transition: all 0.2s;
  }
  .btn-primary { background: var(--primary); color: white; }
  .btn-primary:hover { background: #1640b0; transform: translateY(-1px); }
  .btn-outline { border: 2px solid var(--accent); color: var(--accent); margin-left: 12px; }
  .btn-outline:hover { background: rgba(20, 180, 160, 0.1); }

  /* Footer */
  footer {
    border-top: 1px solid var(--border); padding: 24px 0; text-align: center;
    font-size: 13px; color: var(--text2);
  }
  footer a { color: var(--accent); text-decoration: none; }
  footer a:hover { text-decoration: underline; }

  /* Status indicator */
  .status-dot {
    display: inline-block; width: 8px; height: 8px; border-radius: 50%;
    background: var(--success); margin-right: 6px; animation: pulse 2s infinite;
  }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }

  .endpoint-box {
    background: var(--code-bg); border: 1px solid var(--border); border-radius: 8px;
    padding: 16px 20px; margin: 16px 0; display: flex; align-items: center;
    justify-content: space-between; flex-wrap: wrap; gap: 8px;
  }
  .endpoint-url { font-family: monospace; font-size: 15px; color: var(--accent); font-weight: 600; }
  .endpoint-method {
    background: rgba(34, 197, 94, 0.12); color: var(--success);
    padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 700;
  }
</style>
</head>
<body>

<header>
  <div class="container">
    <a href="https://thinkneo.ai" class="logo">
      <div class="logo-icon">N</div>
      <div class="logo-text">Think<span>NEO</span></div>
    </a>
    <span class="badge">MCP Server v1.2.0 + Marketplace</span>
    <div class="header-links">
      <a href="https://thinkneo.ai">Website</a>
      <a href="https://github.com/thinkneo-ai/mcp-server">GitHub</a>
      <a href="mailto:hello@thinkneo.ai">Contact</a>
    </div>
  </div>
</header>

<div class="container">
  <div class="hero">
    <h1>Enterprise <span class="primary">AI Governance</span><br>via <span class="accent">MCP</span></h1>
    <p>
      ThinkNEO is the control plane between your AI applications and providers.
      Connect from Claude Desktop, Cursor, ChatGPT, or any MCP-compatible client.
    </p>
    <div class="hero-badges">
      <div class="hero-badge green"><span class="status-dot"></span>Operational</div>
      <div class="hero-badge blue">20 Tools</div>
      <div class="hero-badge teal">500 Free Calls/mo</div>
    </div>
  </div>

  <div class="endpoint-box">
    <div>
      <span class="endpoint-method">POST</span>
      <span class="endpoint-url">https://mcp.thinkneo.ai/mcp</span>
    </div>
    <span style="color: var(--text2); font-size: 13px;">Streamable HTTP transport</span>
  </div>

  <!-- Tools Section -->
  <section>
    <h2>Available Tools</h2>
    <div class="tool-grid">
      <div class="tool-card">
        <div class="tool-name">thinkneo_provider_status</div>
        <div class="tool-desc">Real-time health and performance of 7 AI providers (OpenAI, Anthropic, Google, Mistral, xAI, Cohere, Together)</div>
        <span class="tool-tag public">PUBLIC</span>
      </div>
      <div class="tool-card">
        <div class="tool-name">thinkneo_schedule_demo</div>
        <div class="tool-desc">Book a demo or discovery call with the ThinkNEO team</div>
        <span class="tool-tag public">PUBLIC</span>
      </div>
      <div class="tool-card">
        <div class="tool-name">thinkneo_read_memory</div>
        <div class="tool-desc">Read Claude Code project memory files for cross-session context</div>
        <span class="tool-tag public">PUBLIC</span>
      </div>
      <div class="tool-card">
        <div class="tool-name">thinkneo_check</div>
        <div class="tool-desc">Free prompt safety check: detects injection patterns and PII (cards, CPF, SSN, email)</div>
        <span class="tool-tag free">FREE</span>
      </div>
      <div class="tool-card">
        <div class="tool-name">thinkneo_usage</div>
        <div class="tool-desc">Your usage stats: calls today/week/month, limits, top tools, estimated cost</div>
        <span class="tool-tag free">FREE</span>
      </div>
      <div class="tool-card">
        <div class="tool-name">thinkneo_write_memory</div>
        <div class="tool-desc">Write or update project memory files for persistent context</div>
        <span class="tool-tag public">PUBLIC</span>
      </div>
      <div class="tool-card">
        <div class="tool-name">thinkneo_evaluate_guardrail</div>
        <div class="tool-desc">Pre-flight prompt safety evaluation against workspace guardrail policies</div>
        <span class="tool-tag auth">AUTH REQUIRED</span>
      </div>
      <div class="tool-card">
        <div class="tool-name">thinkneo_check_spend</div>
        <div class="tool-desc">AI cost breakdown by provider, model, team, and time period</div>
        <span class="tool-tag auth">AUTH REQUIRED</span>
      </div>
      <div class="tool-card">
        <div class="tool-name">thinkneo_check_policy</div>
        <div class="tool-desc">Verify model, provider, or action is allowed by governance policies</div>
        <span class="tool-tag auth">AUTH REQUIRED</span>
      </div>
      <div class="tool-card">
        <div class="tool-name">thinkneo_get_budget_status</div>
        <div class="tool-desc">Budget utilization, enforcement status, and projections</div>
        <span class="tool-tag auth">AUTH REQUIRED</span>
      </div>
      <div class="tool-card">
        <div class="tool-name">thinkneo_list_alerts</div>
        <div class="tool-desc">Active alerts and incidents for a workspace</div>
        <span class="tool-tag auth">AUTH REQUIRED</span>
      </div>
      <div class="tool-card">
        <div class="tool-name">thinkneo_get_compliance_status</div>
        <div class="tool-desc">SOC2, GDPR, HIPAA compliance readiness and governance score</div>
        <span class="tool-tag auth">AUTH REQUIRED</span>
      </div>
    </div>
  </section>

  <!-- Smart Router Section -->
  <section>
    <h2>AI Smart Router</h2>
    <p style="color: var(--text2); margin-bottom: 20px;">
      Route every AI call to the cheapest model that meets your quality threshold. Track savings automatically.
    </p>
    <div class="tool-grid">
      <div class="tool-card">
        <div class="tool-name">thinkneo_route_model</div>
        <div class="tool-desc">Find the cheapest model meeting your quality threshold across 17+ models from 9 providers</div>
        <span class="tool-tag auth">AUTH REQUIRED</span>
      </div>
      <div class="tool-card">
        <div class="tool-name">thinkneo_get_savings_report</div>
        <div class="tool-desc">View your AI cost savings: original vs actual cost, breakdown by task type and model</div>
        <span class="tool-tag auth">AUTH REQUIRED</span>
      </div>
      <div class="tool-card">
        <div class="tool-name">thinkneo_simulate_savings</div>
        <div class="tool-desc">Simulate how much you'd save — enter your monthly spend and see the projected savings</div>
        <span class="tool-tag free">FREE</span>
      </div>
    </div>
  </section>

  <!-- Marketplace Section -->
  <section>
    <h2>MCP Marketplace</h2>
    <p style="color: var(--text2); margin-bottom: 20px;">
      The npm for MCP tools. Discover, publish, and install MCP servers from one registry.
    </p>
    <div class="tool-grid">
      <div class="tool-card">
        <div class="tool-name">thinkneo_registry_search</div>
        <div class="tool-desc">Search the marketplace — discover MCP servers by keyword, category, rating, or verified status</div>
        <span class="tool-tag public">PUBLIC</span>
      </div>
      <div class="tool-card">
        <div class="tool-name">thinkneo_registry_get</div>
        <div class="tool-desc">Get full details: readme, tools list, versions, reviews, security score</div>
        <span class="tool-tag public">PUBLIC</span>
      </div>
      <div class="tool-card">
        <div class="tool-name">thinkneo_registry_publish</div>
        <div class="tool-desc">Publish your MCP server — validates endpoint, runs security scan, stores entry</div>
        <span class="tool-tag auth">AUTH REQUIRED</span>
      </div>
      <div class="tool-card">
        <div class="tool-name">thinkneo_registry_review</div>
        <div class="tool-desc">Rate and review MCP servers (1-5 stars, one review per user per package)</div>
        <span class="tool-tag auth">AUTH REQUIRED</span>
      </div>
      <div class="tool-card">
        <div class="tool-name">thinkneo_registry_install</div>
        <div class="tool-desc">Get ready-to-use config JSON for Claude Desktop, Cursor, Windsurf, or custom clients</div>
        <span class="tool-tag public">PUBLIC</span>
      </div>
    </div>
  </section>

  <!-- Pricing Section -->
  <section>
    <h2>Pricing</h2>
    <div class="pricing-grid">
      <div class="pricing-card">
        <div class="pricing-tier">Free</div>
        <div class="pricing-price">$0 <span>/month</span></div>
        <div class="pricing-calls">500 calls/month</div>
        <ul class="pricing-features">
          <li>All 20 tools available</li>
          <li>Usage tracking & stats</li>
          <li>Prompt safety checks</li>
          <li>Auto-provisioned API key</li>
          <li>Community support</li>
        </ul>
      </div>
      <div class="pricing-card featured">
        <div class="pricing-tier">Starter</div>
        <div class="pricing-price">$29 <span>/month</span></div>
        <div class="pricing-calls">5,000 calls/month</div>
        <ul class="pricing-features">
          <li>Everything in Free</li>
          <li>Priority response times</li>
          <li>Custom guardrail rules</li>
          <li>Webhook integrations</li>
          <li>Email support</li>
        </ul>
      </div>
      <div class="pricing-card">
        <div class="pricing-tier">Enterprise</div>
        <div class="pricing-price">Custom</div>
        <div class="pricing-calls">Unlimited calls</div>
        <ul class="pricing-features">
          <li>Everything in Starter</li>
          <li>ML-based injection detection</li>
          <li>SOC2/GDPR/HIPAA scanning</li>
          <li>Custom SLA</li>
          <li>Dedicated support</li>
        </ul>
      </div>
    </div>
  </section>

  <!-- Connect Section -->
  <section>
    <h2>Connect to ThinkNEO</h2>
    <div class="code-tabs">
      <div class="code-tab active" onclick="showTab('claude')">Claude Desktop</div>
      <div class="code-tab" onclick="showTab('cursor')">Cursor</div>
      <div class="code-tab" onclick="showTab('chatgpt')">ChatGPT</div>
      <div class="code-tab" onclick="showTab('python')">Python SDK</div>
    </div>
    <div class="code-block active" id="tab-claude">
      <button class="copy-btn" onclick="copyCode('claude')">Copy</button>
<pre id="code-claude"><span class="code-comment">// ~/.claude/claude_desktop_config.json</span>
{
  <span class="code-key">"mcpServers"</span>: {
    <span class="code-key">"thinkneo"</span>: {
      <span class="code-key">"url"</span>: <span class="code-string">"https://mcp.thinkneo.ai/mcp"</span>,
      <span class="code-key">"headers"</span>: {
        <span class="code-key">"Authorization"</span>: <span class="code-string">"Bearer YOUR_API_KEY"</span>
      }
    }
  }
}</pre>
    </div>
    <div class="code-block" id="tab-cursor">
      <button class="copy-btn" onclick="copyCode('cursor')">Copy</button>
<pre id="code-cursor"><span class="code-comment">// .cursor/mcp.json</span>
{
  <span class="code-key">"mcpServers"</span>: {
    <span class="code-key">"thinkneo"</span>: {
      <span class="code-key">"url"</span>: <span class="code-string">"https://mcp.thinkneo.ai/mcp"</span>,
      <span class="code-key">"headers"</span>: {
        <span class="code-key">"Authorization"</span>: <span class="code-string">"Bearer YOUR_API_KEY"</span>
      }
    }
  }
}</pre>
    </div>
    <div class="code-block" id="tab-chatgpt">
      <button class="copy-btn" onclick="copyCode('chatgpt')">Copy</button>
<pre id="code-chatgpt"><span class="code-comment">// ChatGPT Settings > MCP Servers > Add Server</span>
<span class="code-key">Name:</span>     ThinkNEO
<span class="code-key">URL:</span>      <span class="code-url">https://mcp.thinkneo.ai/mcp</span>
<span class="code-key">Auth:</span>     Bearer Token
<span class="code-key">Token:</span>    <span class="code-string">YOUR_API_KEY</span>

<span class="code-comment">// Or via API plugin configuration:</span>
{
  <span class="code-key">"schema_version"</span>: <span class="code-string">"v1"</span>,
  <span class="code-key">"name_for_human"</span>: <span class="code-string">"ThinkNEO AI Governance"</span>,
  <span class="code-key">"api"</span>: {
    <span class="code-key">"type"</span>: <span class="code-string">"mcp"</span>,
    <span class="code-key">"url"</span>: <span class="code-string">"https://mcp.thinkneo.ai/mcp"</span>
  }
}</pre>
    </div>
    <div class="code-block" id="tab-python">
      <button class="copy-btn" onclick="copyCode('python')">Copy</button>
<pre id="code-python"><span class="code-comment"># pip install mcp</span>
<span class="code-key">from</span> mcp.client.streamable_http <span class="code-key">import</span> streamablehttp_client

<span class="code-key">async with</span> streamablehttp_client(
    <span class="code-string">"https://mcp.thinkneo.ai/mcp"</span>,
    headers={<span class="code-string">"Authorization"</span>: <span class="code-string">"Bearer YOUR_API_KEY"</span>}
) <span class="code-key">as</span> (read, write, _):
    <span class="code-comment"># Initialize and call tools</span>
    <span class="code-key">pass</span></pre>
    </div>
  </section>

  <div class="cta">
    <h2>Start Building with ThinkNEO</h2>
    <p>500 free API calls per month. No credit card required.</p>
    <a href="https://thinkneo.ai/pricing" class="btn btn-primary">Get Free API Key</a>
    <a href="https://thinkneo.ai/demo" class="btn btn-outline">Book a Demo</a>
  </div>
</div>

<footer>
  <div class="container">
    <p>&copy; 2026 ThinkNEO. All rights reserved. |
    <a href="https://thinkneo.ai">thinkneo.ai</a> |
    <a href="https://thinkneo.ai/trust">Trust Center</a> |
    <a href="mailto:hello@thinkneo.ai">hello@thinkneo.ai</a></p>
  </div>
</footer>

<script>
function showTab(name) {
  document.querySelectorAll('.code-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.code-block').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
}
function copyCode(name) {
  const el = document.getElementById('code-' + name);
  const text = el.textContent || el.innerText;
  navigator.clipboard.writeText(text).then(() => {
    const btn = event.target;
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = 'Copy', 2000);
  });
}
</script>
</body>
</html>
"""
