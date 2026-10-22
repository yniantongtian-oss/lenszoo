"""Extract lens prescriptions from Google Patents CN pages (text tables).

Findings that shaped this module (probe of ~700 CN lens patents, 2026-10-09):
* Google Patents serves the CNIPA full text as HTML. Aspheric-coefficient tables
  are usually real <table> elements, but the main surface table (R, d, nd, vd, k)
  is an image in most Sunny/AAC filings ("patent-image-not-available" or a
  BDA*.png figure). Only ~6% of probed patents had at least one surface table in
  text. Image tables go to `lenszoo.extract.ocr` (vision-model hook).
* Empty cells are preserved as empty <td>, so header-based column mapping works.
* Embodiments are sequential: a surface table opens an embodiment, following
  aspheric tables belong to it, and the claimed f / TTL / ImgH / Fno / HFOV
  appear in the text or in a parameter table in the same span.
"""
from __future__ import annotations

# Chinese patent text is written as \uXXXX escapes so the source stays ASCII/English-only;
# the strings reproduce real CN table headers (surface no., radius, thickness, nd, vd, conic, ...).
import html as _html
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..schema import Prescription
from .tables import apply_aspheric, aspheric_header, is_surface_table, rows_to_surfaces

UA = "Mozilla/5.0 (X11; Linux x86_64) lenszoo/0.1 (+research; polite crawler)"
BASE = "https://patents.google.com/patent/{pub}/zh"


def fetch(pub: str, cache_dir: str | Path | None = "data/raw", timeout: int = 40) -> str:
    """Fetch a Google Patents page (Chinese full text), with an on-disk cache."""
    import requests

    if cache_dir:
        p = Path(cache_dir) / f"{pub}.html"
        if p.exists() and p.stat().st_size > 10000:
            return p.read_text(encoding="utf-8")
    r = requests.get(BASE.format(pub=pub), headers={"User-Agent": UA}, timeout=timeout)
    r.raise_for_status()
    if cache_dir:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(r.text, encoding="utf-8")
        time.sleep(1.0)  # be polite
    return r.text


# ------------------------------------------------------------------ html utils
def _cell_text(c: str) -> str:
    c = _html.unescape(c)
    c = re.sub(r"[×xX]\s*10\s*<sup>\s*([+\-\uff0d−]?\s*\d+)\s*</sup>", lambda m: "e" + m.group(1).replace(" ", ""), c)
    c = re.sub(r"<sup>(.*?)</sup>", r"^\1", c)
    c = re.sub(r"<[^>]+>", "", c)
    return _html.unescape(c).strip()


def table_rows(table_html: str) -> list[list[str]]:
    rows = []
    for tr in re.findall(r"<tr.*?</tr>", table_html, re.S):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
        rows.append([_cell_text(td) for td in cells])
    return [r for r in rows if r]


def _text(fragment: str) -> str:
    t = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", _html.unescape(t))


_NUMREF = re.compile(r"&#(x[0-9a-fA-F]+|[0-9]+);")


def _decode_numeric_refs(page: str) -> str:
    """Turn non-ASCII numeric character references (e.g. CJK written as &#x8868;)
    into the characters themselves, so regexes see the same text as on a page
    served as raw UTF-8. ASCII references (markup such as &#60;) are left alone."""
    def sub(m: re.Match) -> str:
        v = m.group(1)
        cp = int(v[1:], 16) if v[0] in "xX" else int(v)
        return chr(cp) if cp > 127 else m.group(0)
    return _NUMREF.sub(sub, page)


def _table_label(caption: str) -> str:
    """Normalize a Chinese table caption ('Table 3' written as U+8868 + '3') to 'Table 3'."""
    return re.sub(r"\u8868\s*(\d+)", r"Table \1", caption).strip()


def metadata(page: str) -> dict:
    def meta(name, scheme=None):
        pat = rf'<meta name="{name}" content="([^"]*)"' + (rf'\s+scheme="{scheme}"' if scheme else "")
        return re.findall(pat, page)

    title = re.search(r"<title>(.*?)</title>", page, re.S)
    t = title.group(1).split(" - ")[1].strip() if title and " - " in title.group(1) else ""
    num = (meta("citation_patent_number") or meta("citation_patent_application_number") or [""])[0]
    return {
        "title": t,
        "assignee": ", ".join(meta("DC.contributor", "assignee")),
        "inventors": meta("DC.contributor", "inventor"),
        "date": (meta("DC.date", "issue") or meta("DC.date", "dateSubmitted") or [""])[0],
        "filed": (meta("DC.date", "dateSubmitted") or [""])[0],
        "number": num,
        "pdf_url": (meta("citation_pdf_url") or [""])[0],
    }


