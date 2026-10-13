"""Strategic Intent Classifier for Competitive Diff Events ("The Why").

Classifies web and pricing modifications into strategic signal tags:
PRICING_CHANGE, TIER_MODIFIED, LIMIT_ADJUSTED, POSITIONING_UPDATE,
FEATURE_ANNOUNCED, ENTERPRISE_PIVOT, DEPRECATION.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class StrategicAnalysis:
    """Classified strategic analysis."""
    intent_tags: List[str]
    summary: str
    pricing_deltas: List[str]
    headline_deltas: List[str]
    confidence_score: float


# Heuristic patterns for rule-based classification
PATTERNS = {
    "PRICING_CHANGE": re.compile(
        r"(\$|€|£|¥)\s*\d+(\.\d{2})?|/mo\b|/month\b|/yr\b|/year\b|/seat\b|/user\b|billed annually|per user|pricing",
        re.I,
    ),
    "TIER_MODIFIED": re.compile(
        r"\b(starter|growth|pro|team|business|enterprise|free tier|essential|scale|professional|hobby|developer)\b\s*(tier|plan)?",
        re.I,
    ),
    "LIMIT_ADJUSTED": re.compile(
        r"\b(\d+[\s\-]*(seats?|users?|credits?|tokens?|gb|tb|api calls?|requests?|projects?|storage))\b|\bunlimited\b|\bquota\b|\brate limit\b",
        re.I,
    ),
    "POSITIONING_UPDATE": re.compile(
        r"\b(all-in-one|ai-powered|next-generation|modern|reimagined|supercharge|the platform for|built for|autonomous|copilot)\b",
        re.I,
    ),
    "FEATURE_ANNOUNCED": re.compile(
        r"\b(introducing|announcing|new:|beta|preview|now available|release|changelog|support for|integrates? with)\b",
        re.I,
    ),
    "ENTERPRISE_PIVOT": re.compile(
        r"\b(sso|saml|okta|soc[\s\-]*2|hipaa|gdpr|sla|uptime|contact sales|custom contract|dedicated support|audit logs?|scim|rbac)\b",
        re.I,
    ),
    "DEPRECATION": re.compile(
        r"\b(deprecated|legacy|discontinued|no longer supported|sunsetting|end of life|retiring|sunset)\b",
        re.I,
    ),
}

PRICE_REGEX = re.compile(r"(\$|€|£|¥)\s*\d+([,\.]\d{2})?(\s*/\s*(mo|month|yr|year|user|seat))?", re.I)


def analyze_diff(diff_text: str) -> StrategicAnalysis:
    """Analyze diff text and classify strategic intent with extracted pricing and headlines."""
    if not diff_text or diff_text.strip() in ("No changes detected.", ""):
        return StrategicAnalysis(
            intent_tags=["NO_CHANGE"],
            summary="No strategic changes detected.",
            pricing_deltas=[],
            headline_deltas=[],
            confidence_score=1.0,
        )

    lines = diff_text.splitlines()
    added_lines = [l[2:].strip() for l in lines if l.startswith("+ ")]
    removed_lines = [l[2:].strip() for l in lines if l.startswith("- ")]

    diff_body = " ".join(added_lines + removed_lines)
    tags_found: Set[str] = set()

    for tag, pattern in PATTERNS.items():
        if pattern.search(diff_body):
            tags_found.add(tag)

    # Extract price signals
    old_prices = set(PRICE_REGEX.findall(" ".join(removed_lines)))
    new_prices = set(PRICE_REGEX.findall(" ".join(added_lines)))

    pricing_deltas: List[str] = []
    old_price_strs = [p[0] for p in PRICE_REGEX.finditer(" ".join(removed_lines))]
    new_price_strs = [p[0] for p in PRICE_REGEX.finditer(" ".join(added_lines))]

    if old_price_strs or new_price_strs:
        tags_found.add("PRICING_CHANGE")
        if old_price_strs and new_price_strs:
            pricing_deltas.append(f"Prices modified: {', '.join(old_price_strs)} -> {', '.join(new_price_strs)}")
        elif new_price_strs:
            pricing_deltas.append(f"New pricing introduced: {', '.join(new_price_strs)}")
        elif old_price_strs:
            pricing_deltas.append(f"Prices removed or hidden: {', '.join(old_price_strs)}")

    # Extract headline deltas
    headline_deltas: List[str] = []
    for line in added_lines:
        if line.startswith("#"):
            headline_deltas.append(f"Added header: {line}")
            tags_found.add("POSITIONING_UPDATE")
    for line in removed_lines:
        if line.startswith("#"):
            headline_deltas.append(f"Removed header: {line}")
            tags_found.add("POSITIONING_UPDATE")

    final_tags = sorted(list(tags_found)) if tags_found else ["POSITIONING_UPDATE"]

    # Generate synthesized executive summary
    summary_parts = []
    if "PRICING_CHANGE" in final_tags:
        if pricing_deltas:
            summary_parts.append(pricing_deltas[0])
        else:
            summary_parts.append("Pricing structure or billing intervals modified.")

    if "TIER_MODIFIED" in final_tags:
        summary_parts.append("Product plan tiers altered or reorganized.")

    if "ENTERPRISE_PIVOT" in final_tags:
        summary_parts.append("Enterprise governance, security, or compliance features added.")

    if "LIMIT_ADJUSTED" in final_tags:
        summary_parts.append("Usage quotas, seats, or credit boundaries updated.")

    if "FEATURE_ANNOUNCED" in final_tags:
        summary_parts.append("New product capabilities or integrations announced.")

    if "DEPRECATION" in final_tags:
        summary_parts.append("Legacy features or plans marked for deprecation.")

    if not summary_parts and headline_deltas:
        summary_parts.append(f"Core messaging updated: {headline_deltas[0]}")

    if not summary_parts:
        summary_parts.append(f"Page content refreshed across {len(added_lines)} additions and {len(removed_lines)} removals.")

    summary = " ".join(summary_parts)
    confidence = min(0.95, 0.5 + (0.1 * len(final_tags)))

    return StrategicAnalysis(
        intent_tags=final_tags,
        summary=summary,
        pricing_deltas=pricing_deltas,
        headline_deltas=headline_deltas,
        confidence_score=confidence,
    )
