"""Model Context Protocol (MCP) Server for competitor-radar.

Local-First Competitive Intelligence Engine: Web Deltas, Pricing Shifts,
Sitemap Traversal, and ATS Hiring Radar.
"""

from __future__ import annotations

import functools
import inspect
import json
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from mcp.types import ToolAnnotations
import requests

from competitor_radar.analyzer import analyze_diff
from competitor_radar.ats import analyze_hiring_data
from competitor_radar.differ import compute_markdown_diff
from competitor_radar.extractor import extract_markdown
from competitor_radar.sitemap import fetch_and_parse_sitemap
from competitor_radar.storage import Storage
from competitor_radar.telemetry import (
    MCP_SERVER_VERSION,
    classify_exception,
    track_event,
    track_tool_call,
)
from competitor_radar.updates import check_server_update, get_upgrade_nudge

mcp = MCPServer(
    "competitor-radar",
    title="Competitor Radar MCP Server",
    version=MCP_SERVER_VERSION,
    website_url="https://github.com/surendranb/competitor-radar",
)

_ANNOTATIONS_EXTERNAL = ToolAnnotations(read_only_hint=False, idempotent_hint=True, open_world_hint=True)
_ANNOTATIONS_LOCAL = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)

_storage: Optional[Storage] = None


def get_storage() -> Storage:
    """Lazy initialize storage instance."""
    global _storage
    if _storage is None:
        _storage = Storage()
    return _storage


# ---------------------------------------------------------------------------
# Skills Registry & Dynamic Fetching
# ---------------------------------------------------------------------------
_LOCAL_SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"
_GITHUB_RAW_BASE = "https://raw.githubusercontent.com/surendranb/competitor-radar/main/skills"

_STARTER_SKILL_NAME = "competitor_analysis"
_STARTER_SKILL_CONTENT = """---
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

### A. Register and Watch a Competitor
```json
{
  "name": "Acme Corp",
  "url": "https://acme.com",
  "pricing_url": "https://acme.com/pricing",
  "ats_provider": "greenhouse",
  "ats_slug": "acme"
}
```

### B. Capture a Snapshot and Classify Intent
```json
{
  "name": "Acme Corp"
}
```

### C. Discover Unlisted and Staging URLs via Sitemap
```json
{
  "name_or_domain": "acme.com"
}
```

### D. Probe Hiring Radar
```json
{
  "slug": "acme",
  "provider": "greenhouse"
}
```

### E. Compile 360-Degree Intelligence Brief
```json
{
  "name": "Acme Corp"
}
```
"""


def _append_upgrade_nudge(result: Any) -> Any:
    try:
        nudge = get_upgrade_nudge("competitor-radar", MCP_SERVER_VERSION)
        if nudge:
            if isinstance(result, str):
                return result + nudge
    except Exception:
        pass
    return result


def _wrap_tool_nudge(fn):
    if inspect.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            res = await fn(*args, **kwargs)
            if fn.__name__ != "check_for_updates":
                res = _append_upgrade_nudge(res)
            return res
        return async_wrapper
    else:
        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            res = fn(*args, **kwargs)
            if fn.__name__ != "check_for_updates":
                res = _append_upgrade_nudge(res)
            return res
        return sync_wrapper


