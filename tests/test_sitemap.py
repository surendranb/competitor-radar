"""Tests for Sitemap and Sitemap Index XML Parsing."""

from unittest.mock import MagicMock, patch

from competitor_radar.sitemap import (
    fetch_and_parse_sitemap,
    parse_sitemap_xml,
)

SAMPLE_SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://acme.com/</loc>
    <lastmod>2026-03-01T12:00:00Z</lastmod>
  </url>
  <url>
    <loc>https://acme.com/pricing</loc>
    <lastmod>2026-03-05T12:00:00Z</lastmod>
  </url>
  <url>
    <loc>https://acme.com/beta/ai-workflows</loc>
    <lastmod>2026-03-10T12:00:00Z</lastmod>
  </url>
</urlset>
"""


def test_parse_sitemap_xml():
    urls = parse_sitemap_xml(SAMPLE_SITEMAP_XML)
    assert len(urls) == 3
    assert urls[0].url == "https://acme.com/"
    assert urls[1].url == "https://acme.com/pricing"
    assert urls[1].category == "pricing"
    assert urls[2].url == "https://acme.com/beta/ai-workflows"
    assert urls[2].is_staging_or_beta is True


def test_fetch_and_parse_sitemap_mock():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = SAMPLE_SITEMAP_XML

    with patch("requests.get", return_value=mock_resp):
        res = fetch_and_parse_sitemap("acme.com")
        assert res.total_urls == 3
        assert len(res.staging_or_beta_urls) == 1
        assert "beta" in res.staging_or_beta_urls[0]
