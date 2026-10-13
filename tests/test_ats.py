"""Tests for ATS Hiring Radar with Mock Greenhouse and Ashby Fixtures."""

from unittest.mock import MagicMock, patch

from competitor_radar.ats import (
    analyze_hiring_data,
    classify_canonical_department,
    fetch_ashby_jobs,
    fetch_greenhouse_jobs,
)

MOCK_GREENHOUSE_RESPONSE = {
    "jobs": [
        {
            "id": 101,
            "title": "Staff AI Research Engineer",
            "departments": [{"id": 1, "name": "Research"}],
            "location": {"name": "San Francisco, CA"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/101",
        },
        {
            "id": 102,
            "title": "VP of Enterprise Sales",
            "departments": [{"id": 2, "name": "Revenue"}],
            "location": {"name": "Remote, US"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/102",
        },
        {
            "id": 103,
            "title": "Senior Backend Developer",
            "departments": [{"id": 3, "name": "Engineering"}],
            "location": {"name": "New York, NY"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/103",
        },
    ]
}

MOCK_ASHBY_RESPONSE = {
    "apiVersion": "1.0",
    "jobs": [
        {
            "id": "ashby-1",
            "title": "Principal Product Designer",
            "department": "Design",
            "location": "Remote",
            "jobPostingUrl": "https://jobs.ashbyhq.com/acme/ashby-1",
        },
        {
            "id": "ashby-2",
            "title": "Director of Growth Marketing",
            "department": "Growth",
            "location": "San Francisco",
            "jobPostingUrl": "https://jobs.ashbyhq.com/acme/ashby-2",
        },
    ]
}


def test_classify_canonical_department():
    assert classify_canonical_department("R&D", "Staff AI Research Engineer") == "AI & Machine Learning"
    assert classify_canonical_department("Core", "Senior Infrastructure Engineer") == "Engineering"
    assert classify_canonical_department("GTM", "Enterprise Account Executive") == "Sales & GTM"
    assert classify_canonical_department("Product", "Senior Product Manager") == "Product & Design"
    assert classify_canonical_department("Marketing", "Content Specialist") == "Marketing"
    assert classify_canonical_department("People", "Technical Recruiter") == "Operations & G&A"


def test_fetch_greenhouse_jobs_mock():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = MOCK_GREENHOUSE_RESPONSE

    with patch("requests.get", return_value=mock_resp):
        jobs = fetch_greenhouse_jobs("acme")
        assert len(jobs) == 3
        assert jobs[0].is_ai_role is True
        assert jobs[0].is_leadership is True  # Staff
        assert jobs[0].canonical_dept == "AI & Machine Learning"
        assert jobs[1].is_leadership is True  # VP
        assert jobs[1].canonical_dept == "Sales & GTM"


def test_fetch_ashby_jobs_mock():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = MOCK_ASHBY_RESPONSE

    with patch("requests.get", return_value=mock_resp):
        jobs = fetch_ashby_jobs("acme")
        assert len(jobs) == 2
        assert jobs[0].canonical_dept == "Product & Design"
        assert jobs[1].is_leadership is True  # Director
        assert jobs[1].canonical_dept == "Marketing"


def test_analyze_hiring_data_report():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = MOCK_GREENHOUSE_RESPONSE

    with patch("requests.get", return_value=mock_resp):
        report = analyze_hiring_data("acme", provider="greenhouse")
        assert report.total_active_jobs == 3
        assert report.remote_percentage > 0
        assert len(report.leadership_roles) == 2
        assert len(report.ai_roles) == 1
        assert "AI" in report.strategic_signal or "leadership" in report.strategic_signal
