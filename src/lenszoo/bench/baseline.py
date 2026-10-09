"""Baseline agents.

* `nearest`        : pick the closest corpus design by spec, scale it to the target EFL.
* `nearest_opt`    : `nearest`, then Optiland's damped-least-squares (SciPy
                     least_squares) on radii + back focal distance, targeting
                     EFL, RMS spot at 3 fields and the TTL limit.
Both respect task.reference.exclude_patents (no peeking at the source patent).
"""
from __future__ import annotations

import copy
import math
import time
import warnings
from pathlib import Path

import numpy as np

from ..schema import Prescription
from ..verify.build import build_optic
from ..verify.check import quiet
from .scorer import prepare
from .tasks import Task

USABLE = ("verified", "verified_refined", "plausible")


def load_corpus(folder: str | Path, statuses=USABLE) -> list[Prescription]:
    out = []
    for f in sorted(Path(folder).rglob("*.json")):
        try:
            p = Prescription.load(f)
        except Exception:
            continue
        if p.verification.get("status") in statuses:
            out.append(p)
    return out


def design_spec(p: Prescription) -> dict:
    m = p.verification.get("refined", {}).get("metrics") or p.verification.get("metrics") or {}
    efl = p.claimed.get("efl") or m.get("efl")
    return {"efl": efl, "fno": p.claimed.get("fno") or m.get("fno"),
            "hfov_deg": p.claimed.get("hfov_deg") or m.get("hfov_deg"), "ttl": p.ttl(), "n": p.lens_count()}


def spec_distance(task: Task, p: Prescription) -> float:
    d = design_spec(p)
    s = task.spec
    if not d["efl"] or d["efl"] <= 0:
        return math.inf
    dist = abs(d["hfov_deg"] - s["hfov_deg"]) / 10 + abs(d["fno"] - s["fno"]) / 0.5
    dist += abs(d["ttl"] / d["efl"] - s["ttl_max"] / s["efl"]) / 0.2
    if task.constraints.get("max_elements") and d["n"] > task.constraints["max_elements"]:
        dist += 10
    if math.isfinite(p.surfaces[0].thickness):   # designed for a finite (macro) object
        dist += 5
    return dist


def refocus(p: Prescription, task: Task) -> Prescription:
    """Move the image plane to the paraxial focus (adjust the last gap)."""
    from ..verify import metrics as M

    with quiet():
        op, _ = build_optic(p, fno=task.spec["fno"], hfov_deg=task.spec["hfov_deg"], fields=(0.0,))
        dz = M.paraxial_defocus(op)
    if math.isfinite(dz):
        q = copy.deepcopy(p)
        q.surfaces[-2].thickness = max(0.02, q.surfaces[-2].thickness + dz)
        return q
    return p


def nearest(task: Task, corpus: list[Prescription]) -> tuple[Prescription, dict]:
    excl = set(task.reference.get("exclude_patents", []))
    pool = [p for p in corpus if p.source.get("patent") not in excl]
    if not pool:
        raise RuntimeError("empty corpus after exclusions")
    best = min(pool, key=lambda p: spec_distance(task, p))
    with quiet():
        op, _ = build_optic(prepare(best, task), fno=task.spec["fno"], hfov_deg=task.spec["hfov_deg"], fields=(0.0,))
        k = task.spec["efl"] / float(op.paraxial.f2())
    cand = prepare(best.scaled(k, new_id=f"nearest:{best.id}@x{k:.3f}"), task)
    if math.isfinite(best.surfaces[0].thickness):
        # seed was designed for a finite object: move the image plane to the
        # paraxial focus for an object at infinity (patent image planes sit at
        # best focus, so infinite-conjugate seeds are left alone)
        cand = refocus(cand, task)
    return cand, {"seed": best.id, "scale": round(k, 4), "spec_distance": round(spec_distance(task, best), 3)}


def _optic_to_prescription(op, template: Prescription) -> Prescription:
    q = copy.deepcopy(template)
    for i, s in enumerate(q.surfaces):
        g = op.surfaces.surfaces[i].geometry
        r = float(np.asarray(getattr(g, "radius", math.inf)).ravel()[0])
        s.radius = r
        if s.role not in ("object", "image") and i + 1 < len(q.surfaces):
            z0 = float(np.asarray(op.surfaces.surfaces[i].geometry.cs.z).ravel()[0])
            z1 = float(np.asarray(op.surfaces.surfaces[i + 1].geometry.cs.z).ravel()[0])
            s.thickness = z1 - z0
    return q


