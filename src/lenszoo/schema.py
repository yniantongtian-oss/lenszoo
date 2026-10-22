"""LensZoo prescription schema (v0.1).

A prescription is a plain JSON document. Units: millimetres, degrees, micrometres
for wavelengths. Infinite radius / thickness is written as the string "inf".

Surface rows follow patent convention: the medium (nd/vd or glass) on a row is the
medium *after* that surface, the thickness is the axial distance to the next row.
Aspheric coefficients use the even-asphere sag

    z = c r^2 / (1 + sqrt(1 - (1+k) c^2 r^2)) + A4 r^4 + A6 r^6 + ...

stored as {"A4": .., "A6": ..}. (Optiland indexes coefficients from r^2, so the
builder inserts A2 = 0; see lenszoo.verify.build.)
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "0.1"
INF = math.inf


def _num(x: Any) -> float | None:
    if x is None:
        return None
    if isinstance(x, str):
        if x.strip().lower() in ("inf", "infinity", "+inf"):
            return INF
        if x.strip().lower() in ("-inf", "-infinity"):
            return -INF
        return float(x)
    return float(x)


def _out(x: float | None):
    if x is None:
        return None
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    return x


@dataclass
class Surface:
    name: str                       # "S1", "STO", "IMA" ...
    radius: float = INF             # mm, INF = plane
    thickness: float = 0.0          # mm to next row (INF allowed for object)
    nd: float | None = None         # medium after surface; None = air
    vd: float | None = None
    glass: str | None = None        # catalog glass, "NAME" or "NAME|catalog" (e.g. "H-ZF52|cdgm")
    conic: float = 0.0
    aspheric: dict[str, float] = field(default_factory=dict)  # {"A4": ...}
    is_stop: bool = False
    role: str = "surface"           # object | stop | surface | image

    def to_dict(self) -> dict:
        d = asdict(self)
        d["radius"] = _out(self.radius)
        d["thickness"] = _out(self.thickness)
        if not d["aspheric"]:
            d.pop("aspheric")
        return {k: v for k, v in d.items() if v is not None}

    @classmethod
    def from_dict(cls, d: dict) -> "Surface":
        d = dict(d)
        d["radius"] = _num(d.get("radius", "inf"))
        d["thickness"] = _num(d.get("thickness", 0.0))
        d["aspheric"] = {k: float(v) for k, v in (d.get("aspheric") or {}).items()}
        allowed = {item.name for item in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in allowed})

    @property
    def is_aspheric(self) -> bool:
        return any(v != 0 for v in self.aspheric.values()) or self.conic != 0


@dataclass
class Prescription:
    id: str
    surfaces: list[Surface]
    source: dict[str, Any] = field(default_factory=dict)
    # values the patent states (used as checksums): efl, fno, hfov_deg, ttl, imgh, bfl
    claimed: dict[str, float] = field(default_factory=dict)
    wavelengths_um: list[float] = field(default_factory=lambda: [0.4861327, 0.5875618, 0.6562725])
    primary_wavelength_um: float = 0.5875618
    provenance: dict[str, Any] = field(default_factory=dict)
    verification: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    # ------------------------------------------------------------------ io
    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "source": self.source,
            "claimed": self.claimed,
            "wavelengths_um": self.wavelengths_um,
            "primary_wavelength_um": self.primary_wavelength_um,
            "surfaces": [s.to_dict() for s in self.surfaces],
            "provenance": self.provenance,
            "verification": self.verification,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Prescription":
        validate(d)
        return cls(
            id=d["id"],
            surfaces=[Surface.from_dict(s) for s in d["surfaces"]],
            source=d.get("source", {}),
            claimed={k: float(v) for k, v in (d.get("claimed") or {}).items() if v is not None},
            wavelengths_um=d.get("wavelengths_um") or [0.4861327, 0.5875618, 0.6562725],
            primary_wavelength_um=d.get("primary_wavelength_um", 0.5875618),
            provenance=d.get("provenance", {}),
            verification=d.get("verification", {}),
            schema_version=d.get("schema_version", SCHEMA_VERSION),
        )

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "Prescription":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    # ------------------------------------------------------------- helpers
    @property
    def optical_surfaces(self) -> list[Surface]:
        return [s for s in self.surfaces if s.role in ("surface", "stop")]

    def lens_count(self) -> int:
        """Number of elements with a non-air medium, excluding plane-parallel plates."""
        n = 0
        rows = self.optical_surfaces
        for i, s in enumerate(rows):
            if s.nd and s.nd > 1.0 and i + 1 < len(rows):
                nxt = rows[i + 1]
                if not (math.isinf(s.radius) and math.isinf(nxt.radius)):
                    n += 1
        return n

    def ttl(self) -> float:
        """Axial distance from the first refracting surface vertex to the image."""
        rows = self.surfaces
        start = None
        for i, s in enumerate(rows):
            if s.role == "surface" and (not math.isinf(s.radius) or (s.nd or 1.0) > 1.0):
                start = i
                break
        if start is None:
            return float("nan")
        return float(sum(s.thickness for s in rows[start:] if s.role != "image"))

    def scaled(self, k: float, new_id: str | None = None) -> "Prescription":
        """Return a copy scaled by factor k (radii, thicknesses, asphere terms)."""
        if not math.isfinite(k) or k <= 0:
            raise ValueError("scale factor must be a positive finite number")
        surfs = []
        for s in self.surfaces:
            d = s.to_dict()
            t = Surface.from_dict(d)
            if not math.isinf(t.radius):
                t.radius *= k
            if not math.isinf(t.thickness) and t.role != "object":
                t.thickness *= k
            t.aspheric = {a: v * k ** (1 - int(a[1:])) for a, v in t.aspheric.items()}
            surfs.append(t)
        p = Prescription.from_dict(self.to_dict())
        p.surfaces = surfs
        p.id = new_id or f"{self.id}@x{k:.4g}"
        p.claimed = {kk: (v * k if kk in ("efl", "ttl", "imgh", "bfl") else v) for kk, v in self.claimed.items()}
        p.verification = {}
        return p


# --------------------------------------------------------------- validation
_REQUIRED_TOP = ("id", "surfaces")


class SchemaError(ValueError):
    pass


def validate(d: dict) -> None:
    """Light-weight validation (no jsonschema dependency)."""
    if not isinstance(d, dict):
        raise SchemaError("prescription must be an object")
    for k in _REQUIRED_TOP:
        if k not in d:
            raise SchemaError(f"missing key: {k}")
    surfs = d["surfaces"]
    if not isinstance(surfs, list) or len(surfs) < 3:
        raise SchemaError("need at least object, one surface and image")
    if not all(isinstance(s, dict) for s in surfs):
        raise SchemaError("surface rows must be objects")
    roles = [s.get("role", "surface") for s in surfs]
    if roles[0] != "object":
        raise SchemaError("first surface must have role 'object'")
    if roles[-1] != "image":
        raise SchemaError("last surface must have role 'image'")
    for s in surfs:
        for field in ('radius', 'thickness'):
            if field in s:
                try:
                    value = _num(s[field])
                except (TypeError, ValueError) as exc:
                    raise SchemaError(f"invalid {field} on {s.get('name')}") from exc
                if value is None or math.isnan(value):
                    raise SchemaError(f"invalid {field} on {s.get('name')}")
        for field in ('conic', 'vd'):
            if s.get(field) is not None:
                _finite(s[field], f"{field} on {s.get('name')}")
        for a in (s.get("aspheric") or {}):
            if not (a.startswith("A") and a[1:].isdigit() and int(a[1:]) % 2 == 0 and int(a[1:]) >= 4):
                raise SchemaError(f"bad aspheric key {a} on {s.get('name')}")
            _finite(s['aspheric'][a], f"{a} on {s.get('name')}")
        nd = s.get("nd")
        if nd is not None and not (1.0 <= float(nd) <= 2.6):
            raise SchemaError(f"implausible nd {nd} on {s.get('name')}")
    wavelengths = d.get('wavelengths_um')
    if wavelengths is not None:
        if not isinstance(wavelengths, list) or not wavelengths:
            raise SchemaError("wavelengths_um must be a nonempty array")
        for value in wavelengths:
            if _finite(value, 'wavelength') <= 0:
                raise SchemaError("wavelengths must be positive")
    if 'primary_wavelength_um' in d and _finite(d['primary_wavelength_um'], 'primary wavelength') <= 0:
        raise SchemaError("primary wavelength must be positive")


def _finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SchemaError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise SchemaError(f"{label} must be finite")
    return number


JSON_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "LensZoo prescription",
    "type": "object",
    "required": ["id", "surfaces"],
    "properties": {
        "schema_version": {"type": "string"},
        "id": {"type": "string", "description": "e.g. CN114740587B-ex1"},
        "source": {"type": "object", "properties": {
            "patent": {"type": "string"}, "url": {"type": "string"}, "title": {"type": "string"},
            "assignee": {"type": "string"}, "date": {"type": "string"}, "embodiment": {"type": "integer"},
            "table": {"type": ["string", "null"]}}},
        "claimed": {"type": "object", "properties": {k: {"type": "number"} for k in
                    ("efl", "fno", "hfov_deg", "ttl", "imgh", "bfl")}},
        "wavelengths_um": {"type": "array", "items": {"type": "number"}},
        "primary_wavelength_um": {"type": "number"},
        "surfaces": {"type": "array", "minItems": 3, "items": {"type": "object", "required": ["name"], "properties": {
            "name": {"type": "string"},
            "role": {"enum": ["object", "stop", "surface", "image"]},
            "radius": {"type": ["number", "string"]},
            "thickness": {"type": ["number", "string"]},
            "nd": {"type": "number"}, "vd": {"type": "number"}, "glass": {"type": "string"},
            "conic": {"type": "number"},
            "aspheric": {"type": "object", "additionalProperties": False,
                         "patternProperties": {"^A([468]|[1-9][02468])$": {"type": "number"}}},
            "is_stop": {"type": "boolean"}}}},
        "provenance": {"type": "object"},
        "verification": {"type": "object"},
    },
}
