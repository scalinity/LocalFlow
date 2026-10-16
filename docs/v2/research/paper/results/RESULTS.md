# Results (generated; do not edit)

Development set, 431 cases, delivered text, selected checkpoint of each run. Percent values; seed spread is the sample SD over seeds (M1, M2 only).
Bootstrap: 10000 resamples, seed 20261015. Unjudged rows counted as failures: {'anthropic': 0, 'openai': 0, 'openrouter': 0}.
Judge runs behind each column: {'anthropic': 'dev-main-anthropic', 'openai': 'dev-swap-openai', 'openrouter': 'dev-main-openrouter'}.

## Arm values

| Metric | C | base-4b-prod-prompt | base-9b-prod-prompt | A2prime | A2 | A1 | A3 | M1 | M2 | M3 |
|---|---|---|---|---|---|---|---|---|---|---|
| Opus judged pass (primary) | 85.4% | 71.0% | 71.7% | 90.0% | 91.6% | 90.0% | 89.3% | 89.2% (sd 1.1) | 88.9% (sd 0.7) | 89.1% |
| Opus judged no-flag | 99.3% | 94.7% | 91.0% | 97.7% | 98.8% | 99.5% | 99.3% | 99.1% (sd 0.9) | 99.5% (sd 0.1) | 99.3% |
| Opus semantic damage | 0.5% | 1.6% | 1.6% | 0.7% | 0.5% | 0.2% | 0.7% | 0.7% (sd 0.6) | 0.5% (sd 0.1) | 0.2% |
| Opus hallucination | 0.0% | 0.5% | 0.2% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% (sd 0.0) | 0.0% (sd 0.0) | 0.0% |
| Opus unwanted edit | 0.2% | 4.4% | 8.6% | 1.9% | 0.7% | 0.2% | 0.0% | 0.5% (sd 0.8) | 0.1% (sd 0.1) | 0.5% |
| Opus cleanup complete | 26.7% | 15.8% | 19.7% | 32.9% | 33.4% | 31.3% | 30.6% | 30.5% (sd 1.0) | 30.2% (sd 0.7) | 30.6% |
| gpt-6.1-sol judged pass | 83.5% | 73.3% | 77.3% | 91.9% | 93.3% | 91.0% | 88.4% | 89.3% (sd 0.8) | 88.2% (sd 0.9) | 89.1% |
| Muse judged pass | 81.7% | 72.2% | 73.8% | 88.4% | 90.5% | 86.5% | 84.9% | 84.8% (sd 0.7) | 84.3% (sd 0.5) | 85.2% |
| Engine damage | 1.6% | 3.0% | 5.6% | 5.1% | 2.3% | 0.9% | 0.5% | 0.9% (sd 0.5) | 0.9% (sd 0.3) | 0.9% |
| Engine no-op preserved | 99.6% | 70.4% | 55.7% | 94.1% | 95.7% | 98.0% | 99.6% | 98.3% (sd 1.0) | 99.1% (sd 1.3) | 98.4% |
| Engine repair success | 33.6% | 20.2% | 22.0% | 34.1% | 35.3% | 36.0% | 36.0% | 35.8% (sd 1.1) | 35.5% (sd 0.6) | 35.5% |
| Engine correction success | 78.3% | 11.6% | 14.5% | 85.5% | 87.0% | 88.4% | 89.9% | 88.4% (sd 3.8) | 87.0% (sd 3.8) | 85.5% |

## Contrasts on anthropic:judged_pass

| Contrast | n | Difference (first better) | 95% interval | Adjusted interval | p | Holm p | Seed SD | Supported |
|---|---|---|---|---|---|---|---|---|
| M2 vs A2prime | 431 | -1.16 pts | [-3.71, +1.39] | [-4.56, +2.27] | 0.3574 | 1.0000 | 0.70 pts | no |
| M1 vs A2 | 431 | -2.40 pts | [-4.64, -0.23] | [-5.41, +0.54] | 0.0248 | 0.1736 | 1.14 pts | no |
| M1 vs A1 | 431 | -0.77 pts | [-1.86, +0.23] | [-2.24, +0.70] | 0.1186 | 0.7115 | 1.14 pts | no |
| M1 vs A3 | 431 | -0.08 pts | [-1.16, +1.08] | [-1.62, +1.55] | 0.8193 | 1.0000 | 1.14 pts | no |
| M3 vs M1 | 431 | -0.15 pts | [-1.62, +1.16] | [-2.17, +1.70] | 0.8941 | 1.0000 | 1.14 pts | no |

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

