# Competitor Radar 📡

> **Local-First Competitive Intelligence Engine & Model Context Protocol (MCP) Server.**  
> Continuous web deltas, pricing structure shifts, sitemap traversal, and zero-auth ATS hiring radar.

Free forever. Zero auth required. All data processing and ledger history stays strictly on your local machine.

---

## ⚡ The Two Deployment Variants

Competitor Radar offers two deployment models to match your operational environment:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           COMPETITOR RADAR ARCHITECTURE                         │
├───────────────────────────────────────┬─────────────────────────────────────────┤
│    VARIANT A: REMOTE MCP (Edge Gateway)│      VARIANT B: LOCAL MCP (stdio)       │
├───────────────────────────────────────┼─────────────────────────────────────────┤
│ • Endpoint:                           │ • Command:                              │
│   https://competitor.builditwithai.xyz/mcp│   uvx competitor-radar                  │
│ • No PyPI / npm updates required      │ • Cold boot: < 50ms                     │
│ • Serves dynamic tool contracts &     │ • Local SQLite ledger:                  │
│   skills live from edge               │   ~/.competitor-radar/timeline.db       │
│ • Stateless public reconnaissance     │ • High-frequency diffing & snapshots    │
│ • Zero host data stored on cloud      │ • Complete privacy: zero data egress    │
└───────────────────────────────────────┴─────────────────────────────────────────┘
```

In **both** variants, no private data ever leaves your computer. Snapshots, diffs, and competitor targets are computed and stored on your device.

---

## 🚀 Quickstart & Client Setup

### 1-Line Universal Installer
```bash
curl -fsSL https://competitor.builditwithai.xyz/install | bash
```

---

### Configuration by Client

#### Claude Desktop

**Option 1: Local MCP (Recommended)**
Add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "competitor-radar": {
      "command": "uvx",
      "args": ["competitor-radar"]
    }
  }
}
```

**Option 2: Remote MCP (Streamable HTTP / SSE)**
```json
{
  "mcpServers": {
    "competitor-radar": {
      "url": "https://competitor.builditwithai.xyz/mcp"
    }
  }
}
```

---

#### Cursor

Add to `~/.cursor/mcp.json` or project `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "competitor-radar": {
      "command": "uvx",
      "args": ["competitor-radar"]
    }
  }
}
```

---

#### OpenCode / Claude Code CLI

```bash
# Claude Code CLI
claude mcp add competitor-radar -- uvx competitor-radar

# Node / npx alternative
claude mcp add competitor-radar -- npx -y @surendranb/competitor-radar
```

---

## 🛠️ The 6 High-Value MCP Tools

| Tool | Purpose | Primary Output |
|---|---|---|
| `watch_competitor` | Register or update competitor target | Target ID, normalized domain, ATS slugs |
| `snapshot_competitor` | Capture page, compute diff against baseline, classify intent | CommonMark diff, intent tags, pricing deltas |
| `sitemap_delta` | Traverse XML sitemaps for newly published & staging URLs | New pages, updated lastmod, `/beta/` URLs |
| `hiring_radar` | Probe Greenhouse/Ashby boards for department velocity | Active jobs, department breakdown, leadership/AI roles |
| `competitor_timeline` | Query historical changes across competitors | Chronological ledger of strategic modifications |
| `competitor_brief` | Synthesize 360-degree executive dossier | Comprehensive CommonMark competitive briefing |

### 1. `watch_competitor`
Register a competitor once:
```json
{
  "name": "Linear",
  "url": "https://linear.app",
  "pricing_url": "https://linear.app/pricing",
  "ats_provider": "ashby",
  "ats_slug": "linear"
}
```

### 2. `snapshot_competitor`
Captures HTML, strips navigation/scripts/cookie banners, isolates main content, hashes the markdown, and computes semantic diffs:
```json
{
  "name": "Linear"
}
```
**Intent Classification Tags:**
- `PRICING_CHANGE`: Currency modifications, seat price hikes, annual billing adjustments.
- `TIER_MODIFIED`: Plan structure shifts (Starter, Growth, Pro, Enterprise).
- `LIMIT_ADJUSTED`: Quota modifications (seats, credits, tokens, storage).
- `POSITIONING_UPDATE`: Tagline, hero header, and value proposition shifts.
- `FEATURE_ANNOUNCED`: New feature releases, betas, and integrations.
- `ENTERPRISE_PIVOT`: SSO/SAML, SOC 2, HIPAA, SLA, and custom contract additions.
- `DEPRECATION`: Sunsetting of legacy plans or endpoints.

### 3. `sitemap_delta`
Traverses `sitemap.xml` and nested `sitemap_index.xml` trees:
```json
{
  "name_or_domain": "linear.app"
}
```
Detects unlisted staging paths: e.g. `/beta/realtime-sync`, `/preview/v2-pricing`.

### 4. `hiring_radar`
Zero-auth ATS reconnaissance:
```json
{
  "slug": "linear",
  "provider": "ashby"
}
```
Returns departmental distribution (Engineering, AI & ML, Sales/GTM, Product), remote %, and flags strategic hires (e.g. VP Sales, AI Research Lead).

### 5. `competitor_timeline`
Query the historical SQLite ledger:
```json
{
  "name": "Linear",
  "category": "PRICING_CHANGE",
  "limit": 10
}
```

### 6. `competitor_brief`
Compiles an executive 360-degree competitive dossier:
```json
{
  "name": "Linear"
}
```

---

## 💻 Standalone CLI

Competitor Radar includes a complete terminal CLI:

```bash
# Register competitor
competitor-radar watch Linear https://linear.app --pricing-url https://linear.app/pricing --ats-provider ashby --ats-slug linear

# Capture snapshot
competitor-radar snapshot Linear

# View latest diff
competitor-radar diff Linear

# Scan sitemap
competitor-radar sitemap linear.app

# Check hiring velocity
competitor-radar hiring linear --provider ashby

# Query timeline
competitor-radar timeline --category PRICING_CHANGE

# Generate full brief
competitor-radar brief Linear

# Start MCP stdio server
competitor-radar serve
```

---

## 📂 Local Storage Ledger

All data is stored locally in an embedded SQLite database:
- **Default path**: `~/.competitor-radar/timeline.db`
- **Custom path**: set `COMPETITOR_RADAR_DB_PATH=/path/to/timeline.db`
- WAL mode enabled for high concurrency and zero locking overhead.

---

## 🔒 Privacy & Telemetry Policy

- **Zero Host Data Stored on Cloud**: No competitor URLs, names, snapshots, diffs, or database records are sent to any remote server.
- **Anonymous Usage Telemetry**: Competitor Radar sends minimal anonymous operational telemetry (tool execution count, latency, platform) to maintain server health.
- **Opt-Out**: Set `DO_NOT_TRACK=1` or `COMPETITOR_RADAR_TELEMETRY=false` in your environment to disable all telemetry.

---

## 📄 License

MIT © [Surendran B](https://github.com/surendranb)
