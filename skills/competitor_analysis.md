---
name: competitor_analysis
description: Tactical playbook for conducting competitive audits, pricing shift detection, sitemap reconnaissance, and ATS hiring signals.
version: "1.0.0"
---

# Competitive Radar Playbook

Consolidated operational guide for AI agents and market intelligence leads tracking fast-moving SaaS competitors.

## 1. When to Use
Use this skill when:
- Monitoring competitor pricing page alterations (new tiers, seat limits, price hikes, billing frequencies).
- Detecting stealth product launches and staging URLs from XML sitemaps before public announcements.
- Tracking competitor hiring momentum and strategic departmental expansion via Greenhouse/Ashby.
- Generating a 360-degree competitive dossier before executive strategy reviews, board decks, or sales calls.

## 2. Tool Workflows

### A. Register and Watch a Competitor
Register a competitor once into the local SQLite ledger (`~/.competitor-radar/timeline.db`).
```json
{
  "name": "Linear",
  "url": "https://linear.app",
  "pricing_url": "https://linear.app/pricing",
  "ats_provider": "ashby",
  "ats_slug": "linear"
}
```

### B. Capture a Snapshot & Classify Intent
Fetches the target page, isolates content, strips cookie modals/scripts, runs semantic CommonMark diffing against the prior snapshot, and tags strategic intent (`PRICING_CHANGE`, `TIER_MODIFIED`, `LIMIT_ADJUSTED`, `ENTERPRISE_PIVOT`, etc.).
```json
{
  "name": "Linear"
}
```

### C. Discover Unlisted & Staging URLs via Sitemap
Recursively crawls `sitemap.xml` / `sitemap_index.xml` to discover unpublished landing pages, `/beta/` features, and removed pages.
```json
{
  "name_or_domain": "linear.app"
}
```

### D. Probe Hiring Radar
Fetches live job requisitions from Greenhouse or Ashby, maps titles to canonical departments (Engineering, AI & ML, Sales/GTM, Product), and flags key leadership and AI hires.
```json
{
  "slug": "linear",
  "provider": "ashby"
}
```

### E. Query Historical Ledger Timeline
Inspect chronological shifts across competitors or filter by specific strategic tag (e.g., `PRICING_CHANGE`).
```json
{
  "name": "Linear",
  "category": "PRICING_CHANGE",
  "limit": 10
}
```

### F. Synthesize 360-Degree Intelligence Brief
Generates a comprehensive executive dossier combining pricing, web deltas, sitemap signals, and hiring momentum.
```json
{
  "name": "Linear"
}
```
