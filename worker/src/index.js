/**
 * Cloudflare Worker Edge Gateway for Competitor Radar (Fleet v2 Standard)
 * Serves:
 * 1. Remote MCP Streamable JSON-RPC 2.0 Endpoint (/mcp)
 * 2. Telemetry Ingestion Relay (/e)
 * 3. Post-Install Telemetry Ping (/telemetry)
 * 4. Universal 1-Line Curl Installer (/install, /install.sh)
 * 5. Health Check (/health)
 */

const GATEWAY_VERSION = "2";
const SERVER_NAME = "competitor-radar";
const PACKAGE_NAME = "competitor-radar";
const CLI_CMD = "competitor-radar";
const DISPLAY_NAME = "Competitor Radar";
const DESCRIPTION = "Local-First Competitive Intelligence Engine: Web Deltas, Pricing Shifts, Sitemap Traversal & ATS Hiring Radar";
const DOCS_URL = "https://competitor.builditwithai.xyz";
const RUNTIME_PREF = "uvx";
const DEFAULT_ENV = "{}";

const TOOLS = [
  {
    name: "watch_competitor",
    description: "Register or update a competitor target in the local SQLite ledger.",
    inputSchema: {
      type: "object",
      properties: {
        name: { type: "string", description: "Competitor company or product name" },
        url: { type: "string", description: "Primary website URL" },
        pricing_url: { type: "string", description: "Specific pricing page URL" },
        ats_provider: { type: "string", enum: ["greenhouse", "ashby"], description: "Applicant Tracking System provider" },
        ats_slug: { type: "string", description: "Job board slug (e.g. 'stripe' or 'linear')" }
      },
      required: ["name", "url"]
    }
  },
  {
    name: "snapshot_competitor",
    description: "Capture competitor page, compute semantic diff against prior version, record diff event, and classify strategic intent.",
    inputSchema: {
      type: "object",
      properties: {
        name: { type: "string", description: "Competitor name" },
        url: { type: "string", description: "Optional URL override to capture" }
      },
      required: ["name"]
    }
  },
  {
    name: "sitemap_delta",
    description: "Scan sitemap for new, updated, or removed pages and discover hidden staging/beta URLs.",
    inputSchema: {
      type: "object",
      properties: {
        name_or_domain: { type: "string", description: "Competitor name or domain (e.g. 'linear.app')" }
      },
      required: ["name_or_domain"]
    }
  },
  {
    name: "hiring_radar",
    description: "Fetch live hiring data from Greenhouse/Ashby and calculate departmental signals.",
    inputSchema: {
      type: "object",
      properties: {
        slug: { type: "string", description: "Job board slug" },
        provider: { type: "string", enum: ["greenhouse", "ashby"], default: "greenhouse", description: "ATS provider" }
      },
      required: ["slug"]
    }
  },
  {
    name: "competitor_timeline",
    description: "Query historical timeline ledger of what changed, why, and when across competitors.",
    inputSchema: {
      type: "object",
      properties: {
        name: { type: "string", description: "Filter by competitor name" },
        limit: { type: "number", default: 20, description: "Maximum entries to return" },
        category: { type: "string", description: "Filter by strategic intent tag (e.g. 'PRICING_CHANGE')" }
      }
    }
  },
  {
    name: "competitor_brief",
    description: "Synthesize 360-degree competitive intel brief combining pricing, web deltas, hiring signals, and timeline.",
    inputSchema: {
      type: "object",
      properties: {
        name: { type: "string", description: "Competitor name" }
      },
      required: ["name"]
    }
  },
  {
    name: "skills_list",
    description: "List all dynamic skill playbooks available in competitor-radar.",
    inputSchema: { type: "object", properties: {} }
  },
  {
    name: "skill_read",
    description: "Read a specific competitive intelligence skill playbook.",
    inputSchema: {
      type: "object",
      properties: {
        skill_name: { type: "string", description: "Skill name to read" }
      },
      required: ["skill_name"]
    }
  }
];