## Contrasts on openai:judged_pass

| Contrast | n | Difference (first better) | 95% interval | Adjusted interval | p | Holm p | Seed SD | Supported |
|---|---|---|---|---|---|---|---|---|
| M2 vs A2prime | 431 | -3.63 pts | [-6.19, -1.16] | [-7.19, -0.23] | 0.0040 | 0.0240 | 0.94 pts | no |
| M1 vs A2 | 431 | -3.94 pts | [-6.34, -1.70] | [-7.35, -0.85] | 0.0012 | 0.0084 | 0.80 pts | no |
| M1 vs A1 | 431 | -1.62 pts | [-3.02, -0.31] | [-3.56, +0.08] | 0.0092 | 0.0460 | 0.80 pts | no |
| M1 vs A3 | 431 | +0.93 pts | [-0.31, +2.32] | [-0.77, +2.78] | 0.1744 | 0.6975 | 0.80 pts | no |
| M3 vs M1 | 431 | -0.23 pts | [-1.78, +1.24] | [-2.40, +1.78] | 0.8151 | 1.0000 | 0.80 pts | no |

## Contrasts on openrouter:judged_pass

| Contrast | n | Difference (first better) | 95% interval | Adjusted interval | p | Holm p | Seed SD | Supported |
|---|---|---|---|---|---|---|---|---|
| M2 vs A2prime | 431 | -4.10 pts | [-6.89, -1.31] | [-7.97, -0.39] | 0.0034 | 0.0170 | 0.54 pts | no |
| M1 vs A2 | 431 | -5.65 pts | [-8.35, -3.17] | [-9.44, -2.09] | 0.0002 | 0.0014 | 0.75 pts | no |
| M1 vs A1 | 431 | -1.70 pts | [-2.86, -0.62] | [-3.33, -0.23] | 0.0008 | 0.0048 | 0.75 pts | no |
| M1 vs A3 | 431 | -0.08 pts | [-1.08, +1.01] | [-1.55, +1.47] | 0.8229 | 1.0000 | 0.75 pts | no |
| M3 vs M1 | 431 | +0.31 pts | [-1.47, +1.93] | [-2.01, +2.55] | 0.6871 | 1.0000 | 0.75 pts | no |

## Exploratory contrasts on anthropic:judged_clean (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | -0.15 pts | [-0.70, +0.46] | 0.5001 |
| M2 vs C | 431 | +0.15 pts | [-0.62, +0.93] | 0.8157 |
| M3 vs C | 431 | +0.00 pts | [-0.70, +0.70] | 1.0000 |
| M2 vs base-4b-prod-prompt | 431 | +4.80 pts | [+2.78, +6.96] | 0.0002 |
| M2 vs M1 | 431 | +0.31 pts | [-0.23, +0.85] | 0.1938 |
| A2prime vs C | 431 | -1.62 pts | [-3.02, -0.23] | 0.0192 |

## Exploratory contrasts on anthropic:judged_cleanup_complete (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | +3.87 pts | [+1.78, +6.11] | 0.0002 |
| M2 vs C | 431 | +3.48 pts | [+1.31, +5.72] | 0.0010 |
| M3 vs C | 431 | +3.94 pts | [+1.39, +6.50] | 0.0026 |
| M2 vs base-4b-prod-prompt | 431 | +14.39 pts | [+10.36, +18.48] | 0.0002 |
| M2 vs M1 | 431 | -0.39 pts | [-1.24, +0.39] | 0.3848 |
| A2prime vs C | 431 | +6.26 pts | [+3.71, +9.05] | 0.0002 |

## Exploratory contrasts on anthropic:judged_pass (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | +3.87 pts | [+1.78, +6.03] | 0.0002 |
| M2 vs C | 431 | +3.48 pts | [+1.24, +5.80] | 0.0022 |
| M3 vs C | 431 | +3.71 pts | [+1.16, +6.26] | 0.0052 |
| M2 vs base-4b-prod-prompt | 431 | +17.87 pts | [+13.61, +22.27] | 0.0002 |
| M2 vs M1 | 431 | -0.39 pts | [-1.31, +0.46] | 0.4548 |
| A2prime vs C | 431 | +4.64 pts | [+1.62, +7.66] | 0.0026 |

