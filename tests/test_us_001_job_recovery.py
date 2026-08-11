from datetime import datetime, timedelta, timezone
import pytest
from brokenlinkbrief.projects import ProjectStore
from brokenlinkbrief.scan_jobs import JobLeaseLost, ScanJobStore

def test_us_001_expired_lease_recovers_without_repeating_completed_source(tmp_path):
    db=tmp_path/'x.db'; p=ProjectStore(db).create('P',['https://example.com/a','https://example.com/b'])
    store=ScanJobStore(db); job=store.create(p.id,p.name,list(p.targets)); claimed=store.claim('worker-a', lease_seconds=1)
    sources=store.sources(job['id']); store.start_source(sources[0]['id'],'worker-a'); store.finish_source(sources[0]['id'],'worker-a',True,[])
    store.start_source(sources[1]['id'],'worker-a')
    past=(datetime.now(timezone.utc)-timedelta(seconds=5)).isoformat(); store.force_lease_expiry(job['id'],past)
    recovered=ScanJobStore(db).claim('worker-b',lease_seconds=30)
    assert recovered['id']==job['id']; states=[x['state'] for x in store.sources(job['id'])]
    assert states==['COMPLETED','PENDING']
    with pytest.raises(JobLeaseLost): store.heartbeat(job['id'],'worker-a')

def test_us_001_only_one_worker_claims(tmp_path):
    db=tmp_path/'x.db'; p=ProjectStore(db).create('P',['https://example.com/']); store=ScanJobStore(db); store.create(p.id,p.name,list(p.targets))
    assert store.claim('one') is not None
    assert store.claim('two') is None
