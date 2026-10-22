"""Turn prescription tables (rows of strings) into LensZoo Surfaces.

This module is source-agnostic: rows can come from Google Patents HTML
(`lenszoo.extract.gpatents`) or from an OCR / vision-model backend
(`lenszoo.extract.ocr`). Keeping one code path means OCR output gets exactly
the same normalisation and the same ray-trace checks.
"""
from __future__ import annotations

# Chinese patent text is written as \uXXXX escapes so the source stays ASCII/English-only;
# the strings reproduce real CN table headers (surface no., radius, thickness, nd, vd, conic, ...).
import math
import re

from ..schema import INF, Surface

# ------------------------------------------------------------ number parsing
_INF_WORDS = ("\u65e0\u7a77", "infinity", "inf", "∞", "\u65e0\u9650", "\u5e73\u9762", "plano", "flat")
_MINUS = str.maketrans({"\uff0d": "-", "−": "-", "–": "-", "﹣": "-", "\uff0b": "+", "\uff0e": ".", "\uff0c": ","})


def parse_number(s: str | None) -> float | None:
    """Parse patent-style numbers: '-1.0220E-02', '3.5×10^-3', 'infinity' (or its Chinese equivalent), '1.54'."""
    if s is None:
        return None
    t = str(s).strip().translate(_MINUS).replace(" ", "")
    if not t or t in ("-", "/", "—", "--", "*"):
        return None
    low = t.lower()
    if any(w == low or low == "-" + w for w in _INF_WORDS) or low.startswith("\u65e0\u7a77") or low == "∞":
        return -INF if low.startswith("-") else INF
    t = re.sub(r"[×xX\*]10\^?\(?([+-]?\d+)\)?", r"e\1", t)
    t = t.replace("E+", "e").replace("E", "e")
    m = re.fullmatch(r"[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?", t)
    if not m:
        return None
    return float(t)


# ------------------------------------------------------------ header mapping
def _norm(h: str) -> str:
    h = re.sub(r"[(\uff08]\s*mm\s*[)\uff09]", "", h)
    return re.sub(r"[\s()\uff08\uff09/]", "", h).lower()


_RULES = [
    ("material", lambda n: ("\u6298\u5c04\u7387" in n and ("\u963f\u8d1d" in n or "\u8272\u6563" in n)) or n in ("nd/vd", "nd,vd")),
    ("type", lambda n: "\u7c7b\u578b" in n or n == "\u9762\u578b"),
    ("name", lambda n: n.startswith(("\u9762\u53f7", "\u9762\u5e8f\u53f7", "\u8868\u9762\u5e8f\u53f7", "\u9762\u7f16\u53f7", "\u8868\u9762\u7f16\u53f7", "\u5e8f\u53f7"))
        or n in ("\u9762", "surface", "s", "si", "no.", "no", "i")),
    ("radius", lambda n: "\u66f2\u7387\u534a\u5f84" in n or "\u534a\u5f84" in n or n in ("r", "ri", "radius")),
    ("thickness", lambda n: any(k in n for k in ("\u539a\u5ea6", "\u95f4\u9694", "\u95f4\u8ddd", "\u8ddd\u79bb", "thickness"))
        or n in ("d", "di", "t")),
    ("efl_el", lambda n: "\u7126\u8ddd" in n),
    ("nd", lambda n: "\u6298\u5c04\u7387" in n or n in ("nd", "n")),
    ("vd", lambda n: "\u963f\u8d1d" in n or "\u8272\u6563" in n or n in ("vd", "v", "abbe", "νd", "ν", "υd")),
    ("conic", lambda n: "\u5706\u9525" in n or "\u4e8c\u6b21\u66f2\u9762" in n or n in ("k", "conic")),
    ("material2", lambda n: "\u6750\u6599" in n or "\u73bb\u7483" in n or "material" in n),
]


def map_header(cells: list[str]) -> dict[int, str]:
    """Map column index -> canonical key for a surface-table header row."""
    out: dict[int, str] = {}
    used: set[str] = set()
    for i, c in enumerate(cells):
        n = _norm(c)
        if not n:
            continue
        for key, rule in _RULES:
            if key not in used and rule(n):
                out[i] = "material" if key == "material2" and "material" not in used else key
                used.add(out[i])
                break
    if "name" not in used and 0 not in out:
        out[0] = "name"          # unlabeled first column = surface number
    return out


def is_surface_table(rows: list[list[str]]) -> bool:
    if len(rows) < 4:
        return False
    hdr = map_header(rows[0])
    keys = set(hdr.values())
    return "radius" in keys and "thickness" in keys and ("nd" in keys or "material" in keys)


_ASPH_HDR = re.compile(r"^A(\d{1,2})$")


def aspheric_header(cells: list[str]) -> dict[int, str] | None:
    """Return column->coefficient map for aspheric tables, or None.

    Supports 'A4 A6 ...' and the older 'K A B C D E' (A=r^4) convention.
    """
    norm = [re.sub(r"[\s<>/sup]", "", c) for c in cells]
    out: dict[int, str] = {}
    for i, c in enumerate(norm):
        m = _ASPH_HDR.match(c)
        if m and int(m.group(1)) % 2 == 0 and int(m.group(1)) >= 4:
            out[i] = f"A{int(m.group(1))}"
        elif c.upper() in ("K", "CONIC") or c in ("\u5706\u9525\u7cfb\u6570", "k"):
            out[i] = "conic"
    if sum(1 for v in out.values() if v.startswith("A")) >= 2:
        return out
    letters = {"A": 4, "B": 6, "C": 8, "D": 10, "E": 12, "F": 14, "G": 16, "H": 18, "J": 20}
    out = {}
    for i, c in enumerate(norm):
        if c in letters:
            out[i] = f"A{letters[c]}"
        elif c.upper() == "K" or c == "\u5706\u9525\u7cfb\u6570":
            out[i] = "conic"
    if sum(1 for v in out.values() if v.startswith("A")) >= 3:
        return out
    return None


