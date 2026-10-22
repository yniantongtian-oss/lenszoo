"""Parser aliases, corpus audit, MCP server, and checker fixes added in 0.2."""
import json
import math
from argparse import Namespace
from io import BytesIO
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_embodiment_numbers_and_header_cells():
    from lenszoo.extract.gpatents import embodiment_number, table_rows

    assert embodiment_number("9") == 9
    assert embodiment_number("\u4e5d") == 9
    assert embodiment_number("\u5341") == 10
    assert embodiment_number("\u5341\u4e00") == 11
    assert embodiment_number("\u4e8c\u5341") == 20
    assert embodiment_number("\u4e8c\u5341\u4e09") == 23
    assert embodiment_number("abc") is None
    html = "<table><tr><th>\u9762\u53f7</th><th>\u66f2\u7387\u534a\u5f84</th></tr><tr><td>S1</td><td>10</td></tr></table>"
    assert table_rows(html)[0] == ["\u9762\u53f7", "\u66f2\u7387\u534a\u5f84"]


def test_asphere_rows_match_stop_aliases():
    from lenszoo.extract.tables import apply_aspheric
    from lenszoo.schema import Surface

    surfs = [
        Surface("OBJ", role="object"),
        Surface("STO+S1", role="stop", is_stop=True),
        Surface("2(APE)", role="stop", is_stop=True),
        Surface("S3", role="surface"),
        Surface("IMA", role="image"),
    ]
    warns = apply_aspheric(surfs, [
        ["\u9762", "A4", "A6"],
        ["S1", "0.1", "0.01"],
        ["2", "0.2", "-0.02"],
        ["S3", "0.3", "0.03"],
        ["S9", "1", "1"],
    ])
    assert surfs[1].aspheric["A4"] == pytest.approx(0.1)
    assert surfs[2].aspheric["A4"] == pytest.approx(0.2)
    assert surfs[3].aspheric["A6"] == pytest.approx(0.03)
    assert warns == ["aspheric row S9: no matching surface"]


def test_claim_tables_and_empty_page():
    from lenszoo.extract.gpatents import (
        claims_from_param_table,
        claims_from_summary_table,
        claims_from_text,
        extract_page,
        sane,
    )

    got = claims_from_param_table([
        ["\u53c2\u6570", "f(mm)", "TTL", "Fno", "FOV"],
        ["\u6570\u503c", "4.04", "4.67", "2.2", "72.8"],
    ])
    assert got["efl"] == 4.04 and got["hfov_deg"] == pytest.approx(36.4)
    summary = claims_from_summary_table([
        ["\u5b9e\u65bd\u4f8b", "1", "2"],
        ["f(mm)", "4", "5"],
        ["TTL", "5", "6"],
    ])
    assert summary[2]["efl"] == 5 and summary[2]["ttl"] == 6
    assert sane({"efl": 1e9, "fov_deg": 80}) == {"hfov_deg": 40}
    assert claims_from_text("\u6709\u6548\u7126\u8ddd f=4.04 mm TTL=4.67")["efl"] == 4.04
    page = "<html><head><title>CN1 - title - Google Patents</title></head><body><section itemprop='description'></section></body></html>"
    report = extract_page(page, "CN1")
    assert report.prescriptions == []
    assert report.warnings


def test_fetch_reads_cache_without_network(tmp_path, monkeypatch):
    import requests

    from lenszoo.extract.gpatents import fetch

    cached = tmp_path / "CN1.html"
    cached.write_text("z" * 10001, encoding="utf-8")

    def boom(*_a, **_k):
        raise AssertionError("network")

    monkeypatch.setattr(requests, "get", boom)
    assert fetch("CN1", cache_dir=tmp_path).startswith("zzz")


def test_vlm_client_parses_tsv(monkeypatch):
    import requests

    from lenszoo.extract.ocr import OpenAICompatibleVLM, get_backend

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "a\tb\n1\t2\n"}}]}

    monkeypatch.setattr(requests, "post", lambda *_a, **_k: Response())
    rows = OpenAICompatibleVLM(url="http://example/v1", model="m", api_key="k").image_to_rows(b"png")
    assert rows == [["a", "b"], ["1", "2"]]
    with pytest.raises(ValueError):
        OpenAICompatibleVLM(url="", model="m")
    monkeypatch.delenv("LENSZOO_VLM_URL", raising=False)
    assert type(get_backend()).__name__ == "NullBackend"
    monkeypatch.setenv("LENSZOO_VLM_URL", "http://example/v1")
    assert isinstance(get_backend(), OpenAICompatibleVLM)