# ---------------------------------------------------------------------------
# High-Value MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool(
    name="watch_competitor",
    description="Register or update a competitor target in the local SQLite ledger.",
    annotations=_ANNOTATIONS_EXTERNAL,
)
def watch_competitor(
    name: str,
    url: str,
    pricing_url: Optional[str] = None,
    ats_provider: Optional[str] = None,
    ats_slug: Optional[str] = None,
) -> str:
    """Register or update a competitor target."""
    t0 = time.perf_counter()
    try:
        store = get_storage()
        parsed = urllib.parse.urlparse(url if "://" in url else f"https://{url}")
        domain = parsed.netloc.lower() or parsed.path.lower().split("/")[0]

        target = store.upsert_target(
            name=name.strip(),
            domain=domain,
            main_url=url.strip(),
            pricing_url=pricing_url.strip() if pricing_url else None,
            ats_provider=ats_provider.strip().lower() if ats_provider else None,
            ats_slug=ats_slug.strip() if ats_slug else None,
        )

        ats_info = f"{target['ats_provider']} ({target['ats_slug']})" if target.get('ats_slug') else "Not configured"
        res = (
            f"### Target Registered: {target['name']}\n"
            f"- **Target ID**: `{target['id']}`\n"
            f"- **Domain**: `{target['domain']}`\n"
            f"- **Main URL**: {target['main_url']}\n"
            f"- **Pricing URL**: {target['pricing_url'] or 'Not configured'}\n"
            f"- **ATS Radar**: {ats_info}\n"
            f"- **Database**: `{store.db_path}`\n\n"
            f"Run `snapshot_competitor(name='{target['name']}')` to capture the baseline snapshot."
        )

        track_tool_call(
            "watch_competitor",
            (time.perf_counter() - t0) * 1000.0,
            status="success",
            rows_returned=1,
            result_chars=len(res),
        )
        return _append_upgrade_nudge(res)
    except Exception as exc:
        track_tool_call(
            "watch_competitor",
            (time.perf_counter() - t0) * 1000.0,
            status="error",
            error_category=classify_exception(exc),
            error_message=str(exc),
        )
        return f"Error registering competitor: {exc}"


@mcp.tool(
    name="snapshot_competitor",
    description="Capture competitor page, compute semantic diff against prior version, record diff event, and classify strategic intent.",
    annotations=_ANNOTATIONS_EXTERNAL,
)
def snapshot_competitor(name: str, url: Optional[str] = None) -> str:
    """Capture page, compute diff against prior version, record diff event, classify strategic intent."""
    t0 = time.perf_counter()
    try:
        store = get_storage()
        target = store.get_target(name)
        if not target:
            # Auto-register if URL passed
            if url:
                parsed = urllib.parse.urlparse(url if "://" in url else f"https://{url}")
                domain = parsed.netloc.lower() or parsed.path.lower().split("/")[0]
                target = store.upsert_target(name=name, domain=domain, main_url=url)
            else:
                return (
                    f"Error: Competitor '{name}' is not registered yet. "
                    f"Call `watch_competitor(name='{name}', url='https://...')` first or specify the `url` parameter."
                )

        target_url = url or target.get("pricing_url") or target.get("main_url")
        if not target_url:
            return f"Error: No URL configured for '{name}'. Please provide a url."

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 CompetitorRadar/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        resp = requests.get(target_url, headers=headers, timeout=15.0)
        resp.raise_for_status()

        extracted = extract_markdown(resp.text, base_url=target_url)

        # Retrieve previous snapshot
        prev_snap = store.get_latest_snapshot(target["id"], target_url)
        prev_md = prev_snap["raw_markdown"] if prev_snap else ""

        # Insert new snapshot
        snap_id = store.insert_snapshot(
            target_id=target["id"],
            url=target_url,
            content_hash=extracted.content_hash,
            raw_markdown=extracted.markdown,
            word_count=extracted.word_count,
        )

        diff_res = compute_markdown_diff(prev_md, extracted.markdown)
        analysis = analyze_diff(diff_res.diff_text)

        event_id = None
        if diff_res.has_changes:
            event_id = store.insert_diff_event(
                target_id=target["id"],
                url=target_url,
                prev_snapshot_id=prev_snap["id"] if prev_snap else None,
                curr_snapshot_id=snap_id,
                diff_text=diff_res.diff_text,
                added_lines_count=diff_res.added_lines_count,
                removed_lines_count=diff_res.removed_lines_count,
                intent_tags=analysis.intent_tags,
                summary=analysis.summary,
            )

        tag_badges = " ".join([f"`[{tag}]`" for tag in analysis.intent_tags])
        out_lines = [
            f"### Snapshot Captured: {target['name']}",
            f"- **URL**: {target_url}",
            f"- **Page Title**: {extracted.title or 'N/A'}",
            f"- **Content Word Count**: {extracted.word_count} words",
            f"- **Snapshot ID**: `{snap_id}`",
            f"- **Strategic Intent**: {tag_badges}",
            f"- **Executive Summary**: {analysis.summary}",
        ]

        if analysis.pricing_deltas:
            out_lines.append("\n#### Pricing Signals:")
            for p in analysis.pricing_deltas:
                out_lines.append(f"- {p}")

        if analysis.headline_deltas:
            out_lines.append("\n#### Headline / Positioning Shifts:")
            for h in analysis.headline_deltas:
                out_lines.append(f"- {h}")

        if diff_res.has_changes:
            out_lines.append(f"\n#### Changes Detected (+{diff_res.added_lines_count} / -{diff_res.removed_lines_count}):")
            # Present top 40 lines of diff
            diff_sample = "\n".join(diff_res.diff_text.splitlines()[:40])
            out_lines.append(f"```diff\n{diff_sample}\n```")
            if len(diff_res.diff_text.splitlines()) > 40:
                out_lines.append(f"*... and {len(diff_res.diff_text.splitlines()) - 40} more lines in ledger.*")
        else:
            out_lines.append("\n*Page content is unchanged since prior snapshot.*")

        result_str = "\n".join(out_lines)
        track_tool_call(
            "snapshot_competitor",
            (time.perf_counter() - t0) * 1000.0,
            status="success",
            rows_returned=1,
            result_chars=len(result_str),
        )
        return _append_upgrade_nudge(result_str)
    except Exception as exc:
        track_tool_call(
            "snapshot_competitor",
            (time.perf_counter() - t0) * 1000.0,
            status="error",
            error_category=classify_exception(exc),
            error_message=str(exc),
        )
        return f"Error capturing competitor snapshot: {exc}"


