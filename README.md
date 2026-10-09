# LensZoo

**Open, ray-trace-verified lens designs from Chinese patents, plus a lens-design agent benchmark that needs no Zemax licence.**

[![tests](https://github.com/yniantongtian-oss/lenszoo/actions/workflows/tests.yml/badge.svg)](https://github.com/yniantongtian-oss/lenszoo/actions/workflows/tests.yml)

MIT licence (code) · CC0 (our annotations; see [data/README.md](data/README.md))

Phone-camera lens makers in China file tens of thousands of CN patents. Each one prints full prescriptions: R, d, nd, vd, conic and asphere coefficients. Nobody has turned these into an open, machine-checked dataset. The one commercial patent corpus (Photonium) covers US patents only and is licensed, not open. Recent lens-design agents (LensDesigner/LensArena, OptiAgent) are evaluated inside Zemax, and their code is not public.

LensZoo does three things:

1. **extract**: parses Google Patents CN full text into a JSON prescription schema. Most CN surface tables are images; for those it provides a vision-model OCR hook.
2. **verify**: rebuilds every design in [Optiland](https://github.com/optiland/optiland) and checks it against the patent's own numbers (EFL, TTL, ImgH, focus, image quality). A transcription error almost always breaks at least one of these. Each design is labelled `verified`, `verified_refined`, `plausible`, `needs_review` or `failed`.
3. **bench**: lens-design tasks with a deterministic Optiland scorer (geometric MTF plus constraint penalties) and two baselines. Patent-spec tasks hide their source patent from the agent.

> Status: v0.1.0. The corpus counts below describe the files included in this release. Benchmark results are recorded in `results/`.

## What works today (real outputs)

```
$ pip install -e .            # Python 3.11+, pulls optiland 0.6.x (tested with 0.6.2)
$ pytest -q
13 passed

$ lenszoo extract CN105116519B          # uses the cached page in data/raw if present
CN105116519B: 12 text prescription table(s), 0 image-only table(s)
  CN105116519B-ex1   verified_refined  claimed={'efl': 3.98, 'ttl': 4.57, 'fno': 2.2, 'hfov_deg': 36.62}
  CN105116519B-ex2   verified          claimed={'efl': 4.04, 'ttl': 4.67, 'fno': 2.2, 'hfov_deg': 36.4}
  CN105116519B-ex3   verified_refined  claimed={'efl': 3.85, 'ttl': 4.47, 'fno': 2.2, 'hfov_deg': 37.73}
  CN105116519B-ex4   needs_review      ... failed=['focus', 'image_quality']
  ...

$ python examples/quickstart.py
CN105116519B-ex2: Imaging lens / Zhejiang Sunny Optics Co Ltd / 7 elements
  efl           PASS  claimed 4.04, computed 4.0453 (+0.13 %)
  ttl           PASS  claimed 4.67, computed 4.6708
  focus         PASS  defocus 0.0167 mm
  image_quality PASS  mean polychromatic RMS spot 2.56 um
with a sign typo on S3 -> needs_review failed: ['efl', 'focus', 'image_quality']
suggested fix: S3 radius 58.0389 -> -58.0389 (sign flip), EFL error after 0.13 %
reference design on its own task T01: score 46.62, pass True
```

**Corpus v0.1: 161 embodiments from 34 CN patents** (only patents whose surface tables Google serves as text):

| status | count | meaning |
|---|---|---|
| verified | 1 | EFL + TTL (+ ImgH) match the patent, focused, mean RMS spot ≤ 15 µm |
| verified_refined | 3 | same, after recovering nd values that the patent printed to 2 decimals (|Δn| ≤ 0.005, stored separately) |
| plausible | 2 | focus and image quality pass, but the patent text gives no EFL to check against |
| needs_review | 132 | at least one check fails. Typical causes: asphere table only available as an image, coefficients truncated, odd-order asphere convention, missing F/# or FOV, data copied between embodiments in the patent |
| failed | 23 | not traceable |

Verified designs: CN105116519B ex1/ex2/ex3 (7P phone lens, f ≈ 4 mm, F/2.2, Sunny) and CN214751066U ex5 (3P macro lens). Plausible: CN111796396B ex2 and CN110794552B ex3 (automotive, Sunny Automotive).

**Benchmark v0.1: 14 tasks** (8 built from real CN patent specs, 6 synthetic). Baselines, from [results/BENCHMARK_RESULTS.md](results/BENCHMARK_RESULTS.md):

| agent | mean score | tasks passed |
|---|---|---|
| `nearest` (closest corpus design, scaled to the target EFL) | 4.30 | 1/14 |
| `nearest_opt` (nearest + damped least squares on curvatures and BFL) | 5.39 | 1/14 |
| oracle: the patent's own design on T01 | 46.62 | pass |

The baselines are weak on purpose. With 6 usable seeds and the source patent excluded, there is almost nothing to start from. That gap is the case for growing the corpus.

## Findings from building it (useful even if you never use the code)

* About 6% of ~700 CN lens patents probed on Google Patents had a surface table in text. The rest are images (`patent-image-not-available` or `BDA*.png`). **OCR or a VLM is mandatory at scale.**
* Asphere tables are text more often than surface tables, and are sometimes split across a page break into a header-less continuation table. The extractor merges these.
* **Two-decimal indices** (1.54/56.1) alone shift EFL by about 1.5–2% and defocus an F/2 lens by about 0.1 mm. Without index recovery, an honest checker would reject correct designs.
* Optiland 0.6.2 loses whole rays on strong phone aspheres. The Newton intersection seeds from the base conic, which steep rays can miss, and one NaN ray stops early exit for every ray. `lenszoo/verify/_patches.py` fixes both (5× faster, rays recovered) and is a candidate upstream PR.
* Bare glass names are ambiguous in Optiland: `"F2"` is not Schott F2. The schema supports `"F2|schott"`.
* Google Patents rate-limits scripted access. After about 720 page fetches in one session the sandbox got HTTP 503 "Sorry…". `patentimages.storage.googleapis.com` (PDFs and figures) returned 403 from the sandbox.

## Install & CLI

```bash
pip install -e ".[dev]"
lenszoo list                                  # corpus summary (usable designs)
lenszoo verify data/designs/verified/*.json   # re-run checks
lenszoo fixes some_design.json                # single-edit OCR fix suggestions
lenszoo extract CN105116519B --out data/designs/new
lenszoo bench prompt data/tasks/T01-main7p-f4.04.json
lenszoo bench score data/tasks/T01-main7p-f4.04.json my_design.json
lenszoo bench run --agent nearest_opt --out results/mine.json [--only T01,T02]
```

## Prescription format (excerpt)

```json
{"id": "CN105116519B-ex2",
 "source": {"patent": "CN105116519B", "assignee": "Zhejiang Sunny Optics Co Ltd", "embodiment": 2, "url": "..."},
 "claimed": {"efl": 4.04, "ttl": 4.67, "fno": 2.2, "hfov_deg": 36.4},
 "surfaces": [
   {"name": "OBJ", "role": "object", "radius": "inf", "thickness": "inf"},
   {"name": "STO", "role": "stop", "radius": "inf", "thickness": -0.2831, "is_stop": true},
   {"name": "S1", "radius": 1.4064, "thickness": 0.6812, "nd": 1.544, "vd": 56.11, "conic": -0.5485,
    "aspheric": {"A4": 0.024078, "A6": 0.0072677, "A8": -0.020818, "...": "...", "A16": -0.012328}},
   {"name": "IMA", "role": "image"}],
 "provenance": {"method": "google_patents_text_table", "warnings": []},
 "verification": {"status": "verified", "checks": {"...": "..."}}}
```

Full JSON Schema: [schema/prescription.schema.json](schema/prescription.schema.json). Row convention: the medium on a row is the medium *after* that surface. The even-asphere coefficients start at A4. Optiland's list starts at r², and the builder handles that offset.

## OCR / vision-model fallback (stub)

`lenszoo.extract.ocr` defines `OCRBackend.image_to_rows(image) -> rows`, a fixed transcription prompt, and an OpenAI-compatible client (`LENSZOO_VLM_URL`, `LENSZOO_VLM_MODEL`, for example Qwen2.5-VL served by vLLM). The default `NullBackend` refuses rather than inventing numbers. OCR rows go through the same parser and the same ray-trace checks. **No OCR model was run in v0.1**, and the VLM client has not been tested against a live endpoint.

## How it differs from existing work

| | LensZoo | Photonium corpus | LensArena / LensDesigner (arXiv 2609.30450) | OptiAgent (2602.23761) | Zemax MCP servers |
|---|---|---|---|---|---|
| patent source | **CN** | US | none (generated LensLib100K) | none | none |
| openness | MIT code, CC0 annotations | licensed (50-design sample) | code "will be released" | no code found | open, need Zemax |
| ray-trace engine | Optiland (open) | Zemax / CODE V | Zemax | Zemax | Zemax |
| checksum verification vs patent values | yes | yes ("raytrace as checksum") | n/a | n/a | n/a |

## Limits (honest)

* Only 6 designs are usable today. The corpus is a pipeline demo, not yet a dataset.
* The image-quality check assumes F/2.0 and 30° when the patent text states neither. The full field may be vignetted because patents omit clear apertures.
* Why CN105116519B ex4–ex12 fail (EFL and TTL match, but defocus is 0.13–0.22 mm) is **not yet explained**. ex10's S9 row duplicates ex9's and ex11's duplicates ex1's, which points to copy errors in the published text, but this is unconfirmed.
* Odd-order (Fujifilm KA/Am) and Forbes aspheres are not supported yet.
* Not legal advice. Patents may be in force; see the disclaimer below and [data/README.md](data/README.md).

## Disclaimer

The patent data in this repository consists of numeric facts (surface prescriptions and claimed specifications) transcribed from published patents, each with a citation to its source document. It is provided for research and education only and is **not legal advice**. Many of these designs may still be covered by patents in force; using them commercially may infringe those patents even though publishing the numbers is lawful. See [data/README.md](data/README.md) for licensing notes.

## Repo layout

```
src/lenszoo/schema.py         prescription dataclasses, JSON schema, scaling
src/lenszoo/extract/          gpatents.py (HTML tables), tables.py (row parser), ocr.py (VLM hook, stub)
src/lenszoo/verify/           build.py (-> Optiland), metrics.py, check.py (checksums, nd refinement, fix finder), _patches.py
src/lenszoo/bench/            tasks.py, scorer.py, baseline.py
src/lenszoo/cli.py            `lenszoo` command
data/designs/{verified,plausible,needs_review,failed}/   161 extracted embodiments
data/tasks/                   14 benchmark tasks
results/                      baseline runs, quickstart output
tests/                        pytest suite (13 tests)
```
