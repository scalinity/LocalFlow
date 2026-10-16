# Results (generated; do not edit)

Development set, 431 cases, delivered text, selected checkpoint of each run. Percent values; seed spread is the sample SD over seeds (M1, M2 only).
Bootstrap: 10000 resamples, seed 20261015. Unjudged rows counted as failures: {'anthropic': 0}.

## Arm values

| Metric | C | base-4b-prod-prompt | base-9b-prod-prompt | A2prime | A2 | A1 | A3 | M1 | M2 | M3 |
|---|---|---|---|---|---|---|---|---|---|---|
| Opus judged pass (primary) | 86.1% | 71.0% | 72.4% | 94.2% | 94.2% | 90.3% | 90.5% | 90.0% (sd 0.4) | 89.6% (sd 0.2) | 90.0% |
| Opus judged no-flag | 100.0% | 93.7% | 90.5% | 100.0% | 99.8% | 99.8% | 99.8% | 99.7% (sd 0.1) | 99.8% (sd 0.0) | 100.0% |
| Opus semantic damage | 0.0% | 1.6% | 2.1% | 0.0% | 0.0% | 0.2% | 0.2% | 0.3% (sd 0.1) | 0.2% (sd 0.0) | 0.0% |
| Opus hallucination | 0.0% | 0.5% | 0.2% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% (sd 0.0) | 0.0% (sd 0.0) | 0.0% |
| Opus unwanted edit | 0.0% | 5.3% | 9.0% | 0.0% | 0.2% | 0.2% | 0.0% | 0.2% (sd 0.3) | 0.0% (sd 0.0) | 0.0% |
| Opus cleanup complete | 27.1% | 15.8% | 19.7% | 35.3% | 35.5% | 31.6% | 32.0% | 31.5% (sd 0.4) | 31.1% (sd 0.2) | 31.1% |
| Engine damage | 1.6% | 3.0% | 5.6% | 1.4% | 1.4% | 0.7% | 0.7% | 0.7% (sd 0.0) | 0.7% (sd 0.0) | 0.7% |
| Engine no-op preserved | 99.6% | 70.4% | 55.7% | 96.8% | 96.8% | 99.2% | 98.8% | 98.9% (sd 0.6) | 99.1% (sd 0.5) | 99.6% |
| Engine repair success | 33.6% | 20.2% | 22.0% | 35.7% | 36.0% | 36.2% | 36.4% | 36.2% (sd 0.2) | 35.7% (sd 0.4) | 36.2% |
| Engine correction success | 78.3% | 11.6% | 14.5% | 91.3% | 91.3% | 89.9% | 91.3% | 90.8% (sd 2.2) | 88.9% (sd 1.7) | 92.8% |

## Contrasts on anthropic:judged_pass

| Contrast | n | Difference (first better) | 95% interval | Adjusted interval | p | Holm p | Seed SD | Supported |
|---|---|---|---|---|---|---|---|---|
| M2 vs A2prime | 431 | -4.64 pts | [-6.96, -2.55] | [-7.81, -1.86] | 0.0002 | 0.0014 | 0.23 pts | no |
| M1 vs A2 | 431 | -4.18 pts | [-6.50, -2.09] | [-7.35, -1.24] | 0.0002 | 0.0014 | 0.40 pts | no |
| M1 vs A1 | 431 | -0.23 pts | [-0.93, +0.46] | [-1.24, +0.70] | 0.4582 | 1.0000 | 0.40 pts | no |
| M1 vs A3 | 431 | -0.46 pts | [-1.16, +0.15] | [-1.39, +0.31] | 0.0984 | 0.4920 | 0.40 pts | no |
| M3 vs M1 | 431 | +0.00 pts | [-1.39, +1.31] | [-1.93, +1.86] | 0.9337 | 1.0000 | 0.40 pts | no |

## Contrasts on engine_damage

| Contrast | n | Difference (first better) | 95% interval | Adjusted interval | p | Holm p | Seed SD | Supported |
|---|---|---|---|---|---|---|---|---|
| M2 vs A2prime | 431 | +0.70 pts | [-0.00, +1.62] | [-0.00, +1.92] | 0.0924 | 0.6467 | 0.00 pts | no |
| M1 vs A2 | 431 | +0.70 pts | [-0.23, +1.86] | [-0.70, +2.32] | 0.2546 | 1.0000 | 0.00 pts | no |
| M1 vs A1 | 431 | -0.00 pts | [-0.00, -0.00] | [-0.00, -0.00] | 1.0000 | 1.0000 | 0.00 pts | no |
| M1 vs A3 | 431 | -0.00 pts | [-0.00, -0.00] | [-0.00, -0.00] | 1.0000 | 1.0000 | 0.00 pts | no |
| M3 vs M1 | 431 | -0.00 pts | [-0.00, -0.00] | [-0.00, -0.00] | 1.0000 | 1.0000 | 0.00 pts | no |

