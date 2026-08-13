"""Command-line interface for CI baseline evaluation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ci_gate import CiPolicy, evaluate_ci, write_baseline


def main(argv: list[str] | None = None) -> int:
    """Run the brokenlinkbrief CLI and return the process exit code."""
    parser = argparse.ArgumentParser(prog="brokenlinkbrief")
    sub = parser.add_subparsers(dest="command", required=True)
    ci = sub.add_parser("ci")
    ci.add_argument("--findings", required=True)
    ci.add_argument("--baseline", required=True)
    ci.add_argument("--max-new", type=int, default=0)
    base = sub.add_parser("baseline")
    base.add_argument("--findings", required=True)
    base.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    findings = json.loads(Path(args.findings).read_text())
    if args.command == "baseline":
        write_baseline(findings, args.output)
        return 0
    result = evaluate_ci(findings, args.baseline, CiPolicy(args.max_new))
    print(json.dumps(result.__dict__))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
