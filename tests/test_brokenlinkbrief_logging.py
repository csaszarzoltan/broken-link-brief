"""Acceptance tests for BrokenLinkBrief JSONL usage log."""
from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import HTTPServer

import pytest

from apps.brokenlinkbrief.app import _Handler
from apps.brokenlinkbrief.package import LinkResult


class TestLogScanInterface:
    def test_log_scan_callable(self):
        from apps.brokenlinkbrief.app import _log_scan

        assert callable(_log_scan)

    def test_log_scan_signature(self):
        import inspect

        from apps.brokenlinkbrief.app import _log_scan

        sig = inspect.signature(_log_scan)
        params = list(sig.parameters.values())
        assert len(params) == 4
        assert params[0].name == "target_url"
        assert params[1].name == "results"
        assert params[2].name == "response_format"
        assert params[3].name == "latency_seconds"

    def test_log_scan_produces_one_json_line(self, capsys):
        from apps.brokenlinkbrief.app import _log_scan

        results = [
            LinkResult(
                url="https://example.com", status=200, reason="OK", location=None
            )
        ]
        _log_scan("https://example.com", results, "json", 0.05)
        captured = capsys.readouterr()
        assert captured.err.count("\n") == 1

    def test_log_scan_line_is_valid_json(self, capsys):
        from apps.brokenlinkbrief.app import _log_scan

        results = [
            LinkResult(
                url="https://example.com", status=200, reason="OK", location=None
            )
        ]
        _log_scan("https://example.com", results, "json", 0.05)
        captured = capsys.readouterr()
        line = captured.err.strip()
        assert line
        parsed = json.loads(line)
        assert isinstance(parsed, dict)

    def test_log_scan_timestamp_iso8601(self, capsys):
        from apps.brokenlinkbrief.app import _log_scan

        results = [
            LinkResult(
                url="https://example.com", status=200, reason="OK", location=None
            )
        ]
        _log_scan("https://example.com", results, "json", 0.05)
        captured = capsys.readouterr()
        parsed = json.loads(captured.err.strip())
        ts = parsed["timestamp"]
        import datetime
        datetime.datetime.fromisoformat(ts)

    def test_log_scan_fields_present(self, capsys):
        from apps.brokenlinkbrief.app import _log_scan

        results = [
            LinkResult(
                url="https://example.com", status=200, reason="OK", location=None
            )
        ]
        _log_scan("https://example.com", results, "json", 0.05)
        captured = capsys.readouterr()
        parsed = json.loads(captured.err.strip())
        assert parsed["target_url"] == "https://example.com"
        assert parsed["result_count"] == 1
        assert parsed["broken_count"] == 0
        assert parsed["format"] == "json"
        assert "latency_seconds" in parsed
        assert parsed["status"] == "ok"

    def test_log_scan_status_error_for_http_errors(self, capsys):
        from apps.brokenlinkbrief.app import _log_scan

        results = [
            LinkResult(
                url="https://ok.com", status=200, reason="OK", location=None
            ),
            LinkResult(
                url="https://broken.com",
                status=404,
                reason="Not Found",
                location=None,
            ),
        ]
        _log_scan("https://example.com", results, "json", 0.05)
        captured = capsys.readouterr()
        parsed = json.loads(captured.err.strip())
        assert parsed["status"] == "error"
        assert parsed["broken_count"] == 1

    def test_log_scan_broken_count_non_ok_reason(self, capsys):
        from apps.brokenlinkbrief.app import _log_scan

        results = [
            LinkResult(
                url="https://ok.com", status=200, reason="OK", location=None
            ),
            LinkResult(
                url="https://broken.com",
                status=None,
                reason="fetch-failed",
                location=None,
            ),
        ]
        _log_scan("https://example.com", results, "json", 0.05)
        captured = capsys.readouterr()
        parsed = json.loads(captured.err.strip())
        assert parsed["broken_count"] == 1
        assert parsed["status"] == "error"