def test_unknown_surface_keys_are_ignored_and_odd_aspheres_rejected():
    from lenszoo.schema import JSON_SCHEMA, Prescription, SchemaError

    data = {
        "id": "boundary",
        "surfaces": [
            {"name": "OBJ", "role": "object", "radius": "inf", "thickness": "inf"},
            {"name": "S1", "radius": 10.0, "thickness": 1.0, "nd": 1.5, "comment": "keep going", "aspheric": {"A4": 0.001}},
            {"name": "IMA", "role": "image"},
        ],
    }
    loaded = Prescription.from_dict(data)
    assert loaded.surfaces[1].radius == 10
    data["surfaces"][1]["aspheric"] = {"A3": 0.1}
    with pytest.raises(SchemaError):
        Prescription.from_dict(data)
    from jsonschema import Draft202012Validator

    Draft202012Validator(JSON_SCHEMA).validate(Prescription.from_dict({
        "id": "ok",
        "surfaces": [
            {"name": "OBJ", "role": "object"},
            {"name": "S1", "radius": 10, "thickness": 1, "nd": 1.5, "aspheric": {"A4": 0.1, "A30": 1e-6}},
            {"name": "IMA", "role": "image"},
        ],
    }).to_dict())
    with pytest.raises(Exception):
        Draft202012Validator(JSON_SCHEMA).validate({"id": "bad", "surfaces": [
            {"name": "OBJ", "role": "object"},
            {"name": "S1", "aspheric": {"A3": 1}},
            {"name": "IMA", "role": "image"},
        ]})


def test_schema_rejects_shape_errors():
    from lenszoo.schema import Prescription, SchemaError

    with pytest.raises(SchemaError):
        Prescription.from_dict([])
    with pytest.raises(SchemaError):
        Prescription.from_dict({"surfaces": []})
    with pytest.raises(SchemaError):
        Prescription.from_dict({"id": "x", "surfaces": ["nope", {}, {}]})
    with pytest.raises(SchemaError):
        Prescription.from_dict({"id": "x", "surfaces": [
            {"name": "S1", "role": "surface"}, {"name": "S2"}, {"name": "IMA", "role": "image"},
        ]})
    with pytest.raises(SchemaError):
        Prescription.from_dict({"id": "x", "surfaces": [
            {"name": "OBJ", "role": "object"}, {"name": "S1", "nd": 9}, {"name": "IMA", "role": "image"},
        ]})
    with pytest.raises(SchemaError):
        Prescription.from_dict({"id": "x", "wavelengths_um": [], "surfaces": [
            {"name": "OBJ", "role": "object"}, {"name": "S1"}, {"name": "IMA", "role": "image"},
        ]})


def test_untraceable_prescription_is_failed_even_if_refinement_was_attempted(monkeypatch):
    from lenszoo.schema import Prescription
    from lenszoo.verify import check

    p = Prescription.from_dict({
        "id": "dead",
        "claimed": {"efl": 4.0},
        "surfaces": [
            {"name": "OBJ", "role": "object", "radius": "inf", "thickness": "inf"},
            {"name": "S1", "radius": 10.0, "thickness": 1.0, "nd": 1.5},
            {"name": "IMA", "role": "image"},
        ],
    })

    def boom(_p, **_kw):
        return {
            "efl": 4.0, "fno": 2.0, "ttl": 1.0, "defocus": 0.0, "hfov_deg": 20.0,
            "assumptions": [], "n_lenses": 1, "imgh_real": 1.0, "distortion_pct": 0.0,
            "rms_um_mean": float("inf"), "fields": [], "mtf_mean": 0.0, "mtf_freq_lpmm": 100.0,
            "airy_um": 1.0, "min_center_thickness": 1.0, "min_edge_thickness": 1.0,
            "full_field_vignetted": True,
        }

    monkeypatch.setattr(check, "evaluate", boom)
    monkeypatch.setattr(check, "refine_indices", lambda *_a, **_k: (_p_copy(p), {"1.5/None": 1.5}))
    result = check.verify(p)
    assert result["status"] == "failed"

    def explode(*_a, **_k):
        raise RuntimeError("solver")

    monkeypatch.setattr(check, "refine_indices", explode)
    again = check.verify(Prescription.from_dict(p.to_dict()))
    assert again["status"] == "failed"
    assert any("refinement failed" in note for note in again["notes"])


