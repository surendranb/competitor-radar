"""SQLite Ledger Database for Competitor Radar.

Stores targets, page snapshots, diff events with strategic intent,
sitemap discovery catalogs, and ATS job posting histories.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def get_default_db_path() -> Path:
    """Resolve database path from environment variable or standard home directory."""
    custom_path = os.getenv("COMPETITOR_RADAR_DB_PATH")
    if custom_path:
        return Path(custom_path).expanduser().resolve()
    base_dir = Path.home() / ".competitor-radar"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "timeline.db"


class Storage:
    """Thread-safe SQLite ledger storage for competitive tracking."""

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        if db_path is None:
            self.db_path = get_default_db_path()
        else:
            self.db_path = Path(db_path).expanduser().resolve()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Create and configure a SQLite connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self) -> None:
        """Initialize database schema if not present."""
        with self.get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS targets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    domain TEXT,
                    main_url TEXT,
                    pricing_url TEXT,
                    ats_provider TEXT,
                    ats_slug TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    raw_markdown TEXT NOT NULL,
                    word_count INTEGER NOT NULL DEFAULT 0,
                    captured_at TEXT NOT NULL,
                    FOREIGN KEY(target_id) REFERENCES targets(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS diff_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    prev_snapshot_id INTEGER,
                    curr_snapshot_id INTEGER NOT NULL,
                    diff_text TEXT NOT NULL,
                    added_lines_count INTEGER NOT NULL DEFAULT 0,
                    removed_lines_count INTEGER NOT NULL DEFAULT 0,
                    intent_tags TEXT NOT NULL DEFAULT '[]',
                    summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(target_id) REFERENCES targets(id) ON DELETE CASCADE,
                    FOREIGN KEY(prev_snapshot_id) REFERENCES snapshots(id) ON DELETE SET NULL,
                    FOREIGN KEY(curr_snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS sitemap_urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    lastmod TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    UNIQUE(target_id, url),
                    FOREIGN KEY(target_id) REFERENCES targets(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS job_postings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_id INTEGER NOT NULL,
                    external_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    department TEXT,
                    location TEXT,
                    first_seen_at TEXT NOT NULL,
                    closed_at TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    UNIQUE(target_id, external_id),
                    FOREIGN KEY(target_id) REFERENCES targets(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_snapshots_target_url
                    ON snapshots(target_id, url, captured_at DESC);

                CREATE INDEX IF NOT EXISTS idx_diff_events_target
                    ON diff_events(target_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_sitemap_target_status
                    ON sitemap_urls(target_id, status);

                CREATE INDEX IF NOT EXISTS idx_jobs_target_status
                    ON job_postings(target_id, status);
                """
            )

    # -------------------------------------------------------------------------
    # Target Operations
    # -------------------------------------------------------------------------

    def upsert_target(
        self,
        name: str,
        domain: Optional[str] = None,
        main_url: Optional[str] = None,
        pricing_url: Optional[str] = None,
        ats_provider: Optional[str] = None,
        ats_slug: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert or update a competitor target."""
        clean_name = name.strip()
        now = _now_iso()

        with self.get_connection() as conn:
            existing = conn.execute(
                "SELECT * FROM targets WHERE LOWER(name) = LOWER(?)", (clean_name,)
            ).fetchone()

            if existing:
                target_id = existing["id"]
                conn.execute(
                    """
                    UPDATE targets
                    SET domain = COALESCE(?, domain),
                        main_url = COALESCE(?, main_url),
                        pricing_url = COALESCE(?, pricing_url),
                        ats_provider = COALESCE(?, ats_provider),
                        ats_slug = COALESCE(?, ats_slug),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (domain, main_url, pricing_url, ats_provider, ats_slug, now, target_id),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO targets (name, domain, main_url, pricing_url, ats_provider, ats_slug, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (clean_name, domain, main_url, pricing_url, ats_provider, ats_slug, now, now),
                )
                target_id = cursor.lastrowid

            row = conn.execute("SELECT * FROM targets WHERE id = ?", (target_id,)).fetchone()
            return dict(row)

    def get_target(self, name_or_domain: str) -> Optional[Dict[str, Any]]:
        """Look up a target by name or domain."""
        query_val = name_or_domain.strip().lower()
        with self.get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM targets
                WHERE LOWER(name) = ?
                   OR LOWER(domain) = ?
                   OR LOWER(domain) = ?
                LIMIT 1
                """,
                (query_val, query_val, query_val.replace("https://", "").replace("http://", "").split("/")[0]),
            ).fetchone()
            return dict(row) if row else None

    def list_targets(self) -> List[Dict[str, Any]]:
        """List all registered competitor targets."""
        with self.get_connection() as conn:
            rows = conn.execute("SELECT * FROM targets ORDER BY name ASC").fetchall()
            return [dict(r) for r in rows]

    # -------------------------------------------------------------------------
    # Snapshot Operations
    # -------------------------------------------------------------------------

    def insert_snapshot(
        self,
        target_id: int,
        url: str,
        content_hash: str,
        raw_markdown: str,
        word_count: int,
    ) -> int:
        """Record a new web content snapshot."""
        now = _now_iso()
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO snapshots (target_id, url, content_hash, raw_markdown, word_count, captured_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (target_id, url, content_hash, raw_markdown, word_count, now),
            )
            return cursor.lastrowid

    def get_latest_snapshot(self, target_id: int, url: str) -> Optional[Dict[str, Any]]:
        """Retrieve the most recent snapshot for a target URL."""
        with self.get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM snapshots
                WHERE target_id = ? AND url = ?
                ORDER BY captured_at DESC, id DESC
                LIMIT 1
                """,
                (target_id, url),
            ).fetchone()
            return dict(row) if row else None

    def get_previous_snapshot(
        self, target_id: int, url: str, before_snapshot_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieve the prior snapshot preceding a given snapshot ID."""
        with self.get_connection() as conn:
            if before_snapshot_id:
                row = conn.execute(
                    """
                    SELECT * FROM snapshots
                    WHERE target_id = ? AND url = ? AND id < ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (target_id, url, before_snapshot_id),
                ).fetchone()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM snapshots
                    WHERE target_id = ? AND url = ?
                    ORDER BY id DESC
                    LIMIT 2
                    """,
                    (target_id, url),
                ).fetchall()
                row = rows[1] if len(rows) > 1 else None

            return dict(row) if row else None

    # -------------------------------------------------------------------------
    # Diff Event Operations
    # -------------------------------------------------------------------------

    def insert_diff_event(
        self,
        target_id: int,
        url: str,
        prev_snapshot_id: Optional[int],
        curr_snapshot_id: int,
        diff_text: str,
        added_lines_count: int,
        removed_lines_count: int,
        intent_tags: List[str],
        summary: str,
    ) -> int:
        """Record a strategic diff event."""
        now = _now_iso()
        tags_json = json.dumps(intent_tags)
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO diff_events (
                    target_id, url, prev_snapshot_id, curr_snapshot_id,
                    diff_text, added_lines_count, removed_lines_count,
                    intent_tags, summary, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target_id,
                    url,
                    prev_snapshot_id,
                    curr_snapshot_id,
                    diff_text,
                    added_lines_count,
                    removed_lines_count,
                    tags_json,
                    summary,
                    now,
                ),
            )
            return cursor.lastrowid

    def get_diff_events(
        self,
        target_id: Optional[int] = None,
        limit: int = 20,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve timeline diff events with optional target and tag filtering."""
        with self.get_connection() as conn:
            query = """
                SELECT d.*, t.name as target_name, t.domain as target_domain
                FROM diff_events d
                JOIN targets t ON d.target_id = t.id
                WHERE 1=1
            """
            params: List[Any] = []

            if target_id is not None:
                query += " AND d.target_id = ?"
                params.append(target_id)

            if category:
                query += " AND LOWER(d.intent_tags) LIKE ?"
                params.append(f"%{category.strip().lower()}%")

            query += " ORDER BY d.created_at DESC LIMIT ?"
            params.append(max(1, limit))

            rows = conn.execute(query, params).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                try:
                    item["intent_tags"] = json.loads(item["intent_tags"])
                except Exception:
                    item["intent_tags"] = []
                results.append(item)
            return results

    # -------------------------------------------------------------------------
    # Sitemap Operations
    # -------------------------------------------------------------------------

    def sync_sitemap_urls(
        self, target_id: int, discovered_urls: List[Dict[str, Optional[str]]]
    ) -> Dict[str, Any]:
        """Sync discovered sitemap URLs against storage and calculate deltas."""
        now = _now_iso()
        discovered_map = {item["url"]: item.get("lastmod") for item in discovered_urls if item.get("url")}
        added_urls = []
        updated_urls = []

        with self.get_connection() as conn:
            existing_rows = conn.execute(
                "SELECT * FROM sitemap_urls WHERE target_id = ?", (target_id,)
            ).fetchall()
            existing_map = {r["url"]: dict(r) for r in existing_rows}

            for url, lastmod in discovered_map.items():
                if url not in existing_map:
                    conn.execute(
                        """
                        INSERT INTO sitemap_urls (target_id, url, lastmod, first_seen_at, last_seen_at, status)
                        VALUES (?, ?, ?, ?, ?, 'active')
                        """,
                        (target_id, url, lastmod, now, now),
                    )
                    added_urls.append({"url": url, "lastmod": lastmod, "status": "new"})
                else:
                    curr = existing_map[url]
                    needs_update = (curr["status"] != "active") or (lastmod and curr["lastmod"] != lastmod)
                    conn.execute(
                        """
                        UPDATE sitemap_urls
                        SET lastmod = COALESCE(?, lastmod),
                            last_seen_at = ?,
                            status = 'active'
                        WHERE target_id = ? AND url = ?
                        """,
                        (lastmod, now, target_id, url),
                    )
                    if needs_update and lastmod and curr["lastmod"] != lastmod:
                        updated_urls.append(
                            {"url": url, "prev_lastmod": curr["lastmod"], "new_lastmod": lastmod}
                        )

            # Detect removed / stale URLs
            removed_urls = []
            for url, curr in existing_map.items():
                if url not in discovered_map and curr["status"] == "active":
                    conn.execute(
                        "UPDATE sitemap_urls SET status = 'removed' WHERE target_id = ? AND url = ?",
                        (target_id, url),
                    )
                    removed_urls.append({"url": url, "status": "removed"})

            total_active = conn.execute(
                "SELECT COUNT(*) as cnt FROM sitemap_urls WHERE target_id = ? AND status = 'active'",
                (target_id,),
            ).fetchone()["cnt"]

            return {
                "target_id": target_id,
                "added": added_urls,
                "updated": updated_urls,
                "removed": removed_urls,
                "total_active": total_active,
            }

    def get_sitemap_urls(
        self, target_id: int, status: Optional[str] = "active"
    ) -> List[Dict[str, Any]]:
        """Retrieve stored sitemap URLs for a target."""
        with self.get_connection() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM sitemap_urls WHERE target_id = ? AND status = ? ORDER BY last_seen_at DESC",
                    (target_id, status),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sitemap_urls WHERE target_id = ? ORDER BY last_seen_at DESC",
                    (target_id,),
                ).fetchall()
            return [dict(r) for r in rows]

    # -------------------------------------------------------------------------
    # Job Postings (ATS) Operations
    # -------------------------------------------------------------------------

    def sync_job_postings(
        self, target_id: int, active_jobs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Sync live ATS job postings, track newly opened and closed roles."""
        now = _now_iso()
        incoming_map = {str(j["external_id"]): j for j in active_jobs if j.get("external_id")}
        added = []

        with self.get_connection() as conn:
            existing_rows = conn.execute(
                "SELECT * FROM job_postings WHERE target_id = ?", (target_id,)
            ).fetchall()
            existing_map = {str(r["external_id"]): dict(r) for r in existing_rows}

            for ext_id, job in incoming_map.items():
                title = job.get("title", "Untitled Role")
                dept = job.get("department", "General")
                loc = job.get("location", "Remote")

                if ext_id not in existing_map:
                    conn.execute(
                        """
                        INSERT INTO job_postings (target_id, external_id, title, department, location, first_seen_at, status)
                        VALUES (?, ?, ?, ?, ?, ?, 'active')
                        """,
                        (target_id, ext_id, title, dept, loc, now),
                    )
                    added.append({"external_id": ext_id, "title": title, "department": dept, "location": loc})
                else:
                    # Reactivate if previously closed or update details
                    conn.execute(
                        """
                        UPDATE job_postings
                        SET title = ?, department = ?, location = ?, status = 'active', closed_at = NULL
                        WHERE target_id = ? AND external_id = ?
                        """,
                        (title, dept, loc, target_id, ext_id),
                    )

            # Find jobs that were closed
            closed = []
            for ext_id, curr in existing_map.items():
                if ext_id not in incoming_map and curr["status"] == "active":
                    conn.execute(
                        "UPDATE job_postings SET status = 'closed', closed_at = ? WHERE target_id = ? AND external_id = ?",
                        (now, target_id, ext_id),
                    )
                    closed.append({"external_id": ext_id, "title": curr["title"], "department": curr["department"]})

            # Department breakdown of current active roles
            dept_counts_rows = conn.execute(
                """
                SELECT department, COUNT(*) as cnt
                FROM job_postings
                WHERE target_id = ? AND status = 'active'
                GROUP BY department
                ORDER BY cnt DESC
                """,
                (target_id,),
            ).fetchall()
            dept_breakdown = {r["department"]: r["cnt"] for r in dept_counts_rows}

            total_active = sum(dept_breakdown.values())

            return {
                "target_id": target_id,
                "added": added,
                "closed": closed,
                "active_count": total_active,
                "department_breakdown": dept_breakdown,
            }

    def get_job_postings(
        self, target_id: int, status: str = "active"
    ) -> List[Dict[str, Any]]:
        """Retrieve job postings for a target."""
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM job_postings WHERE target_id = ? AND status = ? ORDER BY first_seen_at DESC",
                (target_id, status),
            ).fetchall()
            return [dict(r) for r in rows]
