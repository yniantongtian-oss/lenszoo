# Needs-review triage

Structural audit of `data/designs`. No file was moved. A design is promoted only when `lenszoo verify` reaches `verified`, `verified_refined` or `plausible` under the gates in `lenszoo.verify.check.TOL`.

Designs: 161. Needs review: 132. Structural errors: 0.

## Stored status

| status | count |
|---|---|
| failed | 23 |
| needs_review | 132 |
| plausible | 2 |
| verified | 1 |
| verified_refined | 3 |

## Primary reason among needs_review

| reason | count |
|---|---|
| image_quality_only | 52 |
| defocus_and_spots | 34 |
| first_order_checksum | 20 |
| aspheres_only_in_image | 17 |
| asphere_rows_unmatched | 5 |
| focus_only | 2 |
| misparsed_surface_names | 2 |

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


## misparsed_surface_names (2)

Surface names are numeric radii. The header was not recognised and the coefficient table could not attach. The stored prescription is not a lens.

| id | failed checks | RMS µm | EFL | F/# | HFOV |
|---|---|---|---|---|---|
| CN105242374B-ex1 | efl, ttl, focus, image_quality | 1768.84 | 11.9 | 1.85 | - |
| CN105242374B-ex2 | efl, ttl, focus, image_quality | 1206.068 | 10.62 | 1.88 | - |

## aspheres_only_in_image (17)

The surface table marks aspheres, but the coefficient table was an image. Even-asphere terms are missing, so the ray trace is of the base conic only.

| id | failed checks | RMS µm | EFL | F/# | HFOV |
|---|---|---|---|---|---|
| CN105204138B-ex1 | image_quality | 126.502 | 2.97 | 2.0 | 46.9 |
| CN105204138B-ex2 | image_quality | 101.292 | 2.97 | 2.0 | 47.0 |
| CN105204138B-ex3 | image_quality | 101.31 | 2.97 | 2.0 | 46.8 |
| CN105204138B-ex4 | image_quality | 51.594 | 2.92 | 2.0 | 45.5 |
| CN105204138B-ex5 | image_quality | 76.299 | 2.95 | 2.0 | 45.4 |
| CN105204138B-ex8 | efl, focus, image_quality | 63.815 | 2.95 | 2.0 | 47.0 |
| CN105988185B-ex10 | image_quality | - | 2.86 | - | 46.3 |
| CN105988185B-ex6 | ttl, image_quality | 126.626 | 3.13 | - | 43.8 |
| CN105988186B-ex4 | image_quality | 508.348 | 6.74 | - | 19.6 |
| CN105988186B-ex6 | image_quality | - | 5.04 | - | 25.1 |
| CN105988186B-ex8 | image_quality | - | 6.14 | - | 21.6 |
| CN110632744B-ex1 | image_quality | 123.144 | - | - | - |
| CN111679399B-ex1 | image_quality | 153.901 | - | - | - |
| CN111679399B-ex3 | image_quality | 201.645 | - | - | - |
| CN114740587B-ex1 | image_quality | - | 4.96 | - | - |
| CN213903939U-ex3 | image_quality | - | 5.41 | - | - |
| CN213903939U-ex8 | efl, focus, image_quality | - | 5.43 | - | - |

## asphere_rows_unmatched (5)

Coefficient rows did not match surface names (stop written as STO+S1, 2(APE), or a bare index). Those coefficients are not in the JSON; recovering them needs a re-extract.

| id | failed checks | RMS µm | EFL | F/# | HFOV |
|---|---|---|---|---|---|
| CN105988185B-ex7 | ttl, image_quality | - | 3.04 | - | 42.6 |
| CN109445077B-ex1 | image_quality | - | - | - | - |
| CN111796396B-ex1 | image_quality | 174.28 | - | - | - |
| CN111796396B-ex3 | image_quality | 48.781 | - | - | - |
| CN216792560U-ex1 | ttl, imgh, focus, image_quality | 374479.093 | - | 1.9 | 39.78 |

## first_order_checksum (20)

EFL, TTL or image height disagrees with the patent text. A single-edit suggestion may exist via `lenszoo fixes`, but the file was not rewritten.