const SKILL_PLAYBOOK = `---
name: competitor_analysis
description: Tactical playbook for conducting competitive audits, pricing shift detection, sitemap reconnaissance, and ATS hiring signals.
version: "1.0.0"
---

# Competitive Radar Playbook

## 1. When to Use
Use this skill when:
- Monitoring competitor pricing page alterations (new tiers, seat limits, price hikes).
- Detecting stealth product launches and staging URLs from XML sitemaps.
- Tracking competitor hiring momentum and strategic departmental expansion via Greenhouse/Ashby.
- Generating a 360-degree competitive dossier before executive strategy reviews or sales calls.

## 2. Tool Workflows
- **watch_competitor**: Register target domain, pricing URL, and ATS slugs.
- **snapshot_competitor**: Capture page, compute CommonMark diffs, and classify strategic intent tags.
- **sitemap_delta**: Traverse sitemap XML for /beta/ URLs and newly published pages.
- **hiring_radar**: Probe live job boards on Greenhouse/Ashby for department velocity.
- **competitor_brief**: Synthesize executive 360-degree dossier.
`;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const pathname = url.pathname.toLowerCase();
    const userAgent = request.headers.get("user-agent") || "";
    const clientIp = request.headers.get("cf-connecting-ip") || request.headers.get("x-real-ip") || "";
    const isCurl = userAgent.toLowerCase().includes("curl") || userAgent.toLowerCase().includes("wget");
    const dnt = request.headers.get("dnt") === "1" || request.headers.get("sec-gpc") === "1";

    const cf = request.cf || {};
    const country = cf.country || "unknown";
    const city = cf.city || "unknown";
    const continent = cf.continent || "unknown";
    const timezone = cf.timezone || "unknown";
    const asn = cf.asn || 0;
    const asOrganization = cf.asOrganization || "unknown";

    const corsHeaders = {
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "GET, POST, OPTIONS",
      "access-control-allow-headers": "content-type, authorization, baggage, sentry-trace",
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    // Route 0: Health Check
    if (pathname === "/health") {
      return new Response(JSON.stringify({
        status: "ok",
        server: SERVER_NAME,
        version: GATEWAY_VERSION,
        timestamp: new Date().toISOString(),
      }), {
        headers: { ...corsHeaders, "content-type": "application/json" },
      });
    }

    // Route 1: Remote MCP Protocol Endpoint (/mcp or POST /)
    if (request.method === "POST" && (pathname === "/mcp" || (pathname === "/" && request.headers.get("content-type")?.includes("json")))) {
      return await handleMCPJsonRpc(request, env, ctx, {
        clientIp, country, city, timezone, asn, asOrganization, dnt, userAgent
      });
    }

    // Route 2: Telemetry Ingestion Relay (/e)
    if (request.method === "POST" && pathname === "/e") {
      if (dnt) {
        return new Response(JSON.stringify({ recorded: false, reason: "dnt" }), {
          headers: { ...corsHeaders, "content-type": "application/json" },
        });
      }
      let body;
      try {
        body = await request.json();
      } catch (e) {
        return new Response(JSON.stringify({ recorded: false, reason: "invalid_json" }), {
          status: 400, headers: { ...corsHeaders, "content-type": "application/json" },
        });
      }

      const eventName = typeof body.event === "string" ? body.event.slice(0, 200) : "mcp_event";
      let props = (body.properties && typeof body.properties === "object") ? body.properties : {};
      if (clientIp) props.$ip = clientIp;
      props.as_organization = asOrganization;
      props.asn = asn;
      props.cf_country = country;
      props.cf_timezone = timezone;
      props.via_gateway = true;
      props.gateway_version = GATEWAY_VERSION;
      props.mcp_server_name = SERVER_NAME;

      ctx.waitUntil(sendPostHogEvent(env, {
        event: eventName,
        distinct_id: String(body.distinct_id || `anon_${crypto.randomUUID()}`).slice(0, 200),
        properties: props,
      }));

      return new Response(JSON.stringify({ recorded: true }), {
        headers: { ...corsHeaders, "content-type": "application/json" },
      });
    }

    // Route 3: Post-Install Completion Telemetry Ping
    if (request.method === "POST" && pathname === "/telemetry") {
      try {
        const body = await request.json();
        if (!dnt) {
          ctx.waitUntil(sendPostHogEvent(env, {
            event: "install_completed",
            distinct_id: body.anonymous_id || `anon_${crypto.randomUUID()}`,
            properties: {
              $ip: clientIp || null,
              mcp_server_name: SERVER_NAME,
              as_organization: asOrganization,
              asn: asn,
              cf_country: country,
              cf_timezone: timezone,
              via_gateway: true,
              execution_mode: body.execution_mode || "unknown",
              harnesses_detected: body.harnesses_detected || [],
              configured_harnesses: body.configured_harnesses || [],
              terminal_app: body.terminal_app || "unknown",
              shell_type: body.shell_type || "unknown",
              os_name: body.os_name || "unknown",
              arch: body.arch || "unknown",
              install_outcome: body.install_outcome || "success",
            },
          }));
        }
        return new Response(JSON.stringify({ recorded: true }), {
          headers: { ...corsHeaders, "content-type": "application/json" },
        });
      } catch (e) {
        return new Response(JSON.stringify({ error: e.message }), { status: 400 });
      }
    }

    // Route 4: Universal 1-Line Installer (/install, /install.sh, curl /)
    const isInstallerRequest = isCurl || pathname === "/install" || pathname === "/install.sh" || (pathname === "/" && isCurl);
    if (isInstallerRequest) {
      if (!dnt) {
        ctx.waitUntil(sendPostHogEvent(env, {
          event: "install_intent",
          distinct_id: `anon_${crypto.randomUUID()}`,
          properties: {
            $ip: clientIp || null,
            via_gateway: true,
            mcp_server_name: SERVER_NAME,
            path: pathname,
            is_curl: isCurl,
            user_agent: userAgent,
            cf_country: country,
            cf_city: city,
          },
        }));
      }
      return new Response(getInstallerScript(url.hostname), {
        headers: {
          "content-type": "text/plain; charset=utf-8",
          "cache-control": "no-cache",
        },
      });
    }

    // Default: Redirect browser to GitHub repository documentation
    return Response.redirect(env.DOCS_URL || env.GITHUB_REPO, 302);
  },
};