# --------------------------------------------------------------- claimed specs
_F = r"([0-9]+(?:\.[0-9]+)?)"
_CLAIM_PATTERNS = {
    "efl": [rf"(?:\u603b\u6709\u6548\u7126\u8ddd|\u6709\u6548\u7126\u8ddd|\u7cfb\u7edf\u7126\u8ddd|\u6574\u4f53\u7126\u8ddd)\s*f\s*[=\uff1d\u4e3a:\uff1a]\s*{_F}", rf"(?<![0-9a-zA-Z_])f\s*[=\uff1d]\s*{_F}\s*mm"],
    "ttl": [rf"TTL\s*[=\uff1d\u4e3a:\uff1a]\s*{_F}"],
    "imgh": [rf"ImgH\s*[=\uff1d\u4e3a:\uff1a]\s*{_F}", rf"\u50cf\u9ad8\s*(?:IH|Y|ImgH)?\s*[=\uff1d\u4e3a]\s*{_F}"],
    "fno": [rf"(?:Fno|FNO|F\u6570|Fno\.|\u5149\u5708\u503c|F/#)\s*[=\uff1d\u4e3a:\uff1a]\s*{_F}"],
    "hfov_deg": [rf"(?:HFOV|Semi-FOV|\u534a\u89c6\u573a\u89d2|\u534a\u89c6\u89d2|\u6700\u5927\u534a\u89c6\u573a\u89d2|ω)\s*[=\uff1d\u4e3a:\uff1a]\s*{_F}"],
    "fov_deg": [rf"(?<![\u534aSemi\-H])(?:FOV|\u6700\u5927\u89c6\u573a\u89d2|\u5168\u89c6\u573a\u89d2)\s*[=\uff1d\u4e3a:\uff1a]\s*{_F}"],
}


_PLAUSIBLE = {"efl": (0.3, 2000), "ttl": (0.5, 2000), "imgh": (0.2, 200), "fno": (0.7, 32),
              "hfov_deg": (2, 100), "fov_deg": (4, 200), "bfl": (0.05, 500)}


def sane(d: dict[str, float]) -> dict[str, float]:
    """Drop values outside plausible ranges (regex hits on condition formulas)."""
    out = {k: v for k, v in d.items() if k not in _PLAUSIBLE or _PLAUSIBLE[k][0] <= v <= _PLAUSIBLE[k][1]}
    if "hfov_deg" not in out and "fov_deg" in out:
        out["hfov_deg"] = out["fov_deg"] / 2
    out.pop("fov_deg", None)
    return out


