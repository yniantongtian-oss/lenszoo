"""Corpus audit, triage, and spec search. No ray tracing.

``audit`` checks the files on disk: each prescription loads, its id matches
the filename, the folder matches ``verification.status``, and ``failed_checks``
matches the stored pass/fail flags. ``classify`` explains why a design is not
usable. ``search_designs`` ranks the usable corpus with the same spec distance
the benchmark baselines use.

Promoting a file from ``needs_review`` is a separate step. It requires a fresh
``verify`` to reach ``verified``, ``verified_refined`` or ``plausible``. This
module never relabels a design.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

from .schema import Prescription

FOLDER_FOR = {
    "verified": "verified",
    "verified_refined": "verified",
    "plausible": "plausible",
    "needs_review": "needs_review",
    "failed": "failed",
}

# Decimal radii used as names (24.15, -13.7). Bare indices such as "1" are real surface numbers.
_FLOAT_NAME = re.compile(r"^[+-]?(?:\d+\.\d+|\.\d+)$")

# Most specific reason first. A file can carry several reasons; the report
# groups it under the first one that applies.
_PRIORITY = (
    "misparsed_surface_names",
    "aspheres_only_in_image",
    "asphere_coefficients_truncated",
    "asphere_rows_unmatched",
    "untraceable",
    "first_order_checksum",
    "defocus_and_spots",
    "focus_only",
    "image_quality_only",
    "no_efl_checksum",
    "aperture_or_field_assumed",
    "image_row_appended",
    "other",
)

_REASON_TEXT = {
    "misparsed_surface_names": "Surface names are numeric radii. The header was not recognised and the coefficient table could not attach. The stored prescription is not a lens.",
    "aspheres_only_in_image": "The surface table marks aspheres, but the coefficient table was an image. Even-asphere terms are missing, so the ray trace is of the base conic only.",
    "asphere_coefficients_truncated": "The text mentions higher-order coefficients than the text tables contain. The missing orders are enough to move focus and spot size.",
    "asphere_rows_unmatched": "Coefficient rows did not match surface names (stop written as STO+S1, 2(APE), or a bare index). Those coefficients are not in the JSON; recovering them needs a re-extract.",
    "untraceable": "The pupil does not trace. Stored under failed/ when the whole prescription is unusable.",
    "first_order_checksum": "EFL, TTL or image height disagrees with the patent text. A single-edit suggestion may exist via `lenszoo fixes`, but the file was not rewritten.",
    "defocus_and_spots": "Paraxial focus and the published image plane disagree, and the spots at that plane are large. See the CN105116519B note below before treating this as a checker bug.",
    "focus_only": "Spots pass, but the image plane is outside 3x the diffraction depth of focus. No EFL checksum, or the focal length already matches.",
    "image_quality_only": "First order and focus pass (after index recovery when it ran). Mean RMS spot is over the 15 µm gate. Several of these are fast lenses or were traced at an assumed F/2 and 30°.",
    "no_efl_checksum": "The patent text gives no EFL, so a passing trace can only reach plausible, never verified.",
    "aperture_or_field_assumed": "F-number or half-field is missing, so the checker assumed F/2.0 and/or 30°. Spot size under that assumption is not the patent's claim.",
    "image_row_appended": "The table had no image row. One was appended after the last surface, which moves the image plane.",
    "other": "Does not match a named bucket. Read verification.checks in the file.",
}


def _warnings(p: Prescription) -> list[str]:
    notes = list((p.verification or {}).get("notes") or [])
    prov = list((p.provenance or {}).get("warnings") or [])
    return notes + prov


def _checks(p: Prescription) -> dict:
    v = p.verification or {}
    return (v.get("refined") or {}).get("checks") or v.get("checks") or {}


def classify(p: Prescription) -> dict:
    """Reason codes for one prescription, from stored verification only."""
    warnings = _warnings(p)
    failed = list((p.verification or {}).get("failed_checks") or [])
    reasons: list[str] = []
    if any(_FLOAT_NAME.match(s.name) for s in p.surfaces):
        reasons.append("misparsed_surface_names")
    if any("no aspheric-coefficient table" in w for w in warnings):
        reasons.append("aspheres_only_in_image")
    if any("truncated" in w for w in warnings):
        reasons.append("asphere_coefficients_truncated")
    if any(w.startswith("aspheric row") and "no matching surface" in w for w in warnings):
        reasons.append("asphere_rows_unmatched")
    if (p.verification or {}).get("status") == "failed":
        reasons.append("untraceable")
    if any(key in failed for key in ("efl", "ttl", "imgh")):
        reasons.append("first_order_checksum")
    if "focus" in failed and "image_quality" in failed:
        reasons.append("defocus_and_spots")
    elif failed == ["focus"]:
        reasons.append("focus_only")
    elif failed == ["image_quality"]:
        reasons.append("image_quality_only")
    if "efl" not in p.claimed:
        reasons.append("no_efl_checksum")
    if "fno" not in p.claimed or "hfov_deg" not in p.claimed:
        reasons.append("aperture_or_field_assumed")
    if any("no image row" in w for w in warnings):
        reasons.append("image_row_appended")
    if not reasons:
        reasons.append("other")
    primary = next(code for code in _PRIORITY if code in reasons)
    iq = _checks(p).get("image_quality") or {}
    focus = _checks(p).get("focus") or {}
    return {
        "id": p.id,
        "status": (p.verification or {}).get("status"),
        "patent": (p.source or {}).get("patent"),
        "primary": primary,
        "reasons": reasons,
        "failed_checks": failed,
        "rms_um": iq.get("rms_um_mean"),
        "defocus_mm": focus.get("defocus_mm"),
        "efl": p.claimed.get("efl"),
        "fno": p.claimed.get("fno"),
        "hfov_deg": p.claimed.get("hfov_deg"),
    }


def _failed_set(p: Prescription) -> set[str]:
    return {key for key, row in _checks(p).items() if not row.get("pass")}


def audit(designs: str | Path) -> dict:
    """Structural audit. Returns a JSON-serialisable report. Does not trace."""
    root = Path(designs)
    errors: list[dict] = []
    rows: list[dict] = []
    by_status: Counter[str] = Counter()
    for path in sorted(root.rglob("*.json")):
        rel = str(path.relative_to(root))
        try:
            p = Prescription.load(path)
        except Exception as exc:
            errors.append({"path": rel, "error": f"{exc.__class__.__name__}: {exc}"})
            continue
        if p.id != path.stem:
            errors.append({"path": rel, "error": f"id {p.id!r} does not match filename"})
        status = (p.verification or {}).get("status")
        by_status[status or "?"] += 1
        expected = FOLDER_FOR.get(status or "")
        if path.parent.name != expected:
            errors.append({"path": rel, "error": f"status {status!r} stored in folder {path.parent.name!r}"})
        stored = set((p.verification or {}).get("failed_checks") or [])
        actual = _failed_set(p)
        if stored != actual:
            errors.append({"path": rel, "error": f"failed_checks {sorted(stored)} != checks {sorted(actual)}"})
        rows.append(classify(p))
    review = [row for row in rows if row["status"] == "needs_review"]
    return {
        "ok": not errors,
        "designs": len(rows),
        "errors": errors,
        "by_status": dict(by_status),
        "needs_review": len(review),
        "needs_review_primary": dict(Counter(row["primary"] for row in review)),
        "rows": rows,
    }


def search_designs(designs: str | Path, *, efl: float, fno: float = 2.0, hfov_deg: float = 30.0,
                   ttl_max: float | None = None, max_elements: int | None = None, limit: int = 5) -> list[dict]:
    """Nearest usable designs by the baseline spec distance. No ray tracing."""
    from .bench.baseline import design_spec, load_corpus, spec_distance
    from .bench.tasks import Task

    if not math.isfinite(efl) or efl <= 0:
        raise ValueError("efl must be a positive finite number")
    task = Task(
        id="search",
        title="search",
        prompt="",
        spec={
            "efl": float(efl),
            "fno": float(fno),
            "hfov_deg": float(hfov_deg),
            "ttl_max": float(ttl_max) if ttl_max is not None else float(efl) * 1.2,
        },
        constraints={"max_elements": max_elements} if max_elements else {},
    )
    ranked = sorted(load_corpus(designs), key=lambda p: (spec_distance(task, p), p.id))
    out = []
    for p in ranked[: max(0, limit)]:
        spec = design_spec(p)
        distance = spec_distance(task, p)
        out.append({
            "id": p.id,
            "status": p.verification.get("status"),
            "distance": None if not math.isfinite(distance) else round(distance, 4),
            "efl": spec.get("efl"),
            "fno": spec.get("fno"),
            "hfov_deg": spec.get("hfov_deg"),
            "elements": spec.get("n"),
            "patent": p.source.get("patent"),
            "assignee": p.source.get("assignee"),
        })
    return out


_INVESTIGATION = """\
## Near misses that were re-traced and not promoted