| id | failed checks | RMS µm | EFL | F/# | HFOV |
|---|---|---|---|---|---|
| CN101131464B-ex1 | efl, focus, image_quality | 217.528 | 3.79 | - | - |
| CN105116519B-ex6 | efl, ttl, focus, image_quality | 31.537 | 4.05 | 2.3 | 37.32 |
| CN111123479B-ex1 | efl, focus, image_quality | 165.877 | 2.8 | - | - |
| CN113156611B-ex1 | efl, focus, image_quality | 185.323 | 4.5791 | - | - |
| CN113156611B-ex2 | efl, focus, image_quality | 50.633 | 2.59347 | - | - |
| CN113156611B-ex4 | efl, focus, image_quality | 153.85 | 2.8346 | - | - |
| CN206209180U-ex1 | ttl, focus, image_quality | 342.873 | - | 1.8 | 29.0 |
| CN206209180U-ex2 | ttl, image_quality | 207.013 | - | 2.0 | 30.0 |
| CN213876159U-ex6 | efl, focus, image_quality | 1347.983 | 16.1 | 1.01 | - |
| CN214751066U-ex3 | imgh, image_quality | 125.904 | 3.32 | 1.51 | 21.39 |
| CN214751066U-ex6 | imgh, image_quality | 117.954 | 3.18 | 2.26 | 22.81 |
| CN216792560U-ex1b | ttl, imgh, focus, image_quality | 380828.071 | - | 1.9 | 39.78 |
| CN216792560U-ex2 | ttl, imgh, focus, image_quality | 374127.268 | - | 1.92 | 39.76 |
| CN216792560U-ex2b | ttl, imgh, focus, image_quality | 373671.758 | - | 1.92 | 39.76 |
| CN216792560U-ex3 | ttl, imgh, focus, image_quality | 374797.997 | - | 1.9 | 39.89 |
| CN216792560U-ex3b | ttl, imgh, focus, image_quality | 381194.411 | - | 1.9 | 39.89 |
| CN216792560U-ex4 | ttl, imgh, focus, image_quality | 371393.953 | - | 1.9 | 40.08 |
| CN216792560U-ex4b | ttl, imgh, focus, image_quality | 377737.882 | - | 1.9 | 40.08 |
| CN216792560U-ex5 | ttl, imgh, focus, image_quality | 382256.699 | - | 1.9 | 39.58 |
| CN216792560U-ex6 | ttl, imgh, focus, image_quality | 371593.631 | - | 1.9 | 40.23 |

## defocus_and_spots (34)

Paraxial focus and the published image plane disagree, and the spots at that plane are large. See the CN105116519B note below before treating this as a checker bug.

| id | failed checks | RMS µm | EFL | F/# | HFOV |
|---|---|---|---|---|---|
| CN101131464B-ex9 | focus, image_quality | 627.785 | - | - | - |
| CN101606095B-ex11 | focus, image_quality | 111.139 | - | - | - |
| CN101606095B-ex2 | focus, image_quality | 60.887 | - | - | - |
| CN101606095B-ex2b | focus, image_quality | 85.656 | - | - | - |
| CN101606095B-ex2bb | focus, image_quality | 36.39 | - | - | - |
| CN101606095B-ex2bbb | focus, image_quality | 39.736 | - | - | - |
| CN101606095B-ex8 | focus, image_quality | 56.28 | - | - | - |
| CN103676092B-ex1 | focus, image_quality | 409.242 | - | 1.6 | 35.0 |
| CN103676092B-ex2 | focus, image_quality | 306.198 | - | - | - |
| CN105116519B-ex10 | focus, image_quality | 360.846 | 4.32 | 2.52 | 34.76 |
| CN105116519B-ex11 | focus, image_quality | 28.847 | 3.98 | 2.6 | 37.79 |
| CN105116519B-ex12 | focus, image_quality | 36.484 | 3.97 | 2.2 | 38.14 |
| CN105116519B-ex4 | focus, image_quality | 397.712 | 4.33 | 2.5 | 27.84 |
| CN105116519B-ex5 | focus, image_quality | 34.668 | 4.0 | 2.2 | 37.62 |
| CN105116519B-ex7 | focus, image_quality | 449.075 | 4.31 | 2.4 | 29.11 |
| CN105116519B-ex8 | focus, image_quality | 389.821 | 4.3 | 2.5 | 28.03 |
| CN105116519B-ex9 | focus, image_quality | 390.351 | 4.28 | 2.5 | 27.91 |
| CN109541780B-ex1 | focus, image_quality | 380.405 | - | - | - |
| CN109541780B-ex2 | focus, image_quality | 100.267 | - | - | - |
| CN110858028B-ex1 | focus, image_quality | 178.9 | - | - | - |
| CN110858028B-ex2 | focus, image_quality | 304.957 | - | - | - |
| CN110858028B-ex3 | focus, image_quality | 254.722 | - | - | - |
| CN110858028B-ex4 | focus, image_quality | 196.558 | - | - | - |
| CN111367061B-ex1 | focus, image_quality | 705.744 | - | - | - |
| CN111367061B-ex2 | focus, image_quality | 738.44 | - | - | - |
| CN111367061B-ex3 | focus, image_quality | 842.528 | - | - | - |
| CN113156611B-ex3 | focus, image_quality | 43.766 | 3.57312 | - | - |
| CN206209180U-ex3 | focus, image_quality | - | - | - | - |
| CN206209180U-ex4 | focus, image_quality | 594.331 | - | - | - |
| CN206209180U-ex5 | focus, image_quality | 628.508 | - | - | - |
| CN206209180U-ex6 | focus, image_quality | 594.298 | - | - | - |
| CN206209180U-ex7 | focus, image_quality | - | - | - | - |
| CN206209180U-ex8 | focus, image_quality | 600.129 | - | - | - |
| CN213876159U-ex2b | focus, image_quality | 1490.768 | 16.4 | 1.12 | - |