## Exploratory contrasts on anthropic:judged_semantic_damage (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | -0.23 pts | [-0.70, +0.23] | 0.3908 |
| M2 vs C | 431 | -0.08 pts | [-0.77, +0.62] | 0.9189 |
| M3 vs C | 431 | +0.23 pts | [-0.00, +0.70] | 0.7433 |
| M2 vs base-4b-prod-prompt | 431 | +1.08 pts | [-0.00, +2.32] | 0.0656 |
| M2 vs M1 | 431 | +0.15 pts | [-0.31, +0.62] | 0.6135 |
| A2prime vs C | 431 | -0.23 pts | [-1.16, +0.46] | 0.7777 |

## Exploratory contrasts on anthropic:judged_unwanted_edit (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | -0.23 pts | [-0.70, +0.23] | 0.3972 |
| M2 vs C | 431 | +0.15 pts | [-0.23, +0.70] | 0.7381 |
| M3 vs C | 431 | -0.23 pts | [-0.70, -0.00] | 0.7343 |
| M2 vs base-4b-prod-prompt | 431 | +4.33 pts | [+2.47, +6.26] | 0.0002 |
| M2 vs M1 | 431 | +0.39 pts | [-0.00, +0.77] | 0.0660 |
| A2prime vs C | 431 | -1.62 pts | [-3.02, -0.46] | 0.0014 |

## Exploratory contrasts on engine_damage (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | +0.77 pts | [-0.08, +1.86] | 0.0660 |
| M2 vs C | 431 | +0.77 pts | [+0.00, +1.70] | 0.0424 |
| M3 vs C | 431 | +0.70 pts | [-0.00, +1.62] | 0.0996 |
| M2 vs base-4b-prod-prompt | 431 | +2.17 pts | [+0.54, +3.94] | 0.0082 |
| M2 vs M1 | 431 | -0.00 pts | [-0.39, +0.39] | 0.9601 |
| A2prime vs C | 431 | -3.48 pts | [-5.34, -1.86] | 0.0002 |

## Exploratory contrasts on openai:judged_clean (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | -0.39 pts | [-0.77, -0.08] | 0.0142 |
| M2 vs C | 431 | -0.31 pts | [-0.85, +0.00] | 0.2724 |
| M3 vs C | 431 | +0.00 pts | [+0.00, +0.00] | 1.0000 |
| M2 vs base-4b-prod-prompt | 431 | +2.47 pts | [+0.93, +4.18] | 0.0006 |
| M2 vs M1 | 431 | +0.08 pts | [-0.39, +0.54] | 0.6421 |
| A2prime vs C | 431 | -0.46 pts | [-1.16, +0.00] | 0.2676 |

## Exploratory contrasts on openai:judged_cleanup_complete (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | +5.80 pts | [+3.33, +8.28] | 0.0002 |
| M2 vs C | 431 | +4.72 pts | [+2.17, +7.35] | 0.0002 |
| M3 vs C | 431 | +5.57 pts | [+2.55, +8.58] | 0.0002 |
| M2 vs base-4b-prod-prompt | 431 | +13.53 pts | [+9.67, +17.63] | 0.0002 |
| M2 vs M1 | 431 | -1.08 pts | [-2.09, -0.08] | 0.0372 |
| A2prime vs C | 431 | +8.58 pts | [+5.57, +11.60] | 0.0002 |

## Exploratory contrasts on openai:judged_semantic_damage (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | -0.39 pts | [-0.77, -0.08] | 0.0142 |
| M2 vs C | 431 | -0.31 pts | [-0.85, -0.00] | 0.2724 |
| M3 vs C | 431 | -0.00 pts | [-0.00, -0.00] | 1.0000 |
| M2 vs base-4b-prod-prompt | 431 | +0.39 pts | [-0.46, +1.39] | 0.4412 |
| M2 vs M1 | 431 | +0.08 pts | [-0.39, +0.54] | 0.8273 |
| A2prime vs C | 431 | -0.23 pts | [-0.70, -0.00] | 0.7437 |