Checked with Optiland 0.6.3 and the existing gates (EFL 1%, TTL 0.02 mm or 0.5%,
focus within 3x the diffraction depth of focus, mean RMS spot <= 15 µm).
None of these reach `verified` or `plausible`.

* **CN214751066U-ex8** (3P macro, F/1.46, object at 9 mm). Stored refined check:
  focus passes after a 2-decimal index recovery, mean RMS 20.97 µm. The
  unrecovered trace is RMS 15.16 µm at the default 6-ring pupil and defocus
  0.105 mm. The sibling ex5 (F/3.27) is `verified_refined`. ex8 is a fast
  lens over the spot gate, not a mis-filed pass.
* **CN110794552B-ex4** and **CN114740587B-ex3** fail image quality only, at
  22.6 µm and 24.9 µm. Left in review.
* **CN105116519B ex5 and ex11** (the defocus mystery in the v0.1 README).
  EFL and TTL already match. Sweeping the last air gap on Optiland 0.6.3
  (4-ring pupil) drops ex11 from RMS 33.9 µm / defocus +0.233 mm to RMS 4.0 µm
  at +0.20 mm, and ex5 from 41.7 µm / +0.217 mm to 4.0 µm at the same shift.
  That shift moves TTL by 0.20 mm, which fails the TTL checksum against the
  printed thicknesses. The published image distance is short of the paraxial
  focus; the file cannot pass both gates at once. ex12 has the same stored
  signature (defocus 0.21 mm, RMS 36 µm). **ex4, ex7, ex8, ex9 and ex10**
  stay at RMS of hundreds of micrometres across ±0.4 mm of focus, so they are
  not a back-focal typo. ex10 still duplicates another embodiment's S9 row.
