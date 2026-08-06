from pathlib import Path
from brokenlinkbrief.confidence import ProbeAttempt
from brokenlinkbrief.findings import FindingStore, VersionConflict
from brokenlinkbrief.finding_service import FindingService
from brokenlinkbrief.triage import extract_occurrences


def attempts(status):
    return [ProbeAttempt('HEAD', status, None, .01), ProbeAttempt('GET', status, None, .02)]


def test_confirmed_observation_upserts_stable_source_aware_finding(tmp_path: Path):
    store = FindingStore(tmp_path/'state.db')
    store.ensure_project('p', 'Project')
    service = FindingService(store)
    occ = extract_occurrences('https://site.test/a', '<a href="/missing">Manual</a>')[0]
    first = service.observe('p', occ, attempts(404))
    second = service.observe('p', occ, attempts(404))
    assert first and second and first['id'] == second['id']
    detail = store.detail(first['id'])
    assert detail['classification'] == 'CONFIRMED_BROKEN'
    assert detail['occurrences'][0]['anchor_text'] == 'Manual'
    assert len(detail['evidence']) == 4


def test_transient_does_not_create_finding(tmp_path: Path):
    store = FindingStore(tmp_path/'state.db'); store.ensure_project('p', 'Project')
    service = FindingService(store)
    occ = extract_occurrences('https://site.test', '<a href="/x">x</a>')[0]
    assert service.observe('p', occ, [ProbeAttempt('HEAD', None, 'timeout', .1)]) is None
    assert store.list('p')['total'] == 0


def test_lifecycle_versioning_ignore_and_reopen(tmp_path: Path):
    store = FindingStore(tmp_path/'state.db'); store.ensure_project('p', 'Project')
    service = FindingService(store)
    occ = extract_occurrences('https://site.test', '<a href="/x">x</a>')[0]
    finding = service.observe('p', occ, attempts(404))
    acknowledged = store.acknowledge(finding['id'], finding['version'])
    ignored = store.ignore(finding['id'], acknowledged['version'], 'expected outage', None)
    assert ignored['state'] == 'IGNORED'
    try:
        store.reopen(finding['id'], acknowledged['version'])
        assert False, 'expected conflict'
    except VersionConflict:
        pass
    reopened = store.reopen(finding['id'], ignored['version'])
    assert reopened['state'] == 'OPEN'
    assert len(store.detail(finding['id'])['audit']) >= 4


def test_verification_outcomes_are_evidence_backed(tmp_path: Path):
    store = FindingStore(tmp_path/'state.db'); store.ensure_project('p', 'Project')
    service = FindingService(store)
    occ = extract_occurrences('https://site.test', '<a href="/x">x</a>')[0]
    finding = service.observe('p', occ, attempts(404))
    result = service.verify(finding['id'], finding['version'], attempts(200), {'https://site.test': '<p>removed</p>'})
    assert result['outcome'] == 'RECOVERED'
    assert result['finding']['state'] == 'RESOLVED'

from brokenlinkbrief.package import scan_link_detailed

def test_detailed_probe_retries_and_preserves_legacy_result():
    values=iter([(429,'429',None),(200,'200',None)])
    obs=scan_link_detailed('https://example.test/x', requester=lambda u,m,t: next(values), sleeper=lambda n: None)
    assert [a.status for a in obs.attempts] == [429,200]
    assert obs.assessment.classification == 'RECOVERED'
    assert obs.result.url == 'https://example.test/x'

def test_detailed_probe_uses_real_local_http_io():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    class Handler(BaseHTTPRequestHandler):
        def do_HEAD(self): self.send_response(404); self.end_headers()
        def do_GET(self): self.send_response(404); self.end_headers()
        def log_message(self, *args): pass
    server=HTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        obs=scan_link_detailed(f'http://127.0.0.1:{server.server_port}/missing', sleeper=lambda n:None)
        assert obs.assessment.classification == 'CONFIRMED_BROKEN'
        assert [a.method for a in obs.attempts] == ['HEAD','GET']
    finally:
        server.shutdown();thread.join()
