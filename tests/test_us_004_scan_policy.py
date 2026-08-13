import pytest

from brokenlinkbrief.projects import ProjectStore
from brokenlinkbrief.scan_policy import ScanPolicyStore


def test_us_004_exact_host_override_wins(tmp_path):
    db = tmp_path / "x.db"
    p = ProjectStore(db).create("P", ["https://example.com/"])
    s = ScanPolicyStore(db)
    d = s.get(p.id)
    saved = s.save(
        p.id,
        0,
        d["defaults"],
        [
            {
                "hostname": "api.example.com",
                "overrides": {"max_concurrency": 2, "max_attempts": 3},
            }
        ],
    )
    e = s.resolve(p.id, "https://api.example.com/x")
    assert (
        saved["version"] == 1
        and e.rule == "HOST_OVERRIDE"
        and e.policy.max_concurrency == 2
        and e.policy.max_attempts == 3
    )


def test_us_004_invalid_attempts_create_no_version(tmp_path):
    db = tmp_path / "x.db"
    p = ProjectStore(db).create("P", ["https://example.com/"])
    s = ScanPolicyStore(db)
    d = s.get(p.id)
    d["defaults"]["max_attempts"] = 4
    with pytest.raises(ValueError):
        s.save(p.id, 0, d["defaults"], [])
    assert s.get(p.id)["version"] == 0