def _p_copy(p):
    import copy
    return copy.deepcopy(p)


def test_build_states_assumptions_and_stop_fallback():
    from lenszoo.schema import Prescription, Surface
    from lenszoo.verify import build_optic

    def rows():
        return [
            Surface("OBJ", thickness=math.inf, role="object"),
            Surface("S1", radius=20, thickness=2, nd=1.5, conic=-0.2, role="surface"),
            Surface("S2", radius=-20, thickness=18, role="surface"),
            Surface("IMA", role="image"),
        ]

    _op, info = build_optic(Prescription(id="singlet", surfaces=rows(), claimed={}), ray_aiming="paraxial")
    assert any("F/2" in item for item in info["assumptions"])
    assert any("30 deg" in item for item in info["assumptions"])
    assert any("first refracting" in item for item in info["assumptions"])
    _op, info = build_optic(Prescription(id="imgh", surfaces=rows(), claimed={"imgh": 2.0, "fno": 2.8}))
    assert any("ImgH" in item for item in info["assumptions"])
    air_stop = [
        Surface("OBJ", thickness=math.inf, role="object"),
        Surface("S1", radius=20, thickness=2, nd=1.5, vd=55, role="surface"),
        Surface("S2", radius=-20, thickness=1, role="surface"),
        Surface("S3", radius=math.inf, thickness=1, role="surface"),
        Surface("S4", radius=25, thickness=2, nd=1.6, vd=40, role="surface"),
        Surface("S5", radius=-25, thickness=10, role="surface"),
        Surface("IMA", role="image"),
    ]
    _op, info = build_optic(Prescription(id="air", surfaces=air_stop, claimed={"fno": 4, "hfov_deg": 10}))
    assert any("plane air" in item for item in info["assumptions"])
    stop_only = [
        Surface("OBJ", thickness=math.inf, role="object"),
        Surface("STO", radius=math.inf, thickness=1, role="stop", is_stop=True),
        Surface("IMA", role="image"),
    ]
    _op, info = build_optic(Prescription(id="stop", surfaces=stop_only, claimed={"fno": 4, "hfov_deg": 5}))
    assert any("no refracting" in item for item in info["assumptions"])
    with pytest.raises(ValueError):
        build_optic(Prescription(id="empty", surfaces=[
            Surface("OBJ", role="object"), Surface("IMA", role="image"),
        ], claimed={"fno": 2, "hfov_deg": 5}))


def test_newton_patch_accepts_aperture_and_replaces_nonfinite_seed():
    from optiland.coordinate_system import CoordinateSystem
    from optiland.geometries.even_asphere import EvenAsphere
    from optiland.geometries.standard import StandardGeometry
    from optiland.rays import RealRays

    from lenszoo.verify._patches import apply

    apply()
    geometry = EvenAsphere(CoordinateSystem(), radius=5.0, conic=-0.5, coefficients=[0.0, 0.0, -1e-4], max_iter=30, tol=1e-8)
    direction = math.sqrt(1 - 0.0)
    rays = RealRays([0.0], [12.0], [-2.0], [0.0], [0.0], [direction], [1.0], [0.55])
    import numpy as np

    def scalar(value) -> float:
        return float(np.asarray(value, dtype=float).ravel()[0])

    seed = scalar(StandardGeometry.distance(geometry, rays, aperture=None))
    assert not math.isfinite(seed)
    distance = scalar(geometry.distance(rays, aperture=None))
    assert math.isfinite(distance)


def test_metrics_helpers_and_edge_failure():
    from lenszoo.schema import Prescription
    from lenszoo.verify import build_optic
    from lenszoo.verify.metrics import center_thicknesses, distortion_pct, edge_thickness

    p = Prescription.load(ROOT / "data/designs/verified/CN105116519B-ex2.json")
    optic, _info = build_optic(p, fields=(0.0, 1.0))
    assert math.isfinite(distortion_pct(optic, p.claimed["hfov_deg"]))
    assert any(name == "S1" for name, _t in center_thicknesses(p))
    assert math.isfinite(edge_thickness(optic, p)) or math.isnan(edge_thickness(optic, p))

    class Boom:
        primary_wavelength = 0.5876

        def trace_generic(self, *_a, **_k):
            raise RuntimeError("no")

    assert math.isnan(edge_thickness(Boom(), p))