@mcp.tool(
    name="sitemap_delta",
    description="Scan sitemap for new, updated, or removed pages and discover hidden staging/beta URLs.",
    annotations=_ANNOTATIONS_EXTERNAL,
)
def sitemap_delta(name_or_domain: str) -> str:
    """Scan sitemap for new, updated, or removed pages."""
    t0 = time.perf_counter()
    try:
        store = get_storage()
        target = store.get_target(name_or_domain)
        target_id = target["id"] if target else None

        domain_to_crawl = target["domain"] if target else name_or_domain
        if not target:
            target = store.upsert_target(name=domain_to_crawl, domain=domain_to_crawl, main_url=f"https://{domain_to_crawl}")
            target_id = target["id"]

        parse_res = fetch_and_parse_sitemap(domain_to_crawl)

        # Sync with SQLite ledger
        discovered_dicts = [{"url": u.url, "lastmod": u.lastmod} for u in parse_res.urls]
        sync_res = store.sync_sitemap_urls(target_id, discovered_dicts)

        out_lines = [
            f"### Sitemap Discovery: {domain_to_crawl}",
            f"- **Target Sitemaps Inspected**: {parse_res.sitemaps_inspected}",
            f"- **Total Active URLs**: {sync_res['total_active']}",
            f"- **Newly Published Pages**: {len(sync_res['added'])}",
            f"- **Updated Pages**: {len(sync_res['updated'])}",
            f"- **Removed Pages**: {len(sync_res['removed'])}",
        ]

        if parse_res.staging_or_beta_urls:
            out_lines.append("\n#### ⚠️ Staging / Beta / Preview URLs Discovered:")
            for bu in parse_res.staging_or_beta_urls[:10]:
                out_lines.append(f"- `{bu}`")

        if sync_res["added"]:
            out_lines.append("\n#### Recently Added URLs:")
            for ad in sync_res["added"][:10]:
                out_lines.append(f"- {ad['url']} (Lastmod: {ad.get('lastmod') or 'None'})")

        if sync_res["updated"]:
            out_lines.append("\n#### Recently Updated URLs:")
            for up in sync_res["updated"][:5]:
                out_lines.append(f"- {up['url']} (`{up.get('prev_lastmod')}` -> `{up.get('new_lastmod')}`)")

        res_str = "\n".join(out_lines)
        track_tool_call(
            "sitemap_delta",
            (time.perf_counter() - t0) * 1000.0,
            status="success",
            rows_returned=len(parse_res.urls),
            result_chars=len(res_str),
        )
        return _append_upgrade_nudge(res_str)
    except Exception as exc:
        track_tool_call(
            "sitemap_delta",
            (time.perf_counter() - t0) * 1000.0,
            status="error",
            error_category=classify_exception(exc),
            error_message=str(exc),
        )
        return f"Error scanning sitemap: {exc}"


