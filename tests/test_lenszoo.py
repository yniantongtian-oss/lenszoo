# Chinese patent text is written as \uXXXX escapes so the source stays ASCII/English-only;
# the strings reproduce real CN table headers (surface no., radius, thickness, nd, vd, conic, ...).
import copy
import json
import math
import warnings
from pathlib import Path

import numpy as np
import pytest

warnings.filterwarnings("ignore")
np.seterr(all="ignore")

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "mini_patent.html"
VERIFIED = ROOT / "data" / "designs" / "verified" / "CN105116519B-ex2.json"
T01 = ROOT / "data" / "tasks" / "T01-main7p-f4.04.json"


# ---------------------------------------------------------------- parsing
def test_parse_number_variants():
    from lenszoo.extract.tables import parse_number

    assert parse_number("-1.0220E-02") == pytest.approx(-0.01022)
    assert parse_number("3.5×10^-3") == pytest.approx(3.5e-3)
    assert parse_number("\uff0d2.5") == -2.5
    assert math.isinf(parse_number("\u65e0\u7a77"))
    assert parse_number("--") is None
    assert parse_number("1.544/56.11") is None


def test_header_mapping_and_rows():
    from lenszoo.extract.tables import map_header, rows_to_surfaces

    hdr = ["\u9762\u53f7", "\u8868\u9762\u7c7b\u578b", "\u66f2\u7387\u534a\u5f84", "\u539a\u5ea6/\u8ddd\u79bb", "\u7126\u8ddd", "\u6298\u5c04\u7387", "\u8272\u6563\u7cfb\u6570", "\u5706\u9525\u7cfb\u6570"]
    m = map_header(hdr)
    assert {m[0], m[2], m[3], m[5], m[6], m[7]} == {"name", "radius", "thickness", "nd", "vd", "conic"}
    rows = [hdr,
            ["OBJ", "\u7403\u9762", "\u65e0\u7a77", "\u65e0\u7a77", "", "", "", ""],
            ["STO", "\u7403\u9762", "\u65e0\u7a77", "-0.5435", "", "", "", ""],
            ["S1", "\u975e\u7403\u9762", "2.1164", "0.7019", "5.84", "1.54", "56.1", "-0.0688"],
            ["S2", "\u975e\u7403\u9762", "5.5561", "0.5", "", "", "", "-12.1597"],
            ["S3", "\u7403\u9762", "\u65e0\u7a77", "", "", "", "", ""]]
    surfs, warns = rows_to_surfaces(rows)
    assert [s.role for s in surfs] == ["object", "stop", "surface", "surface", "image"]
    assert surfs[2].nd == 1.54 and surfs[2].vd == 56.1 and surfs[2].conic == -0.0688
    assert surfs[3].nd is None


def test_combined_nd_vd_column_and_letter_aspheres():
    from lenszoo.extract.tables import apply_aspheric, rows_to_surfaces

    rows = [["\u8868\u9762\u7f16\u53f7", "\u8868\u9762\u7c7b\u578b", "\u66f2\u7387\u534a\u5f84", "\u539a\u5ea6", "\u6298\u5c04\u7387/\u963f\u8d1d\u6570", "\u5706\u9525\u7cfb\u6570"],
            ["OBJ", "\u7403\u9762", "\u65e0\u7a77", "\u65e0\u7a77", "--", "--"],
            ["S1", "\u975e\u7403\u9762", "1.8947", "0.5787", "1.544/56.11", "0.0727"],
            ["S2", "\u975e\u7403\u9762", "8.4586", "0.3", "--", "-42.97"],
            ["S3", "\u7403\u9762", "\u65e0\u7a77", "", "", ""]]
    surfs, _ = rows_to_surfaces(rows)
    assert surfs[1].nd == 1.544 and surfs[1].vd == 56.11
    apply_aspheric(surfs, [["\u9762\u5e8f\u53f7", "K", "A", "B", "C"], ["S1", "-1.3", "-3.8e-3", "1.4e-4", "1.8e-6"]])
    assert surfs[1].conic == -1.3 and surfs[1].aspheric == {"A4": -3.8e-3, "A6": 1.4e-4, "A8": 1.8e-6}


def test_extract_fixture_page():
    from lenszoo.extract.gpatents import extract_page

    rep = extract_page(FIX.read_text(encoding="utf-8"), "CN000000000X")
    assert len(rep.prescriptions) == 1
    p = rep.prescriptions[0]
    assert p.source["embodiment"] == 2
    assert p.claimed == {"efl": 4.04, "ttl": 4.67, "fno": 2.2, "hfov_deg": 36.4}
    # continuation table (S9..S14, no header) and escaped <sup> exponents both parsed
    s14 = next(s for s in p.surfaces if s.name == "S14")
    assert len(s14.aspheric) == 7
    assert rep.image_tables and rep.image_tables[0]["caption"] == "Table 5"


