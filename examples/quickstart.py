"""LensZoo quickstart: verify a real CN patent design, catch a typo, score it on a task.

Run from the repo root:  python examples/quickstart.py
"""
import copy
import json
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
np.seterr(all="ignore")

from lenszoo.bench import Task, render_prompt, score  # noqa: E402
from lenszoo.schema import Prescription  # noqa: E402
from lenszoo.verify import suggest_fixes, verify  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# 1. A 7-element phone lens transcribed automatically from CN105116519B (Sunny), embodiment 2
p = Prescription.load(ROOT / "data/designs/verified/CN105116519B-ex2.json")
print(f"{p.id}: {p.source['title']} / {p.source['assignee']} / {p.lens_count()} elements")
print("claimed by the patent:", p.claimed)

v = verify(copy.deepcopy(p))
print("verification:", v["status"])
for k, c in v["checks"].items():
    print(f"  {k:<14}{'PASS' if c['pass'] else 'FAIL'}  {json.dumps({x: y for x, y in c.items() if x != 'pass'})}")
print("  RMS spot by field (um):", [round(f["rms_um"], 2) for f in v["metrics"]["fields"]])

# 2. Simulate an OCR error: drop the minus sign on S3's radius
bad = copy.deepcopy(p)
s3 = next(s for s in bad.surfaces if s.name == "S3")
s3.radius = -s3.radius
vb = verify(bad, refine=False)
print("\nwith a sign typo on S3 ->", vb["status"], "failed:", vb["failed_checks"])
print("suggested single-edit fixes:", suggest_fixes(bad)[:2])

# 3. Use it as a benchmark reference
task = Task.load(ROOT / "data/tasks/T01-main7p-f4.04.json")
print("\n" + render_prompt(task))
r = score(p, task)
print("reference design on its own task:", {k: r[k] for k in ("score", "pass", "Q_mtf_mean", "rms_um_mean", "efl_rel_err")})
