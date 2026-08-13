import threading
import time

from brokenlinkbrief.job_service import JobService
from brokenlinkbrief.projects import ProjectStore
from brokenlinkbrief.scan_jobs import ScanJobStore
from brokenlinkbrief.scan_policy import ScanPolicyStore


def test_us_001_coordinator_heartbeats_while_scanner_blocks(tmp_path):
    db = tmp_path / "x.db"
    ps = ProjectStore(db)
    p = ps.create("P", ["https://example.com/"])
    jobs = ScanJobStore(db)
    entered = threading.Event()
    release = threading.Event()

    def scanner(url):
        entered.set()
        release.wait(2)
        return []

    svc = JobService(jobs, ps, ScanPolicyStore(db), scanner)
    svc.heartbeat_interval = 0.05
    job = svc.create_project_job(p.id)
    thread = threading.Thread(target=svc.run_once)
    thread.start()
    assert entered.wait(1)
    first = jobs.get(job["id"])["heartbeat_at"]
    time.sleep(0.15)
    second = jobs.get(job["id"])["heartbeat_at"]
    release.set()
    thread.join(2)
    assert second > first