def claims_from_text(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, pats in _CLAIM_PATTERNS.items():
        for p in pats:
            for m in re.finditer(p, text):
                v = float(m.group(1))
                if key not in _PLAUSIBLE or _PLAUSIBLE[key][0] <= v <= _PLAUSIBLE[key][1]:
                    out[key] = v
                    break
            if key in out:
                break
    return sane(out)


_PARAM_LABELS = [
    ("efl", re.compile(r"^(f|f\(mm\)|efl|\u6709\u6548\u7126\u8dddf?\(?mm\)?)$", re.I)),
    ("ttl", re.compile(r"^ttl(\(mm\))?$", re.I)),
    ("imgh", re.compile(r"^(imgh|ih)(\(mm\))?$", re.I)),
    ("fno", re.compile(r"^(fno|f\u6570|fno\.|f/#)$", re.I)),
    ("hfov_deg", re.compile(r"^(hfov|semi-fov|\u534a\u89c6\u573a\u89d2)(\(°\)|\(deg\)|°)?$", re.I)),
    ("fov_deg", re.compile(r"^(fov|\u89c6\u573a\u89d2)(\(°\)|\(deg\)|°)?$", re.I)),
]


def _label(cell: str) -> str | None:
    c = re.sub(r"\s+", "", cell)
    for key, rx in _PARAM_LABELS:
        if rx.match(c):
            return key
    return None


def claims_from_param_table(rows: list[list[str]]) -> dict[str, float]:
    """Key/value parameter tables (one embodiment): a 'Parameter f1 f2 ...' row
    followed by a 'Value ...' row (Chinese headers in the source patents)."""
    from .tables import parse_number

    out: dict[str, float] = {}
    for i in range(len(rows) - 1):
        a, b = rows[i], rows[i + 1]
        if a and b and re.sub(r"\s", "", a[0]) in ("\u53c2\u6570", "Parameter") and len(a) == len(b):
            for k, v in zip(a[1:], b[1:]):
                key = _label(k)
                val = parse_number(v)
                if key and val is not None:
                    out[key] = val
    # row-label layout: 'f(mm) 4.05' per row
    for r in rows:
        if len(r) == 2:
            key, val = _label(r[0]), parse_number(r[1])
            if key and val is not None:
                out.setdefault(key, val)
    if "hfov_deg" not in out and "fov_deg" in out:
        out["hfov_deg"] = out["fov_deg"] / 2
    out.pop("fov_deg", None)
    return out


def claims_from_summary_table(rows: list[list[str]]) -> dict[int, dict[str, float]]:
    """Multi-embodiment tables whose header is 'Parameter/Embodiment 1 2 3 ...'."""
    from .tables import parse_number

    if not rows or len(rows[0]) < 3:
        return {}
    heads = [re.sub(r"\D", "", h) for h in rows[0][1:]]
    if not all(h.isdigit() for h in heads):
        return {}
    idx = [int(h) for h in heads]
    out: dict[int, dict[str, float]] = {i: {} for i in idx}
    for r in rows[1:]:
        key = _label(r[0]) if r else None
        if not key:
            continue
        for e, v in zip(idx, r[1:]):
            val = parse_number(v)
            if val is not None:
                out[e][key] = val
    for d in out.values():
        if "hfov_deg" not in d and "fov_deg" in d:
            d["hfov_deg"] = d["fov_deg"] / 2
        d.pop("fov_deg", None)
    return {k: v for k, v in out.items() if v}


# ------------------------------------------------------------------- results
@dataclass
class ExtractionReport:
    pub: str
    prescriptions: list[Prescription] = field(default_factory=list)
    image_tables: list[dict] = field(default_factory=list)  # tables only available as images
    warnings: list[str] = field(default_factory=list)


_CN_DIGITS = "\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d"
_CN_TEN = "\u5341"


def embodiment_number(token: str) -> int | None:
    """Parse an embodiment index written with Arabic or Chinese numerals."""
    e = token.strip()
    if e.isdigit():
        return int(e)
    if not e or any(ch not in _CN_DIGITS + _CN_TEN for ch in e):
        return None
    if e == _CN_TEN:
        return 10
    if e.startswith(_CN_TEN) and len(e) == 2 and e[1] in _CN_DIGITS:
        return 10 + _CN_DIGITS.index(e[1]) + 1
    if e.endswith(_CN_TEN) and len(e) == 2 and e[0] in _CN_DIGITS:
        return (_CN_DIGITS.index(e[0]) + 1) * 10
    if len(e) == 3 and e[1] == _CN_TEN and e[0] in _CN_DIGITS and e[2] in _CN_DIGITS:
        return (_CN_DIGITS.index(e[0]) + 1) * 10 + _CN_DIGITS.index(e[2]) + 1
    if len(e) == 1 and e in _CN_DIGITS:
        return _CN_DIGITS.index(e) + 1
    return None


def _description(page: str) -> str:
    i = page.find('itemprop="description"')
    if i < 0:
        return page
    j = page.find("</section>", i)
    return page[i: j if j > 0 else None]


def extract_page(page: str, pub: str) -> ExtractionReport:
    rep = ExtractionReport(pub=pub)
    page = _decode_numeric_refs(page)
    meta = metadata(page)
    desc = _description(page)
    tables = [(m.start(), m.end(), table_rows(m.group(0)))
              for m in re.finditer(r"<table[^>]*>.*?</table>", desc, re.S)]

    # image-only tables: placeholders followed by a 'Table N' caption (Chinese: \u8868N)
    for m in re.finditer(r'(patent-image-not-available|<img[^>]+src="([^"]+)")[^\u8868]{0,400}?>\s*(\u8868\s*\d+)\s*<', desc):
        rep.image_tables.append({"caption": _table_label(m.group(3)), "image_url": m.group(2) or None,
                                 "pdf_url": meta["pdf_url"]})

    # merge header-less continuation tables (page breaks split long tables)
    merged: list[tuple[int, int, list[list[str]]]] = []
    for t in tables:
        rows = t[2]
        if merged and rows and re.match(r"^\*?S?\d+[A-Z]?\*?$", rows[0][0].strip().upper()) \
                and not _text(desc[merged[-1][1]:t[0]]).strip() \
                and (aspheric_header(merged[-1][2][0]) or is_surface_table(merged[-1][2])) \
                and len(rows[0]) == len(merged[-1][2][0]):
            merged[-1] = (merged[-1][0], t[1], merged[-1][2] + rows)
        else:
            merged.append(t)
    tables = merged

    surf_idx = [i for i, t in enumerate(tables) if is_surface_table(t[2])]
    summary: dict[int, dict] = {}
    for _, _, rows in tables:
        summary.update(claims_from_summary_table(rows) or {})

    def emb_before(pos: int, window: int = 400) -> int | None:
        found = re.findall(r"(?:\u5b9e\u65bd\u4f8b|\u4f8b\u5b50|\u5b9e\u65bd\u65b9\u5f0f|\u793a\u4f8b)\s*([0-9]+|[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+)", _text(desc[max(0, pos - window): pos]))
        if not found:
            return None
        return embodiment_number(found[-1])

    surf_emb = {ti: emb_before(tables[ti][0]) for ti in surf_idx}
    asph_idx = [k for k, t in enumerate(tables) if t[2] and aspheric_header(t[2][0]) and k not in surf_idx]
    owner: dict[int, int] = {}
    for k in asph_idx:
        e = emb_before(tables[k][0], 300)
        cands = [ti for ti in surf_idx if surf_emb[ti] == e and e is not None]
        if cands:
            owner[k] = cands[0]
        else:  # sequential fallback: last surface table before it
            prev = [ti for ti in surf_idx if ti < k]
            if prev:
                owner[k] = prev[-1]

    for n, ti in enumerate(surf_idx):
        start, end, rows = tables[ti]
        nxt = tables[surf_idx[n + 1]][0] if n + 1 < len(surf_idx) else len(desc)
        post_text = _text(re.sub(r"<table.*?</table>", " ", desc[end:nxt], flags=re.S))
        pre_text = _text(desc[max(0, start - 600): start])
        surfs, w = rows_to_surfaces(rows)
        warns = list(w)
        asph_used = [k for k in asph_idx if owner.get(k) == ti]
        for k in asph_used:
            warns += apply_aspheric(surfs, tables[k][2])
        # embodiment number
        emb_no = surf_emb[ti]
        if emb_no:
            # stop at the heading of the next embodiment so its numbers are not borrowed
            m_next = re.search(rf"(?:\u5b9e\u65bd\u4f8b|\u4f8b\u5b50|\u5b9e\u65bd\u65b9\u5f0f)\s*(?!{emb_no}(?!\d))[0-9\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+", post_text)
            if m_next:
                post_text = post_text[:m_next.start()]
        claimed = claims_from_text(post_text)
        if emb_no:
            m_pre = list(re.finditer(rf"(?:\u5b9e\u65bd\u4f8b|\u4f8b\u5b50)\s*{emb_no}(?!\d)", pre_text))
            if m_pre:
                for kk, vv in claims_from_text(pre_text[m_pre[-1].end():]).items():
                    claimed.setdefault(kk, vv)
        for k in range(ti + 1, len(tables)):
            if k in surf_idx:
                break
            for kk, vv in claims_from_param_table(tables[k][2]).items():
                claimed.setdefault(kk, vv)
        if emb_no and emb_no in summary:
            for kk, vv in summary[emb_no].items():
                claimed.setdefault(kk, vv)
        claimed = sane(claimed)
        cap = re.search(r"^\s*(?:</[^>]+>\s*)*(?:<[^>]+>\s*)*(\u8868\s*\d+)", desc[end:end + 400])
        # truncated coefficient sets: text mentions A30 but tables only reach A16
        mentioned = [int(x) for x in re.findall(r"A\s*(?:<sub>)?\s*(\d{1,2})\s*(?:</sub>)?", desc[start:nxt])
                     if x.isdigit() and int(x) % 2 == 0 and 4 <= int(x) <= 40]
        have = [int(k[1:]) for s_ in surfs for k in s_.aspheric]
        if asph_used and mentioned and have and max(mentioned) > max(have):
            warns.append(f"aspheric coefficients truncated: text mentions up to A{max(mentioned)}, "
                         f"text tables give up to A{max(have)} (rest likely in an image table)")
        has_asph_type = any("\u975e\u7403\u9762" in (r[1] if len(r) > 1 else "") for r in rows[1:])
        if has_asph_type and not asph_used:
            warns.append("table marks aspheric surfaces but no aspheric-coefficient table was found in text (image?)")
        pid = f"{pub}-ex{emb_no or n + 1}"
        while any(q.id == pid for q in rep.prescriptions):
            pid += "b"
        p = Prescription(
            id=pid,
            surfaces=surfs,
            source={"patent": pub, "url": BASE.format(pub=pub), "title": meta["title"], "assignee": meta["assignee"],
                    "date": meta["date"], "embodiment": emb_no or n + 1,
                    "table": _table_label(cap.group(1)) if cap else None, "pdf_url": meta["pdf_url"]},
            claimed=claimed,
            provenance={"method": "google_patents_text_table", "extractor": "lenszoo.extract.gpatents 0.2",
                        "aspheric_tables": len(asph_used), "warnings": warns},
        )
        rep.prescriptions.append(p)
    if not surf_idx:
        rep.warnings.append("no text surface table found; see image_tables for OCR fallback")
    return rep


def extract(pub: str, cache_dir: str | Path | None = "data/raw") -> ExtractionReport:
    return extract_page(fetch(pub, cache_dir=cache_dir), pub)
