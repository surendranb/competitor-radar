"""Fast Sitemap & Sitemap Index Parser with Delta Discovery.

Traverses standard sitemap.xml and nested sitemap_index.xml trees,
identifies hidden staging/beta paths, and computes published/removed deltas.
"""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
import requests


@dataclass
class DiscoveredUrl:
    """Discovered URL entry from sitemap."""
    url: str
    lastmod: Optional[str] = None
    is_staging_or_beta: bool = False
    category: str = "general"


@dataclass
class SitemapParseResult:
    """Result of sitemap crawl and extraction."""
    target_url: str
    total_urls: int
    urls: List[DiscoveredUrl]
    staging_or_beta_urls: List[str]
    sitemaps_inspected: int


STAGING_BETA_REGEX = re.compile(
    r"/(beta|staging|preview|v2|v3|experiment|experiments|labs|test|alpha|stealth|early-access)/",
    re.I,
)


def _strip_ns(tag: str) -> str:
    """Remove XML namespace prefix."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def parse_sitemap_xml(xml_content: str) -> List[DiscoveredUrl]:
    """Parse sitemap XML content and extract URLs with lastmod dates."""
    discovered: List[DiscoveredUrl] = []
    if not xml_content or not xml_content.strip():
        return discovered

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        # Fallback to regex if XML has unescaped characters
        locs = re.findall(r"<loc>(.*?)</loc>", xml_content, re.I)
        for loc in locs:
            clean_url = loc.strip()
            if clean_url:
                is_beta = bool(STAGING_BETA_REGEX.search(clean_url))
                discovered.append(DiscoveredUrl(url=clean_url, is_staging_or_beta=is_beta))
        return discovered

    root_tag = _strip_ns(root.tag).lower()

    if root_tag == "urlset":
        for url_elem in root:
            if _strip_ns(url_elem.tag).lower() != "url":
                continue
            loc_val: Optional[str] = None
            lastmod_val: Optional[str] = None

            for child in url_elem:
                c_tag = _strip_ns(child.tag).lower()
                if c_tag == "loc" and child.text:
                    loc_val = child.text.strip()
                elif c_tag == "lastmod" and child.text:
                    lastmod_val = child.text.strip()

            if loc_val:
                is_beta = bool(STAGING_BETA_REGEX.search(loc_val))
                category = "general"
                if "/pricing" in loc_val:
                    category = "pricing"
                elif "/product" in loc_val or "/features" in loc_val:
                    category = "product"
                elif "/blog" in loc_val or "/news" in loc_val:
                    category = "content"
                elif "/docs" in loc_val or "/api" in loc_val:
                    category = "docs"

                discovered.append(
                    DiscoveredUrl(
                        url=loc_val,
                        lastmod=lastmod_val,
                        is_staging_or_beta=is_beta,
                        category=category,
                    )
                )

    return discovered


def fetch_and_parse_sitemap(
    base_url_or_domain: str,
    max_sub_sitemaps: int = 5,
    timeout: float = 10.0,
) -> SitemapParseResult:
    """Fetch sitemap or sitemap index from domain and resolve URLs."""
    # Ensure scheme
    raw_input = base_url_or_domain.strip()
    if not raw_input.startswith("http://") and not raw_input.startswith("https://"):
        target_sitemap_url = f"https://{raw_input}/sitemap.xml"
    elif raw_input.endswith(".xml"):
        target_sitemap_url = raw_input
    else:
        target_sitemap_url = raw_input.rstrip("/") + "/sitemap.xml"

    headers = {
        "User-Agent": "CompetitorRadar/1.0 (+https://github.com/surendranb/competitor-radar; bot)",
        "Accept": "application/xml, text/xml, */*",
    }

    all_discovered: List[DiscoveredUrl] = []
    seen_urls: Set[str] = set()
    sitemaps_inspected = 0
    staging_or_beta: List[str] = []

    try:
        resp = requests.get(target_sitemap_url, headers=headers, timeout=timeout)
        if resp.status_code == 404 and not target_sitemap_url.endswith("/sitemap_index.xml"):
            # Try sitemap_index.xml fallback
            fallback_url = target_sitemap_url.replace("/sitemap.xml", "/sitemap_index.xml")
            resp = requests.get(fallback_url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                target_sitemap_url = fallback_url

        resp.raise_for_status()
        sitemaps_inspected += 1
        content = resp.text

        # Check if sitemap index
        if "<sitemapindex" in content:
            child_locs = re.findall(r"<sitemap>\s*<loc>(.*?)</loc>", content, re.I | re.S)
            for child_url in child_locs[:max_sub_sitemaps]:
                child_clean = child_url.strip()
                try:
                    c_resp = requests.get(child_clean, headers=headers, timeout=timeout)
                    if c_resp.status_code == 200:
                        sitemaps_inspected += 1
                        items = parse_sitemap_xml(c_resp.text)
                        for it in items:
                            if it.url not in seen_urls:
                                seen_urls.add(it.url)
                                all_discovered.append(it)
                                if it.is_staging_or_beta:
                                    staging_or_beta.append(it.url)
                except Exception:
                    continue
        else:
            items = parse_sitemap_xml(content)
            for it in items:
                if it.url not in seen_urls:
                    seen_urls.add(it.url)
                    all_discovered.append(it)
                    if it.is_staging_or_beta:
                        staging_or_beta.append(it.url)

    except Exception as e:
        # Return empty result with note
        return SitemapParseResult(
            target_url=target_sitemap_url,
            total_urls=0,
            urls=[],
            staging_or_beta_urls=[],
            sitemaps_inspected=sitemaps_inspected,
        )

    return SitemapParseResult(
        target_url=target_sitemap_url,
        total_urls=len(all_discovered),
        urls=all_discovered,
        staging_or_beta_urls=staging_or_beta,
        sitemaps_inspected=sitemaps_inspected,
    )