/**
 * Handle MCP JSON-RPC 2.0 requests
 */
async function handleMCPJsonRpc(request, env, ctx, meta) {
  let body;
  try {
    body = await request.json();
  } catch (e) {
    return new Response(JSON.stringify({
      jsonrpc: "2.0",
      id: null,
      error: { code: -32700, message: "Parse error: Invalid JSON" }
    }), { status: 400, headers: { "content-type": "application/json" } });
  }

  const id = body.id !== undefined ? body.id : null;
  const method = body.method;
  const params = body.params || {};

  switch (method) {
    case "initialize": {
      if (!meta.dnt) {
        ctx.waitUntil(sendPostHogEvent(env, {
          event: "mcp_remote_initialized",
          distinct_id: `anon_${crypto.randomUUID()}`,
          properties: {
            $ip: meta.clientIp || null,
            mcp_server_name: SERVER_NAME,
            protocol_version: params.protocolVersion || "2024-11-05",
            client_name: params.clientInfo?.name || "unknown",
          }
        }));
      }
      return new Response(JSON.stringify({
        jsonrpc: "2.0",
        id,
        result: {
          protocolVersion: "2024-11-05",
          serverInfo: {
            name: SERVER_NAME,
            version: GATEWAY_VERSION,
          },
          capabilities: {
            tools: { listChanged: false },
            prompts: { listChanged: false },
            resources: { listChanged: false },
          },
          instructions: "Competitor Radar Remote Edge Gateway: Serves real-time dynamic tool definitions and public reconnaissance statelessly. Local database and persistence stay on the user's device via local stdio or local filesystem."
        }
      }), { headers: { "content-type": "application/json" } });
    }

    case "notifications/initialized":
      return new Response(null, { status: 204 });

    case "ping":
      return new Response(JSON.stringify({ jsonrpc: "2.0", id, result: {} }), {
        headers: { "content-type": "application/json" }
      });

    case "tools/list":
      return new Response(JSON.stringify({
        jsonrpc: "2.0",
        id,
        result: { tools: TOOLS }
      }), { headers: { "content-type": "application/json" } });

    case "tools/call": {
      const toolName = params.name;
      const args = params.arguments || {};

      if (!meta.dnt) {
        ctx.waitUntil(sendPostHogEvent(env, {
          event: "remote_tool_called",
          distinct_id: `anon_${crypto.randomUUID()}`,
          properties: {
            tool_name: toolName,
            mcp_server_name: SERVER_NAME,
            $ip: meta.clientIp || null,
          }
        }));
      }

      if (toolName === "skills_list") {
        return new Response(JSON.stringify({
          jsonrpc: "2.0",
          id,
          result: { content: [{ type: "text", text: "Available skills: competitor_analysis" }] }
        }), { headers: { "content-type": "application/json" } });
      }

      if (toolName === "skill_read") {
        return new Response(JSON.stringify({
          jsonrpc: "2.0",
          id,
          result: { content: [{ type: "text", text: SKILL_PLAYBOOK }] }
        }), { headers: { "content-type": "application/json" } });
      }

      if (toolName === "sitemap_delta") {
        const domain = args.name_or_domain || "";
        const sitemapUrl = domain.startsWith("http") ? domain : `https://${domain}/sitemap.xml`;
        try {
          const resp = await fetch(sitemapUrl, {
            headers: { "User-Agent": "CompetitorRadar/1.0 (+https://github.com/surendranb/competitor-radar; bot)" }
          });
          const text = await resp.text();
          const matches = [...text.matchAll(/<loc>(.*?)<\/loc>/gi)].map(m => m[1]);
          const betaUrls = matches.filter(u => /(beta|staging|preview|v2|labs)/i.test(u));
          return new Response(JSON.stringify({
            jsonrpc: "2.0",
            id,
            result: {
              content: [{
                type: "text",
                text: `### Remote Sitemap Inspection: ${domain}\n- Total URLs found: ${matches.length}\n- Staging/Beta URLs: ${betaUrls.length}\n${betaUrls.map(u => `  - ${u}`).slice(0, 10).join("\n")}\n\n*Note: To sync deltas against historical runs and persist to local SQLite, use local MCP: uvx competitor-radar*`
              }]
            }
          }), { headers: { "content-type": "application/json" } });
        } catch (e) {
          return new Response(JSON.stringify({
            jsonrpc: "2.0",
            id,
            result: { content: [{ type: "text", text: `Error inspecting remote sitemap: ${e.message}` }] }
          }), { headers: { "content-type": "application/json" } });
        }
      }

      if (toolName === "hiring_radar") {
        const slug = args.slug;
        const provider = (args.provider || "greenhouse").toLowerCase();
        const targetUrl = provider === "ashby"
          ? `https://api.ashbyhq.com/posting-api/job-board/${slug}`
          : `https://boards-api.greenhouse.io/v1/boards/${slug}/jobs`;

        try {
          const resp = await fetch(targetUrl, {
            headers: { "User-Agent": "CompetitorRadar/1.0 (+https://github.com/surendranb/competitor-radar; bot)" }
          });
          const data = await resp.json();
          const rawJobs = data.jobs || data.jobPostings || [];
          return new Response(JSON.stringify({
            jsonrpc: "2.0",
            id,
            result: {
              content: [{
                type: "text",
                text: `### Remote Hiring Radar: ${slug} (${provider})\n- Active Requisitions: ${rawJobs.length}\n${rawJobs.slice(0, 8).map(j => `  - ${j.title || j.name}`).join("\n")}\n\n*Note: Complete departmental breakdowns and closed-job tracking are stored in local SQLite via 'uvx competitor-radar'.*`
              }]
            }
          }), { headers: { "content-type": "application/json" } });
        } catch (e) {
          return new Response(JSON.stringify({
            jsonrpc: "2.0",
            id,
            result: { content: [{ type: "text", text: `Error fetching remote hiring radar: ${e.message}` }] }
          }), { headers: { "content-type": "application/json" } });
        }
      }

      // Default directive for local-compute tools
      return new Response(JSON.stringify({
        jsonrpc: "2.0",
        id,
        result: {
          content: [{
            type: "text",
            text: `[Remote MCP Directive] '${toolName}' operates on local device ledger storage. Run via local stdio MCP (command: 'uvx competitor-radar') to store and diff in ~/.competitor-radar/timeline.db. Zero host data leaves your device.`
          }]
        }
      }), { headers: { "content-type": "application/json" } });
    }

    default:
      return new Response(JSON.stringify({
        jsonrpc: "2.0",
        id,
        error: { code: -32601, message: `Method '${method}' not found` }
      }), { status: 404, headers: { "content-type": "application/json" } });
  }
}

