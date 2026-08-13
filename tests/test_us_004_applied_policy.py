from brokenlinkbrief.package import scan_link_detailed
from brokenlinkbrief.scan_policy import EffectivePolicy, ScanPolicy


def test_us_004_effective_policy_controls_attempts_timeout_and_backoff():
    calls = []
    waits = []

    def requester(url, method, timeout):
        calls.append((method, timeout))
        return 503, "busy", None

    policy = EffectivePolicy(
        ScanPolicy(
            timeout_seconds=7,
            max_attempts=3,
            backoff_seconds=0.4,
            temporary_statuses=(503,),
        ),
        2,
        "HOST_OVERRIDE",
        "api.example.com",
    )
    out = scan_link_detailed(
        "https://api.example.com/x",
        policy=policy,
        requester=requester,
        sleeper=waits.append,
    )
    assert len(out.attempts) == 3
    assert calls == [("HEAD", 7), ("GET", 7), ("GET", 7)]
    assert waits == [0.4, 0.8]


def test_us_004_temporary_status_not_configured_stops_without_retry():
    calls = []

    def requester(url, method, timeout):
        calls.append(method)
        return 503, "busy", None

    policy = EffectivePolicy(
        ScanPolicy(max_attempts=3, temporary_statuses=(429,)),
        1,
        "PROJECT_DEFAULT",
        "example.com",
    )
    scan_link_detailed(
        "https://example.com/",
        policy=policy,
        requester=requester,
        sleeper=lambda n: None,
    )
    assert calls == ["HEAD"]
