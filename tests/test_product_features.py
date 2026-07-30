from __future__ import annotations

import json
from pathlib import Path

import pytest

from brokenlinkbrief.ci_gate import CiPolicy, evaluate_ci
from brokenlinkbrief.confidence import ProbeAttempt, classify_evidence
from brokenlinkbrief.governance import GovernanceStore, Role
from brokenlinkbrief.policy import CrawlPolicy, PolicyViolation, validate_target
from brokenlinkbrief.scheduler import ScheduleStore
from brokenlinkbrief.triage import FindingStore, extract_occurrences


def test_due_schedule_survives_reopen_and_is_claimed_once(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    first = ScheduleStore(db)
    schedule = first.create("project-a", "*/5 * * * *", "UTC", next_due_at=10)
    second = ScheduleStore(db)
    claimed = second.claim_due(now=10, worker_id="worker-1")
    assert [item.id for item in claimed] == [schedule.id]
    assert second.claim_due(now=10, worker_id="worker-2") == []


def test_occurrence_preserves_source_anchor_and_context(tmp_path: Path) -> None:
    html = '<p>Read <a href="/missing">the manual</a> today.</p>'
    occurrences = extract_occurrences("https://example.test/docs", html)
    assert occurrences[0].target_url == "https://example.test/missing"
    assert occurrences[0].anchor_text == "the manual"
    store = FindingStore(tmp_path / "findings.db")
    finding = store.record(occurrences[0], status=404)
    task = store.assign(finding.id, "alice")
    assert task.assignee == "alice" and task.state == "ASSIGNED"


def test_403_then_success_is_bot_blocked_not_broken() -> None:
    result = classify_evidence([
        ProbeAttempt("HEAD", 403, None, 0.1),
        ProbeAttempt("GET_BROWSER", 200, None, 0.2),
    ])
    assert result.classification == "BOT_BLOCKED"


def test_redirect_to_private_address_is_blocked() -> None:
    policy = CrawlPolicy()
    with pytest.raises(PolicyViolation, match="private"):
        validate_target("http://169.254.169.254/latest", policy)


def test_operator_cannot_read_other_organization(tmp_path: Path) -> None:
    store = GovernanceStore(tmp_path / "governance.db")
    org_a = store.create_organization("A")
    org_b = store.create_organization("B")
    store.add_member(org_a, "alice", Role.OPERATOR)
    with pytest.raises(PermissionError):
        store.require("alice", org_b, "project:read")


def test_ci_fails_only_for_new_confirmed_findings(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"schema": 1, "confirmed": ["https://a/old"]}))
    result = evaluate_ci(
        [
            {"url": "https://a/old", "classification": "CONFIRMED_BROKEN"},
            {"url": "https://a/transient", "classification": "TRANSIENT"},
            {"url": "https://a/new", "classification": "CONFIRMED_BROKEN"},
        ],
        baseline,
        CiPolicy(max_new=0),
    )
    assert result.outcome == "FAIL"
    assert result.new_confirmed == ("https://a/new",)
    assert result.exit_code == 2


def test_invalid_timezone_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(Exception):
        ScheduleStore(tmp_path / "s.db").create("p", "daily", "Not/AZone", next_due_at=1)


def test_duplicate_assignment_is_rejected(tmp_path: Path) -> None:
    store = FindingStore(tmp_path / "f.db")
    finding = store.record(extract_occurrences("https://e.test", '<a href="/x">x</a>')[0], 404)
    store.assign(finding.id, "alice")
    with pytest.raises(ValueError, match="TRIAGE_ASSIGNMENT_CONFLICT"):
        store.assign(finding.id, "bob")


def test_repeated_terminal_status_is_confirmed() -> None:
    assessment = classify_evidence([
        ProbeAttempt("HEAD", 404, None, 0.1),
        ProbeAttempt("GET", 404, None, 0.2),
    ])
    assert assessment.classification == "CONFIRMED_BROKEN"


def test_policy_blocks_disallowed_port() -> None:
    with pytest.raises(PolicyViolation, match="port"):
        validate_target("https://example.test:8443", CrawlPolicy())


def test_viewer_cannot_create_service_key(tmp_path: Path) -> None:
    store = GovernanceStore(tmp_path / "g.db")
    org = store.create_organization("Org")
    store.add_member(org, "viewer", Role.VIEWER)
    with pytest.raises(PermissionError):
        store.create_key(org, "viewer", {"project:read"})


def test_bad_baseline_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    path.write_text('{"schema": 99, "confirmed": []}')
    with pytest.raises(ValueError, match="CI_BASELINE_SCHEMA_UNSUPPORTED"):
        evaluate_ci([], path)