class TestEndpointLogging:
    def test_scan_json_logs_to_stderr_by_default(self, capsys):
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("BROKENLINKBRIEF_SCAN_TOKEN", "secret")
        monkeypatch.delenv("BROKENLINKBRIEF_LOG_FILE", raising=False)

        def fake_scan(url: str, timeout: float = 10.0):
            return [LinkResult(url=url, status=200, reason="OK", location=None)]

        monkeypatch.setattr("apps.brokenlinkbrief.app.scan_page", fake_scan)

        sock = HTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=sock.serve_forever, daemon=True)
        thread.start()
        try:
            conn = HTTPConnection("127.0.0.1", sock.server_address[1], timeout=5)
            conn.request(
                "GET",
                "/scan?url=https://example.com&token=secret",
                headers={"Host": "127.0.0.1"},
            )
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")
            conn.close()
            assert resp.status == 200
            assert resp.getheader("Content-Type") == "application/json"
            parsed = json.loads(body)
            assert isinstance(parsed, list)
        finally:
            sock.shutdown()
            monkeypatch.undo()

        captured = capsys.readouterr()
        assert captured.err.count("\n") >= 1
        lines = [line for line in captured.err.strip().split("\n") if line]
        assert len(lines) == 1
        log = json.loads(lines[0])
        assert log["target_url"] == "https://example.com"
        assert log["result_count"] == 1
        assert log["format"] == "json"
        assert isinstance(log["latency_seconds"], float)

    def test_scan_csv_logs_to_stderr_by_default(self, capsys):
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("BROKENLINKBRIEF_SCAN_TOKEN", "secret")
        monkeypatch.delenv("BROKENLINKBRIEF_LOG_FILE", raising=False)

        def fake_scan(url: str, timeout: float = 10.0):
            return [LinkResult(url=url, status=200, reason="OK", location=None)]

        monkeypatch.setattr("apps.brokenlinkbrief.app.scan_page", fake_scan)

        sock = HTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=sock.serve_forever, daemon=True)
        thread.start()
        try:
            conn = HTTPConnection("127.0.0.1", sock.server_address[1], timeout=5)
            conn.request(
                "GET",
                "/scan?url=https://example.com&format=csv&token=secret",
                headers={"Host": "127.0.0.1"},
            )
            resp = conn.getresponse()
            resp.read()
            conn.close()
            assert resp.status == 200
            assert resp.getheader("Content-Type") == "text/csv; charset=utf-8"
        finally:
            sock.shutdown()
            monkeypatch.undo()

        captured = capsys.readouterr()
        assert captured.err.count("\n") >= 1

    def test_scan_writes_to_file_when_configured(self, tmp_path):
        log_file = tmp_path / "scan.log"
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("BROKENLINKBRIEF_SCAN_TOKEN", "secret")
        monkeypatch.setenv("BROKENLINKBRIEF_LOG_FILE", str(log_file))

        def fake_scan(url: str, timeout: float = 10.0):
            return [LinkResult(url=url, status=200, reason="OK", location=None)]

        monkeypatch.setattr("apps.brokenlinkbrief.app.scan_page", fake_scan)

        sock = HTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=sock.serve_forever, daemon=True)
        thread.start()
        try:
            conn = HTTPConnection("127.0.0.1", sock.server_address[1], timeout=5)
            conn.request(
                "GET",
                "/scan?url=https://example.com&token=secret",
                headers={"Host": "127.0.0.1"},
            )
            resp = conn.getresponse()
            resp.read()
            conn.close()
            assert resp.status == 200
        finally:
            sock.shutdown()
            monkeypatch.undo()

        assert log_file.exists()
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 1
        log = json.loads(lines[0])
        assert log["target_url"] == "https://example.com"
        assert log["broken_count"] == 0
        assert log["format"] == "json"
        assert isinstance(log["latency_seconds"], float)

    def test_does_not_log_on_400_public_server_with_no_token(self, capsys):
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.delenv("BROKENLINKBRIEF_SCAN_TOKEN", raising=False)
        monkeypatch.delenv("BROKENLINKBRIEF_LOG_FILE", raising=False)

        def fake_scan(url: str, timeout: float = 10.0):
            return []

        monkeypatch.setattr("apps.brokenlinkbrief.app.scan_page", fake_scan)

        sock = HTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=sock.serve_forever, daemon=True)
        thread.start()
        try:
            conn = HTTPConnection("127.0.0.1", sock.server_address[1], timeout=5)
            conn.request(
                "GET",
                "/scan",
                headers={"Host": "127.0.0.1"},
            )
            resp = conn.getresponse()
            resp.read()
            conn.close()
            assert resp.status in {400, 401}
        finally:
            sock.shutdown()
            monkeypatch.undo()

        captured = capsys.readouterr()
        assert captured.err == ""

    def test_does_not_log_on_401(self, capsys):
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("BROKENLINKBRIEF_SCAN_TOKEN", "secret")
        monkeypatch.delenv("BROKENLINKBRIEF_LOG_FILE", raising=False)

        sock = HTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=sock.serve_forever, daemon=True)
        thread.start()
        try:
            conn = HTTPConnection("127.0.0.1", sock.server_address[1], timeout=5)
            conn.request(
                "GET",
                "/scan?url=https://example.com",
                headers={"Host": "127.0.0.1"},
            )
            resp = conn.getresponse()
            resp.read()
            conn.close()
            assert resp.status == 401
        finally:
            sock.shutdown()
            monkeypatch.undo()

        captured = capsys.readouterr()
        assert captured.err == ""

    def test_does_not_log_on_404(self, capsys):
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.delenv("BROKENLINKBRIEF_LOG_FILE", raising=False)

        sock = HTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=sock.serve_forever, daemon=True)
        thread.start()
        try:
            conn = HTTPConnection("127.0.0.1", sock.server_address[1], timeout=5)
            conn.request(
                "GET",
                "/unknown",
                headers={"Host": "127.0.0.1"},
            )
            resp = conn.getresponse()
            resp.read()
            conn.close()
            assert resp.status == 404
        finally:
            sock.shutdown()
            monkeypatch.undo()

        captured = capsys.readouterr()
        assert captured.err == ""

    def test_broken_count_correct_for_failures(self, capsys):
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setenv("BROKENLINKBRIEF_SCAN_TOKEN", "secret")
        monkeypatch.delenv("BROKENLINKBRIEF_LOG_FILE", raising=False)

        def fake_scan(url: str, timeout: float = 10.0):
            return [
                LinkResult(
                    url="https://ok.com", status=200, reason="OK", location=None
                ),
                LinkResult(
                    url="https://broken.com",
                    status=404,
                    reason="Not Found",
                    location=None,
                ),
            ]

        monkeypatch.setattr("apps.brokenlinkbrief.app.scan_page", fake_scan)

        sock = HTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=sock.serve_forever, daemon=True)
        thread.start()
        try:
            conn = HTTPConnection("127.0.0.1", sock.server_address[1], timeout=5)
            conn.request(
                "GET",
                "/scan?url=https://example.com&token=secret",
                headers={"Host": "127.0.0.1"},
            )
            resp = conn.getresponse()
            resp.read()
            conn.close()
            assert resp.status == 200
        finally:
            sock.shutdown()
            monkeypatch.undo()

        captured = capsys.readouterr()
        lines = [line for line in captured.err.strip().split("\n") if line]
        assert len(lines) == 1
        log = json.loads(lines[0])
        assert log["result_count"] == 2
        assert log["broken_count"] == 1
        assert log["status"] == "error"
