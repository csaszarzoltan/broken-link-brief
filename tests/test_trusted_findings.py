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


def test_all_verification_outcomes_and_occurrence_reconciliation(tmp_path: Path):
    def create(name):
        store = FindingStore(tmp_path / f'{name}.db')
        store.ensure_project('p', 'Project')
        service = FindingService(store)
        occurrence = extract_occurrences(
            'https://site.test/source', '<a href="/x">Anchor</a>'
        )[0]
        finding = service.observe('p', occurrence, attempts(404))
        return store, service, finding

    store, service, finding = create('removed')
    removed = service.verify(
        finding['id'], finding['version'], attempts(404),
        {'https://site.test/source': '<p>gone</p>'},
    )
    assert removed['outcome'] == 'REMOVED_FROM_SOURCE'
    assert store.detail(finding['id'])['occurrences'][0]['active'] == 0

    _, service, finding = create('broken')
    broken = service.verify(
        finding['id'], finding['version'], attempts(404),
        {'https://site.test/source': '<a href="/x">Anchor</a>'},
    )
    assert broken['outcome'] == 'STILL_BROKEN'
    assert broken['finding']['state'] == 'OPEN'

    _, service, finding = create('unknown')
    unknown = service.verify(
        finding['id'], finding['version'],
        [ProbeAttempt('HEAD', None, 'timeout', .1)],
        {'https://site.test/source': None},
    )
    assert unknown['outcome'] == 'INCONCLUSIVE'
    assert unknown['finding']['state'] == 'OPEN'


def test_archived_project_is_read_only(tmp_path: Path):
    from brokenlinkbrief.projects import ProjectStore
    db = tmp_path / 'state.db'
    project = ProjectStore(db).create('P', ['https://site.test/'])
    store = FindingStore(db)
    service = FindingService(store)
    occurrence = extract_occurrences(
        'https://site.test/', '<a href="/x">x</a>'
    )[0]
    finding = service.observe(project.id, occurrence, attempts(404))
    ProjectStore(db).archive(project.id)
    import pytest
    with pytest.raises(ValueError, match='read-only'):
        store.acknowledge(finding['id'], finding['version'])


def test_expired_ignore_reopens_and_search_includes_occurrence(tmp_path: Path):
    store = FindingStore(tmp_path / 'state.db')
    store.ensure_project('p', 'Project')
    finding = FindingService(store).observe(
        'p',
        extract_occurrences(
            'https://site.test/help', '<a href="/x">Unique manual phrase</a>'
        )[0],
        attempts(404),
    )
    ignored = store.ignore(finding['id'], finding['version'], 'old', '2000-01-01')
    assert store.get(ignored['id'])['state'] == 'OPEN'
    assert store.list('p', q='Unique manual')['total'] == 1
    assert store.list('p', q='site.test/help')['total'] == 1


def test_evidence_errors_redact_secret_values(tmp_path: Path):
    store = FindingStore(tmp_path / 'state.db')
    store.ensure_project('p', 'Project')
    occurrence = extract_occurrences(
        'https://site.test/', '<a href="/x">x</a>'
    )[0]
    finding = FindingService(store).observe(
        'p', occurrence,
        [ProbeAttempt('HEAD', None, 'token=supersecretvalue', .1)],
    )
    assert finding is None
    # Add an existing confirmed finding, then retain later transient evidence.
    finding = FindingService(store).observe('p', occurrence, attempts(404))
    FindingService(store).observe(
        'p', occurrence,
        [ProbeAttempt('HEAD', None, 'token=supersecretvalue', .1)],
    )
    text = str(store.detail(finding['id'])['evidence'])
    assert 'supersecretvalue' not in text
    assert '[redacted]' in text


def test_new_outbound_paths_validate_urls_before_fetching():
    from pathlib import Path
    source = Path('src/brokenlinkbrief/app.py').read_text()
    project_block = source[source.index('for occurrence in extract_occurrences'):source.index('# Record scan and trigger')]
    verify_block = source[source.index('elif action == "verify"'):source.index('else: raise KeyError(action)')]
    assert 'validate_scan_url(occurrence.target_url)' in project_block
    assert 'validate_scan_url(detail["target_url"])' in verify_block
    assert 'validate_scan_url(item["source_url"])' in verify_block
