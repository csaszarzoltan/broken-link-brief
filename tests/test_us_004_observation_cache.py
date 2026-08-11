from brokenlinkbrief.observation_cache import ObservationCache

def test_us_004_cache_is_project_and_fingerprint_scoped(tmp_path):
    c=ObservationCache(tmp_path/'x.db'); c.put('p1','https://example.com/','fp1',{'classification':'RECOVERED'},60,'RECOVERED')
    assert c.get('p1','https://example.com/','fp1')['classification']=='RECOVERED'
    assert c.get('p2','https://example.com/','fp1') is None
    assert c.get('p1','https://example.com/','fp2') is None

def test_us_004_ineligible_evidence_is_not_cached(tmp_path):
    c=ObservationCache(tmp_path/'x.db')
    assert c.put('p','https://example.com/','fp',{'classification':'TRANSIENT'},60,'TRANSIENT') is False
    assert c.get('p','https://example.com/','fp') is None