def test_audit_search_and_triage_document():
    from lenszoo.corpus import audit, classify, render_triage, search_designs
    from lenszoo.schema import Prescription

    report = audit(ROOT / "data" / "designs")
    assert report["ok"]
    assert report["needs_review"] == 132
    assert report["by_status"]["verified"] == 1
    text = (ROOT / "data" / "designs" / "TRIAGE.md").read_text(encoding="utf-8")
    assert text == render_triage(report)
    assert "CN214751066U-ex8" in text and "Not promoted" in text
    ex8 = Prescription.load(ROOT / "data/designs/needs_review/CN214751066U-ex8.json")
    assert classify(ex8)["primary"] == "image_quality_only"
    parsed = Prescription.load(ROOT / "data/designs/needs_review/CN105242374B-ex1.json")
    assert classify(parsed)["primary"] == "misparsed_surface_names"
    sunny = Prescription.load(ROOT / "data/designs/needs_review/CN105116519B-ex11.json")
    assert classify(sunny)["primary"] == "defocus_and_spots"
    hits = search_designs(ROOT / "data/designs", efl=4.04, fno=2.2, hfov_deg=36.4, limit=3)
    assert hits[0]["id"] == "CN105116519B-ex2"
    with pytest.raises(ValueError):
        search_designs(ROOT / "data/designs", efl=0)


def test_cli_audit_search_and_list():
    from lenszoo.cli import cmd_audit, cmd_list, cmd_search, main

    assert cmd_audit(Namespace(designs=ROOT / "data/designs", write=None)) == 0
    assert cmd_list(Namespace(designs=ROOT / "data/designs", all=False)) == 0
    assert cmd_search(Namespace(
        designs=ROOT / "data/designs", efl=4.04, fno=2.2, hfov=36.4, ttl=None, max_elements=None, limit=2,
    )) == 0
    assert main(["audit", "--designs", str(ROOT / "data/designs")]) == 0


def test_cli_skips_unreadable_design(tmp_path, capsys):
    from lenszoo.cli import cmd_list

    (tmp_path / "nope.json").write_text("{", encoding="utf-8")
    assert cmd_list(Namespace(designs=tmp_path, all=True)) == 0
    assert "nope.json" in capsys.readouterr().err


def test_mcp_roundtrip_lists_and_rejects_unknown_tools():
    from lenszoo.mcp_server import handle, read_message, serve, write_message

    init = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "lenszoo"
    assert handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert handle({"jsonrpc": "2.0", "id": 2, "method": "ping"})["result"] == {}
    listed = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert "verify_design" in names and "search_designs" in names
    called = handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
        "name": "list_designs",
        "arguments": {"designs": str(ROOT / "data/designs/verified"), "status": "verified", "limit": 5},
    }})
    body = json.loads(called["result"]["content"][0]["text"])
    assert body["designs"] and body["designs"][0]["status"] == "verified"
    missing = handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "nope", "arguments": {}}})
    assert missing["result"]["isError"] is True
    unknown = handle({"jsonrpc": "2.0", "id": 6, "method": "nope"})
    assert unknown["error"]["code"] == -32601
    audit = handle({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {
        "name": "audit_corpus", "arguments": {"designs": str(ROOT / "data/designs")},
    }})
    assert json.loads(audit["result"]["content"][0]["text"])["ok"] is True

    stream = BytesIO()
    write_message(stream, {"jsonrpc": "2.0", "id": 8, "method": "tools/list"})
    stream.seek(0)
    assert read_message(stream)["id"] == 8
    out = BytesIO()
    serve(stdin=BytesIO(stream.getvalue()), stdout=out)
    out.seek(0)
    reply = read_message(out)
    assert reply["id"] == 8 and "tools" in reply["result"]
    assert read_message(BytesIO(b"")) is None
    assert read_message(BytesIO(b"Content-Length: 0\r\n\r\n")) is None
    assert read_message(BytesIO(b"Content-Length: 5\r\n\r\n{}")) is None


