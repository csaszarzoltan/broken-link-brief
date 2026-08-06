"""Durable project findings, evidence, occurrences, verification, and audit."""
from __future__ import annotations
import hashlib, json, sqlite3, uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from brokenlinkbrief.projects import configured_project_db

STATES = {"OPEN", "ACKNOWLEDGED", "IGNORED", "RESOLVED"}
CLASSIFICATIONS = {"UNVERIFIED", "TRANSIENT", "BOT_BLOCKED", "RECOVERED", "INCONCLUSIVE", "CONFIRMED_BROKEN"}

def _now() -> str: return datetime.now(timezone.utc).isoformat()
class VersionConflict(ValueError): pass

class FindingStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = str(path or configured_project_db()); self._migrate()
    def _db(self):
        db=sqlite3.connect(self.path, timeout=10); db.row_factory=sqlite3.Row; db.execute("PRAGMA foreign_keys=ON"); return db
    def _migrate(self):
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
            CREATE TABLE IF NOT EXISTS project_findings(id TEXT PRIMARY KEY, project_id TEXT NOT NULL, target_url TEXT NOT NULL, latest_status INTEGER, classification TEXT NOT NULL, reason TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'OPEN', assignee TEXT, ignore_reason TEXT, ignore_expiry TEXT, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, resolved_at TEXT, latest_verification_at TEXT, latest_verification_outcome TEXT, version INTEGER NOT NULL DEFAULT 1, UNIQUE(project_id,target_url));
            CREATE TABLE IF NOT EXISTS finding_occurrences(id TEXT PRIMARY KEY, finding_id TEXT NOT NULL, source_url TEXT NOT NULL, anchor_text TEXT NOT NULL, context TEXT NOT NULL, fingerprint TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, UNIQUE(finding_id,source_url,fingerprint), FOREIGN KEY(finding_id) REFERENCES project_findings(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS finding_evidence(id TEXT PRIMARY KEY, finding_id TEXT NOT NULL, observed_at TEXT NOT NULL, method TEXT NOT NULL, status INTEGER, error TEXT, latency_seconds REAL NOT NULL, sequence INTEGER NOT NULL, classification TEXT NOT NULL, reason TEXT NOT NULL, FOREIGN KEY(finding_id) REFERENCES project_findings(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS finding_verifications(id TEXT PRIMARY KEY, finding_id TEXT NOT NULL, completed_at TEXT NOT NULL, outcome TEXT NOT NULL, source_checked INTEGER NOT NULL, source_present INTEGER NOT NULL, failures_json TEXT NOT NULL, FOREIGN KEY(finding_id) REFERENCES project_findings(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS finding_audit_events(id TEXT PRIMARY KEY, finding_id TEXT NOT NULL, event_type TEXT NOT NULL, created_at TEXT NOT NULL, old_state TEXT, new_state TEXT, metadata_json TEXT NOT NULL, FOREIGN KEY(finding_id) REFERENCES project_findings(id) ON DELETE CASCADE);
            CREATE INDEX IF NOT EXISTS idx_pf_project_state ON project_findings(project_id,state,last_seen_at); CREATE INDEX IF NOT EXISTS idx_fo_finding ON finding_occurrences(finding_id,active); CREATE INDEX IF NOT EXISTS idx_fe_finding ON finding_evidence(finding_id,observed_at); CREATE INDEX IF NOT EXISTS idx_fa_finding ON finding_audit_events(finding_id,created_at);
            """)
    def ensure_project(self, project_id: str, name: str="Project"):
        """Test/embedding helper; production projects are created by ProjectStore."""
        now=_now()
        with self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,archived INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,pinned INTEGER NOT NULL DEFAULT 0)")
            db.execute("INSERT OR IGNORE INTO projects VALUES(?,?,?,?,?,?)",(project_id,name,0,now,now,0))
    def _row(self, db, fid):
        row=db.execute("SELECT * FROM project_findings WHERE id=?",(fid,)).fetchone()
        if not row: raise KeyError(fid)
        return row
    def _audit(self, db, fid, event, old, new, metadata=None):
        db.execute("INSERT INTO finding_audit_events VALUES(?,?,?,?,?,?,?)",(uuid.uuid4().hex,fid,event,_now(),old,new,json.dumps(metadata or {},sort_keys=True)))
    def upsert(self, project_id, occurrence, assessment, attempts):
        now=_now(); target=occurrence.target_url
        with self._db() as db:
            row=db.execute("SELECT * FROM project_findings WHERE project_id=? AND target_url=?",(project_id,target)).fetchone()
            if not row:
                if assessment.classification != "CONFIRMED_BROKEN": return None
                fid=uuid.uuid4().hex
                db.execute("INSERT INTO project_findings(id,project_id,target_url,latest_status,classification,reason,state,first_seen_at,last_seen_at,version) VALUES(?,?,?,?,?,?,'OPEN',?,?,1)",(fid,project_id,target,attempts[-1].status,assessment.classification,assessment.reason,now,now))
                self._audit(db,fid,"CREATED",None,"OPEN")
            else:
                fid=row['id']; state=row['state']; new_state="OPEN" if assessment.classification=="CONFIRMED_BROKEN" and state=="RESOLVED" else state
                db.execute("UPDATE project_findings SET latest_status=?,classification=?,reason=?,state=?,last_seen_at=?,version=version+1 WHERE id=?",(attempts[-1].status,assessment.classification,assessment.reason,new_state,now,fid))
                if new_state != state: self._audit(db,fid,"AUTO_REOPENED",state,new_state)
            context=occurrence.context[:500]; anchor=occurrence.anchor_text[:500]
            fp=hashlib.sha256((anchor+'\0'+context).encode()).hexdigest()
            db.execute("INSERT INTO finding_occurrences VALUES(?,?,?,?,?,?,1,?,?) ON CONFLICT(finding_id,source_url,fingerprint) DO UPDATE SET active=1,last_seen_at=excluded.last_seen_at",(uuid.uuid4().hex,fid,occurrence.source_url,anchor,context,fp,now,now))
            for i,a in enumerate(attempts):
                error=(a.error or '')[:200] or None
                db.execute("INSERT INTO finding_evidence VALUES(?,?,?,?,?,?,?,?,?,?)",(uuid.uuid4().hex,fid,now,a.method,a.status,error,a.latency_seconds,i,assessment.classification,assessment.reason))
        return self.get(fid)
    def get(self,fid):
        with self._db() as db: return dict(self._row(db,fid))
    def detail(self,fid):
        with self._db() as db:
            item=dict(self._row(db,fid))
            item['occurrences']=[dict(r) for r in db.execute("SELECT * FROM finding_occurrences WHERE finding_id=? ORDER BY source_url",(fid,))]
            item['evidence']=[dict(r) for r in db.execute("SELECT * FROM finding_evidence WHERE finding_id=? ORDER BY observed_at DESC,sequence",(fid,))]
            item['verifications']=[dict(r) for r in db.execute("SELECT * FROM finding_verifications WHERE finding_id=? ORDER BY completed_at DESC",(fid,))]
            item['audit']=[dict(r) for r in db.execute("SELECT * FROM finding_audit_events WHERE finding_id=? ORDER BY created_at DESC",(fid,))]
            return item
    def list(self,project_id,state=None,classification=None,q='',limit=50,offset=0):
        limit=max(1,min(100,int(limit))); offset=max(0,int(offset)); where=['project_id=?']; args=[project_id]
        if state: where.append('state=?'); args.append(state)
        else: where.append("state IN ('OPEN','ACKNOWLEDGED')")
        if classification: where.append('classification=?'); args.append(classification)
        if q: where.append('(target_url LIKE ? OR COALESCE(assignee,\'\') LIKE ?)'); args += [f'%{q}%',f'%{q}%']
        sql=' AND '.join(where)
        with self._db() as db:
            total=db.execute('SELECT count(*) FROM project_findings WHERE '+sql,args).fetchone()[0]
            rows=db.execute('SELECT * FROM project_findings WHERE '+sql+' ORDER BY last_seen_at DESC,id LIMIT ? OFFSET ?',args+[limit,offset]).fetchall()
        return {'items':[dict(r) for r in rows],'total':total,'limit':limit,'offset':offset}
    def _transition(self,fid,version,state,event,**fields):
        if state not in STATES: raise ValueError('invalid state')
        with self._db() as db:
            row=self._row(db,fid)
            if row['version'] != version: raise VersionConflict('FINDING_VERSION_CONFLICT')
            values={'state':state,'version':version+1,**fields}; sets=','.join(f'{k}=?' for k in values)
            db.execute(f'UPDATE project_findings SET {sets} WHERE id=?',list(values.values())+[fid]); self._audit(db,fid,event,row['state'],state,fields)
        return self.get(fid)
    def acknowledge(self,fid,version): return self._transition(fid,version,'ACKNOWLEDGED','ACKNOWLEDGED')
    def assign(self,fid,version,assignee):
        value=(assignee or '').strip() or None
        if value and len(value)>120: raise ValueError('assignee must be at most 120 characters')
        row=self.get(fid); return self._transition(fid,version,row['state'],'ASSIGNED',assignee=value)
    def ignore(self,fid,version,reason,expiry):
        reason=reason.strip()
        if not reason or len(reason)>500: raise ValueError('ignore reason must be 1 to 500 characters')
        if expiry: date.fromisoformat(expiry)
        return self._transition(fid,version,'IGNORED','IGNORED',ignore_reason=reason,ignore_expiry=expiry)
    def reopen(self,fid,version): return self._transition(fid,version,'OPEN','REOPENED',ignore_reason=None,ignore_expiry=None,resolved_at=None)
    def record_verification(self,fid,version,outcome,checked,present,failures):
        resolved=outcome in {'RECOVERED','REMOVED_FROM_SOURCE'}; now=_now(); state='RESOLVED' if resolved else self.get(fid)['state']
        with self._db() as db:
            row=self._row(db,fid)
            if row['version']!=version: raise VersionConflict('FINDING_VERSION_CONFLICT')
            db.execute("INSERT INTO finding_verifications VALUES(?,?,?,?,?,?,?)",(uuid.uuid4().hex,fid,now,outcome,checked,present,json.dumps(failures)))
            db.execute("UPDATE project_findings SET state=?,resolved_at=?,latest_verification_at=?,latest_verification_outcome=?,version=version+1 WHERE id=?",(state,now if resolved else row['resolved_at'],now,outcome,fid))
            self._audit(db,fid,'VERIFIED',row['state'],state,{'outcome':outcome})
        return self.get(fid)