* **CN112882200B-ex1 and ex2** fail focus only and quote no EFL, so the best
  status they could earn is `plausible`. ex1 is at 5x the depth of focus
  (limit 3x). Not promoted.

Designs whose coefficient rows did not match (`STO+S1`, `2(APE)`, bare
indices) cannot be repaired from the JSON. The parser now accepts those
aliases on a new extract; the stored files do not contain the dropped numbers.
"""


def render_triage(report: dict) -> str:
    """Markdown triage of a report from ``audit``."""
    review = [row for row in report["rows"] if row["status"] == "needs_review"]
    groups: dict[str, list[dict]] = {code: [] for code in _PRIORITY}
    for row in review:
        groups.setdefault(row["primary"], []).append(row)
    lines = [
        "# Needs-review triage",
        "",
        "Structural audit of `data/designs`. No file was moved. A design is promoted only when `lenszoo verify` reaches `verified`, `verified_refined` or `plausible` under the gates in `lenszoo.verify.check.TOL`.",
        "",
        f"Designs: {report['designs']}. Needs review: {report['needs_review']}. Structural errors: {len(report['errors'])}.",
        "",
        "## Stored status",
        "",
        "| status | count |",
        "|---|---|",
    ]
    for status, count in sorted(report["by_status"].items()):
        lines.append(f"| {status} | {count} |")
    lines += ["", "## Primary reason among needs_review", "", "| reason | count |", "|---|---|"]
    for code, count in sorted(report["needs_review_primary"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {code} | {count} |")
    lines += ["", _INVESTIGATION.rstrip(), ""]
    for code in _PRIORITY:
        bucket = groups.get(code) or []
        if not bucket:
            continue
        lines += ["", f"## {code} ({len(bucket)})", "", _REASON_TEXT.get(code, ""), "", "| id | failed checks | RMS µm | EFL | F/# | HFOV |", "|---|---|---|---|---|---|"]
        for row in bucket:
            failed = ", ".join(row["failed_checks"]) or "-"
            rms = "-" if row["rms_um"] is None else row["rms_um"]
            lines.append(
                f"| {row['id']} | {failed} | {rms} | {row['efl'] if row['efl'] is not None else '-'} | "
                f"{row['fno'] if row['fno'] is not None else '-'} | {row['hfov_deg'] if row['hfov_deg'] is not None else '-'} |"
            )
    lines.append("")
    return "\n".join(lines)
