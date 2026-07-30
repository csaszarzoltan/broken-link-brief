"""Deterministic CI baseline evaluation and exit-code contract."""
from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
@dataclass(frozen=True)
class CiPolicy: max_new:int=0; incomplete_behavior:str="FAIL"
@dataclass(frozen=True)
class CiEvaluation:
    outcome:str; new_confirmed:tuple[str,...]; existing_confirmed:tuple[str,...]; exit_code:int

def evaluate_ci(findings:list[dict],baseline_path:str|Path,policy:CiPolicy=CiPolicy())->CiEvaluation:
    try: base=json.loads(Path(baseline_path).read_text())
    except (OSError,json.JSONDecodeError) as exc: raise ValueError("CI_BASELINE_SCHEMA_UNSUPPORTED") from exc
    if base.get("schema") != 1 or not isinstance(base.get("confirmed"),list): raise ValueError("CI_BASELINE_SCHEMA_UNSUPPORTED")
    current=sorted({x["url"] for x in findings if x.get("classification")=="CONFIRMED_BROKEN"})
    old=set(base["confirmed"]); new=tuple(x for x in current if x not in old); existing=tuple(x for x in current if x in old)
    failed=len(new)>policy.max_new
    return CiEvaluation("FAIL" if failed else "PASS",new,existing,2 if failed else 0)

def write_baseline(findings:list[dict],path:str|Path)->None:
    confirmed=sorted({x["url"] for x in findings if x.get("classification")=="CONFIRMED_BROKEN"})
    Path(path).write_text(json.dumps({"schema":1,"confirmed":confirmed},indent=2)+"\n")
