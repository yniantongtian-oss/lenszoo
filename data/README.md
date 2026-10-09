# LensZoo data card

## designs/
`designs/{verified,plausible,needs_review,failed}/*.json`: 161 embodiments from 34 CN patents, extracted on 2026-10-09 from Google Patents full-text pages (`https://patents.google.com/patent/<pub>/zh`). Each file records:

* `source`: patent number, assignee, title, date, embodiment number, URL.
* `provenance`: extraction method and parser warnings.
* `verification`: all checks, metrics, and any refined indices.

Only factual numeric data (surface numbers, radii, thicknesses, indices, Abbe numbers, conic and asphere coefficients) plus bibliographic citations are stored. No patent prose or figures are copied.

The HTML cache `raw/` is git-ignored and must not be redistributed.

## tasks/
14 tasks. `reference.spec_source` says whether a spec comes from a patent embodiment (and which one) or is synthetic. Where LensZoo chose a value the patent does not state (for example F/#), the task says so.

## Licensing notes (not legal advice)
* PRC Copyright Law (2020 rev.), Art. 3, protects works that show originality. Art. 5 excludes official legislative, administrative and judicial documents, pure factual news, and "calendars, general numerical tables, general forms and formulas". Source: https://www.wipo.int/wipolex/zh/legislation/details/21065
* There is no settled rule that patent specifications fall under Art. 5. One practitioner's opinion (2008) holds that patent documents with originality are works and that building a database from them is constrained by copyright: https://www.ciplawyer.cn/articles/132157.html
* LensZoo's position: numeric prescriptions are facts. The project's own contribution (verification results, refined indices, schema, tasks) is released under **CC0-1.0**. Code is MIT.
* **Patent rights are a separate issue.** Many of these designs may be covered by patents still in force. Using them commercially may infringe even though publishing the numbers is lawful. The corpus is for research and education.
* Google Patents terms and rate limits apply to scraping; scale-up should move to CNIPA open data or bulk services.
