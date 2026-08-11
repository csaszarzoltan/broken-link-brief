import pytest
from brokenlinkbrief.projects import ProjectStore
from brokenlinkbrief.scan_jobs import JobConflict,ScanJobStore

def test_us_002_queued_cancel_calls_no_scanner(tmp_path):
 p=ProjectStore(tmp_path/'x.db').create('P',['https://example.com/']); j=ScanJobStore(tmp_path/'x.db'); job=j.create(p.id,p.name,list(p.targets)); out=j.cancel(job['id'],job['version']); assert out['state']=='CANCELLED'; assert out['cancelled_count']==1
def test_us_002_terminal_cancel_conflicts(tmp_path):
 p=ProjectStore(tmp_path/'x.db').create('P',['https://example.com/']); j=ScanJobStore(tmp_path/'x.db'); job=j.create(p.id,p.name,list(p.targets)); job=j.cancel(job['id'],job['version']);
 with pytest.raises(JobConflict): j.cancel(job['id'],job['version'])
