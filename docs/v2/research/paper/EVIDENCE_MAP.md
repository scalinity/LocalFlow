# Evidence map

One row per claim the paper may make. "Evidence" names the generated file (in `results/`) that holds the number;
"Status" uses the analysis plan's words. Statuses are filled by a session that has read `results/RESULTS.md`;
a row whose status is blank has not been evaluated.

| Claim | Evidence | Status | Notes |
|---|---|---|---|
| H1 (shipped form): M2 beats A2prime on the primary judged pass rate | `analysis.json` contrasts, "M2 vs A2prime" | | Same start (C), different data |
| H1 (clean form): M1 beats A2 | contrast "M1 vs A2" | | Fresh adapters, different data |
| H2: contrast rows reduce wrongful edits on list and question cases without hurting repair recall | contrast "M1 vs A1"; `h2_subset` | exploratory | 35 no-change and 27 repair cases on the development set; see LIMITATIONS 4 |
| H3: verifier filtering beats leaving vetoed rows unfiltered | contrast "M1 vs A3" | | A replication in one setting |
| H4: the 9B beats the 4B enough to matter | contrast "M3 vs M1" | | One 9B run; also check latency and size |
| H5: M2 is within 3 points of each few-shot frontier model at a fraction of cost and latency | contrasts "M2 vs sonnet-5-5-fewshot", "M2 vs opus-5-5-fewshot"; latency and cost tables | not tested until the few-shot systems run | See OPEN_DECISIONS 1 |
| Seed spread of M1 and M2 | `arm_values.csv` (seed_sd) | | Three seeds each |
| Judges agree across vendors | `judge_reliability.json` | | Opus, gpt-6.1-sol, Muse |
| Judges are position-stable | `position_*.json` (swapped-order runs) | | |
| Judges agree with humans | `agreement.json` | not available until annotation exists | OPEN_DECISIONS 3 |
| Latency and memory on device | `latency.json` | | Sequential clean pass |
| Which model to ship | `selection.json` | | Rule in ANALYSIS_PLAN.md |
| The earlier data produces more wrongful edits than the new data (engine metrics) | `arm_values.csv` rows `engine_damage` | | Programmatic, secondary |
