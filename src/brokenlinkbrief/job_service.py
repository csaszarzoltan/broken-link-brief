"""Application service for durable project scan jobs."""
from __future__ import annotations

import threading
import time
from dataclasses import asdict

from .package import scan_page, validate_scan_url
from .projects import ProjectStore
from .scan_jobs import JobConflict, ScanJobStore
from .scan_policy import ScanPolicyStore


class JobService:
    """Owns the worker thread that claims and executes durable scan jobs."""

    def __init__(
        self,
        jobs: ScanJobStore | None = None,
        projects: ProjectStore | None = None,
        policies: ScanPolicyStore | None = None,
        scanner=scan_page,
    ) -> None:
        self.jobs = jobs or ScanJobStore()
        self.projects = projects or ProjectStore(self.jobs.path)
        self.policies = policies or ScanPolicyStore(self.jobs.path)
        self.scanner = scanner
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.heartbeat_interval = 5.0

    def create_project_job(
        self,
        project_id: str,
        idempotency_key: str | None = None,
        origin: str = "MANUAL",
    ) -> dict:
        """Create a job for every target of a project."""
        p = self.projects.get(project_id)
        if p.archived:
            raise ValueError("active project is required")
        problems = {u: validate_scan_url(u) for u in p.targets}
        problems = {k: v for k, v in problems.items() if v}
        if problems:
            raise ValueError(f"unsafe project targets: {problems}")
        policy = self.policies.get(project_id)
        job = self.jobs.create(
            p.id,
            p.name,
            list(p.targets),
            policy["version"],
            origin,
            idempotency_key=idempotency_key,
            policy_snapshot=policy,
        )
        self._wake.set()
        return job

    def _heartbeat_loop(
        self, job: dict, worker_id: str, stop: threading.Event
    ) -> None:
        """Heartbeat the job lease until told to stop."""
        while not stop.wait(self.heartbeat_interval):
            try:
                self.jobs.heartbeat(job["id"], worker_id)
            except Exception:
                break

    def run_once(self) -> dict | None:
        """Claim and execute one job; returns None when no job was available."""
        worker_id = f"worker-{id(self):x}"
        job = self.jobs.claim(worker_id)
        if not job:
            return None
        heartbeat_stop = threading.Event()
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(job, worker_id, heartbeat_stop),
            daemon=True,
            name="brokenlinkbrief-job-heartbeat",
        )
        heartbeat_thread.start()
        for source in self.jobs.sources(job["id"]):
            current = self.jobs.get(job["id"])
            if current["state"] == "CANCEL_REQUESTED":
                break
            self.jobs.start_source(source["id"], worker_id)
            try:
                if validate_scan_url(source["source_url"]):
                    raise ValueError("unsafe target")
                results = self.scanner(source["source_url"])
                payload = [
                    asdict(x) if hasattr(x, "__dataclass_fields__") else x
                    for x in results
                ]
                self.jobs.finish_source(source["id"], worker_id, True, payload)
            except Exception as exc:
                self.jobs.finish_source(
                    source["id"], worker_id, False, error=type(exc).__name__
                )
        heartbeat_stop.set()
        heartbeat_thread.join(1)
        current = self.jobs.get(job["id"])
        if current["state"] == "CANCEL_REQUESTED":
            with self.jobs._db() as db:
                ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                db.execute(
                    "UPDATE scan_job_sources SET state='CANCELLED',completed_at=? "
                    "WHERE job_id=? AND state='PENDING'",
                    (ts, job["id"]),
                )
                db.execute(
                    "UPDATE scan_jobs SET state='CANCELLED',completed_at=?,"
                    "updated_at=?,version=version+1 WHERE id=?",
                    (ts, ts, job["id"]),
                )
            return self.jobs.get(job["id"])
        return self.jobs.finalize(job["id"])

    def start(self) -> None:
        """Start the background worker loop."""
        if self._thread and self._thread.is_alive():
            return

        def loop() -> None:
            while not self._stop.is_set():
                if self.run_once() is None:
                    self._wake.wait(0.25)
                    self._wake.clear()

        self._thread = threading.Thread(
            target=loop, daemon=True, name="brokenlinkbrief-jobs"
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the background worker loop."""
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(2)

    def retry_preview(self, jid: str) -> dict:
        """Return which failed sources can be retried for a job."""
        parent = self.jobs.get(jid)
        if parent["state"] not in {"FAILED", "PARTIALLY_COMPLETED"}:
            raise JobConflict("job has no retryable terminal failures")
        project = self.projects.get(parent["project_id"])
        current = set(project.targets)
        eligible: list[str] = []
        excluded: list[dict] = []
        invalid: list[dict] = []
        for s in self.jobs.sources(jid, "FAILED"):
            u = s["source_url"]
            if u not in current:
                excluded.append({"source_url": u, "code": "NOT_IN_PROJECT"})
            elif validate_scan_url(u):
                invalid.append({"source_url": u, "code": "UNSAFE_TARGET"})
            else:
                eligible.append(u)
        return {"eligible": eligible, "excluded": excluded, "invalid": invalid}

    def retry_failures(self, jid: str, idempotency_key: str | None = None) -> dict:
        """Create a RETRY job for the eligible failed sources of a job."""
        preview = self.retry_preview(jid)
        if not preview["eligible"]:
            raise ValueError("no eligible failed sources")
        p = self.projects.get(self.jobs.get(jid)["project_id"])
        policy = self.policies.get(p.id)
        job = self.jobs.create(
            p.id,
            p.name,
            preview["eligible"],
            policy["version"],
            "RETRY",
            jid,
            idempotency_key,
        )
        self._wake.set()
        return job