@mcp.tool(
    name="hiring_radar",
    description="Fetch live hiring data from Greenhouse/Ashby and calculate departmental signals.",
    annotations=_ANNOTATIONS_EXTERNAL,
)
def hiring_radar(slug: str, provider: str = "greenhouse") -> str:
    """Fetch live hiring data from Greenhouse/Ashby and calculate departmental signals."""
    t0 = time.perf_counter()
    try:
        report = analyze_hiring_data(slug=slug, provider=provider)
        store = get_storage()

        # If matching target in DB, sync jobs history
        target = store.get_target(slug)
        history_delta = None
        if target:
            jobs_dicts = [
                {
                    "external_id": j.external_id,
                    "title": j.title,
                    "department": j.canonical_dept,
                    "location": j.location,
                }
                for j in report.jobs
            ]
            history_delta = store.sync_job_postings(target["id"], jobs_dicts)

        out_lines = [
            f"### Hiring Radar: {slug.capitalize()} ({report.provider.capitalize()})",
            f"- **Total Active Requisitions**: {report.total_active_jobs}",
            f"- **Remote Friendly**: {report.remote_percentage}%",
            f"- **Strategic Signal**: {report.strategic_signal}",
        ]

        if history_delta:
            out_lines.append(
                f"- **Ledger Trajectory**: +{len(history_delta['added'])} newly opened, {len(history_delta['closed'])} closed."
            )

        out_lines.append("\n#### Departmental Distribution:")
        out_lines.append("| Department | Open Positions | Share |")
        out_lines.append("| --- | --- | --- |")
        for dept, cnt in sorted(report.canonical_breakdown.items(), key=lambda x: x[1], reverse=True):
            pct = round((cnt / report.total_active_jobs * 100.0), 1) if report.total_active_jobs else 0
            out_lines.append(f"| **{dept}** | {cnt} | {pct}% |")

        if report.leadership_roles:
            out_lines.append(f"\n#### Leadership Requisitions ({len(report.leadership_roles)}):")
            for lead in report.leadership_roles[:8]:
                out_lines.append(f"- {lead}")

        if report.ai_roles:
            out_lines.append(f"\n#### Dedicated AI / ML Openings ({len(report.ai_roles)}):")
            for ai_r in report.ai_roles[:8]:
                out_lines.append(f"- {ai_r}")

        res_str = "\n".join(out_lines)
        track_tool_call(
            "hiring_radar",
            (time.perf_counter() - t0) * 1000.0,
            status="success",
            rows_returned=report.total_active_jobs,
            result_chars=len(res_str),
        )
        return _append_upgrade_nudge(res_str)
    except Exception as exc:
        track_tool_call(
            "hiring_radar",
            (time.perf_counter() - t0) * 1000.0,
            status="error",
            error_category=classify_exception(exc),
            error_message=str(exc),
        )
        return f"Error analyzing hiring radar: {exc}"


@mcp.tool(
    name="competitor_timeline",
    description="Query historical timeline ledger of what changed, why, and when across competitors.",
    annotations=_ANNOTATIONS_LOCAL,
)
def competitor_timeline(
    name: Optional[str] = None,
    limit: int = 20,
    category: Optional[str] = None,
) -> str:
    """Query historical timeline ledger of what changed, why, and when."""
    t0 = time.perf_counter()
    try:
        store = get_storage()
        target_id = None
        if name:
            target = store.get_target(name)
            if target:
                target_id = target["id"]
            else:
                return f"No records found for competitor '{name}'."

        events = store.get_diff_events(target_id=target_id, limit=limit, category=category)
        if not events:
            return "No timeline events recorded yet. Run `snapshot_competitor` to record baseline and deltas."

        out_lines = [
            f"### Competitive Timeline Ledger ({len(events)} events)",
            "| Date (UTC) | Competitor | Intent Tags | Summary | Lines (+/-) |",
            "| --- | --- | --- | --- | --- |",
        ]

        for ev in events:
            date_short = ev["created_at"][:16].replace("T", " ")
            tags_str = ", ".join(ev["intent_tags"])
            summary_clean = ev["summary"].replace("|", "\\|")
            out_lines.append(
                f"| {date_short} | **{ev['target_name']}** | `{tags_str}` | {summary_clean} | +{ev['added_lines_count']} / -{ev['removed_lines_count']} |"
            )

        res_str = "\n".join(out_lines)
        track_tool_call(
            "competitor_timeline",
            (time.perf_counter() - t0) * 1000.0,
            status="success",
            rows_returned=len(events),
            result_chars=len(res_str),
        )
        return _append_upgrade_nudge(res_str)
    except Exception as exc:
        track_tool_call(
            "competitor_timeline",
            (time.perf_counter() - t0) * 1000.0,
            status="error",
            error_category=classify_exception(exc),
            error_message=str(exc),
        )
        return f"Error retrieving timeline: {exc}"


