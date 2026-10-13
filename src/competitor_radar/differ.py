"""Markdown Line & Semantic Diff Engine.

Generates concise, human-readable CommonMark diffs ("The What"),
annotated with contextual headings and section boundaries.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class DiffResult:
    """Structured diff result."""
    diff_text: str
    added_lines_count: int
    removed_lines_count: int
    has_changes: bool
    sections_affected: List[str]


def compute_markdown_diff(
    prev_markdown: str,
    curr_markdown: str,
    context_lines: int = 1,
) -> DiffResult:
    """Compute semantic markdown diff annotated with nearest heading context."""
    prev_lines = [l.rstrip() for l in prev_markdown.splitlines()]
    curr_lines = [l.rstrip() for l in curr_markdown.splitlines()]

    if prev_lines == curr_lines:
        return DiffResult(
            diff_text="No changes detected.",
            added_lines_count=0,
            removed_lines_count=0,
            has_changes=False,
            sections_affected=[],
        )

    # If initial snapshot
    if not prev_markdown.strip():
        return DiffResult(
            diff_text=f"Initial snapshot captured ({len(curr_lines)} lines).",
            added_lines_count=len(curr_lines),
            removed_lines_count=0,
            has_changes=True,
            sections_affected=["[Initial Baseline]"],
        )

    matcher = difflib.SequenceMatcher(None, prev_lines, curr_lines)
    diff_blocks: List[str] = []
    added_count = 0
    removed_count = 0
    affected_headings = set()

    def find_nearest_heading(lines: List[str], index: int) -> str:
        for idx in range(min(index, len(lines) - 1), -1, -1):
            line = lines[idx].strip()
            if line.startswith("#"):
                return line
        return "[Top of Page]"

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        context_header = find_nearest_heading(curr_lines if j1 < len(curr_lines) else prev_lines, j1 if j1 < len(curr_lines) else i1)
        affected_headings.add(context_header)

        block_lines = [f"\n### Section: {context_header}"]

        if tag in ("delete", "replace"):
            for l in prev_lines[i1:i2]:
                if l.strip():
                    block_lines.append(f"- {l}")
                    removed_count += 1

        if tag in ("insert", "replace"):
            for l in curr_lines[j1:j2]:
                if l.strip():
                    block_lines.append(f"+ {l}")
                    added_count += 1

        diff_blocks.append("\n".join(block_lines))

    clean_diff_text = "\n\n".join(diff_blocks).strip()

    return DiffResult(
        diff_text=clean_diff_text,
        added_lines_count=added_count,
        removed_lines_count=removed_count,
        has_changes=(added_count > 0 or removed_count > 0),
        sections_affected=sorted(list(affected_headings)),
    )