# ------------------------------------------------------------ build / verify
def test_build_matches_optiland_sample():
    """Our schema -> Optiland builder reproduces Optiland's own Cooke triplet EFL."""
    from optiland.samples.objectives import CookeTriplet

    from lenszoo.schema import Prescription, Surface
    from lenszoo.verify import build_optic

    ref = CookeTriplet()
    sg = ref.surfaces.surfaces
    z = [float(np.asarray(x.geometry.cs.z).ravel()[0]) for x in sg]
    rows = [Surface("OBJ", thickness=math.inf, role="object")]
    for i in range(1, len(sg) - 1):
        mat = sg[i].material_post
        glass = getattr(mat, "name", None)
        if glass == "F2":
            glass = "F2|schott"  # bare "F2" resolves to a different catalog's F2
        rows.append(Surface(f"S{i}", radius=float(sg[i].geometry.radius), thickness=z[i + 1] - z[i],
                            glass=glass if glass and glass.lower() != "air" else None,
                            is_stop=sg[i].is_stop, role="stop" if sg[i].is_stop else "surface"))
    rows.append(Surface("IMA", role="image"))
    p = Prescription(id="cooke", surfaces=rows, claimed={"fno": 5.0, "hfov_deg": 20.0},
                     wavelengths_um=[0.48, 0.55, 0.65], primary_wavelength_um=0.55)
    op, _ = build_optic(p)
    assert float(op.paraxial.f2()) == pytest.approx(float(ref.paraxial.f2()), rel=1e-6)


@pytest.fixture(scope="module")
def verified_design():
    from lenszoo.schema import Prescription

    return Prescription.load(VERIFIED)


def test_real_patent_design_verifies(verified_design):
    from lenszoo.verify import verify

    p = copy.deepcopy(verified_design)
    v = verify(p)
    assert v["status"] == "verified"
    assert abs(v["checks"]["efl"]["rel_err"]) < 0.01
    assert v["checks"]["image_quality"]["rms_um_mean"] < 15


def test_typo_is_caught_and_fix_suggested(verified_design):
    from lenszoo.verify import suggest_fixes, verify

    p = copy.deepcopy(verified_design)
    s3 = next(s for s in p.surfaces if s.name == "S3")
    s3.radius = -s3.radius  # simulated OCR sign error
    v = verify(p, refine=False)
    assert v["status"] != "verified"
    fixes = suggest_fixes(p)
    assert any(f["surface"] == "S3" and f["kind"] == "sign flip" for f in fixes)


def test_scaling_scales_efl(verified_design):
    from lenszoo.verify import build_optic

    op1, _ = build_optic(verified_design, fields=(0.0,))
    op2, _ = build_optic(verified_design.scaled(1.5), fields=(0.0,))
    assert float(op2.paraxial.f2()) == pytest.approx(1.5 * float(op1.paraxial.f2()), rel=1e-6)


def test_schema_roundtrip(tmp_path, verified_design):
    from lenszoo.schema import Prescription

    f = verified_design.save(tmp_path / "x.json")
    q = Prescription.load(f)
    assert q.to_dict()["surfaces"] == verified_design.to_dict()["surfaces"]
    json.loads(f.read_text(encoding="utf-8"))


def test_corpus_matches_published_schema():
    from jsonschema import Draft202012Validator

    from lenszoo.schema import JSON_SCHEMA

    schema = json.loads((ROOT / "schema" / "prescription.schema.json").read_text(encoding="utf-8"))
    assert schema == JSON_SCHEMA
    validator = Draft202012Validator(schema)
    for path in sorted((ROOT / "data" / "designs").rglob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["id"] == path.stem
        validator.validate(document)


# ------------------------------------------------------------------- bench
def test_reference_design_scores_well_on_its_task(verified_design):
    from lenszoo.bench import Task, score

    r = score(verified_design, Task.load(T01))
    assert r["pass"] and r["score"] > 40


def test_tasks_load_and_render():
    from lenszoo.bench import load_tasks, render_prompt

    tasks = load_tasks(ROOT / "data" / "tasks")
    assert len(tasks) >= 10
    prompt = render_prompt(tasks[0])
    assert "EFL" in prompt and tasks[0].prompt in prompt and tasks[0].title


def test_ocr_null_backend_refuses():
    from lenszoo.extract.ocr import NullBackend, tsv_to_rows

    with pytest.raises(NotImplementedError):
        NullBackend().image_to_rows(b"")
    assert tsv_to_rows("\u9762\u53f7\tA4\nS1\t1E-2\n") == [["\u9762\u53f7", "A4"], ["S1", "1E-2"]]