@mcp.tool(
    name="competitor_brief",
    description="Synthesize 360-degree competitive intel brief combining pricing, web deltas, hiring signals, and timeline.",
    annotations=_ANNOTATIONS_EXTERNAL,
)
def competitor_brief(name: str) -> str:
    """Synthesize 360-degree competitive intel brief combining pricing, web deltas, hiring signals, and timeline."""
    t0 = time.perf_counter()
    try:
        store = get_storage()
        target = store.get_target(name)
        if not target:
            return (
                f"Competitor '{name}' is not in the ledger. "
                f"Register them with `watch_competitor(name='{name}', url='https://...')` first."
            )

        events = store.get_diff_events(target_id=target["id"], limit=5)
        sitemap_urls = store.get_sitemap_urls(target["id"], status="active")
        jobs = store.get_job_postings(target["id"], status="active")

        ats_info = f"{target['ats_provider']} ({target['ats_slug']})" if target.get('ats_slug') else "Not configured"
        brief_lines = [
            f"# Competitive Intelligence Dossier: {target['name']}",
            f"- **Domain**: `{target['domain']}`",
            f"- **Primary Web**: {target['main_url']}",
            f"- **Pricing URL**: {target['pricing_url'] or 'Not configured'}",
            f"- **ATS Tracker**: {ats_info}",
            f"- **Ledger ID**: `{target['id']}`",
            "\n---",
        ]

        # Strategic summary
        brief_lines.append("\n## 1. Recent Strategic Shifts & Web Deltas")
        if events:
            for ev in events:
                tags = " ".join([f"`[{t}]`" for t in ev["intent_tags"]])
                brief_lines.append(f"- **{ev['created_at'][:10]}** {tags}: {ev['summary']}")
        else:
            brief_lines.append("- *No page changes captured yet.*")

        # Sitemap coverage
        brief_lines.append(f"\n## 2. Digital Surface & Sitemap Footprint")
        brief_lines.append(f"- Total active tracked URLs: **{len(sitemap_urls)}**")
        staging_urls = [u["url"] for u in sitemap_urls if any(k in u["url"] for k in ("beta", "staging", "preview", "v2"))]
        if staging_urls:
            brief_lines.append(f"- Hidden/Staging URLs found: {', '.join(staging_urls[:5])}")

        # Hiring radar signals
        brief_lines.append("\n## 3. Organizational Momentum & Hiring Radar")
        if target.get("ats_slug") and target.get("ats_provider"):
            try:
                report = analyze_hiring_data(target["ats_slug"], target["ats_provider"])
                brief_lines.append(f"- Active Requisitions: **{report.total_active_jobs}**")
                brief_lines.append(f"- Strategic Trajectory: {report.strategic_signal}")
                top_dept = max(report.canonical_breakdown.items(), key=lambda x: x[1])[0] if report.canonical_breakdown else "General"
                brief_lines.append(f"- Top Department: **{top_dept}** ({report.canonical_breakdown.get(top_dept, 0)} roles)")
                if report.leadership_roles:
                    brief_lines.append(f"- Key Leadership Hires: {', '.join(report.leadership_roles[:3])}")
            except Exception as e:
                brief_lines.append(f"- ATS Fetch note: {e}")
        elif jobs:
            brief_lines.append(f"- Tracked Active Requisitions in Ledger: **{len(jobs)}**")
        else:
            brief_lines.append("- *No ATS provider configured.*")

        brief_lines.append("\n---\n*Generated by Competitor Radar (Local-First Fleet v2)*")

        res_str = "\n".join(brief_lines)
        track_tool_call(
            "competitor_brief",
            (time.perf_counter() - t0) * 1000.0,
            status="success",
            rows_returned=1,
            result_chars=len(res_str),
        )
        return _append_upgrade_nudge(res_str)
    except Exception as exc:
        track_tool_call(
            "competitor_brief",
            (time.perf_counter() - t0) * 1000.0,
            status="error",
            error_category=classify_exception(exc),
            error_message=str(exc),
        )
        return f"Error synthesizing competitor brief: {exc}"