def _clean_name(s: str) -> str:
    s = re.sub(r"[\s*\uff0a^]", "", s).upper()
    return s


def _name_keys(name: str) -> set[str]:
    """Names that should resolve to this surface in an asphere table.

    Patents write the stop as ``2(APE)``, ``9(ST)`` or ``STO+S1`` in the
    surface table and as ``2`` / ``S2`` / ``S1`` in the coefficient table.
    Exact names always win; aliases are used only when they are unambiguous.
    """
    raw = _clean_name(name)
    if not raw:
        return set()
    keys = {raw}
    base = re.sub(r"\([^)]*\)", "", raw)
    pieces = [base, *re.split(r"[+/&]", base)]
    for part in pieces:
        part = part.strip()
        if not part:
            continue
        keys.add(part)
        if part.isdigit():
            keys.add("S" + part)
        elif part.startswith("S") and part[1:].isdigit():
            keys.add(part[1:])
    return {key for key in keys if key}


_STOP_RX = re.compile(r"(STO|STOP|\(ST\)|^ST$|\(S\)|APE|\u5149\u9611|\u5b54\u5f84)")


def rows_to_surfaces(rows: list[list[str]]) -> tuple[list[Surface], list[str]]:
    """Convert a surface table into Surfaces. Returns (surfaces, warnings)."""
    warns: list[str] = []
    hdr = map_header(rows[0])
    col = {v: k for k, v in hdr.items()}
    surfs: list[Surface] = []
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        get = lambda key: (r[col[key]] if key in col and col[key] < len(r) else "")  # noqa: E731
        name = _clean_name(get("name") or (r[0] if r else ""))
        if not name or name in ("\u9762\u53f7",):
            continue
        R = parse_number(get("radius"))
        d = parse_number(get("thickness"))
        nd = parse_number(get("nd"))
        vd = parse_number(get("vd"))
        k = parse_number(get("conic"))
        mat = get("material").strip()
        glass = None
        if nd is None and re.search(r"\d\s*[/,\uff0c:]\s*\d", get("nd") or ""):
            mat, nd = get("nd"), None
        if mat and nd is None:
            m = re.match(r"([\d.]+)\s*[/:,\uff0c]\s*([\d.]+)", mat)
            if m:
                nd, vd = float(m.group(1)), float(m.group(2))
            elif re.search(r"[A-Za-z]", mat):
                glass = mat
        if nd is not None and not (1.0 < nd < 2.6):
            warns.append(f"{name}: nd={nd} implausible, ignored")
            nd = None
        role = "surface"
        if name.startswith("OBJ") or name in ("\u7269\u9762", "OB", "0") and not surfs:
            role = "object"
        elif name.startswith("IMA") or name in ("\u50cf\u9762", "IMG", "IM"):
            role = "image"
        is_stop = bool(_STOP_RX.search(name))
        if is_stop and R is None:
            R = INF
        if R is None:
            R = INF
            if role == "surface" and not is_stop:
                warns.append(f"{name}: missing radius, assumed plane")
        s = Surface(name=name, radius=R, thickness=d if d is not None else 0.0, nd=nd, vd=vd,
                    glass=glass, conic=k or 0.0, is_stop=is_stop,
                    role=role if not is_stop else "stop")
        surfs.append(s)
    # object row
    if not surfs or surfs[0].role != "object":
        surfs.insert(0, Surface(name="OBJ", radius=INF, thickness=INF, role="object"))
    # image row: last row with no thickness, or append one
    last = surfs[-1]
    if last.role != "image":
        if math.isinf(last.radius) and last.thickness == 0.0 and last.nd is None and len(surfs) > 3:
            last.role = "image"
        else:
            surfs.append(Surface(name="IMA", radius=INF, thickness=0.0, role="image"))
            warns.append("no image row in table; appended image after last row")
    # object thickness default infinite
    if surfs[0].thickness == 0.0:
        surfs[0].thickness = INF
    return surfs, warns


def apply_aspheric(surfs: list[Surface], rows: list[list[str]]) -> list[str]:
    """Merge an aspheric-coefficient table into surfaces (in place)."""
    warns = []
    hdr = aspheric_header(rows[0])
    if hdr is None:
        return ["not an aspheric table"]
    exact = {s.name: s for s in surfs}
    alias: dict[str, Surface] = {}
    ambiguous: set[str] = set()
    for s in surfs:
        for key in _name_keys(s.name):
            if key in exact:
                continue
            if key in alias and alias[key] is not s:
                ambiguous.add(key)
                alias.pop(key, None)
            elif key not in ambiguous:
                alias[key] = s

    def resolve(name: str) -> Surface | None:
        if name in exact:
            return exact[name]
        for key in _name_keys(name):
            if key in exact:
                return exact[key]
            if key in alias:
                return alias[key]
        return None

    for r in rows[1:]:
        if not r:
            continue
        h2 = aspheric_header(r)
        if h2 is not None:      # repeated header (split A4-A16 / A18-A30 tables)
            hdr = h2
            continue
        name = _clean_name(r[0])
        tgt = resolve(name)
        if tgt is None:
            if name:
                warns.append(f"aspheric row {name}: no matching surface")
            continue
        for i, key in hdr.items():
            if i >= len(r):
                continue
            v = parse_number(r[i])
            if v is None:
                continue
            if key == "conic":
                tgt.conic = v
            else:
                tgt.aspheric[key] = v
    return warns