def test_task_roundtrip_and_score_error(tmp_path, monkeypatch):
    from lenszoo.bench import scorer
    from lenszoo.bench.tasks import Task
    from lenszoo.schema import Prescription

    task = Task.load(ROOT / "data/tasks/T01-main7p-f4.04.json")
    task.save(tmp_path / "t.json")
    assert Task.load(tmp_path / "t.json").id == task.id
    candidate = Prescription.load(ROOT / "data/designs/verified/CN105116519B-ex2.json")

    def explode(*_a, **_k):
        raise RuntimeError("trace")

    monkeypatch.setattr(scorer, "evaluate", explode)
    failed = scorer.score(candidate, task)
    assert failed["score"] == 0.0 and "trace" in failed["error"]


def test_refined_example_still_verifies():
    from lenszoo.schema import Prescription
    from lenszoo.verify import verify

    design = Prescription.load(ROOT / "data/designs/verified/CN105116519B-ex1.json")
    result = verify(design)
    assert result["status"] == "verified_refined"
    assert result["refined"]["nd"]
    assert result["refined"]["checks"]["efl"]["pass"]
    assert result["refined"]["checks"]["image_quality"]["pass"]


def test_audit_flags_bad_files_and_reason_codes(tmp_path):
    from lenszoo.corpus import audit, classify
    from lenszoo.schema import Prescription

    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    design = Prescription.load(ROOT / "data/designs/verified/CN105116519B-ex2.json")
    design.id = "renamed"
    (tmp_path / "verified").mkdir()
    design.save(tmp_path / "verified" / "CN105116519B-ex2.json")
    design.id = "placed"
    design.verification = {"status": "verified", "checks": {"efl": {"pass": False}}, "failed_checks": []}
    (tmp_path / "needs_review").mkdir()
    design.save(tmp_path / "needs_review" / "placed.json")
    report = audit(tmp_path)
    assert report["ok"] is False
    assert len(report["errors"]) >= 3
    design.provenance = {"warnings": ["aspheric coefficients truncated: text mentions up to A30"]}
    design.verification = {"status": "needs_review", "failed_checks": ["image_quality"], "checks": {}}
    assert "asphere_coefficients_truncated" in classify(design)["reasons"]
    blank = Prescription.load(ROOT / "data/designs/plausible/CN110794552B-ex3.json")
    blank.verification = {"status": "plausible", "failed_checks": [], "checks": {}}
    blank.claimed = {}
    blank.provenance = {"warnings": []}
    assert classify(blank)["primary"] == "no_efl_checksum"


def test_cli_verify_fixes_bench_and_audit_write(tmp_path, monkeypatch, capsys):
    from lenszoo.cli import cmd_audit, cmd_bench, cmd_fixes, cmd_mcp, cmd_verify
    from lenszoo.schema import Prescription

    design = Prescription.load(ROOT / "data/designs/verified/CN105116519B-ex2.json")
    path = design.save(tmp_path / "lens.json")

    def fake_verify(prescription):
        prescription.verification = {"status": "plausible"}
        return {"status": "plausible", "checks": {"focus": {"pass": True, "defocus_mm": 0.0}}, "failed_checks": []}

    monkeypatch.setattr("lenszoo.verify.verify", fake_verify)
    monkeypatch.setattr("lenszoo.verify.suggest_fixes", lambda _p: [{"surface": "S1", "kind": "sign flip"}])
    assert cmd_verify(Namespace(files=[path], write=True)) == 0
    assert json.loads(path.read_text(encoding="utf-8"))["verification"]["status"] == "plausible"
    assert cmd_fixes(Namespace(file=path)) == 0
    assert "sign flip" in capsys.readouterr().out

    from lenszoo.bench.tasks import Task

    monkeypatch.setattr("lenszoo.bench.load_tasks", lambda _folder: [Task.load(ROOT / "data/tasks/T01-main7p-f4.04.json")])
    monkeypatch.setattr("lenszoo.bench.baseline.load_corpus", lambda *_a, **_k: [design])
    monkeypatch.setattr("lenszoo.bench.baseline.AGENTS", {"nearest": lambda task, corpus: (design, {"seed": design.id})})
    monkeypatch.setattr("lenszoo.bench.score", lambda candidate, task: {
        "task": task.id, "score": 1.0, "pass": True, "efl_rel_err": 0.0, "rms_um_mean": 1.0,
    })
    out = tmp_path / "bench.json"
    assert cmd_bench(Namespace(
        bench_cmd="run", agent="nearest", tasks=ROOT / "data/tasks", designs=ROOT / "data/designs",
        only="T01", out=str(out), force=True,
    )) == 0
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved["results"][0]["score"] == 1.0
    assert cmd_bench(Namespace(bench_cmd="prompt", task=ROOT / "data/tasks/T01-main7p-f4.04.json")) == 0
    assert cmd_audit(Namespace(designs=ROOT / "data/designs", write=tmp_path / "triage.md")) == 0
    assert (tmp_path / "triage.md").read_text(encoding="utf-8").startswith("# Needs-review triage")

    monkeypatch.setattr("lenszoo.mcp_server.serve", lambda: None)
    assert cmd_mcp(Namespace()) == 0


