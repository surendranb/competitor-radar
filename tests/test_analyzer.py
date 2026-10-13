"""Tests for Strategic Intent Classifier."""

from competitor_radar.analyzer import analyze_diff


def test_analyze_pricing_and_tier_change():
    diff_text = """### Section: ## Pricing
- Starter Tier: $19 / mo
+ Growth Tier: $49 / mo
- 3 seats included
+ 10 seats included"""

    analysis = analyze_diff(diff_text)
    assert "PRICING_CHANGE" in analysis.intent_tags
    assert "TIER_MODIFIED" in analysis.intent_tags
    assert "LIMIT_ADJUSTED" in analysis.intent_tags
    assert len(analysis.pricing_deltas) > 0
    assert "$19" in analysis.summary or "$49" in analysis.summary


def test_analyze_enterprise_pivot():
    diff_text = """### Section: ## Security & Compliance
+ Enterprise SSO via Okta and SAML
+ SOC 2 Type II certified
+ 99.99% uptime SLA and dedicated support
+ Contact sales for custom enterprise contracts"""

    analysis = analyze_diff(diff_text)
    assert "ENTERPRISE_PIVOT" in analysis.intent_tags
    assert "Enterprise" in analysis.summary


def test_analyze_feature_announced():
    diff_text = """### Section: # Changelog
+ Introducing real-time collaborative workspaces (beta)
+ Support for custom webhooks and Slack notifications"""

    analysis = analyze_diff(diff_text)
    assert "FEATURE_ANNOUNCED" in analysis.intent_tags


def test_analyze_deprecation():
    diff_text = """### Section: ## Legacy API
+ The v1 REST endpoint has been deprecated and will be discontinued in Q4."""

    analysis = analyze_diff(diff_text)
    assert "DEPRECATION" in analysis.intent_tags


def test_analyze_no_change():
    analysis = analyze_diff("No changes detected.")
    assert "NO_CHANGE" in analysis.intent_tags