## Exploratory contrasts on openai:judged_unwanted_edit (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | -0.39 pts | [-0.77, -0.08] | 0.0142 |
| M2 vs C | 431 | -0.31 pts | [-0.85, -0.00] | 0.2724 |
| M3 vs C | 431 | -0.00 pts | [-0.00, -0.00] | 1.0000 |
| M2 vs base-4b-prod-prompt | 431 | +2.47 pts | [+0.93, +4.18] | 0.0006 |
| M2 vs M1 | 431 | +0.08 pts | [-0.39, +0.54] | 0.8273 |
| A2prime vs C | 431 | -0.46 pts | [-1.16, -0.00] | 0.2676 |

## Exploratory contrasts on openrouter:judged_clean (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | -0.46 pts | [-0.85, -0.15] | 0.0044 |
| M2 vs C | 431 | -0.31 pts | [-0.85, +0.00] | 0.2724 |
| M3 vs C | 431 | -0.23 pts | [-0.70, +0.00] | 0.7249 |
| M2 vs base-4b-prod-prompt | 431 | +2.94 pts | [+1.31, +4.80] | 0.0004 |
| M2 vs M1 | 431 | +0.15 pts | [-0.31, +0.62] | 0.4470 |
| A2prime vs C | 431 | -1.62 pts | [-2.78, -0.46] | 0.0012 |

## Exploratory contrasts on openrouter:judged_cleanup_complete (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | +3.25 pts | [+1.24, +5.34] | 0.0008 |
| M2 vs C | 431 | +2.63 pts | [+0.39, +4.95] | 0.0232 |
| M3 vs C | 431 | +3.48 pts | [+0.70, +6.26] | 0.0196 |
| M2 vs base-4b-prod-prompt | 431 | +10.52 pts | [+6.34, +14.77] | 0.0002 |
| M2 vs M1 | 431 | -0.62 pts | [-1.62, +0.31] | 0.2382 |
| A2prime vs C | 431 | +7.66 pts | [+4.87, +10.67] | 0.0002 |

## Exploratory contrasts on openrouter:judged_semantic_damage (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | -0.46 pts | [-0.85, -0.15] | 0.0044 |
| M2 vs C | 431 | -0.31 pts | [-0.85, -0.00] | 0.2724 |
| M3 vs C | 431 | -0.23 pts | [-0.70, -0.00] | 0.7249 |
| M2 vs base-4b-prod-prompt | 431 | +0.85 pts | [-0.23, +2.09] | 0.1302 |
| M2 vs M1 | 431 | +0.15 pts | [-0.31, +0.62] | 0.6037 |
| A2prime vs C | 431 | -1.16 pts | [-2.32, -0.23] | 0.0128 |

## Exploratory contrasts on openrouter:judged_unwanted_edit (outside the pre-declared family; no multiplicity adjustment)

| Contrast | n | Difference (first better) | 95% interval | p |
|---|---|---|---|---|
| M1 vs C | 431 | -0.46 pts | [-0.85, -0.15] | 0.0044 |
| M2 vs C | 431 | -0.31 pts | [-0.85, -0.00] | 0.2724 |
| M3 vs C | 431 | -0.23 pts | [-0.70, -0.00] | 0.7249 |
| M2 vs base-4b-prod-prompt | 431 | +2.94 pts | [+1.31, +4.80] | 0.0004 |
| M2 vs M1 | 431 | +0.15 pts | [-0.31, +0.62] | 0.6037 |
| A2prime vs C | 431 | -1.62 pts | [-2.78, -0.46] | 0.0012 |

## H2 subset (list and question cases)

62 cases: 35 need no change, 27 need repair. Underpowered; exploratory.