/**
 * Universal curl installer script
 */
function getInstallerScript(hostname) {
  const host = hostname || "competitor.builditwithai.xyz";
  return `#!/usr/bin/env bash
# ==============================================================================
# Competitor Radar Universal AI Installer (Fleet v2 Standard)
# ==============================================================================
set -e

echo "⚡ Installing Competitor Radar (Local-First Fleet v2)..."
echo "  Variant A: Remote MCP Endpoint -> https://${host}/mcp"
echo "  Variant B: Local stdio MCP    -> uvx competitor-radar"
echo ""

if command -v uvx &>/dev/null; then
  echo "✔ uvx detected. Ready to run."
elif command -v npx &>/dev/null; then
  echo "✔ npx detected. Ready to run via npm wrapper."
else
  echo "ℹ Recommend installing uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

echo ""
echo "Claude Desktop configuration snippet (~/.config/Claude/claude_desktop_config.json):"
echo '{'
echo '  "mcpServers": {'
echo '    "competitor-radar": {'
echo '      "command": "uvx",'
echo '      "args": ["competitor-radar"]'
echo '    }'
echo '  }'
echo '}'
`;
}

async function sendPostHogEvent(env, payload) {
  try {
    const posthogHost = env.POSTHOG_HOST || "https://us.i.posthog.com";
    await fetch(`${posthogHost}/capture/`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        api_key: env.POSTHOG_API_KEY,
        event: payload.event,
        distinct_id: payload.distinct_id,
        properties: payload.properties,
        timestamp: new Date().toISOString(),
      }),
    });
  } catch (err) {
    // Fail silently
  }
}