def test_mcp_trace_tools_are_callable(monkeypatch):
    from lenszoo.mcp_server import handle
    from lenszoo.schema import Prescription

    design = Prescription.load(ROOT / "data/designs/verified/CN105116519B-ex2.json")
    monkeypatch.setattr("lenszoo.verify.verify", lambda p: {"status": "verified", "failed_checks": [], "checks": {"efl": {"pass": True}}})
    monkeypatch.setattr("lenszoo.verify.suggest_fixes", lambda p: [])
    monkeypatch.setattr("lenszoo.bench.score", lambda candidate, task: {"task": task.id, "score": 3.0, "pass": False})
    verified = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "verify_design", "arguments": {"path": str(ROOT / "data/designs/verified/CN105116519B-ex2.json")},
    }})
    assert json.loads(verified["result"]["content"][0]["text"])["status"] == "verified"
    scored = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
        "name": "score_design",
        "arguments": {"task": str(ROOT / "data/tasks/T01-main7p-f4.04.json"), "prescription": design.to_dict()},
    }})
    assert json.loads(scored["result"]["content"][0]["text"])["score"] == 3.0
    fixes = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
        "name": "suggest_fixes", "arguments": {"prescription": design.to_dict()},
    }})
    assert json.loads(fixes["result"]["content"][0]["text"])["fixes"] == []
    missing = handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "verify_design", "arguments": {}}})
    assert missing["result"]["isError"] is True
    found = handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {
        "name": "search_designs",
        "arguments": {"efl": 4.04, "fno": 2.2, "hfov_deg": 36.4, "ttl_max": 4.8, "limit": 1,
                      "designs": str(ROOT / "data/designs")},
    }})
    assert json.loads(found["result"]["content"][0]["text"])["designs"][0]["id"] == "CN105116519B-ex2"


def test_module_entrypoint(monkeypatch):
    import runpy
    import sys

    monkeypatch.setattr(sys, "argv", ["lenszoo", "--help"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("lenszoo", run_name="__main__")
    assert exc.value.code == 0


def test_baseline_nearest_and_guards(monkeypatch):
    from lenszoo.bench.baseline import load_corpus, nearest, nearest_opt, refocus, spec_distance
    from lenszoo.bench.tasks import Task
    from lenszoo.schema import Prescription

    corpus = load_corpus(ROOT / "data/designs")
    task = Task.load(ROOT / "data/tasks/T10-main-f5.0-F2.0.json")
    candidate, info = nearest(task, corpus)
    assert info["seed"] == "CN105116519B-ex2"
    assert info["scale"] > 1
    assert candidate.claimed["efl"] == pytest.approx(task.spec["efl"], rel=0.01)
    blocked = Task.load(ROOT / "data/tasks/T10-main-f5.0-F2.0.json")
    blocked.reference = {"exclude_patents": [p.source.get("patent") for p in corpus]}
    with pytest.raises(RuntimeError, match="empty corpus"):
        nearest(blocked, corpus)
    bare = Prescription.load(ROOT / "data/designs/verified/CN105116519B-ex2.json")
    bare.claimed = {"efl": 4.0}
    bare.verification = {}
    assert math.isinf(spec_distance(task, bare))
    macro = Prescription.load(ROOT / "data/designs/verified/CN214751066U-ex5.json")
    moved = refocus(macro, task)
    assert moved.surfaces[-2].thickness != macro.surfaces[-2].thickness
    optimized, info = nearest_opt(task, corpus, max_nfev=1)
    assert info["seed"] == "CN105116519B-ex2"
    assert math.isfinite(info["score_seed"])
    assert optimized.id

    class Fake:
        class paraxial:
            @staticmethod
            def f2():
                return -4.0

    monkeypatch.setattr("lenszoo.bench.baseline.build_optic", lambda *_a, **_k: (Fake(), {}))
    with pytest.raises(RuntimeError, match="wrong sign"):
        nearest(task, corpus[:1])
