# Results (generated; do not edit)

Development set, 431 cases, delivered text, selected checkpoint of each run. Percent values; seed spread is the sample SD over seeds (M1, M2 only).
Bootstrap: 10000 resamples, seed 20261015. Unjudged rows counted as failures: {'anthropic': 0}.
Judge runs behind each column: {'anthropic': 'dev-norm-final-anthropic'}.

## Arm values

| Metric | C | base-4b-prod-prompt | base-9b-prod-prompt | A2prime | A2 | A1 | A3 | M1 | M2 | M3 |
|---|---|---|---|---|---|---|---|---|---|---|
| Opus judged pass (primary) | 88.6% | 70.8% | 72.9% | 94.4% | 94.4% | 94.4% | 94.9% | 94.3% (sd 0.4) | 94.3% (sd 0.1) | 94.4% |
| Opus judged no-flag | 100.0% | 93.7% | 91.4% | 100.0% | 99.8% | 99.8% | 99.8% | 99.5% (sd 0.2) | 99.7% (sd 0.1) | 99.8% |
| Opus semantic damage | 0.0% | 1.9% | 2.1% | 0.0% | 0.0% | 0.2% | 0.2% | 0.5% (sd 0.2) | 0.3% (sd 0.1) | 0.2% |
| Opus hallucination | 0.0% | 0.5% | 0.2% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% (sd 0.0) | 0.0% (sd 0.0) | 0.0% |
| Opus unwanted edit | 0.0% | 5.3% | 8.1% | 0.0% | 0.2% | 0.2% | 0.0% | 0.3% (sd 0.4) | 0.1% (sd 0.1) | 0.2% |
| Opus cleanup complete | 29.2% | 15.5% | 19.3% | 35.0% | 35.3% | 35.0% | 35.5% | 34.9% (sd 0.1) | 34.6% (sd 0.1) | 34.8% |
| Engine damage | 1.6% | 3.0% | 5.6% | 1.4% | 1.4% | 0.7% | 0.7% | 0.7% (sd 0.0) | 0.7% (sd 0.0) | 0.7% |
| Engine no-op preserved | 99.6% | 70.4% | 55.7% | 96.8% | 96.8% | 99.2% | 98.8% | 98.9% (sd 0.6) | 99.1% (sd 0.5) | 99.6% |
| Engine repair success | 33.6% | 20.2% | 22.0% | 35.7% | 36.0% | 36.2% | 36.4% | 36.2% (sd 0.2) | 35.7% (sd 0.4) | 36.2% |
| Engine correction success | 78.3% | 11.6% | 14.5% | 91.3% | 91.3% | 89.9% | 91.3% | 90.8% (sd 2.2) | 88.9% (sd 1.7) | 92.8% |

## Contrasts on anthropic:judged_pass

| Contrast | n | Difference (first better) | 95% interval | Adjusted interval | p | Holm p | Seed SD | Supported |
|---|---|---|---|---|---|---|---|---|
| M2 vs A2prime | 431 | -0.15 pts | [-1.55, +1.24] | [-2.09, +1.80] | 0.7879 | 1.0000 | 0.13 pts | no |
| M1 vs A2 | 431 | -0.15 pts | [-1.47, +1.16] | [-1.93, +1.78] | 0.7609 | 1.0000 | 0.35 pts | no |
| M1 vs A1 | 431 | -0.15 pts | [-0.93, +0.62] | [-1.24, +0.85] | 0.6269 | 1.0000 | 0.35 pts | no |
| M1 vs A3 | 431 | -0.62 pts | [-1.31, -0.00] | [-1.62, +0.23] | 0.0342 | 0.2394 | 0.35 pts | no |
| M3 vs M1 | 431 | +0.15 pts | [-1.16, +1.47] | [-1.78, +1.93] | 0.7729 | 1.0000 | 0.35 pts | no |

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
| M1 vs C | 431 | -0.46 pts | [-1.01, -0.08] | 0.0354 |
| M2 vs C | 431 | -0.31 pts | [-0.85, +0.00] | 0.2724 |
| M3 vs C | 431 | -0.23 pts | [-0.70, +0.00] | 0.7405 |
| M2 vs base-4b-prod-prompt | 431 | +5.96 pts | [+3.71, +8.35] | 0.0002 |
| M2 vs M1 | 431 | +0.15 pts | [-0.15, +0.46] | 0.2590 |
| A2prime vs C | 431 | +0.00 pts | [+0.00, +0.00] | 1.0000 |

