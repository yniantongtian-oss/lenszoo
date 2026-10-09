# Baseline results (run 2026-10-09, sandbox, Optiland 0.6.2, NumPy backend)

Six designs were usable as seeds (status verified, verified_refined or plausible). Each patent-spec task excludes its own source patent (strict split).

| task | nearest score | pass | nearest_opt score | pass | seed design | kept | wall time (s) |
|---|---|---|---|---|---|---|---|
| T01-main7p-f4.04 | 0.0 | False | 0.0 | False | CN214751066U-ex5 | optimized | 20.6 |
| T02-std7p-f4.33 | 0.0 | False | 0.0 | False | CN214751066U-ex5 | optimized | 8.0 |
| T03-compact7p-f3.98 | 0.0 | False | 0.0 | False | CN214751066U-ex5 | optimized | 22.4 |
| T04-wide6p-f2.97 | 0.0 | False | 0.0 | False | CN214751066U-ex5 | optimized | 13.4 |
| T05-wide6p-f2.95 | 0.0 | False | 0.0 | False | CN214751066U-ex5 | optimized | 17.3 |
| T06-tele-f6.74 | 0.0 | False | 0.0 | False | CN214751066U-ex5 | optimized | 6.7 |
| T07-ultracompact-f3.13 | 0.88 | False | 1.03 | False | CN105116519B-ex3 | optimized | 51.2 |
| T08-bigsensor-f4.96 | 2.08 | False | 2.79 | False | CN105116519B-ex3 | optimized | 75.3 |
| T09-main7p-shorter | 15.39 | False | 18.03 | False | CN105116519B-ex1 | optimized | 63.1 |
| T10-main-f5.0-F2.0 | 33.65 | True | 45.41 | True | CN105116519B-ex2 | optimized | 41.7 |
| T11-cheap3p-f3.0 | 0.0 | False | 0.0 | False | CN214751066U-ex5 | optimized | 13.8 |
| T12-ultrawide-f2.5 | 0.0 | False | 0.0 | False | CN214751066U-ex5 | optimized | 26.6 |
| T13-tele5p-f6.0 | 0.0 | False | 0.0 | False | CN214751066U-ex5 | optimized | 8.0 |
| T14-main7p-F1.8 | 8.21 | False | 8.21 | False | CN105116519B-ex3 | seed | 50.3 |

Mean score: nearest 4.30, nearest_opt 5.39. Pass: nearest 1/14, nearest_opt 1/14.

Oracle sanity check: the patent's own verified embodiment, CN105116519B-ex2, scores 46.62 on T01 and passes (`lenszoo bench score data/tasks/T01-main7p-f4.04.json data/designs/verified/CN105116519B-ex2.json`).

How to read this: only 6 seeds are usable, and each task's source patent is excluded, so the baselines fail every patent-spec task. The single pass, T10, comes from scaling a verified 7-element design and re-optimising it (score 33.65 -> 45.41). That gap is the headroom the benchmark is meant to expose, and growing the corpus is the main way to close it.
