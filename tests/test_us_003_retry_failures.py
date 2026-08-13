from brokenlinkbrief.job_service import JobService
from brokenlinkbrief.projects import ProjectStore
from brokenlinkbrief.scan_jobs import ScanJobStore
from brokenlinkbrief.scan_policy import ScanPolicyStore


def test_us_003_retry_contains_only_failed_sources(tmp_path):
    db = tmp_path / "x.db"
    ps = ProjectStore(db)
    p = ps.create("P", ["https://example.com/a", "https://example.com/b"])
    js = ScanJobStore(db)
    svc = JobService(
        js,
        ps,
        ScanPolicyStore(db),
        lambda u: (_ for _ in ()).throw(RuntimeError()) if u.endswith("/b") else [],
    )
    parent = svc.create_project_job(p.id)
    svc.run_once()
    child = svc.retry_failures(parent["id"])
    assert [x["source_url"] for x in js.sources(child["id"])] == [
        "https://example.com/b"
    ]


def test_us_003_removed_source_is_excluded(tmp_path):
    db = tmp_path / "x.db"
    ps = ProjectStore(db)
    p = ps.create("P", ["https://example.com/a", "https://example.com/b"])
    js = ScanJobStore(db)
    svc = JobService(
        js, ps, ScanPolicyStore(db), lambda u: (_ for _ in ()).throw(RuntimeError())
    )
    parent = svc.create_project_job(p.id)
    svc.run_once()
    ps.update(p.id, "P", ["https://example.com/a"])
    preview = svc.retry_preview(parent["id"])
    assert preview["excluded"] == [
        {"source_url": "https://example.com/b", "code": "NOT_IN_PROJECT"}
    ]
