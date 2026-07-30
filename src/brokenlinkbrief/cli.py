"""Command-line interface for CI baseline evaluation."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from .ci_gate import CiPolicy,evaluate_ci,write_baseline

def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="brokenlinkbrief"); sub=p.add_subparsers(dest="command",required=True)
    ci=sub.add_parser("ci"); ci.add_argument("--findings",required=True); ci.add_argument("--baseline",required=True); ci.add_argument("--max-new",type=int,default=0)
    base=sub.add_parser("baseline"); base.add_argument("--findings",required=True); base.add_argument("--output",required=True)
    a=p.parse_args(argv); findings=json.loads(Path(a.findings).read_text())
    if a.command=="baseline": write_baseline(findings,a.output); return 0
    result=evaluate_ci(findings,a.baseline,CiPolicy(a.max_new)); print(json.dumps(result.__dict__)); return result.exit_code
if __name__=="__main__": raise SystemExit(main())
