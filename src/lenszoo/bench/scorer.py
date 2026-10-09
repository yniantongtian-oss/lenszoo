"""Deterministic scorer for lens-design tasks, running on Optiland (no Zemax).

score = 100 * Q * P
  Q = mean over task fields of the polychromatic geometric MTF (T+S)/2 at the
      task frequency (default: 1/4 of the diffraction cutoff), 0..1
  P = product of soft penalties exp(-violation/scale) for EFL error beyond
      tolerance, TTL over the limit, distortion over the limit, thin elements,
      too many elements, and untraceable fields.
pass = every hard constraint satisfied (EFL within tol, TTL <= max,
      |distortion| <= max, CT >= min, elements <= max, all fields trace).
"""
from __future__ import annotations

import copy
import math

from ..schema import INF, Prescription
from ..verify.check import evaluate
from .tasks import Task


def prepare(candidate: Prescription, task: Task) -> Prescription:
    """Put the candidate under the task's conditions (object at infinity, wavelengths)."""
    p = copy.deepcopy(candidate)
    p.surfaces[0].thickness = INF
    if task.spec.get("wavelengths_um"):
        p.wavelengths_um = list(task.spec["wavelengths_um"])
        p.primary_wavelength_um = task.spec.get("primary_wavelength_um", p.wavelengths_um[len(p.wavelengths_um) // 2])
    return p


def score(candidate: Prescription, task: Task) -> dict:
    p = prepare(candidate, task)
    s, c = task.spec, task.constraints
    try:
        m = evaluate(p, fno=s["fno"], hfov=s["hfov_deg"], rel_fields=tuple(task.fields), freq_lpmm=task.freq)
    except Exception as e:  # unbuildable / untraceable
        return {"task": task.id, "candidate": candidate.id, "score": 0.0, "pass": False, "error": repr(e)[:200]}

    viol: dict[str, float] = {}
    efl_err = (m["efl"] - s["efl"]) / s["efl"]
    viol["efl"] = max(0.0, abs(efl_err) - task.efl_tol) / 0.02
    ttl_slack = c.get("ttl_tol_abs", 0.01)   # patents print TTL to 0.01 mm
    viol["ttl"] = max(0.0, m["ttl"] - s["ttl_max"] - ttl_slack) / (0.05 * s["ttl_max"])
    dist = m.get("distortion_pct", float("nan"))
    if c.get("max_distortion_pct") is not None and math.isfinite(dist):
        viol["distortion"] = max(0.0, abs(dist) - c["max_distortion_pct"]) / 2.0
    ct = m.get("min_center_thickness", float("nan"))
    if c.get("min_center_thickness") is not None and math.isfinite(ct):
        viol["center_thickness"] = max(0.0, c["min_center_thickness"] - ct) / 0.05
    if c.get("max_elements") is not None:
        viol["elements"] = max(0, m["n_lenses"] - c["max_elements"]) * 1.0
    bad_fields = sum(1 for f in m["fields"] if not math.isfinite(f["rms_um"]))
    viol["untraced_fields"] = bad_fields * 1.0

    Q = 0.0
    good = [f for f in m["fields"] if math.isfinite(f["rms_um"])]
    if good:
        Q = sum((f["mtf_t"] + f["mtf_s"]) / 2 for f in good) / len(m["fields"])
    P = math.exp(-sum(viol.values()))
    passed = all(v == 0 for v in viol.values())
    rms = [f["rms_um"] for f in good]
    return {
        "task": task.id, "candidate": candidate.id,
        "score": round(100 * Q * P, 2), "pass": passed,
        "Q_mtf_mean": round(Q, 4), "penalty": round(P, 4),
        "violations": {k: round(v, 4) for k, v in viol.items() if v},
        "efl": round(m["efl"], 4), "efl_rel_err": round(efl_err, 4), "ttl": round(m["ttl"], 4),
        "distortion_pct": round(dist, 3) if math.isfinite(dist) else None,
        "rms_um_mean": round(sum(rms) / len(rms), 3) if rms else None,
        "rms_um_by_field": [round(f["rms_um"], 2) if math.isfinite(f["rms_um"]) else None for f in m["fields"]],
        "mtf_freq_lpmm": round(task.freq, 1), "n_lenses": m["n_lenses"],
    }
