"""Ray-trace verification: the patent's own numbers are the checksum.

For each prescription we rebuild the lens in Optiland and compare recomputed
first-order values with the values the patent states (EFL, TTL, ImgH at the
stated half-field), then check focus and image quality. A transcription error
(sign flip, dropped exponent, swapped digits) almost always breaks at least one
of these. Result: status = verified | verified_refined | needs_review | failed.

Index precision: many CN filings print nd to 2 decimals (1.54 / 56.1). That
rounding alone moves EFL by ~1-2 % and defocuses an F/2 phone lens by ~0.1 mm.
`refine_indices` therefore solves for per-material index offsets inside the
rounding interval (|dn| <= 0.005) that restore the claimed EFL and focus. The
refined values are stored separately and flagged; the published numbers are
never overwritten.
"""
from __future__ import annotations

import copy
import math
import warnings
from contextlib import contextmanager

import numpy as np

from ..schema import Prescription
from . import metrics as M
from .build import build_optic

TOL = {
    "efl_rel": 0.01,       # 1 %
    "ttl_abs": 0.02,       # mm (or 0.5 %)
    "ttl_rel": 0.005,
    "imgh_rel": 0.03,      # real chief-ray height vs stated ImgH
    "defocus_dof": 3.0,    # |defocus| <= 3 x (2 lambda F^2)
    "rms_um": 15.0,        # mean polychromatic RMS spot over fields, at the image plane
}


@contextmanager
def quiet():
    with warnings.catch_warnings(), np.errstate(all="ignore"):
        warnings.simplefilter("ignore")
        yield


def _two_decimal(x: float | None) -> bool:
    return x is not None and abs(round(x, 2) - x) < 1e-12 and abs(round(x, 3) - x) < 1e-12 and \
        abs(x * 100 - round(x * 100)) < 1e-9


def material_groups(p: Prescription) -> dict[tuple, list[int]]:
    g: dict[tuple, list[int]] = {}
    for i, s in enumerate(p.surfaces):
        if s.nd and s.nd > 1.0 and not s.glass:
            g.setdefault((s.nd, s.vd), []).append(i)
    return g


def _with_offsets(p: Prescription, groups, dn) -> Prescription:
    q = copy.deepcopy(p)
    for (key, idx), d in zip(groups.items(), dn):
        for i in idx:
            q.surfaces[i].nd = key[0] + float(d)
    return q


def refine_indices(p: Prescription, fno: float, hfov: float, bound: float = 0.005):
    """Least-squares index offsets (within rounding) to match claimed EFL and focus."""
    from scipy.optimize import least_squares

    groups = {k: v for k, v in material_groups(p).items() if _two_decimal(k[0])}
    if not groups:
        return None
    f_claim = p.claimed.get("efl")
    dof = 2 * 0.5876e-3 * fno ** 2

    def resid(dn):
        q = _with_offsets(p, groups, dn)
        with quiet():
            op, _ = build_optic(q, fno=fno, hfov_deg=hfov, fields=(0.0,))
            r = [M.paraxial_defocus(op) / dof]
            if f_claim:
                r.append((M.efl(op) - f_claim) / (0.002 * f_claim))
        return np.array(r + list(np.asarray(dn) / bound * 0.3))  # mild regulariser

    sol = least_squares(resid, np.zeros(len(groups)), bounds=(-bound, bound), xtol=1e-10)
    q = _with_offsets(p, groups, sol.x)
    return q, {f"{k[0]}/{k[1]}": round(k[0] + float(d), 5) for k, d in zip(groups, sol.x)}


