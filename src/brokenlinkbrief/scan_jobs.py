"""Durable SQLite scan-job state and leasing."""
from __future__ import annotations
import hashlib,json,sqlite3,uuid
from datetime import datetime,timezone
from pathlib import Path
from .projects import configured_project_db
TERMINAL={"PARTIALLY_COMPLETED","COMPLETED","FAILED","CANCELLED"}
def now(): return datetime.now(timezone.utc).isoformat()
class JobConflict(ValueError): pass
class ScanJobStore:
 def __init__(self,path:str|Path|None=None): self.path=str(path or configured_project_db()); self._migrate()
 def _db(self):
  db=sqlite3.connect(self.path,timeout=10); db.row_factory=sqlite3.Row; db.execute("PRAGMA foreign_keys=ON"); return db
 def _migrate(self):
  with self._db() as db:
   db.execute("PRAGMA journal_mode=WAL")
   db.execute("CREATE TABLE IF NOT EXISTS scan_jobs (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, project_name TEXT NOT NULL, origin TEXT NOT NULL, state TEXT NOT NULL, parent_job_id TEXT, policy_version INTEGER NOT NULL, created_at TEXT NOT NULL, started_at TEXT, completed_at TEXT, updated_at TEXT NOT NULL, cancel_requested_at TEXT, version INTEGER NOT NULL DEFAULT 1, error TEXT)")
   db.execute("CREATE TABLE IF NOT EXISTS scan_job_sources (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, ordinal INTEGER NOT NULL, source_url TEXT NOT NULL, state TEXT NOT NULL, started_at TEXT, completed_at TEXT, result_json TEXT, error TEXT, attempts_count INTEGER NOT NULL DEFAULT 0, UNIQUE(job_id,source_url), FOREIGN KEY(job_id) REFERENCES scan_jobs(id) ON DELETE CASCADE)")
   db.execute("CREATE TABLE IF NOT EXISTS scan_job_idempotency (scope TEXT NOT NULL, key_hash TEXT NOT NULL, request_hash TEXT NOT NULL, job_id TEXT NOT NULL, PRIMARY KEY(scope,key_hash))")
 def create(self,project_id,name,targets,policy_version=0,origin="MANUAL",parent_job_id=None,idempotency_key=None,scope="default"):
  req=hashlib.sha256(json.dumps([project_id,targets,origin,parent_job_id],sort_keys=True).encode()).hexdigest(); kh=hashlib.sha256((idempotency_key or uuid.uuid4().hex).encode()).hexdigest()
  with self._db() as db:
   if idempotency_key:
    old=db.execute("SELECT * FROM scan_job_idempotency WHERE scope=? AND key_hash=?",(scope,kh)).fetchone()
    if old:
     if old["request_hash"]!=req: raise JobConflict("idempotency key reused for different request")
     return self.get(old["job_id"])
   jid=uuid.uuid4().hex; ts=now(); db.execute("INSERT INTO scan_jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(jid,project_id,name,origin,"QUEUED",parent_job_id,policy_version,ts,None,None,ts,None,1,None))
   db.executemany("INSERT INTO scan_job_sources(id,job_id,ordinal,source_url,state) VALUES (?,?,?,?,?)",[(uuid.uuid4().hex,jid,i,u,"PENDING") for i,u in enumerate(targets)])
   if idempotency_key: db.execute("INSERT INTO scan_job_idempotency VALUES (?,?,?,?)",(scope,kh,req,jid))
  return self.get(jid)
 def get(self,jid):
  with self._db() as db:
   row=db.execute("SELECT * FROM scan_jobs WHERE id=?",(jid,)).fetchone()
   if not row: raise KeyError(jid)
   counts={r["state"]:r["n"] for r in db.execute("SELECT state,count(*) n FROM scan_job_sources WHERE job_id=? GROUP BY state",(jid,))}
  d=dict(row); d.update({f"{s.lower()}_count":counts.get(s,0) for s in ["PENDING","RUNNING","COMPLETED","FAILED","CANCELLED"]}); d["target_count"]=sum(counts.values()); return d
 def sources(self,jid,state=None):
  with self._db() as db:
   sql="SELECT * FROM scan_job_sources WHERE job_id=?"; args=[jid]
   if state: sql+=" AND state=?"; args.append(state)
   sql+=" ORDER BY ordinal"; return [dict(r) for r in db.execute(sql,args)]
 def list(self,project_id=None):
  with self._db() as db:
   rows=db.execute("SELECT id FROM scan_jobs"+(" WHERE project_id=?" if project_id else "")+" ORDER BY created_at DESC",((project_id,) if project_id else ())).fetchall()
  return [self.get(r["id"]) for r in rows]
 def claim(self):
  with self._db() as db:
   db.execute("BEGIN IMMEDIATE"); r=db.execute("SELECT id FROM scan_jobs WHERE state='QUEUED' ORDER BY created_at LIMIT 1").fetchone()
   if not r:return None
   ts=now(); db.execute("UPDATE scan_jobs SET state='RUNNING',started_at=COALESCE(started_at,?),updated_at=?,version=version+1 WHERE id=?",(ts,ts,r["id"])); return self.get(r["id"])
 def start_source(self,sid):
  with self._db() as db: db.execute("UPDATE scan_job_sources SET state='RUNNING',started_at=? WHERE id=? AND state='PENDING'",(now(),sid))
 def finish_source(self,sid,ok,result=None,error=None,attempts=0):
  with self._db() as db: db.execute("UPDATE scan_job_sources SET state=?,completed_at=?,result_json=?,error=?,attempts_count=? WHERE id=?",("COMPLETED" if ok else "FAILED",now(),json.dumps(result) if result is not None else None,error,attempts,sid))
 def finalize(self,jid):
  src=self.sources(jid); failed=sum(x["state"]=="FAILED" for x in src); done=sum(x["state"]=="COMPLETED" for x in src); state="COMPLETED" if done==len(src) else "FAILED" if failed==len(src) else "PARTIALLY_COMPLETED"
  with self._db() as db: db.execute("UPDATE scan_jobs SET state=?,completed_at=?,updated_at=?,version=version+1 WHERE id=?",(state,now(),now(),jid))
  return self.get(jid)
 def cancel(self,jid,version):
  job=self.get(jid)
  if job["version"]!=version: raise JobConflict("job version conflict")
  if job["state"] in TERMINAL: raise JobConflict("terminal job cannot be cancelled")
  ts=now()
  with self._db() as db:
   db.execute("UPDATE scan_jobs SET state='CANCEL_REQUESTED',cancel_requested_at=?,updated_at=?,version=version+1 WHERE id=?",(ts,ts,jid))
   if job["state"]=="QUEUED":
    db.execute("UPDATE scan_job_sources SET state='CANCELLED',completed_at=? WHERE job_id=? AND state='PENDING'",(ts,jid)); db.execute("UPDATE scan_jobs SET state='CANCELLED',completed_at=?,version=version+1 WHERE id=?",(ts,jid))
  return self.get(jid)
