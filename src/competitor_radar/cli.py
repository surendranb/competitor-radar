"""Standalone CLI executable for competitor-radar.

Subcommands:
  watch     Register or update a competitor
  snapshot  Capture a page snapshot and compute strategic diff
  diff      Inspect the diff between recent snapshots
  sitemap   Discover URLs and staging paths from sitemap.xml
  hiring    Analyze hiring velocity and departmental momentum
  timeline  Query the chronological competitive ledger
  brief     Generate a 360-degree competitive dossier
  serve     Launch the stdio Model Context Protocol (MCP) server
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from competitor_radar import __version__
from competitor_radar.analyzer import analyze_diff
from competitor_radar.ats import analyze_hiring_data
from competitor_radar.differ import compute_markdown_diff
from competitor_radar.extractor import extract_markdown
from competitor_radar.sitemap import fetch_and_parse_sitemap
from competitor_radar.storage import Storage


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


def cmd_watch(args: argparse.Namespace) -> int:
    store = Storage()
    import urllib.parse
    parsed = urllib.parse.urlparse(args.url if "://" in args.url else f"https://{args.url}")
    domain = parsed.netloc.lower() or parsed.path.lower().split("/")[0]

    target = store.upsert_target(
        name=args.name,
        domain=domain,
        main_url=args.url,
        pricing_url=args.pricing_url,
        ats_provider=args.ats_provider,
        ats_slug=args.ats_slug,
    )

    if args.json:
        _print_json(target)
    else:
        print(f"✔ Registered competitor: {target['name']} (ID: {target['id']})")
        print(f"  Domain:      {target['domain']}")
        print(f"  Main URL:    {target['main_url']}")
        print(f"  Pricing URL: {target['pricing_url'] or 'Not set'}")
        print(f"  ATS Radar:   {target['ats_provider'] or 'None'} ({target['ats_slug'] or 'None'})")
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    store = Storage()
    target = store.get_target(args.name)
    if not target:
        if args.url:
            import urllib.parse
            parsed = urllib.parse.urlparse(args.url if "://" in args.url else f"https://{args.url}")
            domain = parsed.netloc.lower() or parsed.path.lower().split("/")[0]
            target = store.upsert_target(name=args.name, domain=domain, main_url=args.url)
        else:
            print(f"Error: Competitor '{args.name}' not found. Run 'competitor-radar watch' first.", file=sys.stderr)
            return 1

    target_url = args.url or target.get("pricing_url") or target.get("main_url")
    if not target_url:
        print(f"Error: No URL found for '{args.name}'. Specify --url.", file=sys.stderr)
        return 1

    import requests
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 CompetitorRadar/1.0",
    }
    resp = requests.get(target_url, headers=headers, timeout=15.0)
    resp.raise_for_status()

    extracted = extract_markdown(resp.text, base_url=target_url)
    prev_snap = store.get_latest_snapshot(target["id"], target_url)
    prev_md = prev_snap["raw_markdown"] if prev_snap else ""

    snap_id = store.insert_snapshot(
        target_id=target["id"],
        url=target_url,
        content_hash=extracted.content_hash,
        raw_markdown=extracted.markdown,
        word_count=extracted.word_count,
    )

    diff_res = compute_markdown_diff(prev_md, extracted.markdown)
    analysis = analyze_diff(diff_res.diff_text)

    if diff_res.has_changes:
        store.insert_diff_event(
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

    if args.json:
        _print_json({
            "target": target["name"],
            "url": target_url,
            "snapshot_id": snap_id,
            "word_count": extracted.word_count,
            "has_changes": diff_res.has_changes,
            "intent_tags": analysis.intent_tags,
            "summary": analysis.summary,
            "added_lines": diff_res.added_lines_count,
            "removed_lines": diff_res.removed_lines_count,
        })
    else:
        print(f"✔ Snapshot #{snap_id} captured for {target['name']} ({extracted.word_count} words)")
        print(f"  URL:     {target_url}")
        print(f"  Tags:    {', '.join(analysis.intent_tags)}")
        print(f"  Summary: {analysis.summary}")
        if diff_res.has_changes:
            print(f"  Deltas:  +{diff_res.added_lines_count} / -{diff_res.removed_lines_count} lines")
        else:
            print("  Status:  Unchanged since prior snapshot.")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    store = Storage()
    target = store.get_target(args.name)
    if not target:
        print(f"Error: Competitor '{args.name}' not found.", file=sys.stderr)
        return 1

    events = store.get_diff_events(target_id=target["id"], limit=1)
    if not events:
        print(f"No diff events on record for '{args.name}'.", file=sys.stderr)
        return 1

    ev = events[0]
    if args.json:
        _print_json(ev)
    else:
        print(f"Diff for {target['name']} @ {ev['created_at']}")
        print(f"Tags:    {', '.join(ev['intent_tags'])}")
        print(f"Summary: {ev['summary']}")
        print("\n" + ev["diff_text"])
    return 0


def cmd_sitemap(args: argparse.Namespace) -> int:
    store = Storage()
    target = store.get_target(args.name_or_domain)
    target_id = target["id"] if target else None
    domain = target["domain"] if target else args.name_or_domain

    if not target:
        target = store.upsert_target(name=domain, domain=domain, main_url=f"https://{domain}")
        target_id = target["id"]

    parse_res = fetch_and_parse_sitemap(domain)
    sync_res = store.sync_sitemap_urls(
        target_id, [{"url": u.url, "lastmod": u.lastmod} for u in parse_res.urls]
    )

    if args.json:
        _print_json({
            "domain": domain,
            "total_urls": sync_res["total_active"],
            "added": sync_res["added"],
            "updated": sync_res["updated"],
            "removed": sync_res["removed"],
            "staging_or_beta": parse_res.staging_or_beta_urls,
        })
    else:
        print(f"✔ Sitemap scanned for {domain}")
        print(f"  Total URLs:      {sync_res['total_active']}")
        print(f"  New Pages:       {len(sync_res['added'])}")
        print(f"  Updated Pages:   {len(sync_res['updated'])}")
        print(f"  Removed Pages:   {len(sync_res['removed'])}")
        if parse_res.staging_or_beta_urls:
            print(f"  Staging/Beta ({len(parse_res.staging_or_beta_urls)}):")
            for bu in parse_res.staging_or_beta_urls[:5]:
                print(f"    - {bu}")
    return 0


def cmd_hiring(args: argparse.Namespace) -> int:
    report = analyze_hiring_data(slug=args.slug, provider=args.provider)
    if args.json:
        _print_json({
            "provider": report.provider,
            "slug": report.slug,
            "total_jobs": report.total_active_jobs,
            "departments": report.canonical_breakdown,
            "leadership": report.leadership_roles,
            "ai_roles": report.ai_roles,
            "remote_pct": report.remote_percentage,
            "strategic_signal": report.strategic_signal,
        })
    else:
        print(f"✔ Hiring Radar: {args.slug} ({report.provider.capitalize()})")
        print(f"  Active Requisitions: {report.total_active_jobs} (Remote: {report.remote_percentage}%)")
        print(f"  Strategic Signal:    {report.strategic_signal}")
        print("\n  Departments:")
        for dept, cnt in sorted(report.canonical_breakdown.items(), key=lambda x: x[1], reverse=True):
            print(f"    - {dept:22s} {cnt:3d}")
        if report.leadership_roles:
            print(f"\n  Leadership Hires ({len(report.leadership_roles)}):")
            for lead in report.leadership_roles[:5]:
                print(f"    - {lead}")
        if report.ai_roles:
            print(f"\n  Dedicated AI Roles ({len(report.ai_roles)}):")
            for ai in report.ai_roles[:5]:
                print(f"    - {ai}")
    return 0


def cmd_timeline(args: argparse.Namespace) -> int:
    store = Storage()
    target_id = None
    if args.name:
        target = store.get_target(args.name)
        if target:
            target_id = target["id"]
        else:
            print(f"Error: Competitor '{args.name}' not found.", file=sys.stderr)
            return 1

    events = store.get_diff_events(target_id=target_id, limit=args.limit, category=args.category)
    if args.json:
        _print_json(events)
    else:
        print(f"=== Competitor Timeline ({len(events)} events) ===")
        for ev in events:
            date_short = ev["created_at"][:16].replace("T", " ")
            tags = ", ".join(ev["intent_tags"])
            print(f"[{date_short}] {ev['target_name']} | [{tags}]")
            print(f"  Summary: {ev['summary']}")
            print(f"  Lines:   +{ev['added_lines_count']} / -{ev['removed_lines_count']}\n")
    return 0


def cmd_brief(args: argparse.Namespace) -> int:
    from competitor_radar.server import competitor_brief
    out = competitor_brief(args.name)
    print(out)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from competitor_radar.server import main as server_main
    server_main()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="competitor-radar",
        description="Local-First Competitive Intelligence Engine & MCP Server",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # watch
    p_watch = subparsers.add_parser("watch", help="Register or update a competitor target")
    p_watch.add_argument("name", help="Competitor name")
    p_watch.add_argument("url", help="Competitor main or website URL")
    p_watch.add_argument("--pricing-url", help="Specific pricing page URL")
    p_watch.add_argument("--ats-provider", choices=["greenhouse", "ashby"], help="ATS provider")
    p_watch.add_argument("--ats-slug", help="ATS job board slug")

    # snapshot
    p_snap = subparsers.add_parser("snapshot", help="Capture snapshot and calculate diff")
    p_snap.add_argument("name", help="Competitor name")
    p_snap.add_argument("--url", help="Optional override URL to capture")

    # diff
    p_diff = subparsers.add_parser("diff", help="View latest diff for competitor")
    p_diff.add_argument("name", help="Competitor name")

    # sitemap
    p_sm = subparsers.add_parser("sitemap", help="Traverse sitemap and discover page deltas")
    p_sm.add_argument("name_or_domain", help="Competitor name or domain")

    # hiring
    p_hire = subparsers.add_parser("hiring", help="Analyze live ATS hiring radar")
    p_hire.add_argument("slug", help="Job board slug (e.g. acme)")
    p_hire.add_argument("--provider", default="greenhouse", choices=["greenhouse", "ashby"], help="ATS provider")

    # timeline
    p_time = subparsers.add_parser("timeline", help="Query competitive timeline ledger")
    p_time.add_argument("--name", help="Filter by competitor name")
    p_time.add_argument("--limit", type=int, default=20, help="Max entries to return")
    p_time.add_argument("--category", help="Filter by intent tag (e.g. PRICING_CHANGE)")

    # brief
    p_brief = subparsers.add_parser("brief", help="Generate 360-degree competitor brief")
    p_brief.add_argument("name", help="Competitor name")

    # serve
    p_serve = subparsers.add_parser("serve", help="Start FastMCP stdio server")

    args = parser.parse_args()

    commands = {
        "watch": cmd_watch,
        "snapshot": cmd_snapshot,
        "diff": cmd_diff,
        "sitemap": cmd_sitemap,
        "hiring": cmd_hiring,
        "timeline": cmd_timeline,
        "brief": cmd_brief,
        "serve": cmd_serve,
    }

    fn = commands.get(args.command)
    if fn:
        sys.exit(fn(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