def evaluate(p: Prescription, fno: float | None = None, hfov: float | None = None,
             rel_fields=(0.0, 0.5, 0.7, 0.85, 1.0), freq_lpmm: float | None = None, num_rings: int = 6) -> dict:
    """Compute metrics for a prescription (no pass/fail)."""
    with quiet():
        op, info = build_optic(p, fno=fno, hfov_deg=hfov, fields=rel_fields)
        fno_, hfov_ = info["fno"], info["hfov_deg"]
        out = {"efl": M.efl(op), "fno": M.fno(op), "ttl": p.ttl(), "defocus": M.paraxial_defocus(op),
               "hfov_deg": hfov_, "assumptions": info["assumptions"], "n_lenses": p.lens_count()}
        try:
            y = M.chief_ray_height(op, 1.0)
            yp_arr = np.asarray(op.paraxial.chief_ray()[0], dtype=float).ravel()
            yp = float(yp_arr[-1])
            out["imgh_real"] = abs(y)
            out["distortion_pct"] = 100 * (abs(y) - abs(yp)) / abs(yp) if yp else float("nan")
        except Exception:
            out["imgh_real"] = float("nan")
            out["distortion_pct"] = float("nan")
        f = freq_lpmm or 0.25 / (0.5876e-3 * fno_)  # quarter of the diffraction cutoff
        out["mtf_freq_lpmm"] = f
        sm = M.spot_and_mtf(op, rel_fields, f, num_rings=num_rings)
        out["fields"] = sm
        # Patents omit clear apertures, so the extreme field may be vignetted.
        # Fields up to 0.85 must all trace; the full field is used if it traces.
        core = [d for d in sm if d["Hy"] <= 0.85 + 1e-9]
        usable = [d for d in sm if math.isfinite(d["rms_um"])]
        ok = all(math.isfinite(d["rms_um"]) for d in core)
        out["rms_um_mean"] = float(np.mean([d["rms_um"] for d in usable])) if ok and usable else float("inf")
        out["full_field_vignetted"] = any(not math.isfinite(d["rms_um"]) for d in sm if d["Hy"] > 0.85 + 1e-9)
        out["mtf_mean"] = float(np.mean([(d["mtf_t"] + d["mtf_s"]) / 2 for d in sm]))
        out["airy_um"] = M.airy_radius_um(fno_)
        out["min_center_thickness"] = min([t for _, t in M.center_thicknesses(p)] or [float("nan")])
        out["min_edge_thickness"] = M.edge_thickness(op, p)
    return out


def _checks(p: Prescription, m: dict) -> dict:
    c = p.claimed
    res: dict[str, dict] = {}
    if "efl" in c:
        err = (m["efl"] - c["efl"]) / c["efl"]
        res["efl"] = {"claimed": c["efl"], "computed": round(m["efl"], 4), "rel_err": round(err, 4),
                      "pass": abs(err) <= TOL["efl_rel"]}
    if "ttl" in c:
        err = m["ttl"] - c["ttl"]
        res["ttl"] = {"claimed": c["ttl"], "computed": round(m["ttl"], 4), "abs_err": round(err, 4),
                      "pass": abs(err) <= max(TOL["ttl_abs"], TOL["ttl_rel"] * c["ttl"])}
    if "imgh" in c and "hfov_deg" in c and math.isfinite(m.get("imgh_real", float("nan"))):
        err = (m["imgh_real"] - c["imgh"]) / c["imgh"]
        res["imgh"] = {"claimed": c["imgh"], "computed": round(m["imgh_real"], 4), "rel_err": round(err, 4),
                       "pass": abs(err) <= TOL["imgh_rel"]}
    dof = 2 * 0.5876e-3 * m["fno"] ** 2
    res["focus"] = {"defocus_mm": round(m["defocus"], 4), "dof_mm": round(dof, 4),
                    "pass": abs(m["defocus"]) <= TOL["defocus_dof"] * dof}
    res["image_quality"] = {"rms_um_mean": round(m["rms_um_mean"], 3) if math.isfinite(m["rms_um_mean"]) else None,
                            "limit_um": TOL["rms_um"], "pass": m["rms_um_mean"] <= TOL["rms_um"]}
    return res


