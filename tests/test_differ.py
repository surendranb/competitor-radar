"""Tests for Markdown Line and Semantic Differ."""

from competitor_radar.differ import compute_markdown_diff


def test_diff_initial_snapshot():
    curr = "# Acme Pricing\n\n$29 per month\n- 5 seats"
    res = compute_markdown_diff("", curr)
    assert res.has_changes is True
    assert "Initial snapshot captured" in res.diff_text
    assert res.added_lines_count == 4
    assert res.removed_lines_count == 0


def test_diff_no_changes():
    text = "# Acme Pricing\n\n$29 per month\n- 5 seats"
    res = compute_markdown_diff(text, text)
    assert res.has_changes is False
    assert res.added_lines_count == 0
    assert res.removed_lines_count == 0
    assert res.diff_text == "No changes detected."


def test_diff_price_modification_with_heading():
    prev = """# Pricing Plans
## Pro Tier
$29 / mo
- 5 seats included
- Standard support"""

    curr = """# Pricing Plans
## Pro Tier
$49 / mo
- 10 seats included
- Standard support"""

    res = compute_markdown_diff(prev, curr)
    assert res.has_changes is True
    assert res.added_lines_count > 0
    assert res.removed_lines_count > 0
    assert "Section: ## Pro Tier" in res.diff_text
    assert "- $29 / mo" in res.diff_text
    assert "+ $49 / mo" in res.diff_text
