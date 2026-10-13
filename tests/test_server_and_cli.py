"""Tests for MCP Tools and CLI Endpoints."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from competitor_radar.server import (
    check_for_updates,
    competitor_brief,
    competitor_timeline,
    skills_list,
    skill_read,
    watch_competitor,
)
from competitor_radar.storage import Storage


@pytest.fixture(autouse=True)
def isolated_storage(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = Path(tmpdir) / "server_test.db"
        store = Storage(db_path=test_db)
        monkeypatch.setattr("competitor_radar.server._storage", store)
        yield store


def test_watch_competitor_tool():
    res = watch_competitor(
        name="Linear",
        url="https://linear.app",
        pricing_url="https://linear.app/pricing",
        ats_provider="ashby",
        ats_slug="linear",
    )
    assert "Target Registered: Linear" in res
    assert "linear.app" in res


def test_competitor_timeline_empty():
    res = competitor_timeline(name="Nonexistent")
    assert "No records found" in res


def test_competitor_brief():
    watch_competitor(
        name="Acme",
        url="https://acme.com",
        pricing_url="https://acme.com/pricing",
    )
    brief = competitor_brief("Acme")
    assert "Competitive Intelligence Dossier: Acme" in brief
    assert "acme.com" in brief


def test_skills_tools():
    skills = skills_list()
    assert "competitor_analysis" in skills

    content = skill_read("competitor_analysis")
    assert "Competitive Radar Playbook" in content


def test_check_for_updates():
    res = check_for_updates()
    assert "competitor-radar" in res