| Metric | C | base-4b-prod-prompt | base-9b-prod-prompt | A2prime | A2 | A1 | A3 | M1 | M2 | M3 |
|---|---|---|---|---|---|---|---|---|---|---|
| anthropic:judged_cleanup_complete@no_change | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| anthropic:judged_cleanup_complete@repair | 59.3% | 51.9% | 70.4% | 85.2% | 88.9% | 77.8% | 70.4% | 77.8% | 74.1% | 77.8% |
| anthropic:judged_semantic_damage@no_change | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 |
| anthropic:judged_semantic_damage@repair | 0/27 | 0/27 | 0/27 | 0/27 | 0/27 | 0/27 | 0/27 | 0/27 | 0/27 | 0/27 |
| anthropic:judged_unwanted_edit@no_change | 0/35 | 0/35 | 2/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 |
| anthropic:judged_unwanted_edit@repair | 1/27 | 0/27 | 3/27 | 1/27 | 1/27 | 0/27 | 0/27 | 0/27 | 0/27 | 1/27 |
| engine_reference_repair@repair | 22.2% | 18.5% | 18.5% | 40.7% | 33.3% | 25.9% | 29.6% | 29.6% | 29.6% | 25.9% |
| engine_unnecessary_edit@no_change | 0/35 | 12/35 | 14/35 | 2/35 | 3/35 | 0/35 | 1/35 | 0/35 | 1/35 | 0/35 |
| openai:judged_cleanup_complete@no_change | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| openai:judged_cleanup_complete@repair | 51.9% | 55.6% | 70.4% | 81.5% | 88.9% | 81.5% | 63.0% | 74.1% | 69.1% | 77.8% |
| openai:judged_semantic_damage@no_change | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 |
| openai:judged_semantic_damage@repair | 0/27 | 1/27 | 1/27 | 0/27 | 1/27 | 0/27 | 0/27 | 0/27 | 0/27 | 0/27 |
| openai:judged_unwanted_edit@no_change | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 |
| openai:judged_unwanted_edit@repair | 0/27 | 1/27 | 1/27 | 0/27 | 1/27 | 0/27 | 0/27 | 0/27 | 0/27 | 0/27 |
| openrouter:judged_cleanup_complete@no_change | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| openrouter:judged_cleanup_complete@repair | 44.4% | 48.1% | 63.0% | 77.8% | 77.8% | 55.6% | 48.1% | 53.1% | 51.9% | 59.3% |
| openrouter:judged_semantic_damage@no_change | 0/35 | 1/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 |
| openrouter:judged_semantic_damage@repair | 0/27 | 1/27 | 2/27 | 1/27 | 1/27 | 0/27 | 0/27 | 0/27 | 0/27 | 1/27 |
| openrouter:judged_unwanted_edit@no_change | 0/35 | 1/35 | 3/35 | 1/35 | 1/35 | 0/35 | 0/35 | 0/35 | 0/35 | 0/35 |
| openrouter:judged_unwanted_edit@repair | 0/27 | 1/27 | 2/27 | 1/27 | 1/27 | 0/27 | 0/27 | 0/27 | 0/27 | 1/27 |

## Selected versus final checkpoint (programmatic, delivered text)

| Run | Damage selected / final | No-op preserved selected / final | Repair success selected / final | Corrections selected / final |
|---|---|---|---|---|
| A1 (A1-ck624, A1-final) | 0.9% / 0.7% | 98.0% / 99.2% | 36.0% / 36.2% | 88.4% / 89.9% |
| A2 (A2-ck199, A2-final) | 2.3% / 1.4% | 95.7% / 96.8% | 35.3% / 36.0% | 87.0% / 91.3% |
| A2prime (A2prime-ck199, A2prime-final) | 5.1% / 1.4% | 94.1% / 96.8% | 34.1% / 35.7% | 85.5% / 91.3% |
| A3 (A3-ck434, A3-final) | 0.5% / 0.7% | 99.6% / 98.8% | 36.0% / 36.4% | 89.9% / 91.3% |
| M1 seed0 (M1s0-ck426, M1s0-final) | 0.7% / 0.7% | 98.4% / 98.8% | 36.4% / 36.0% | 91.3% / 88.4% |
| M1 seed1 (M1s1-ck852, M1s1-final) | 0.5% / 0.7% | 99.2% / 99.6% | 36.4% / 36.4% | 89.9% / 92.8% |
| M1 seed2 (M1s2-ck213, M1s2-final) | 1.4% / 0.7% | 97.2% / 98.4% | 34.6% / 36.2% | 84.1% / 91.3% |
| M2 seed0 (M2s0-ck426, M2s0-final) | 0.7% / 0.7% | 97.6% / 98.8% | 36.2% / 35.3% | 91.3% / 87.0% |
| M2 seed1 (M2s1-ck1065, M2s1-final) | 0.7% / 0.7% | 100.0% / 99.6% | 35.0% / 36.0% | 84.1% / 89.9% |
| M2 seed2 (M2s2-ck852, M2s2-final) | 1.2% / 0.7% | 99.6% / 98.8% | 35.3% / 36.0% | 85.5% / 89.9% |
| M3 (M3-ck426, M3-final) | 0.9% / 0.7% | 98.4% / 99.6% | 35.5% / 36.2% | 85.5% / 92.8% |

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

