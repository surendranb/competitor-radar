"""Zero-Auth ATS Hiring Radar for Greenhouse and Ashby.

Traverses public applicant tracking system endpoints, normalizes job postings,
and calculates departmental velocity and strategic expansion signals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import requests


@dataclass
class NormalizedJob:
    """Standardized job posting representation."""
    external_id: str
    title: str
    department: str
    canonical_dept: str
    location: str
    is_leadership: bool
    is_ai_role: bool
    url: Optional[str] = None


@dataclass
class HiringRadarReport:
    """Synthesized hiring report."""
    provider: str
    slug: str
    total_active_jobs: int
    department_counts: Dict[str, int]
    canonical_breakdown: Dict[str, int]
    leadership_roles: List[str]
    ai_roles: List[str]
    locations: Dict[str, int]
    remote_percentage: float
    strategic_signal: str
    jobs: List[NormalizedJob]


LEADERSHIP_REGEX = re.compile(
    r"\b(vp|vice president|director|head of|chief|lead|principal|staff|executive)\b",
    re.I,
)

AI_ROLE_REGEX = re.compile(
    r"\b(ai\b|machine learning|ml\b|llm|deep learning|data scientist|research scientist|generative|agentic)\b",
    re.I,
)


def classify_canonical_department(dept_raw: str, title: str) -> str:
    """Map company-specific department strings to canonical strategic clusters."""
    text = f"{dept_raw} {title}".lower()

    if AI_ROLE_REGEX.search(text) and "sales" not in text and "marketing" not in text:
        return "AI & Machine Learning"
    if any(k in text for k in ("software", "engineer", "frontend", "backend", "platform", "infra", "devops", "sre", "security", "qa")):
        return "Engineering"
    if any(k in text for k in ("product", "design", "user experience")) or re.search(r"\b(ui|ux)\b", text):
        return "Product & Design"
    if any(k in text for k in ("sales", "account executive", "sdr", "bdr", "business development", "solutions architect", "customer success", "gtm")):
        return "Sales & GTM"
    if any(k in text for k in ("marketing", "growth", "demand gen", "brand", "content", "devrel", "developer relations")):
        return "Marketing"
    if any(k in text for k in ("finance", "legal", "people", "talent", "recruiting", "hr", "operations", "g&a", "accounting")):
        return "Operations & G&A"
    return "General & Other"


def fetch_greenhouse_jobs(slug: str, timeout: float = 10.0) -> List[NormalizedJob]:
    """Fetch and normalize jobs from Greenhouse boards API."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    headers = {
        "User-Agent": "CompetitorRadar/1.0 (+https://github.com/surendranb/competitor-radar; bot)",
        "Accept": "application/json",
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    raw_jobs = data.get("jobs", [])
    normalized: List[NormalizedJob] = []

    for item in raw_jobs:
        ext_id = str(item.get("id"))
        title = item.get("title", "Untitled Role").strip()

        depts = item.get("departments", [])
        dept_name = depts[0].get("name", "General") if depts else "General"

        loc_obj = item.get("location")
        loc_name = loc_obj.get("name", "Unknown") if isinstance(loc_obj, dict) else (loc_obj or "Unknown")

        canonical = classify_canonical_department(dept_name, title)
        is_lead = bool(LEADERSHIP_REGEX.search(title))
        is_ai = bool(AI_ROLE_REGEX.search(title))

        normalized.append(
            NormalizedJob(
                external_id=ext_id,
                title=title,
                department=dept_name,
                canonical_dept=canonical,
                location=str(loc_name),
                is_leadership=is_lead,
                is_ai_role=is_ai,
                url=item.get("absolute_url"),
            )
        )

    return normalized


