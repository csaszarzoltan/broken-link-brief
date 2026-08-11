"""Application service for durable project scan jobs."""
from __future__ import annotations
import threading,time
from dataclasses import asdict
from .package import scan_page,validate_scan_url
from .projects import ProjectStore
from .scan_jobs import JobConflict,ScanJobStore
from .scan_policy import ScanPolicyStore
class JobService:
 def __init__(self,jobs=None,projects=None,policies=None,scanner=scan_page):
  self.jobs=jobs or ScanJobStore(); self.projects=projects or ProjectStore(self.jobs.path); self.policies=policies or ScanPolicyStore(self.jobs.path); self.scanner=scanner; self._wake=threading.Event(); self._stop=threading.Event(); self._thread=None
 def create_project_job(self,project_id,idempotency_key=None,origin="MANUAL"):
  p=self.projects.get(project_id)
  if p.archived: raise ValueError("active project is required")
  problems={u:validate_scan_url(u) for u in p.targets}; problems={k:v for k,v in problems.items() if v}
  if problems: raise ValueError(f"unsafe project targets: {problems}")
  policy=self.policies.get(project_id)
  job=self.jobs.create(p.id,p.name,list(p.targets),policy["version"],origin,idempotency_key=idempotency_key)
  self._wake.set(); return job
 def run_once(self):
  job=self.jobs.claim()
  if not job:return None
  for source in self.jobs.sources(job["id"]):
   current=self.jobs.get(job["id"])
   if current["state"]=="CANCEL_REQUESTED": break
   self.jobs.start_source(source["id"])
   try:
    if validate_scan_url(source["source_url"]): raise ValueError("unsafe target")
    results=self.scanner(source["source_url"])
    self.jobs.finish_source(source["id"],True,[asdict(x) if hasattr(x,"__dataclass_fields__") else x for x in results])
   except Exception as exc:
    self.jobs.finish_source(source["id"],False,error=type(exc).__name__)
  current=self.jobs.get(job["id"])
  if current["state"]=="CANCEL_REQUESTED":
   with self.jobs._db() as db:
    ts=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()); db.execute("UPDATE scan_job_sources SET state='CANCELLED',completed_at=? WHERE job_id=? AND state='PENDING'",(ts,job["id"])); db.execute("UPDATE scan_jobs SET state='CANCELLED',completed_at=?,updated_at=?,version=version+1 WHERE id=?",(ts,ts,job["id"]))
   return self.jobs.get(job["id"])
  return self.jobs.finalize(job["id"])
 def start(self):
  if self._thread and self._thread.is_alive(): return
  def loop():
   while not self._stop.is_set():
    if self.run_once() is None:self._wake.wait(.25);self._wake.clear()
  self._thread=threading.Thread(target=loop,daemon=True,name="brokenlinkbrief-jobs");self._thread.start()
 def stop(self): self._stop.set();self._wake.set(); self._thread and self._thread.join(2)
 def retry_preview(self,jid):
  parent=self.jobs.get(jid)
  if parent["state"] not in {"FAILED","PARTIALLY_COMPLETED"}: raise JobConflict("job has no retryable terminal failures")
  project=self.projects.get(parent["project_id"]); current=set(project.targets); eligible=[];excluded=[];invalid=[]
  for s in self.jobs.sources(jid,"FAILED"):
   u=s["source_url"]
   if u not in current: excluded.append({"source_url":u,"code":"NOT_IN_PROJECT"})
   elif validate_scan_url(u): invalid.append({"source_url":u,"code":"UNSAFE_TARGET"})
   else: eligible.append(u)
  return {"eligible":eligible,"excluded":excluded,"invalid":invalid}
 def retry_failures(self,jid,idempotency_key=None):
  preview=self.retry_preview(jid)
  if not preview["eligible"]: raise ValueError("no eligible failed sources")
  p=self.projects.get(self.jobs.get(jid)["project_id"]); policy=self.policies.get(p.id)
  job=self.jobs.create(p.id,p.name,preview["eligible"],policy["version"],"RETRY",jid,idempotency_key)
  self._wake.set();return job
