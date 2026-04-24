"""
Registry Landing Page — /registry

Simple HTML page for the MCP Marketplace showing what it is and how to use it.
"""

from __future__ import annotations

REGISTRY_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ThinkNEO MCP Marketplace — The npm for MCP Tools</title>
<meta name="description" content="ThinkNEO MCP Marketplace — Discover, publish, and install MCP servers. The npm for the MCP ecosystem.">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>&#x1F4E6;</text></svg>">
<style>
  :root {
    --bg: #0a0f1a; --bg2: #111827; --bg3: #1a2332;
    --primary: #1e50dc; --accent: #14b4a0; --text: #e2e8f0; --text2: #94a3b8;
    --border: #1e293b; --code-bg: #0d1117; --success: #22c55e; --warning: #f59e0b;
    --purple: #a78bfa;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.6; min-height: 100vh;
  }
  .container { max-width: 960px; margin: 0 auto; padding: 0 24px; }

  header { border-bottom: 1px solid var(--border); padding: 20px 0; background: var(--bg2); }
  header .container { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
  .logo { display: flex; align-items: center; gap: 12px; text-decoration: none; color: var(--text); }
  .logo-icon {
    width: 40px; height: 40px; background: linear-gradient(135deg, var(--purple), var(--accent));
    border-radius: 10px; display: flex; align-items: center; justify-content: center;
    font-size: 20px;
  }
  .logo-text { font-size: 20px; font-weight: 700; }
  .logo-text span { color: var(--accent); }
  .header-links { display: flex; gap: 16px; }
  .header-links a { color: var(--text2); text-decoration: none; font-size: 14px; }
  .header-links a:hover { color: var(--accent); }

  .hero { padding: 60px 0 40px; text-align: center; }
  .hero h1 { font-size: 36px; font-weight: 800; margin-bottom: 16px; line-height: 1.2; }
  .hero h1 .accent { color: var(--accent); }
  .hero h1 .purple { color: var(--purple); }
  .hero p { font-size: 18px; color: var(--text2); max-width: 640px; margin: 0 auto 28px; }

  .hero-stats { display: flex; justify-content: center; gap: 32px; margin-top: 24px; flex-wrap: wrap; }
  .stat { text-align: center; }
  .stat-num { font-size: 28px; font-weight: 800; color: var(--accent); }
  .stat-label { font-size: 13px; color: var(--text2); }

  section { padding: 40px 0; }
  section + section { border-top: 1px solid var(--border); }
  h2 { font-size: 24px; font-weight: 700; margin-bottom: 20px; }

  .how-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
  @media (max-width: 640px) { .how-grid { grid-template-columns: 1fr; } }
  .how-card {
    background: var(--bg3); border: 1px solid var(--border); border-radius: 12px; padding: 24px;
  }
  .how-step { font-size: 32px; font-weight: 800; color: var(--accent); margin-bottom: 8px; }
  .how-title { font-size: 16px; font-weight: 700; margin-bottom: 8px; }
  .how-desc { font-size: 14px; color: var(--text2); }

  .code-block {
    background: var(--code-bg); border: 1px solid var(--border); border-radius: 8px;
    padding: 20px; overflow-x: auto; margin: 16px 0;
  }
  pre { font-family: 'SF Mono', 'Fira Code', monospace; font-size: 13px; line-height: 1.6; color: #c9d1d9; }
  .code-comment { color: #6e7681; }
  .code-key { color: #79c0ff; }
  .code-string { color: #a5d6ff; }

  .categories { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; }
  .cat-tag {
    padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 600;
    background: var(--bg3); border: 1px solid var(--border); color: var(--text2);
    transition: all 0.2s;
  }
  .cat-tag:hover { border-color: var(--accent); color: var(--accent); }

  .cta {
    text-align: center; padding: 48px 0;
    background: linear-gradient(135deg, rgba(167, 139, 250, 0.08), rgba(20, 180, 160, 0.08));
    border-radius: 16px; margin: 40px 0;
  }
  .cta h2 { margin-bottom: 12px; }
  .cta p { color: var(--text2); margin-bottom: 24px; }
  .btn {
    display: inline-block; padding: 12px 32px; border-radius: 8px; font-size: 15px;
    font-weight: 700; text-decoration: none; transition: all 0.2s;
  }
  .btn-primary { background: var(--primary); color: white; }
  .btn-primary:hover { background: #1640b0; }

  footer { border-top: 1px solid var(--border); padding: 24px 0; text-align: center; font-size: 13px; color: var(--text2); }
  footer a { color: var(--accent); text-decoration: none; }
</style>
</head>
<body>
<header>
  <div class="container">
    <a href="https://mcp.thinkneo.ai/mcp/docs" class="logo">
      <div class="logo-icon">&#x1F4E6;</div>
      <div class="logo-text">MCP <span>Marketplace</span></div>
    </a>
    <div class="header-links">
      <a href="https://mcp.thinkneo.ai/mcp/docs">MCP Server</a>
      <a href="https://thinkneo.ai">ThinkNEO</a>
      <a href="https://github.com/thinkneo-ai/mcp-server">GitHub</a>
    </div>
  </div>
</header>

<div class="container">
  <div class="hero">
    <h1>The <span class="purple">npm</span> for <span class="accent">MCP Tools</span></h1>
    <p>
      Discover, publish, and install MCP servers from one registry.
      ThinkNEO Marketplace is the distribution layer for the MCP ecosystem.
    </p>
    <div class="hero-stats">
      <div class="stat"><div class="stat-num" id="pkg-count">5</div><div class="stat-label">Packages</div></div>
      <div class="stat"><div class="stat-num">20+</div><div class="stat-label">Tools</div></div>
      <div class="stat"><div class="stat-num">4</div><div class="stat-label">Categories</div></div>
    </div>
  </div>

  <section>
    <h2>How It Works</h2>
    <div class="how-grid">
      <div class="how-card">
        <div class="how-step">1</div>
        <div class="how-title">Discover</div>
        <div class="how-desc">Search the registry via MCP tool call. Filter by category, rating, or verified status.</div>
      </div>
      <div class="how-card">
        <div class="how-step">2</div>
        <div class="how-title">Install</div>
        <div class="how-desc">Get ready-to-use JSON config for Claude Desktop, Cursor, Windsurf, or any MCP client.</div>
      </div>
      <div class="how-card">
        <div class="how-step">3</div>
        <div class="how-title">Publish</div>
        <div class="how-desc">Share your MCP server with the world. Auto-validated, security-scanned, and discoverable.</div>
      </div>
    </div>
  </section>

  <section>
    <h2>Categories</h2>
    <div class="categories">
      <span class="cat-tag">governance</span>
      <span class="cat-tag">security</span>
      <span class="cat-tag">data</span>
      <span class="cat-tag">development</span>
      <span class="cat-tag">productivity</span>
      <span class="cat-tag">communication</span>
      <span class="cat-tag">analytics</span>
      <span class="cat-tag">devops</span>
      <span class="cat-tag">finance</span>
      <span class="cat-tag">marketing</span>
    </div>
  </section>

  <section>
    <h2>Use via MCP</h2>
    <p style="color: var(--text2); margin-bottom: 16px;">
      The marketplace is accessed through MCP tool calls. Connect to the ThinkNEO MCP server, then use these tools:
    </p>
    <div class="code-block">
<pre><span class="code-comment">// 1. Search for MCP servers</span>
<span class="code-key">thinkneo_registry_search</span>(query=<span class="code-string">"database"</span>, category=<span class="code-string">"data"</span>)

<span class="code-comment">// 2. Get full details</span>
<span class="code-key">thinkneo_registry_get</span>(name=<span class="code-string">"postgres"</span>)

<span class="code-comment">// 3. Get install config for your client</span>
<span class="code-key">thinkneo_registry_install</span>(name=<span class="code-string">"postgres"</span>, client_type=<span class="code-string">"claude-desktop"</span>)

<span class="code-comment">// 4. Publish your own server (auth required)</span>
<span class="code-key">thinkneo_registry_publish</span>(
  name=<span class="code-string">"my-server"</span>,
  display_name=<span class="code-string">"My MCP Server"</span>,
  endpoint_url=<span class="code-string">"https://my-server.com/mcp"</span>,
  ...
)

<span class="code-comment">// 5. Rate and review</span>
<span class="code-key">thinkneo_registry_review</span>(name=<span class="code-string">"postgres"</span>, rating=5, comment=<span class="code-string">"Works great!"</span>)</pre>
    </div>
  </section>

  <div class="cta">
    <h2>Publish Your MCP Server</h2>
    <p>Share your MCP server with the ecosystem. Auto-validated, security-scanned, and instantly discoverable.</p>
    <a href="https://mcp.thinkneo.ai/mcp/docs" class="btn btn-primary">Get Started</a>
  </div>
</div>

<footer>
  <div class="container">
    <p>&copy; 2026 ThinkNEO MCP Marketplace |
    <a href="https://thinkneo.ai">thinkneo.ai</a> |
    <a href="https://mcp.thinkneo.ai/mcp/docs">MCP Server Docs</a> |
    <a href="mailto:hello@thinkneo.ai">hello@thinkneo.ai</a></p>
  </div>
</footer>
</body>
</html>
"""
