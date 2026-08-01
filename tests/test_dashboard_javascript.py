"""Syntax regression test for the embedded dashboard JavaScript."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest


def test_embedded_dashboard_javascript_is_valid(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable for JavaScript syntax validation")
    source = Path("src/brokenlinkbrief/app.py").read_text(encoding="utf-8")
    match = re.search(r"<script>(.*?)</script>", source, re.DOTALL)
    assert match is not None
    script = tmp_path / "dashboard.js"
    script.write_text(match.group(1), encoding="utf-8")
    result = subprocess.run(
        [node, "--check", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