## focus_only (2)

Spots pass, but the image plane is outside 3x the diffraction depth of focus. No EFL checksum, or the focal length already matches.

| id | failed checks | RMS µm | EFL | F/# | HFOV |
|---|---|---|---|---|---|
| CN112882200B-ex1 | focus | 6.785 | - | - | - |
| CN112882200B-ex2 | focus | 9.379 | - | - | - |

## image_quality_only (52)

First order and focus pass (after index recovery when it ran). Mean RMS spot is over the 15 µm gate. Several of these are fast lenses or were traced at an assumed F/2 and 30°.

| id | failed checks | RMS µm | EFL | F/# | HFOV |
|---|---|---|---|---|---|
| CN101606095B-ex1 | image_quality | 308.269 | - | - | - |
| CN101606095B-ex12 | image_quality | 289.96 | - | - | - |
| CN101606095B-ex13 | image_quality | 332.0 | - | - | - |
| CN101606095B-ex1b | image_quality | 313.349 | - | - | - |
| CN101606095B-ex1bb | image_quality | 293.569 | - | - | - |
| CN101606095B-ex1bbb | image_quality | 435.606 | - | - | - |
| CN101606095B-ex1bbbb | image_quality | 287.113 | - | - | - |
| CN101606095B-ex1bbbbb | image_quality | 301.33 | - | - | - |
| CN101606095B-ex6 | image_quality | 331.142 | - | - | - |
| CN101606095B-ex7 | image_quality | 265.483 | - | - | - |
| CN105988185B-ex2 | image_quality | - | 3.13 | - | 44.2 |
| CN110412727B-ex1 | image_quality | 133.723 | - | - | - |
| CN110456475B-ex2 | image_quality | - | - | - | - |
| CN110542978B-ex1 | image_quality | 361.114 | - | - | - |
| CN110542978B-ex2 | image_quality | 1970.708 | - | - | - |
| CN110794552B-ex1 | image_quality | 66.78 | - | - | - |
| CN110794552B-ex4 | image_quality | 22.56 | - | - | - |
| CN110794552B-ex5 | image_quality | 459.875 | - | - | - |
| CN111123479B-ex2 | image_quality | 151.7 | - | - | - |
| CN111239961B-ex1 | image_quality | 119.286 | - | - | - |
| CN111239961B-ex2 | image_quality | 38.158 | - | - | - |
| CN111367061B-ex4 | image_quality | - | - | - | - |
| CN111679399B-ex2 | image_quality | - | - | - | - |
| CN111679399B-ex4 | image_quality | - | - | - | - |
| CN111679399B-ex5 | image_quality | - | - | - | - |
| CN111796396B-ex4 | image_quality | 131.283 | - | - | - |
| CN111830694B-ex2 | image_quality | 399.641 | 23.553 | 2.2 | - |
| CN111830694B-ex3 | image_quality | 313.135 | - | - | - |
| CN111830694B-ex4 | image_quality | 1723.856 | 20.875 | 2.06 | - |
| CN111830694B-ex5 | image_quality | 190.086 | 21.727 | 2.06 | - |
| CN112180538B-ex1 | image_quality | 85.024 | - | - | - |
| CN112180538B-ex2 | image_quality | 81.288 | - | - | - |
| CN112180538B-ex3 | image_quality | 43.06 | - | - | - |
| CN112180538B-ex4 | image_quality | 64.0 | - | - | - |
| CN112180538B-ex5 | image_quality | 46.484 | - | - | - |
| CN112180538B-ex6 | image_quality | 53.345 | - | - | - |
| CN114740587B-ex3 | image_quality | 24.856 | 5.89 | - | - |
| CN114740587B-ex4 | image_quality | - | 5.16 | - | - |
| CN213876159U-ex1 | image_quality | 2826.871 | 16.4 | 0.97 | - |
| CN213876159U-ex2 | image_quality | 1010.708 | 16.2 | 1.06 | - |
| CN213876159U-ex4 | image_quality | 2543.105 | 16.5 | 1.03 | - |
| CN213876159U-ex5 | image_quality | 1860.838 | 16.0 | 1.02 | - |
| CN213876159U-ex7 | image_quality | 1786.992 | 15.9 | 1.04 | - |
| CN213876159U-ex8 | image_quality | 1910.579 | 16.8 | 1.08 | - |
| CN213876159U-ex9 | image_quality | 3944.091 | 16.4 | 0.95 | - |
| CN213903939U-ex1 | image_quality | - | 5.45 | - | - |
| CN213903939U-ex2 | image_quality | - | 5.41 | - | - |
| CN213903939U-ex6 | image_quality | - | 5.42 | - | - |
| CN213903939U-ex7 | image_quality | 103.485 | 5.43 | - | - |
| CN214751066U-ex2 | image_quality | 39.685 | 3.29 | 1.67 | 22.35 |
| CN214751066U-ex8 | image_quality | 20.965 | 3.33 | 1.46 | 22.67 |
| CN214751066U-ex9 | image_quality | 43.928 | 3.33 | 1.45 | 22.62 |