## Exploratory contrasts on anthropic:judged_cleanup_complete (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | +5.65 pts | [+3.40, +8.04] | 0.0002 |
| M2 vs C | 431 | +5.41 pts | [+3.17, +7.81] | 0.0002 |
| M3 vs C | 431 | +5.57 pts | [+3.25, +7.89] | 0.0002 |
| M2 vs base-4b-prod-prompt | 431 | +19.10 pts | [+15.39, +22.89] | 0.0002 |
| M2 vs M1 | 431 | -0.23 pts | [-1.01, +0.54] | 0.6417 |
| A2prime vs C | 431 | +5.80 pts | [+3.71, +8.12] | 0.0002 |

## Exploratory contrasts on anthropic:judged_pass (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | +5.65 pts | [+3.40, +8.04] | 0.0002 |
| M2 vs C | 431 | +5.65 pts | [+3.33, +8.12] | 0.0002 |
| M3 vs C | 431 | +5.80 pts | [+3.48, +8.12] | 0.0002 |
| M2 vs base-4b-prod-prompt | 431 | +23.51 pts | [+19.49, +27.53] | 0.0002 |
| M2 vs M1 | 431 | +0.00 pts | [-0.85, +0.85] | 0.9011 |
| A2prime vs C | 431 | +5.80 pts | [+3.71, +8.12] | 0.0002 |

## Exploratory contrasts on anthropic:judged_semantic_damage (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | -0.46 pts | [-1.01, -0.08] | 0.0354 |
| M2 vs C | 431 | -0.31 pts | [-0.85, -0.00] | 0.2724 |
| M3 vs C | 431 | -0.23 pts | [-0.70, -0.00] | 0.7405 |
| M2 vs base-4b-prod-prompt | 431 | +1.55 pts | [+0.23, +3.02] | 0.0166 |
| M2 vs M1 | 431 | +0.15 pts | [-0.15, +0.46] | 0.4402 |
| A2prime vs C | 431 | -0.00 pts | [-0.00, -0.00] | 1.0000 |

## Exploratory contrasts on anthropic:judged_unwanted_edit (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | -0.31 pts | [-0.77, -0.00] | 0.0944 |
| M2 vs C | 431 | -0.08 pts | [-0.23, -0.00] | 0.7405 |
| M3 vs C | 431 | -0.23 pts | [-0.70, -0.00] | 0.7405 |
| M2 vs base-4b-prod-prompt | 431 | +5.26 pts | [+3.25, +7.42] | 0.0002 |
| M2 vs M1 | 431 | +0.23 pts | [-0.00, +0.54] | 0.0944 |
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
| anthropic:judged_cleanup_complete@repair | 59.3% | 48.1% | 66.7% | 81.5% | 85.2% | 88.9% | 92.6% | 90.1% | 87.7% | 85.2% |
| anthropic:judged_semantic_damage@no_change | 0/35 | 1/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 |
| anthropic:judged_semantic_damage@repair | 0/27 | 0/27 | 1/27 | 0/27 | 0/27 | 0/27 | 0/27 | 0/27 | 0/27 | 0/27 |
| anthropic:judged_unwanted_edit@no_change | 0/35 | 2/35 | 3/35 | 0/35 | 1/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 |
| anthropic:judged_unwanted_edit@repair | 0/27 | 1/27 | 2/27 | 0/27 | 0/27 | 0/27 | 0/27 | 0/27 | 0/27 | 0/27 |
| engine_reference_repair@repair | 29.6% | 7.4% | 7.4% | 25.9% | 18.5% | 51.9% | 55.6% | 55.6% | 55.6% | 51.9% |
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