def fetch_ashby_jobs(slug: str, timeout: float = 10.0) -> List[NormalizedJob]:
    """Fetch and normalize jobs from Ashby posting API."""
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    headers = {
        "User-Agent": "CompetitorRadar/1.0 (+https://github.com/surendranb/competitor-radar; bot)",
        "Accept": "application/json",
    }
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    raw_jobs = data.get("jobs") or data.get("jobPostings") or []
    if not raw_jobs and isinstance(data.get("jobBoard"), dict):
        raw_jobs = data["jobBoard"].get("jobPostings") or data["jobBoard"].get("jobs") or []

    normalized: List[NormalizedJob] = []

    for item in raw_jobs:
        ext_id = str(item.get("id"))
        title = item.get("title", "Untitled Role").strip()
        dept_name = item.get("department") or item.get("departmentName") or "General"
        loc_name = item.get("location") or item.get("locationName") or "Remote"

        canonical = classify_canonical_department(str(dept_name), title)
        is_lead = bool(LEADERSHIP_REGEX.search(title))
        is_ai = bool(AI_ROLE_REGEX.search(title))

        normalized.append(
            NormalizedJob(
                external_id=ext_id,
                title=title,
                department=str(dept_name),
                canonical_dept=canonical,
                location=str(loc_name),
                is_leadership=is_lead,
                is_ai_role=is_ai,
                url=item.get("applyUrl") or item.get("jobPostingUrl"),
            )
        )

    return normalized


def analyze_hiring_data(slug: str, provider: str = "greenhouse") -> HiringRadarReport:
    """Fetch live hiring data from specified ATS provider and build analytical dossier."""
    prov_clean = provider.strip().lower()
    if prov_clean in ("greenhouse", "gh"):
        jobs = fetch_greenhouse_jobs(slug)
        provider_name = "greenhouse"
    elif prov_clean in ("ashby", "ashbyhq"):
        jobs = fetch_ashby_jobs(slug)
        provider_name = "ashby"
    else:
        raise ValueError(f"Unsupported ATS provider '{provider}'. Supported: 'greenhouse', 'ashby'")

    dept_counts: Dict[str, int] = {}
    canonical_counts: Dict[str, int] = {}
    locations: Dict[str, int] = {}
    leadership_roles: List[str] = []
    ai_roles: List[str] = []
    remote_count = 0

    for job in jobs:
        dept_counts[job.department] = dept_counts.get(job.department, 0) + 1
        canonical_counts[job.canonical_dept] = canonical_counts.get(job.canonical_dept, 0) + 1

        loc_clean = job.location.strip()
        locations[loc_clean] = locations.get(loc_clean, 0) + 1
        if "remote" in loc_clean.lower() or "distributed" in loc_clean.lower():
            remote_count += 1

        if job.is_leadership:
            leadership_roles.append(f"{job.title} ({job.department})")
        if job.is_ai_role:
            ai_roles.append(f"{job.title} ({job.department})")

    total = len(jobs)
    remote_pct = round((remote_count / total * 100.0), 1) if total > 0 else 0.0

    # Derive strategic hiring signal
    signal_parts = []
    if total == 0:
        signal = "Hiring freeze or zero open postings published."
    else:
        top_dept = max(canonical_counts.items(), key=lambda x: x[1])[0] if canonical_counts else "General"
        top_dept_pct = round((canonical_counts[top_dept] / total * 100.0), 0) if total else 0
        signal_parts.append(f"Heavy focus on {top_dept} ({int(top_dept_pct)}% of open requisitions).")

        if len(leadership_roles) > 0:
            signal_parts.append(f"Active leadership expansion ({len(leadership_roles)} director/VP roles).")

        if len(ai_roles) > 0:
            signal_parts.append(f"Aggressive AI talent acquisition ({len(ai_roles)} dedicated AI/ML openings).")

        signal = " ".join(signal_parts)

    return HiringRadarReport(
        provider=provider_name,
        slug=slug,
        total_active_jobs=total,
        department_counts=dept_counts,
        canonical_breakdown=canonical_counts,
        leadership_roles=leadership_roles,
        ai_roles=ai_roles,
        locations=locations,
        remote_percentage=remote_pct,
        strategic_signal=signal,
        jobs=jobs,
    )
