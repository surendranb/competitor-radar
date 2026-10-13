"""Tests for SQLite Ledger Storage."""

import tempfile
from pathlib import Path

import pytest
from competitor_radar.storage import Storage


@pytest.fixture
def temp_storage():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_timeline.db"
        storage = Storage(db_path=db_path)
        yield storage


def test_target_crud(temp_storage):
    target = temp_storage.upsert_target(
        name="Linear",
        domain="linear.app",
        main_url="https://linear.app",
        pricing_url="https://linear.app/pricing",
        ats_provider="ashby",
        ats_slug="linear",
    )
    assert target["id"] is not None
    assert target["name"] == "Linear"

    fetched = temp_storage.get_target("linear")
    assert fetched is not None
    assert fetched["id"] == target["id"]
    assert fetched["domain"] == "linear.app"

    # Upsert updates without duplicate
    updated = temp_storage.upsert_target(
        name="Linear",
        pricing_url="https://linear.app/pricing-new",
    )
    assert updated["id"] == target["id"]
    assert updated["pricing_url"] == "https://linear.app/pricing-new"

    targets = temp_storage.list_targets()
    assert len(targets) == 1


def test_snapshots_and_diff_events(temp_storage):
    target = temp_storage.upsert_target(name="Acme", domain="acme.com", main_url="https://acme.com")

    # Insert snapshot 1
    snap1_id = temp_storage.insert_snapshot(
        target_id=target["id"],
        url="https://acme.com/pricing",
        content_hash="hash1",
        raw_markdown="# Plan $29",
        word_count=3,
    )
    assert snap1_id > 0

    latest = temp_storage.get_latest_snapshot(target["id"], "https://acme.com/pricing")
    assert latest["id"] == snap1_id

    # Insert snapshot 2
    snap2_id = temp_storage.insert_snapshot(
        target_id=target["id"],
        url="https://acme.com/pricing",
        content_hash="hash2",
        raw_markdown="# Plan $49",
        word_count=3,
    )
    prev = temp_storage.get_previous_snapshot(target["id"], "https://acme.com/pricing", before_snapshot_id=snap2_id)
    assert prev["id"] == snap1_id

    # Insert diff event
    event_id = temp_storage.insert_diff_event(
        target_id=target["id"],
        url="https://acme.com/pricing",
        prev_snapshot_id=snap1_id,
        curr_snapshot_id=snap2_id,
        diff_text="- $29\n+ $49",
        added_lines_count=1,
        removed_lines_count=1,
        intent_tags=["PRICING_CHANGE"],
        summary="Price raised to $49",
    )
    assert event_id > 0

    events = temp_storage.get_diff_events(target_id=target["id"], category="PRICING_CHANGE")
    assert len(events) == 1
    assert events[0]["intent_tags"] == ["PRICING_CHANGE"]


def test_sitemap_sync(temp_storage):
    target = temp_storage.upsert_target(name="Acme", domain="acme.com", main_url="https://acme.com")

    # Initial sync
    initial = [
        {"url": "https://acme.com/home", "lastmod": "2026-01-01"},
        {"url": "https://acme.com/pricing", "lastmod": "2026-01-01"},
    ]
    res1 = temp_storage.sync_sitemap_urls(target["id"], initial)
    assert len(res1["added"]) == 2
    assert res1["total_active"] == 2

    # Second sync: 1 updated, 1 added, 1 removed
    second = [
        {"url": "https://acme.com/home", "lastmod": "2026-02-01"},
        {"url": "https://acme.com/beta-feature", "lastmod": "2026-02-01"},
    ]
    res2 = temp_storage.sync_sitemap_urls(target["id"], second)
    assert len(res2["added"]) == 1
    assert len(res2["updated"]) == 1
    assert len(res2["removed"]) == 1
    assert res2["total_active"] == 2


def test_job_postings_sync(temp_storage):
    target = temp_storage.upsert_target(name="Acme", domain="acme.com", main_url="https://acme.com")

    jobs_1 = [
        {"external_id": "job-1", "title": "AI Engineer", "department": "AI & ML", "location": "Remote"},
        {"external_id": "job-2", "title": "Account Exec", "department": "Sales", "location": "SF"},
    ]
    sync1 = temp_storage.sync_job_postings(target["id"], jobs_1)
    assert len(sync1["added"]) == 2
    assert sync1["active_count"] == 2
    assert sync1["department_breakdown"]["AI & ML"] == 1

    # Second sync: job-1 closed, job-3 opened
    jobs_2 = [
        {"external_id": "job-2", "title": "Account Exec", "department": "Sales", "location": "SF"},
        {"external_id": "job-3", "title": "VP Marketing", "department": "Marketing", "location": "Remote"},
    ]
    sync2 = temp_storage.sync_job_postings(target["id"], jobs_2)
    assert len(sync2["added"]) == 1
    assert len(sync2["closed"]) == 1
    assert sync2["active_count"] == 2
