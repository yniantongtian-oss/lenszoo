"""Optical metrics computed with Optiland (NumPy backend).

All lengths in mm unless the name says _um.
"""
from __future__ import annotations

import math

import numpy as np


def _np(x):
    return np.asarray(x, dtype=float)


def efl(op) -> float:
    return float(op.paraxial.f2())


def fno(op) -> float:
    return float(op.paraxial.FNO())


def paraxial_defocus(op) -> float:
    """Distance from the image surface to the paraxial focus (mm, + = behind)."""
    y, u = op.paraxial.marginal_ray()
    y, u = _np(y).ravel(), _np(u).ravel()
    return float(-y[-1] / u[-1]) if u[-1] != 0 else float("nan")


def chief_ray_height(op, Hy: float = 1.0, wavelength: float | None = None) -> float:
    wl = wavelength or op.primary_wavelength
    rays = op.trace_generic(0.0, Hy, 0.0, 0.0, wl)
    return float(_np(rays.y).ravel()[0])


def distortion_pct(op, hfov_deg: float, Hy: float = 1.0) -> float:
    """f-tan(theta) distortion at relative field Hy, in percent."""
    y_real = chief_ray_height(op, Hy)
    y_ideal = efl(op) * math.tan(math.radians(hfov_deg * Hy))
    return 100.0 * (y_real - y_ideal) / y_ideal if y_ideal else 0.0


def _spot_xy(op, Hy: float, num_rings: int = 8):
    xs, ys = [], []
    lost = 0
    total = 0
    for wl in op.wavelengths.get_wavelengths():
        rays = op.trace(0.0, Hy, wl, num_rings, "hexapolar")
        x, y = _np(rays.x).ravel(), _np(rays.y).ravel()
        inten = _np(rays.i).ravel()
        ok = np.isfinite(x) & np.isfinite(y) & (inten > 0)
        total += x.size
        lost += int((~ok).sum())
        xs.append(x[ok])
        ys.append(y[ok])
    return np.concatenate(xs), np.concatenate(ys), lost, total


def spot_and_mtf(op, rel_fields, freq_lpmm: float, num_rings: int = 8) -> list[dict]:
    """Polychromatic RMS spot (about centroid) and geometric MTF (T and S) per field."""
    out = []
    for Hy in rel_fields:
        try:
            x, y, lost, total = _spot_xy(op, Hy, num_rings)
        except Exception as e:  # ray failure (TIR, missed surface)
            out.append({"Hy": Hy, "error": str(e)[:120], "rms_um": float("inf"), "mtf_t": 0.0, "mtf_s": 0.0,
                        "vignetted_frac": 1.0})
            continue
        if x.size < 3:
            out.append({"Hy": Hy, "rms_um": float("inf"), "mtf_t": 0.0, "mtf_s": 0.0, "vignetted_frac": 1.0})
            continue
        # Patents rarely list clear apertures, so a few rim rays can sweep through
        # asphere zones a real barrel would block. Reject gross outliers
        # (> 10x median radius + 5 um) and report how many were rejected.
        cx, cy = np.median(x), np.median(y)
        r = np.hypot(x - cx, y - cy)
        keep = r <= 10 * np.median(r) + 0.005
        rejected = 1 - keep.mean()
        x, y = x[keep], y[keep]
        dx, dy = x - x.mean(), y - y.mean()
        rms = math.sqrt(float(np.mean(dx ** 2 + dy ** 2)))
        w = 2 * math.pi * freq_lpmm
        mt = abs(np.mean(np.exp(1j * w * dy)))
        ms = abs(np.mean(np.exp(1j * w * dx)))
        lost_frac = lost / max(total, 1)
        if lost_frac + rejected > 0.4:   # too much of the pupil missing: not a usable field
            rms = float("inf")
        out.append({"Hy": Hy, "rms_um": rms * 1e3, "mtf_t": float(mt), "mtf_s": float(ms),
                    "vignetted_frac": lost_frac, "outlier_frac": float(rejected)})
    return out


def airy_radius_um(fno_: float, wl_um: float = 0.5876) -> float:
    return 1.22 * wl_um * fno_


def center_thicknesses(p) -> list[tuple[str, float]]:
    """(name, thickness) of glass/plastic elements, from the prescription."""
    out = []
    for s in p.surfaces:
        if s.role in ("surface", "stop") and s.nd and s.nd > 1.0:
            out.append((s.name, s.thickness))
    return out


def edge_thickness(op, p, Hy: float = 1.0) -> float:
    """Approximate minimum element edge thickness at the clear aperture (mm).

    Uses sag of each element's two surfaces at the marginal ray height of the
    full field (upper rim ray) -- a cheap manufacturability proxy.
    """
    try:
        sg = op.surfaces
        heights = []
        for Py in (1.0, -1.0):
            r = op.trace_generic(0.0, Hy, 0.0, Py, op.primary_wavelength)
            heights.append(np.abs(_np(sg.y)[:, 0]))
        r0 = op.trace_generic(0.0, 0.0, 0.0, 1.0, op.primary_wavelength)
        heights.append(np.abs(_np(sg.y)[:, 0]))
        h = np.max(np.vstack(heights), axis=0)
        del r, r0
        mins = []
        for i, s in enumerate(p.surfaces[:-1]):
            if s.role in ("surface", "stop") and s.nd and s.nd > 1.0:
                a, b = sg.surfaces[i], sg.surfaces[i + 1]
                hh = float(max(h[i], h[i + 1]))
                za = float(_np(a.geometry.sag(0.0, hh)).ravel()[0])
                zb = float(_np(b.geometry.sag(0.0, hh)).ravel()[0])
                mins.append(s.thickness - za + zb)
        return float(min(mins)) if mins else float("nan")
    except Exception:
        return float("nan")
