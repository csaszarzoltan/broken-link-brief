"""Pre-development interface/behavior tests for BrokenLinkBrief export module."""
from __future__ import annotations

import inspect

from brokenlinkbrief.export import render_markdown
from brokenlinkbrief.package import LinkResult


def test_interface_render_markdown_importable() -> None:
    assert callable(render_markdown)


def test_interface_render_markdown_signature_matches_contract() -> None:
    signature = inspect.signature(render_markdown)
    params = list(signature.parameters.values())
    assert len(params) == 1
    assert params[0].name == "results"
    assert str(signature.return_annotation) == "str"


def test_behavior_render_markdown_formats_non_empty_results() -> None:
    results = [
        LinkResult(
            url="https://example.com",
            status=200,
            reason="OK",
            location=None,
        ),
        LinkResult(
            url="https://example.com/x",
            status=None,
            reason="fetch-failed",
            location=None,
        ),
    ]
    rendered = render_markdown(results)
    expected = (
        "# BrokenLinkBrief\n\n"
        "| URL | Status | Reason | Location |\n"
        "| --- | ---: | --- | --- |\n"
        "| https://example.com | 200 | OK |  |\n"
        "| https://example.com/x |  | fetch-failed |  |\n"
    )
    assert rendered == expected


def test_behavior_empty_results_renders_header_only() -> None:
    rendered = render_markdown([])
    assert rendered == (
        "# BrokenLinkBrief\n\n"
        "| URL | Status | Reason | Location |\n"
        "| --- | ---: | --- | --- |\n"
    )