## Contrasts on engine_noop_preserved

| Contrast | n | Difference (first better) | 95% interval | Adjusted interval | p | Holm p | Seed SD | Supported |
|---|---|---|---|---|---|---|---|---|
| M2 vs A2prime | 253 | +2.24 pts | [+0.26, +4.48] | [-0.40, +5.53] | 0.0322 | 0.2226 | 0.46 pts | no |
| M1 vs A2 | 253 | +2.11 pts | [+0.13, +4.35] | [-0.53, +5.40] | 0.0454 | 0.2270 | 0.60 pts | no |
| M1 vs A1 | 253 | -0.26 pts | [-1.05, +0.53] | [-1.45, +0.92] | 0.4276 | 1.0000 | 0.60 pts | no |
| M1 vs A3 | 253 | +0.13 pts | [-0.53, +0.92] | [-0.66, +1.19] | 0.8843 | 1.0000 | 0.60 pts | no |
| M3 vs M1 | 253 | +0.66 pts | [+0.13, +1.45] | [+0.00, +1.84] | 0.0318 | 0.2226 | 0.60 pts | no |

## Contrasts on engine_repair_success

| Contrast | n | Difference (first better) | 95% interval | Adjusted interval | p | Holm p | Seed SD | Supported |
|---|---|---|---|---|---|---|---|---|
| M2 vs A2prime | 431 | -0.00 pts | [-1.01, +1.08] | [-1.31, +1.47] | 0.9389 | 1.0000 | 0.40 pts | no |
| M1 vs A2 | 431 | +0.23 pts | [-0.39, +1.01] | [-0.62, +1.39] | 0.6387 | 1.0000 | 0.23 pts | no |
| M1 vs A1 | 431 | -0.00 pts | [-0.23, +0.23] | [-0.31, +0.31] | 0.9647 | 1.0000 | 0.23 pts | no |
| M1 vs A3 | 431 | -0.23 pts | [-0.62, +0.00] | [-0.85, +0.00] | 0.2770 | 1.0000 | 0.23 pts | no |
| M3 vs M1 | 431 | +0.00 pts | [-0.93, +0.85] | [-1.24, +1.16] | 0.9573 | 1.0000 | 0.23 pts | no |

## Exploratory contrasts on anthropic:judged_clean (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | -0.31 pts | [-0.70, +0.00] | 0.0994 |
| M2 vs C | 431 | -0.23 pts | [-0.70, +0.00] | 0.7437 |
| M3 vs C | 431 | +0.00 pts | [+0.00, +0.00] | 1.0000 |
| M2 vs base-4b-prod-prompt | 431 | +6.03 pts | [+3.71, +8.35] | 0.0002 |
| M2 vs M1 | 431 | +0.08 pts | [-0.15, +0.39] | 0.4546 |
| A2prime vs C | 431 | +0.00 pts | [+0.00, +0.00] | 1.0000 |

## Exploratory contrasts on anthropic:judged_cleanup_complete (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | +4.33 pts | [+2.09, +6.73] | 0.0002 |
| M2 vs C | 431 | +3.94 pts | [+1.70, +6.34] | 0.0002 |
| M3 vs C | 431 | +3.94 pts | [+1.62, +6.26] | 0.0012 |
| M2 vs base-4b-prod-prompt | 431 | +15.31 pts | [+11.29, +19.33] | 0.0002 |
| M2 vs M1 | 431 | -0.39 pts | [-1.24, +0.39] | 0.3868 |
| A2prime vs C | 431 | +8.12 pts | [+5.57, +10.68] | 0.0002 |

## Exploratory contrasts on anthropic:judged_pass (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | +3.94 pts | [+1.62, +6.42] | 0.0008 |
| M2 vs C | 431 | +3.48 pts | [+1.16, +5.96] | 0.0034 |
| M3 vs C | 431 | +3.94 pts | [+1.62, +6.26] | 0.0012 |
| M2 vs base-4b-prod-prompt | 431 | +18.56 pts | [+14.23, +22.89] | 0.0002 |
| M2 vs M1 | 431 | -0.46 pts | [-1.31, +0.31] | 0.3090 |
| A2prime vs C | 431 | +8.12 pts | [+5.57, +10.68] | 0.0002 |

