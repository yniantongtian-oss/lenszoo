"""lenszoo command line.

  lenszoo extract CN105116519B [--out data/designs/new]   fetch + parse Google Patents text tables
  lenszoo verify FILE.json [...] [--write]                 ray-trace checksum verification
  lenszoo fixes FILE.json                                  suggest single-edit OCR fixes that restore EFL
  lenszoo list [--designs data/designs]                    corpus summary
  lenszoo bench score TASK.json CANDIDATE.json             score one candidate
  lenszoo bench run [--agent nearest_opt] [--only T01,T02] [--out results/x.json]
  lenszoo bench prompt TASK.json                         print the agent prompt
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path


def _quiet():
    warnings.filterwarnings("ignore")
    import numpy as np

    np.seterr(all="ignore")


def cmd_extract(a):
    from .extract import extract
    from .verify import verify

    rep = extract(a.pub, cache_dir=a.cache)
    print(f"{a.pub}: {len(rep.prescriptions)} text prescription table(s), {len(rep.image_tables)} image-only table(s)")
    for w in rep.warnings:
        print("  !", w)
    for p in rep.prescriptions:
        if not a.no_verify:
            v = verify(p)
            print(f"  {p.id:<22} {v['status']:<17} claimed={p.claimed} failed={v['failed_checks']}")
        else:
            print(f"  {p.id:<22} claimed={p.claimed}")
        if a.out:
            p.save(Path(a.out) / f"{p.id}.json")
    return 0


def cmd_verify(a):
    from .schema import Prescription
    from .verify import verify

    failed = False
    for f in a.files:
        p = Prescription.load(f)
        v = verify(p)
        failed = failed or v['status'] not in {'verified', 'verified_refined', 'plausible'}
        checks = v.get("refined", {}).get("checks") or v["checks"]
        print(f"{p.id:<22} {v['status']}")
        for k, c in checks.items():
            print(f"   {k:<14} {'PASS' if c['pass'] else 'FAIL'}  " + ", ".join(f"{kk}={vv}" for kk, vv in c.items() if kk != "pass"))
        if "refined" in v:
            print("   refined nd (within print rounding):", v["refined"]["nd"])
        if a.write:
            p.save(f)
    return 1 if failed else 0


def cmd_fixes(a):
    from .schema import Prescription
    from .verify import suggest_fixes

    p = Prescription.load(a.file)
    print(json.dumps(suggest_fixes(p), indent=1, ensure_ascii=False))
    return 0


def cmd_list(a):
    from .schema import Prescription

    rows = []
    for f in sorted(Path(a.designs).rglob("*.json")):
        p = Prescription.load(f)
        rows.append((p.verification.get("status", "?"), p.id, p.lens_count(), p.claimed.get("efl"), p.claimed.get("fno"),
                     p.claimed.get("hfov_deg"), round(p.ttl(), 3), p.source.get("assignee", "")[:28]))
    from collections import Counter

    print(Counter(r[0] for r in rows))
    if a.all:
        for r in rows:
            print(*r, sep="\t")
    else:
        for r in rows:
            if r[0] in ("verified", "verified_refined", "plausible"):
                print(*r, sep="\t")
    return 0


def cmd_bench(a):
    from .bench import load_tasks, render_prompt, score
    from .bench.tasks import Task
    from .schema import Prescription

    if a.bench_cmd == "prompt":
        print(render_prompt(Task.load(a.task)))
        return 0
    if a.bench_cmd == "score":
        r = score(Prescription.load(a.candidate), Task.load(a.task))
        print(json.dumps(r, indent=1, ensure_ascii=False))
        return 0
    # run
    from .bench.baseline import AGENTS, load_corpus

    corpus = load_corpus(a.designs)
    tasks = load_tasks(a.tasks)
    if a.only:
        keep = [x.strip() for x in a.only.split(",")]
        tasks = [t for t in tasks if any(t.id.startswith(k) for k in keep)]
    agent = AGENTS[a.agent]
    results = []
    out = Path(a.out) if a.out else None
    prev = json.loads(out.read_text()) if out and out.exists() else {"results": []}
    done = {r["task"] for r in prev["results"]}
    print(f"corpus: {len(corpus)} usable designs; tasks: {len(tasks)}; agent: {a.agent}")
    for t in tasks:
        if t.id in done and not a.force:
            continue
        t0 = time.time()
        try:
            cand, info = agent(t, corpus)
            r = score(cand, t)
            r["agent_info"] = info
        except Exception as e:
            r = {"task": t.id, "score": 0.0, "pass": False, "error": repr(e)[:200]}
        r["agent"] = a.agent
        r["seconds"] = round(time.time() - t0, 1)
        results.append(r)
        print(f"{t.id:<26} score={r['score']:>6}  pass={r['pass']!s:<5} efl_err={r.get('efl_rel_err')} "
              f"rms={r.get('rms_um_mean')}um seed={r.get('agent_info', {}).get('seed')} ({r['seconds']}s)")
        if out:
            prev["results"] = [x for x in prev["results"] if x["task"] != t.id] + [r]
            prev["agent"] = a.agent
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(prev, indent=1, ensure_ascii=False))
    if out:
        allr = prev["results"]
        print(f"TOTAL {len(allr)} tasks  mean score {sum(r['score'] for r in allr) / max(len(allr), 1):.2f}  "
              f"pass {sum(r['pass'] for r in allr)}/{len(allr)}")
    return 0


def main(argv=None) -> int:
    _quiet()
    ap = argparse.ArgumentParser(prog="lenszoo", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("pub")
    e.add_argument("--out")
    e.add_argument("--cache", default="data/raw")
    e.add_argument("--no-verify", action="store_true")
    v = sub.add_parser("verify")
    v.add_argument("files", nargs="+")
    v.add_argument("--write", action="store_true")
    fx = sub.add_parser("fixes")
    fx.add_argument("file")
    ls = sub.add_parser("list")
    ls.add_argument("--designs", default="data/designs")
    ls.add_argument("--all", action="store_true")
    b = sub.add_parser("bench")
    bs = b.add_subparsers(dest="bench_cmd", required=True)
    br = bs.add_parser("run")
    br.add_argument("--agent", default="nearest_opt", choices=["nearest", "nearest_opt"])
    br.add_argument("--tasks", default="data/tasks")
    br.add_argument("--designs", default="data/designs")
    br.add_argument("--only")
    br.add_argument("--out")
    br.add_argument("--force", action="store_true")
    sc = bs.add_parser("score")
    sc.add_argument("task")
    sc.add_argument("candidate")
    pr = bs.add_parser("prompt")
    pr.add_argument("task")
    a = ap.parse_args(argv)
    return {"extract": cmd_extract, "verify": cmd_verify, "fixes": cmd_fixes, "list": cmd_list, "bench": cmd_bench}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
