# LensZoo: plan (v0.1 → v1.0, 8 weeks)

## 1. Positioning (one line)
**The open, verified dataset and benchmark for AI lens design: CN-patent phone lenses, checked by ray tracing, scored on Optiland, with no Zemax licence needed.**

Who it is for:
* **Optics companies** (Sunny Optical, AAC Technologies, O-Film, Lianchuang Electronic, Huawei/Honor/OPPO imaging and IP teams, DJI): patent landscaping and searching for the nearest prior design.
* **AI labs building agent and RL environments** (Alibaba Qwen, ByteDance Seed, Moonshot AI, DeepSeek, Zhejiang University groups): a verifiable, licence-free task suite.
* **Optics students**: real designs to study, a working Optiland pipeline, clear docs.

Name: **LensZoo**. On 2026-10-09 GitHub repository search for `lenszoo in:name` returned 0 results, and `https://pypi.org/pypi/lenszoo/json` returned 404 (name free). "Zoo" reads like "model zoo" to ML people, it is short, and it works as a CLI name (`lenszoo bench run`). Runner-up: `lensatlas`, also free on both.

## 2. How it differs (do not reinvent)
| existing | what it lacks | LensZoo's answer |
|---|---|---|
| Photonium Patent Corpus (13,091 US lenses) | US only; licensed | CN patents; open; same "raytrace as checksum" idea |
| LensArena / LensDesigner (arXiv 2609.30450) | Zemax; code not released; generated library | Optiland; patent-grounded references; CI-runnable |
| OptiAgent (arXiv 2602.23761) | Zemax; no code found | open scorer that any agent can call |
| Zemax / Optiland MCP servers, agent skills | tools, not data or benchmarks | we **use** Optiland; we don't build another MCP |
| nzhagen/LensLibrary | small set of .zmx files | schema + verification + provenance |

## 3. Architecture
```
Google Patents CN page ──► extract/gpatents.py ─┐            (text tables, ~6% of patents)
CNIPA PDF / image  ──► extract/ocr.py (VLM) ────┤ rows ─► extract/tables.py ─► Prescription JSON
                                                │
Prescription ─► verify/build.py (Optiland Optic) ─► verify/check.py
     checks: EFL, TTL, ImgH(real chief ray), focus, RMS/MTF;  nd recovery (|Δn|≤0.005);  fix finder
     status: verified | verified_refined | plausible | needs_review | failed
Corpus ─► bench/baseline.py (nearest, nearest_opt) ─► bench/scorer.py (MTF × penalties, pass/fail)
Tasks (JSON)  ──┘                                       results/*.json, leaderboard
```

## 4. Eight-week roadmap
| week | goal | deliverable / exit criterion |
|---|---|---|
| 0 (done) | MVP | package installs, 13 tests pass, 161 embodiments extracted, 4 verified + 2 plausible, 14 tasks, 2 baselines run |
| 1 | **Data access at scale** | Move off scraping: CNIPA open data / bulk full text, or EPO OPS for CN documents; polite cached crawler. Target list of 2,000 phone-lens CN patents (IPC G02B13/00, G02B9/6x; CN filings by Sunny/AAC/O-Film/Genius/Largan) |
| 2 | **OCR fallback live** | Qwen2.5-VL (local vLLM) or PaddleOCR PP-Structure behind `OCRBackend`. Measure cell-level accuracy on 30 hand-checked tables. Run the fix finder on OCR output. Exit: at least 60% of OCR'd embodiments reach `verified*` |
| 3 | **Verifier v2** | Odd-order (KA/Am) and Forbes Q aspheres; semi-diameters / vignetting; wavelength sets other than F/d/C (e.g. 470–650 nm with 555 primary); diagnose the CN105116519B ex4–12 defocus mystery and write it up |
| 4 | **Corpus v0.5** | ≥300 verified phone lenses with a manifest (CSV/Parquet), search by EFL/F#/FOV/TTL/element count, and a "nearest patented design" lookup. Export to Optiland JSON and .zmx |
| 5 | **Bench v0.5** | 60 tasks (main, wide, tele, periscope-free, 3P–8P). Splits: open, strict (family excluded), held-out assignees. Manufacturability gates: edge thickness, plastic list, sag slope |
| 6 | **Agents** | Gymnasium-style env + an MCP adapter that only wraps the scorer (no new Zemax MCP). LLM baselines: Qwen and one frontier model, with tool access to Optiland |
| 7 | **Leaderboard + CI** | GitHub Actions scoring on PR; static leaderboard page; Docker image; docs site |
| 8 | **Launch** | v1.0 release, paper-style tech report (arXiv cs.CV / physics.optics), posts (see §6) |

## 5. Risks and mitigations
| risk | likelihood | mitigation |
|---|---|---|
| Most tables are images; OCR errors | certain | VLM + ray-trace checksum + fix finder; never publish `needs_review` as verified |
| Google Patents blocks scraping (seen: 503 after ~720 fetches; 403 on patentimages) | high | CNIPA/EPO bulk sources; cache; rate limit; don't redistribute HTML |
| Legal: in-force patents; copyright debate on patent docs | medium | store numeric facts plus citations only; CC0 annotations; research disclaimer; no prose or figures |
| Photonium extends to CN, or LensArena code drops | medium | stay open and engine-agnostic; differentiate on CN data, Chinese specs, CI-runnable scoring; interoperate (export .zmx) |
| Optiland edge cases (aspheres, ray aiming) | medium | patches upstreamed as PRs; pinned version; regression tests on verified designs |
| Score not matching what lens designers care about | medium | add MTF at Nyquist for a target pixel, distortion, relative illumination and CRA limits; ask 2–3 practising designers to review the tasks |
| Single-maintainer bandwidth | high | narrow scope (phone lenses first); good issues for contributors |

## 6. Launch plan
* **README** in English (done in v0.1). Add GIFs: spot diagrams of verified designs and the typo-catch demo.
* **X (EN)**: thread "We turned Chinese lens patents into an open, ray-trace-verified dataset, and built a Zemax-free benchmark for AI lens design." Show the 4 checks, the typo catch and the baseline gap. Tag @optiland maintainers.
* **Hacker News** (Show HN) and **Reddit r/optics**: focus on the engineering story (only 6% of patents have text tables, the two-decimal index trap, the Optiland patch).
* **Chinese developer communities**: a long-form write-up, "Using ray tracing as a checksum for patent data", with the finding that two-decimal nd values shift EFL by 1.5–2%.
* Upstream: open the Optiland PR (Newton seed + NaN early exit) and link LensZoo from it. Post in the Optiland Discussions.
* Academic: email the LensDesigner and OptiAgent authors offering LensZoo tasks as an open counterpart; submit a short paper to a workshop (e.g. NeurIPS Datasets & Benchmarks track or an optics venue).
* Job angle: pin the repo; one-page PDF summary; 3-minute demo video for campus recruiting (Sunny Optical / Huawei / DJI optics roles).

## 7. Definition of done for v1.0
≥300 verified designs; ≥60 tasks; OCR path measured; Optiland PR submitted; CI leaderboard live; docs; tech report.
