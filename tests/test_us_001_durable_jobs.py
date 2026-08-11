import time
from brokenlinkbrief.job_service import JobService
from brokenlinkbrief.projects import ProjectStore
from brokenlinkbrief.scan_jobs import ScanJobStore
from brokenlinkbrief.scan_policy import ScanPolicyStore

def setup(tmp_path,scanner=lambda u:[]):
 p=ProjectStore(tmp_path/'x.db'); project=p.create('P',['https://example.com/a','https://example.com/b']); jobs=ScanJobStore(tmp_path/'x.db'); return project,jobs,JobService(jobs,p,ScanPolicyStore(tmp_path/'x.db'),scanner)
def test_us_001_job_is_durable_and_partial(tmp_path):
 def scanner(u):
  if u.endswith('/b'): raise TimeoutError()
  return []
 p,j,s=setup(tmp_path,scanner); job=s.create_project_job(p.id,'same'); assert job['state']=='QUEUED'; out=s.run_once(); assert out['state']=='PARTIALLY_COMPLETED'; assert out['completed_count']==1 and out['failed_count']==1; assert ScanJobStore(tmp_path/'x.db').get(job['id'])['state']=='PARTIALLY_COMPLETED'
def test_us_001_idempotency_returns_same_job(tmp_path):
 p,j,s=setup(tmp_path); assert s.create_project_job(p.id,'k')['id']==s.create_project_job(p.id,'k')['id']; assert len(j.list())==1