## Model selection (ANALYSIS_PLAN.md rule)

Decision: **KEEP_C**

no candidate passed the gates

- M1: failed judged_damage_not_above_C
- M2: failed judged_damage_not_above_C
- M3: failed median_latency_within_1.5x_C, quantized_size_within_1.5x_C

## Judge reliability

```json
{
 "krippendorff_alpha_judged_pass": {
  "alpha": 0.779235095761226,
  "expected_disagreement": 0.24372628178458086,
  "observed_disagreement": 0.05380620925864545,
  "omitted_units": 0,
  "ratings": 18102,
  "reason": null,
  "units": 6034
 },
 "order_stability": {
  "anthropic": {
   "judged_pass_changed": 125,
   "outputs": 6034,
   "pass_rate_forward": 0.8660921445144183,
   "pass_rate_reversed": 0.8695724229366921,
   "share_changed": 0.020715942989724893
  }
 },
 "pairwise": {
  "anthropic vs openai": {
   "critical_fact_changed": {
    "kappa": 0.24790600279198888,
    "n": 6034,
    "observed_agreement": 0.995028173682466
   },
   "hallucination": {
    "kappa": -0.00024865312891500166,
    "n": 6034,
    "observed_agreement": 0.9993370898243288
   },
   "judged_clean": {
    "kappa": 0.40313425875769693,
    "n": 6034,
    "observed_agreement": 0.9860788863109049
   },
   "judged_pass": {
    "kappa": 0.7730431474174094,
    "n": 6034,
    "observed_agreement": 0.9482930062976467
   },
   "semantic_damage": {
    "kappa": 0.4895900981777904,
    "n": 6034,
    "observed_agreement": 0.9948624461385482
   },
   "unwanted_edit": {
    "kappa": 0.39859877466068494,
    "n": 6034,
    "observed_agreement": 0.9887305270135897
   }
  },
  "anthropic vs openrouter": {
   "critical_fact_changed": {
    "kappa": 0.16026648230784266,
    "n": 6034,
    "observed_agreement": 0.9948624461385482
   },
   "hallucination": {
    "kappa": 0.0,
    "n": 6034,
    "observed_agreement": 0.9995028173682466
   },
   "judged_clean": {
    "kappa": 0.47820931972236136,
    "n": 6034,
    "observed_agreement": 0.9862446138548226
   },
   "judged_pass": {
    "kappa": 0.7957092762973295,
    "n": 6034,
    "observed_agreement": 0.9481272787537288
   },
   "semantic_damage": {
    "kappa": 0.3798957700546748,
    "n": 6034,
    "observed_agreement": 0.9925422605236991
   },
   "unwanted_edit": {
    "kappa": 0.49079655692732993,
    "n": 6034,
    "observed_agreement": 0.9888962545575074
   }
  },
  "openai vs openrouter": {
   "critical_fact_changed": {
    "kappa": 0.7614982055052345,
    "n": 6034,
    "observed_agreement": 0.999171362280411
   },
   "hallucination": {
    "kappa": 0.0,
    "n": 6034,
    "observed_agreement": 0.9998342724560823
   },
   "judged_clean": {
    "kappa": 0.6790036945044724,
    "n": 6034,
    "observed_agreement": 0.9951939012263838
   },
   "judged_pass": {
    "kappa": 0.7687632659380672,
    "n": 6034,
    "observed_agreement": 0.9421610871726881
   },
   "semantic_damage": {
    "kappa": 0.7189024430823749,
    "n": 6034,
    "observed_agreement": 0.9976798143851509
   },
   "unwanted_edit": {
    "kappa": 0.6790036945044724,
    "n": 6034,
    "observed_agreement": 0.9951939012263838
   }
  }
 },
 "pass_rate": {
  "anthropic": 0.8660921445144183,
  "openai": 0.8717268810076235,
  "openrouter": 0.8360954590652967
 },
 "unjudged_outputs": {
  "anthropic": 0,
  "anthropic:swapped": 0,
  "openai": 0,
  "openrouter": 0
 }
}
```