# ---------------------------------------------------------------------------
# Dynamic Skills Layer & Updates
# ---------------------------------------------------------------------------


@mcp.tool(annotations=_ANNOTATIONS_LOCAL)
def skills_list() -> str:
    """List all dynamic skill playbooks available in competitor-radar."""
    t0 = time.perf_counter()
    try:
        skills = {_STARTER_SKILL_NAME}
        if _LOCAL_SKILLS_DIR.is_dir():
            skills.update(f.stem for f in _LOCAL_SKILLS_DIR.glob("*.md"))
        skills_sorted = sorted(skills)
        res_str = f"Available skills: {', '.join(skills_sorted)}"
        track_tool_call(
            "skills_list",
            (time.perf_counter() - t0) * 1000.0,
            status="success",
            rows_returned=len(skills_sorted),
            result_chars=len(res_str),
        )
        return _append_upgrade_nudge(res_str)
    except Exception as exc:
        track_tool_call(
            "skills_list",
            (time.perf_counter() - t0) * 1000.0,
            status="error",
            error_category=classify_exception(exc),
            error_message=str(exc),
        )
        return f"Error listing skills: {exc}"


@mcp.tool(annotations=_ANNOTATIONS_LOCAL)
def skill_read(skill_name: str) -> str:
    """Read a specific competitive skill playbook."""
    t0 = time.perf_counter()
    try:
        clean_name = skill_name.strip().lower().replace(".md", "")
        # Check local skills directory
        local_path = _LOCAL_SKILLS_DIR / f"{clean_name}.md"
        if local_path.is_file():
            content = local_path.read_text(encoding="utf-8")
        elif clean_name == _STARTER_SKILL_NAME:
            content = _STARTER_SKILL_CONTENT
        else:
            # Fallback to GitHub raw
            try:
                resp = requests.get(f"{_GITHUB_RAW_BASE}/{clean_name}.md", timeout=3.0)
                if resp.status_code == 200:
                    content = resp.text
                else:
                    return f"Skill '{skill_name}' not found. Available skills: {skills_list()}"
            except Exception:
                return f"Skill '{skill_name}' not found."

        track_tool_call(
            "skill_read",
            (time.perf_counter() - t0) * 1000.0,
            status="success",
            rows_returned=1,
            result_chars=len(content),
        )
        return _append_upgrade_nudge(content)
    except Exception as exc:
        track_tool_call(
            "skill_read",
            (time.perf_counter() - t0) * 1000.0,
            status="error",
            error_category=classify_exception(exc),
            error_message=str(exc),
        )
        return f"Error reading skill: {exc}"


@mcp.tool(
    name="check_for_updates",
    description="Check PyPI for newer versions of competitor-radar and get upgrade instructions.",
    annotations=_ANNOTATIONS_LOCAL,
)
def check_for_updates() -> str:
    """Check PyPI for newer versions of competitor-radar."""
    t0 = time.perf_counter()
    try:
        res = check_server_update("competitor-radar", MCP_SERVER_VERSION, force_check=True)
        out = json.dumps(res, indent=2)
        track_tool_call(
            "check_for_updates",
            (time.perf_counter() - t0) * 1000.0,
            status="success",
            rows_returned=1,
            result_chars=len(out),
        )
        return out
    except Exception as exc:
        track_tool_call(
            "check_for_updates",
            (time.perf_counter() - t0) * 1000.0,
            status="error",
            error_category=classify_exception(exc),
            error_message=str(exc),
        )
        return json.dumps({"error": str(exc)}, indent=2)


def main():
    """Server entrypoint for stdio transport."""
    track_event("mcp_started")
    mcp.run()


if __name__ == "__main__":
    main()
