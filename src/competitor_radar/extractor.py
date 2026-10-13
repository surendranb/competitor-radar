"""High-Fidelity HTML-to-Markdown Extractor & Cleaner.

Strips navigational bloat, scripts, cookie banners, tracking iframes,
normalizes tables and headers, and produces clean CommonMark with SHA-256 hashing.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse


@dataclass
class ExtractedContent:
    """Structured extraction result."""
    markdown: str
    content_hash: str
    word_count: int
    title: str
    headings: List[str]
    tables_count: int


# Tags that should be completely dropped along with all their children
DROP_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "canvas",
    "iframe",
    "nav",
    "footer",
    "aside",
    "header",
}

# Substrings in class or ID indicating cookie banners, compliance modals, or ads
BLOCKLIST_ATTR_PATTERNS = [
    re.compile(r"(cookie|consent|onetrust|gdpr|privacy-banner|cookie-banner|modal-cookie)", re.I),
    re.compile(r"(ad-banner|advertisement|newsletter-popup|interstitial)", re.I),
]


class _HTMLToMarkdownParser(HTMLParser):
    """Event-driven parser transforming HTML to formatted markdown."""

    def __init__(self, base_url: str = "") -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.output: List[str] = []
        self.title_tokens: List[str] = []
        self.headings: List[str] = []
        self.tables_count: int = 0

        self._in_title = False
        self._drop_depth = 0
        self._drop_stack: List[str] = []

        self._current_tag: List[str] = []
        self._list_depth = 0
        self._list_item_index: List[int] = []

        # Table processing
        self._in_table = False
        self._table_rows: List[List[str]] = []
        self._current_row: List[str] = []
        self._current_cell: List[str] = []

        # Link processing
        self._current_link_href: Optional[str] = None
        self._current_link_text: List[str] = []

    def _should_drop_element(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> bool:
        if tag.lower() in DROP_TAGS:
            return True
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        combined = f"{attr_dict.get('id', '')} {attr_dict.get('class', '')} {attr_dict.get('role', '')}"
        for pat in BLOCKLIST_ATTR_PATTERNS:
            if pat.search(combined):
                return True
        return False

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        tag_lower = tag.lower()

        if self._drop_depth > 0:
            self._drop_depth += 1
            return

        if self._should_drop_element(tag_lower, attrs):
            self._drop_depth = 1
            return

        self._current_tag.append(tag_lower)

        if tag_lower == "title":
            self._in_title = True
        elif tag_lower in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag_lower[1])
            self.output.append(f"\n\n{'#' * level} ")
        elif tag_lower == "p":
            self.output.append("\n\n")
        elif tag_lower == "br":
            self.output.append("\n")
        elif tag_lower == "hr":
            self.output.append("\n\n---\n\n")
        elif tag_lower in ("ul", "ol"):
            self._list_depth += 1
            self._list_item_index.append(1 if tag_lower == "ol" else 0)
            self.output.append("\n")
        elif tag_lower == "li":
            indent = "  " * max(0, self._list_depth - 1)
            if self._list_item_index and self._list_item_index[-1] > 0:
                idx = self._list_item_index[-1]
                self.output.append(f"\n{indent}{idx}. ")
                self._list_item_index[-1] += 1
            else:
                self.output.append(f"\n{indent}- ")
        elif tag_lower in ("strong", "b"):
            self.output.append("**")
        elif tag_lower in ("em", "i"):
            self.output.append("*")
        elif tag_lower == "code":
            self.output.append("`")
        elif tag_lower == "pre":
            self.output.append("\n\n```\n")
        elif tag_lower == "a":
            attr_dict = {k.lower(): v for k, v in attrs}
            href = attr_dict.get("href")
            if href:
                self._current_link_href = urljoin(self.base_url, href)
                self._current_link_text = []
        elif tag_lower == "table":
            self._in_table = True
            self.tables_count += 1
            self._table_rows = []
        elif tag_lower == "tr":
            if self._in_table:
                self._current_row = []
        elif tag_lower in ("th", "td"):
            if self._in_table:
                self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()

        if self._drop_depth > 0:
            self._drop_depth -= 1
            return

        if self._current_tag and self._current_tag[-1] == tag_lower:
            self._current_tag.pop()

        if tag_lower == "title":
            self._in_title = False
        elif tag_lower in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.output.append("\n")
        elif tag_lower in ("ul", "ol"):
            if self._list_depth > 0:
                self._list_depth -= 1
            if self._list_item_index:
                self._list_item_index.pop()
            self.output.append("\n")
        elif tag_lower in ("strong", "b"):
            self.output.append("**")
        elif tag_lower in ("em", "i"):
            self.output.append("*")
        elif tag_lower == "code":
            self.output.append("`")
        elif tag_lower == "pre":
            self.output.append("\n```\n")
        elif tag_lower == "a":
            if self._current_link_href:
                link_text = "".join(self._current_link_text).strip()
                if link_text:
                    self.output.append(f"[{link_text}]({self._current_link_href})")
                self._current_link_href = None
                self._current_link_text = []
        elif tag_lower in ("th", "td"):
            if self._in_table:
                cell_content = "".join(self._current_cell).strip().replace("\n", " ").replace("|", "\\|")
                self._current_row.append(cell_content)
                self._current_cell = []
        elif tag_lower == "tr":
            if self._in_table and self._current_row:
                self._table_rows.append(self._current_row)
                self._current_row = []
        elif tag_lower == "table":
            if self._in_table:
                self._render_table()
                self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._drop_depth > 0:
            return

        if self._in_title:
            self.title_tokens.append(data)
            return

        if self._in_table:
            self._current_cell.append(data)
            return

        if self._current_link_href is not None:
            self._current_link_text.append(data)
            return

        # Check if inside heading for tracking
        if self._current_tag and self._current_tag[-1] in ("h1", "h2", "h3", "h4", "h5", "h6"):
            clean_token = data.strip()
            if clean_token:
                self.headings.append(clean_token)

        self.output.append(data)

    def _render_table(self) -> None:
        """Render collected table rows as a normalized Markdown table."""
        if not self._table_rows:
            return

        max_cols = max(len(row) for row in self._table_rows)
        if max_cols == 0:
            return

        # Normalize row lengths
        normalized_rows = [row + [""] * (max_cols - len(row)) for row in self._table_rows]

        header = normalized_rows[0]
        divider = ["---"] * max_cols

        table_md = ["\n\n| " + " | ".join(header) + " |"]
        table_md.append("| " + " | ".join(divider) + " |")

        for row in normalized_rows[1:]:
            table_md.append("| " + " | ".join(row) + " |")

        table_md.append("\n\n")
        self.output.append("\n".join(table_md))


def extract_markdown(html_content: str, base_url: str = "") -> ExtractedContent:
    """Transform raw HTML into clean, normalized Markdown."""
    if not html_content or not html_content.strip():
        return ExtractedContent(
            markdown="",
            content_hash=hashlib.sha256(b"").hexdigest(),
            word_count=0,
            title="",
            headings=[],
            tables_count=0,
        )

    parser = _HTMLToMarkdownParser(base_url=base_url)
    parser.feed(html_content)
    parser.close()

    raw_md = "".join(parser.output)

    # Clean whitespace and repeated blank lines
    lines = [line.rstrip() for line in raw_md.splitlines()]
    clean_lines: List[str] = []
    blank_run = 0

    for line in lines:
        if not line.strip():
            blank_run += 1
            if blank_run <= 1:
                clean_lines.append("")
        else:
            blank_run = 0
            clean_lines.append(line)

    cleaned_markdown = "\n".join(clean_lines).strip()
    title = "".join(parser.title_tokens).strip()

    # Word count calculation
    words = re.findall(r"\b\w+\b", cleaned_markdown)
    word_count = len(words)

    # SHA-256 hash of normalized markdown
    content_hash = hashlib.sha256(cleaned_markdown.encode("utf-8")).hexdigest()

    return ExtractedContent(
        markdown=cleaned_markdown,
        content_hash=content_hash,
        word_count=word_count,
        title=title,
        headings=parser.headings,
        tables_count=parser.tables_count,
    )