def _robust_rms(optic, Hy, num_rings=4):
    """Polychromatic RMS spot (mm) with the same outlier/vignetting rules as the scorer.

    Optiland's built-in rms_spot_size returns NaN as soon as one rim ray fails,
    which stalls least-squares on patent designs without clear apertures.
    """
    from ..verify import metrics as M

    with quiet():
        r = M.spot_and_mtf(optic, [Hy], 1.0, num_rings=num_rings)[0]["rms_um"]
    return min(r, 1e3) * 1e-3 if math.isfinite(r) else 1.0


def _mtf_loss(optic, Hy, freq, num_rings=4):
    """1 - polychromatic geometric MTF (T+S)/2 at one field: the scorer's own quality term."""
    from ..verify import metrics as M

    with quiet():
        r = M.spot_and_mtf(optic, [Hy], freq, num_rings=num_rings)[0]
    return 1.0 - (r["mtf_t"] + r["mtf_s"]) / 2 if math.isfinite(r["rms_um"]) else 1.0


def _register_operands():
    from optiland.optimization.operand.operand import operand_registry

    for name, fn in (("lenszoo_rms", _robust_rms), ("lenszoo_mtf_loss", _mtf_loss)):
        try:
            operand_registry.register(name, fn)
        except Exception:
            pass


def nearest_opt(task: Task, corpus: list[Prescription], max_nfev: int = 25) -> tuple[Prescription, dict]:
    """`nearest` + damped least squares on surface curvatures and the back focal gap.

    Uses SciPy least_squares (trf, x_scale='jac') on Optiland ray traces. Residuals
    mirror the scorer: (1 - MTF) at every task field, EFL error, TTL excess.
    Variables are curvatures c = 1/R (smooth through flat surfaces).
    """
    from scipy.optimize import least_squares

    from ..verify import metrics as M

    cand, info = nearest(task, corpus)
    cand = prepare(cand, task)
    t0 = time.time()
    with quiet():
        op, _ = build_optic(cand, fno=task.spec["fno"], hfov_deg=task.spec["hfov_deg"], fields=tuple(task.fields))
        idx = [i for i, s in enumerate(cand.surfaces) if s.role == "surface" and math.isfinite(s.radius)]
        bfl_i = len(cand.surfaces) - 2
        c0 = np.array([1.0 / cand.surfaces[i].radius for i in idx])
        d0 = cand.surfaces[bfl_i].thickness
        f_t, ttl_max = task.spec["efl"], task.spec["ttl_max"]

        def apply(x):
            for i, c in zip(idx, x[:-1]):
                op.set_radius(1.0 / c if abs(c) > 1e-9 else 1e9, i)
            op.set_thickness(max(0.02, d0 + x[-1]), bfl_i)

        def resid(x):
            apply(x)
            r = [5.0 * (M.efl(op) - f_t) / f_t]
            ttl = cand.ttl() - d0 + max(0.02, d0 + x[-1])
            r.append(5.0 * max(0.0, ttl - ttl_max) / ttl_max)
            sm = M.spot_and_mtf(op, task.fields, task.freq, num_rings=4)
            r += [1.0 - (q["mtf_t"] + q["mtf_s"]) / 2 if math.isfinite(q["rms_um"]) else 1.0 for q in sm]
            return np.array(r)

        x0 = np.concatenate([c0, [0.0]])
        r0 = resid(x0)
        try:
            sol = least_squares(resid, x0, method="trf", x_scale="jac", diff_step=1e-3, max_nfev=max_nfev)
            x = sol.x
            nfev = int(sol.nfev)
        except Exception as e:  # keep the seed if the optimizer blows up
            warnings.warn(f"optimizer failed: {e}")
            x, nfev = x0, 0
        r1 = resid(x)
        apply(x)
    out = copy.deepcopy(cand)
    for i, c in zip(idx, x[:-1]):
        out.surfaces[i].radius = 1.0 / c if abs(c) > 1e-9 else math.inf
    out.surfaces[bfl_i].thickness = max(0.02, d0 + x[-1])
    out.id = f"nearest_opt:{info['seed']}"
    # keep whichever of seed / optimized scores better (a sane agent would too)
    from .scorer import score as _score

    s_seed, s_opt = _score(cand, task)["score"], _score(out, task)["score"]
    info.update({"variables": len(x), "merit_before": round(float(r0 @ r0), 5), "merit_after": round(float(r1 @ r1), 5),
                 "nfev": nfev, "opt_seconds": round(time.time() - t0, 1), "score_seed": s_seed, "score_optimized": s_opt})
    if s_seed > s_opt:
        out, info["kept"] = cand, "seed"
    else:
        info["kept"] = "optimized"
    return out, info


AGENTS = {"nearest": nearest, "nearest_opt": nearest_opt}
