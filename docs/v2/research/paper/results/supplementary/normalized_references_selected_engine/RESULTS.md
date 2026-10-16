# Results (generated; do not edit)

Development set, 431 cases, delivered text, selected checkpoint of each run. Percent values; seed spread is the sample SD over seeds (M1, M2 only).
Bootstrap: 10000 resamples, seed 20261015. Unjudged rows counted as failures: {}.
Judge runs behind each column: {}.

## Arm values

| Metric | C | base-4b-prod-prompt | base-9b-prod-prompt | A2prime | A2 | A1 | A3 | M1 | M2 | M3 |
|---|---|---|---|---|---|---|---|---|---|---|
| Engine damage | 1.6% | 3.0% | 5.6% | 5.1% | 2.3% | 0.9% | 0.5% | 0.9% (sd 0.5) | 0.9% (sd 0.3) | 0.9% |
| Engine no-op preserved | 99.6% | 70.4% | 55.7% | 94.1% | 95.7% | 98.0% | 99.6% | 98.3% (sd 1.0) | 99.1% (sd 1.3) | 98.4% |
| Engine repair success | 33.6% | 20.2% | 22.0% | 34.1% | 35.3% | 36.0% | 36.0% | 35.8% (sd 1.1) | 35.5% (sd 0.6) | 35.5% |
| Engine correction success | 78.3% | 11.6% | 14.5% | 85.5% | 87.0% | 88.4% | 89.9% | 88.4% (sd 3.8) | 87.0% (sd 3.8) | 85.5% |

## Contrasts on engine_damage

| Contrast | n | Difference (first better) | 95% interval | Adjusted interval | p | Holm p | Seed SD | Supported |
|---|---|---|---|---|---|---|---|---|
| M2 vs A2prime | 431 | +4.25 pts | [+2.40, +6.26] | [+1.86, +7.04] | 0.0002 | 0.0014 | 0.27 pts | yes |
| M1 vs A2 | 431 | +1.47 pts | [+0.31, +2.78] | [+0.00, +3.40] | 0.0036 | 0.0216 | 0.48 pts | yes |
| M1 vs A1 | 431 | +0.08 pts | [-0.39, +0.70] | [-0.54, +1.01] | 0.7441 | 1.0000 | 0.48 pts | no |
| M1 vs A3 | 431 | -0.39 pts | [-1.01, +0.08] | [-1.31, +0.15] | 0.1730 | 0.8649 | 0.48 pts | no |
| M3 vs M1 | 431 | -0.08 pts | [-0.70, +0.39] | [-1.01, +0.54] | 0.7343 | 1.0000 | 0.48 pts | no |

## Contrasts on engine_noop_preserved

| Contrast | n | Difference (first better) | 95% interval | Adjusted interval | p | Holm p | Seed SD | Supported |
|---|---|---|---|---|---|---|---|---|
| M2 vs A2prime | 253 | +5.01 pts | [+2.24, +8.17] | [+1.32, +9.35] | 0.0002 | 0.0014 | 1.27 pts | yes |
| M1 vs A2 | 253 | +2.64 pts | [+0.13, +5.40] | [-0.79, +6.59] | 0.0396 | 0.1980 | 0.99 pts | no |
| M1 vs A1 | 253 | +0.26 pts | [-1.05, +1.71] | [-1.45, +2.24] | 0.8013 | 1.0000 | 0.99 pts | no |
| M1 vs A3 | 253 | -1.32 pts | [-2.77, -0.13] | [-3.29, +0.40] | 0.0280 | 0.1680 | 0.99 pts | no |
| M3 vs M1 | 253 | +0.13 pts | [-1.45, +1.45] | [-2.11, +1.84] | 0.7443 | 1.0000 | 0.99 pts | no |

## Contrasts on engine_repair_success

| Contrast | n | Difference (first better) | 95% interval | Adjusted interval | p | Holm p | Seed SD | Supported |
|---|---|---|---|---|---|---|---|---|
| M2 vs A2prime | 431 | +1.39 pts | [-0.23, +3.09] | [-0.77, +3.71] | 0.1050 | 0.7349 | 0.61 pts | no |
| M1 vs A2 | 431 | +0.54 pts | [-0.54, +1.78] | [-0.93, +2.24] | 0.3990 | 1.0000 | 1.07 pts | no |
| M1 vs A1 | 431 | -0.15 pts | [-0.77, +0.62] | [-0.93, +0.87] | 0.5463 | 1.0000 | 1.07 pts | no |
| M1 vs A3 | 431 | -0.15 pts | [-0.77, +0.54] | [-1.01, +0.93] | 0.5451 | 1.0000 | 1.07 pts | no |
| M3 vs M1 | 431 | -0.31 pts | [-1.39, +0.62] | [-1.78, +1.01] | 0.6013 | 1.0000 | 1.07 pts | no |

## Exploratory contrasts on engine_damage (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | +0.77 pts | [-0.08, +1.86] | 0.0660 |
| M2 vs C | 431 | +0.77 pts | [+0.00, +1.70] | 0.0424 |
| M3 vs C | 431 | +0.70 pts | [-0.00, +1.62] | 0.0996 |
| M2 vs base-4b-prod-prompt | 431 | +2.17 pts | [+0.54, +3.94] | 0.0082 |
| M2 vs M1 | 431 | -0.00 pts | [-0.39, +0.39] | 0.9601 |
| A2prime vs C | 431 | -3.48 pts | [-5.34, -1.86] | 0.0002 |

## H2 subset (list and question cases)

62 cases: 35 need no change, 27 need repair. Underpowered; exploratory.

| Metric | C | base-4b-prod-prompt | base-9b-prod-prompt | A2prime | A2 | A1 | A3 | M1 | M2 | M3 |
|---|---|---|---|---|---|---|---|---|---|---|
| engine_reference_repair@repair | 29.6% | 7.4% | 7.4% | 29.6% | 14.8% | 40.7% | 59.3% | 48.1% | 55.6% | 40.7% |
| engine_unnecessary_edit@no_change | 0/35 | 12/35 | 14/35 | 2/35 | 3/35 | 0/35 | 1/35 | 0/35 | 1/35 | 0/35 |

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