## Exploratory contrasts on anthropic:judged_semantic_damage (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | -0.31 pts | [-0.70, -0.00] | 0.0994 |
| M2 vs C | 431 | -0.23 pts | [-0.70, -0.00] | 0.7437 |
| M3 vs C | 431 | -0.00 pts | [-0.00, -0.00] | 1.0000 |
| M2 vs base-4b-prod-prompt | 431 | +1.39 pts | [+0.23, +2.78] | 0.0300 |
| M2 vs M1 | 431 | +0.08 pts | [-0.15, +0.39] | 0.7751 |
| A2prime vs C | 431 | -0.00 pts | [-0.00, -0.00] | 1.0000 |

## Exploratory contrasts on anthropic:judged_unwanted_edit (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | -0.15 pts | [-0.39, -0.00] | 0.2612 |
| M2 vs C | 431 | -0.00 pts | [-0.00, -0.00] | 1.0000 |
| M3 vs C | 431 | -0.00 pts | [-0.00, -0.00] | 1.0000 |
| M2 vs base-4b-prod-prompt | 431 | +5.34 pts | [+3.25, +7.42] | 0.0002 |
| M2 vs M1 | 431 | +0.15 pts | [-0.00, +0.39] | 0.2612 |
| A2prime vs C | 431 | -0.00 pts | [-0.00, -0.00] | 1.0000 |

## Exploratory contrasts on engine_damage (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | +0.93 pts | [+0.23, +1.86] | 0.0372 |
| M2 vs C | 431 | +0.93 pts | [+0.23, +1.86] | 0.0372 |
| M3 vs C | 431 | +0.93 pts | [+0.23, +1.86] | 0.0372 |
| M2 vs base-4b-prod-prompt | 431 | +2.32 pts | [+0.70, +4.18] | 0.0074 |
| M2 vs M1 | 431 | -0.00 pts | [-0.00, -0.00] | 1.0000 |
| A2prime vs C | 431 | +0.23 pts | [-0.46, +1.16] | 0.7823 |

## H2 subset (list and question cases)

62 cases: 35 need no change, 27 need repair. Underpowered; exploratory.

| Metric | C | base-4b-prod-prompt | base-9b-prod-prompt | A2prime | A2 | A1 | A3 | M1 | M2 | M3 |
|---|---|---|---|---|---|---|---|---|---|---|
| anthropic:judged_cleanup_complete@no_change | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| anthropic:judged_cleanup_complete@repair | 59.3% | 51.9% | 66.7% | 85.2% | 85.2% | 77.8% | 77.8% | 77.8% | 74.1% | 74.1% |
| anthropic:judged_semantic_damage@no_change | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 |
| anthropic:judged_semantic_damage@repair | 0/27 | 0/27 | 1/27 | 0/27 | 0/27 | 0/27 | 0/27 | 0/27 | 0/27 | 0/27 |
| anthropic:judged_unwanted_edit@no_change | 0/35 | 2/35 | 4/35 | 0/35 | 1/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 |
| anthropic:judged_unwanted_edit@repair | 0/27 | 1/27 | 3/27 | 0/27 | 0/27 | 0/27 | 0/27 | 0/27 | 0/27 | 0/27 |
| engine_reference_repair@repair | 22.2% | 18.5% | 18.5% | 37.0% | 37.0% | 29.6% | 29.6% | 29.6% | 29.6% | 25.9% |
| engine_unnecessary_edit@no_change | 0/35 | 12/35 | 14/35 | 3/35 | 3/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 |

## Latency (sequential clean pass on an idle Mac, 4-bit)

| System | median total (s) | p95 total (s) | median first token (s) | peak MLX (GB) | fallback | same text as earlier run |
|---|---|---|---|---|---|---|
| C | 1.79 | 7.17 | 0.99 | 4.3 | 6.5% | 431/431 |
| base-4b-prod-prompt | 1.80 | 7.22 | 0.99 | 4.3 | 27.6% | - |
| base-9b-prod-prompt | 2.99 | 12.89 | 1.62 | 6.9 | 31.8% | - |
| A2prime | 1.77 | 6.79 | 0.99 | 4.3 | 3.0% | 431/431 |
| A2 | 1.77 | 6.77 | 0.99 | 4.3 | 2.8% | 431/431 |
| A1 | 1.77 | 6.76 | 0.99 | 4.3 | 2.3% | 431/431 |
| A3 | 1.76 | 6.68 | 0.99 | 4.3 | 2.1% | 431/431 |
| M1 | 1.76 | 6.77 | 0.99 | 4.3 | 1.9% | 431/431 |
| M2 | 1.76 | 6.81 | 0.99 | 4.3 | 2.1% | 431/431 |
| M3 | 2.88 | 11.27 | 1.62 | 6.9 | 4.2% | 431/431 |