def verify(p: Prescription, refine: bool = True, **kw) -> dict:
    """Verify a prescription; writes the result into p.verification and returns it."""
    warns = list(p.provenance.get("warnings", []))
    m = evaluate(p, **kw)
    checks = _checks(p, m)
    status = "verified" if all(v["pass"] for v in checks.values()) else "needs_review"
    out = {"status": status, "checks": checks, "metrics": _round(m), "tolerances": TOL}
    if status != "verified" and refine:
        try:
            r = refine_indices(p, fno=m["fno"], hfov=m["hfov_deg"])
        except Exception as exc:
            r = None
            warns.append(f"index refinement failed: {exc.__class__.__name__}")
        if r:
            q, nd_map = r
            m2 = evaluate(q, fno=m["fno"], hfov=m["hfov_deg"], **{k: v for k, v in kw.items() if k not in ("fno", "hfov")})
            c2 = _checks(p, m2)
            out["refined"] = {"nd": nd_map, "checks": c2, "metrics": _round(m2)}
            if all(v["pass"] for v in c2.values()):
                out["status"] = "verified_refined"
    final_checks = out.get("refined", {}).get("checks") or checks
    if out["status"].startswith("verified") and "efl" not in final_checks:
        # quality and focus pass, but no first-order checksum from the patent text
        out["status"] = "plausible"
        warns.append("patent text gives no EFL for this embodiment: first-order checksum unavailable")
    if any("no aspheric-coefficient table" in w or "truncated" in w for w in warns):
        out["status"] = "needs_review"
    # Untraceable designs stay failed even when index refinement was attempted
    # and also failed to trace. Previously any refinement attempt suppressed
    # the failed label and left a dead prescription in needs_review.
    ref_rms = ((out.get("refined") or {}).get("metrics") or {}).get("rms_um_mean")
    refined_traced = isinstance(ref_rms, (int, float)) and math.isfinite(ref_rms)
    if out["status"] not in ("verified", "verified_refined", "plausible") and not math.isfinite(m["rms_um_mean"]) and not refined_traced:
        out["status"] = "failed"
    out["notes"] = warns
    out["failed_checks"] = [k for k, v in (out.get("refined", {}).get("checks") or checks).items() if not v["pass"]]
    p.verification = out
    return out


def _round(m: dict) -> dict:
    def r(v):
        if isinstance(v, float):
            return None if not math.isfinite(v) else round(v, 5)
        if isinstance(v, dict):
            return {k: r(x) for k, x in v.items()}
        if isinstance(v, list):
            return [r(x) for x in v]
        return v
    return r(m)


def suggest_fixes(p: Prescription, max_suggestions: int = 5) -> list[dict]:
    """Try common OCR/transcription errors and report single edits that restore EFL.

    Candidates: radius sign flip; radius digit shift (x10, /10); thickness x10, /10.
    """
    if "efl" not in p.claimed:
        return []
    f0 = p.claimed["efl"]
    out = []
    with quiet():
        base_op, info = build_optic(p, fields=(0.0,))
        base_err = abs(M.efl(base_op) - f0) / f0
        for i, s in enumerate(p.surfaces):
            if s.role not in ("surface",):
                continue
            edits = []
            if math.isfinite(s.radius):
                edits += [("radius", -s.radius, "sign flip"), ("radius", s.radius * 10, "x10"), ("radius", s.radius / 10, "/10")]
            if 0 < s.thickness < 50:
                edits += [("thickness", s.thickness * 10, "x10"), ("thickness", s.thickness / 10, "/10")]
            for attr, val, why in edits:
                q = copy.deepcopy(p)
                setattr(q.surfaces[i], attr, val)
                try:
                    op, _ = build_optic(q, fno=info["fno"], hfov_deg=info["hfov_deg"], fields=(0.0,))
                    err = abs(M.efl(op) - f0) / f0
                except Exception:
                    continue
                if err < base_err / 5 and err < TOL["efl_rel"]:
                    out.append({"surface": s.name, "field": attr, "from": getattr(s, attr), "to": val,
                                "kind": why, "efl_rel_err_after": round(err, 5)})
    return sorted(out, key=lambda d: d["efl_rel_err_after"])[:max_suggestions]
