"""Build an Optiland `Optic` from a LensZoo prescription."""
from __future__ import annotations

import math
import warnings

from ..schema import Prescription, Surface

DEFAULT_FNO = 2.0          # used only when the patent states no F-number (flagged)
DEFAULT_FIELDS = (0.0, 0.5, 0.7, 0.85, 1.0)


def _material(s: Surface):
    from optiland.materials import AbbeMaterial, IdealMaterial

    if s.glass:
        # "F2|schott" pins the catalog; bare names can resolve to another maker's glass
        if "|" in s.glass:
            name, cat = s.glass.split("|", 1)
            return (name.strip(), cat.strip())
        return s.glass
    if s.nd is None or s.nd <= 1.0001:
        return "air"
    if s.vd:
        return AbbeMaterial(s.nd, s.vd, model="buchdahl")
    return IdealMaterial(n=s.nd)


def _coeffs(s: Surface) -> list[float]:
    if not s.aspheric:
        return []
    order = max(int(k[1:]) for k in s.aspheric)
    # Optiland: coefficients[i] multiplies r^(2(i+1)), i.e. index 0 is r^2.
    return [s.aspheric.get(f"A{2 * (i + 1)}", 0.0) for i in range(order // 2)]


def build_optic(p: Prescription, fno: float | None = None, hfov_deg: float | None = None,
                fields=DEFAULT_FIELDS, ray_aiming: str | None = None):
    """Return (optic, assumptions). fno/hfov default to the patent's claimed values."""
    from optiland import optic as _optic

    from ._patches import apply as _apply_patches

    _apply_patches()

    assumptions: list[str] = []
    op = _optic.Optic()
    rows = p.surfaces
    has_stop = any(s.is_stop for s in rows)
    try:
        first_refr = next(i for i, s in enumerate(rows) if s.role == "surface")
    except StopIteration:
        try:
            first_refr = next(i for i, s in enumerate(rows) if s.role == "stop")
        except StopIteration as exc:
            raise ValueError("prescription has no optical surface") from exc
        assumptions.append("no refracting surface: stop used as the first optical surface")
    stop_at = first_refr
    if not has_stop:
        # an unlabeled plane air/air surface between lenses is the aperture stop
        lens_rows = [i for i, s in enumerate(rows) if s.nd and s.nd > 1 and not math.isinf(s.radius)]
        last_lens = max(lens_rows) if lens_rows else 0
        for i in range(first_refr + 1, last_lens):
            s, prev = rows[i], rows[i - 1]
            if math.isinf(s.radius) and not s.nd and not prev.nd and s.role == "surface":
                stop_at = i
                break
        assumptions.append("no stop labelled: " + (f"plane air surface {rows[stop_at].name} used as stop"
                           if stop_at != first_refr else "stop placed at first refracting surface"))
    for i, s in enumerate(rows):
        kw = dict(index=i, radius=s.radius, thickness=s.thickness, material=_material(s))
        if s.role == "image":
            kw.pop("thickness")
        if s.is_stop or (not has_stop and i == stop_at):
            kw["is_stop"] = True
        if s.aspheric or s.conic:
            kw.update(surface_type="even_asphere", conic=s.conic, coefficients=_coeffs(s), max_iter=60, tol=1e-9)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            op.surfaces.add(**kw)

    for w in p.wavelengths_um:
        op.wavelengths.add(value=w, is_primary=abs(w - p.primary_wavelength_um) < 1e-6)
    fno = fno or p.claimed.get("fno")
    if not fno:
        fno = DEFAULT_FNO
        assumptions.append(f"F-number not stated: assumed F/{DEFAULT_FNO}")
    op.set_aperture(aperture_type="imageFNO", value=float(fno))

    if hfov_deg is None:
        hfov_deg = p.claimed.get("hfov_deg")
    if not hfov_deg:
        efl = float(op.paraxial.f2())
        imgh = p.claimed.get("imgh")
        if imgh and efl > 0:
            hfov_deg = math.degrees(math.atan(imgh / efl))
            assumptions.append("HFOV not stated: paraxial atan(ImgH/f) used")
        else:
            hfov_deg = 30.0
            assumptions.append("HFOV and ImgH not stated: assumed 30 deg")
    op.fields.set_type(field_type="angle")
    for f in fields:
        op.fields.add(y=float(f) * float(hfov_deg))
    if ray_aiming:
        op.ray_tracer.set_aiming(ray_aiming)
    return op, {"assumptions": assumptions, "fno": float(fno), "hfov_deg": float(hfov_deg)}
