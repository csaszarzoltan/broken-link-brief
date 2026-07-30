"""SQLite-backed organizations, RBAC, service credentials and audit."""
from __future__ import annotations
import hashlib,secrets,sqlite3,uuid
from enum import Enum
from pathlib import Path

class Role(str,Enum): VIEWER="VIEWER"; OPERATOR="OPERATOR"; ADMIN="ADMIN"
_CAPS={Role.VIEWER:{"project:read"},Role.OPERATOR:{"project:read","scan:run","finding:update"},Role.ADMIN:{"project:read","scan:run","finding:update","member:write","key:write"}}
class GovernanceStore:
    def __init__(self,path:str|Path):
        self.path=str(path)
        with sqlite3.connect(self.path) as db:
            db.executescript("CREATE TABLE IF NOT EXISTS organizations(id TEXT PRIMARY KEY,name TEXT); CREATE TABLE IF NOT EXISTS memberships(org_id TEXT,user_id TEXT,role TEXT,PRIMARY KEY(org_id,user_id)); CREATE TABLE IF NOT EXISTS credentials(id TEXT PRIMARY KEY,org_id TEXT,digest TEXT,scopes TEXT,revoked INTEGER DEFAULT 0); CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,org_id TEXT,actor TEXT,action TEXT,outcome TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);")
    def create_organization(self,name:str)->str:
        if not name.strip(): raise ValueError("name required")
        oid=uuid.uuid4().hex
        with sqlite3.connect(self.path) as db: db.execute("INSERT INTO organizations VALUES (?,?)",(oid,name))
        return oid
    def add_member(self,org_id:str,user_id:str,role:Role)->None:
        with sqlite3.connect(self.path) as db: db.execute("INSERT OR REPLACE INTO memberships VALUES (?,?,?)",(org_id,user_id,role.value))
    def require(self,user_id:str,org_id:str,capability:str)->None:
        with sqlite3.connect(self.path) as db: row=db.execute("SELECT role FROM memberships WHERE org_id=? AND user_id=?",(org_id,user_id)).fetchone()
        if not row or capability not in _CAPS[Role(row[0])]: raise PermissionError("capability denied")
    def create_key(self,org_id:str,actor:str,scopes:set[str])->tuple[str,str]:
        self.require(actor,org_id,"key:write"); raw=secrets.token_urlsafe(32); kid=uuid.uuid4().hex; digest=hashlib.sha256(raw.encode()).hexdigest()
        with sqlite3.connect(self.path) as db: db.execute("INSERT INTO credentials(id,org_id,digest,scopes) VALUES (?,?,?,?)",(kid,org_id,digest,",".join(sorted(scopes))))
        return kid,raw
