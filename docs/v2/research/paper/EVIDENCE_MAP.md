# Evidence map

One row per claim the paper may make. "Evidence" names the generated file (in `results/`) that holds the number; "Status" uses the analysis plan's words.
Statuses reflect `results/` as of the last update; re-derive them from `results/analysis.json` before writing. Narrative: [FINDINGS.md](FINDINGS.md).

| Claim | Evidence | Status | Notes |
|---|---|---|---|
| H1 (shipped form): M2 beats A2prime on the primary judged pass rate | `analysis.json` contrast "M2 vs A2prime" on `anthropic:judged_pass` | **not supported; difference points the other way** (Opus −1.2, gpt-6.1-sol −3.3) | Supported on engine damage (+4.25 points, Holm 0.0014); see FINDINGS 2, 3, 5 |
| H1 (clean form): M1 beats A2 | contrast "M1 vs A2" | **not supported; opposite direction** (Opus −2.4, gpt-6.1-sol −3.4, Holm 0.022) | Engine damage supported (Holm 0.022) |
| H1 at the final checkpoint | `supplementary/final_checkpoints/` | opposite direction on the judged pass rate (A2 and A2prime 94.2 against M1 90.0, M2 89.6, Holm 0.0014) | Post hoc; references follow the earlier policy (FINDINGS 5) |
| H1 with policy-consistent references | `supplementary/normalized_references_final/` | no difference on the judged pass rate (94.3 to 94.9 for every trained arm) | Post hoc; engine exact-repair favors the new data by construction |
| H2: contrast rows reduce wrongful edits on list and question cases without hurting repair recall | contrast "M1 vs A1"; `h2_subset`; `categories_*.json` | **not supported; exploratory** | 35 no-change and 27 repair cases; see LIMITATIONS 4 |
| H3: verifier filtering beats leaving vetoed rows unfiltered | contrast "M1 vs A3" | **not supported** | A3 matches M1 within seed spread |
| H4: the 9B beats the 4B enough to matter | contrast "M3 vs M1"; `latency.json` | **not supported** | Equal quality, 1.6 times the latency, 2.1 times the size |
| H5: M2 within 3 points of each few-shot frontier model at a fraction of cost and latency | contrasts vs `sonnet-5-5-fewshot`, `opus-5-5-fewshot` | **not tested** | Claude few-shot systems did not run (OPEN_DECISIONS 1) |
| Every retrained arm beats C on the judged pass rate | `RESULTS.md` exploratory contrasts "M1/M2/M3 vs C" | observed (+3.5 to +3.9 points, intervals exclude zero); outside the pre-declared family | At the final checkpoint with normalized references C is 88.6 against about 94.4 |
| Seed spread of M1 and M2 | `arm_values.csv` (seed_sd) | measured | Judged pass SD 1.1 (M1), 0.7 (M2) at the selected checkpoint |
| Judges agree across vendors | `judge_reliability.json` | measured: pairwise kappa 0.75 to 0.80, Krippendorff alpha 0.77 over three vendors | Forward-order runs for all three vendors |
| Judges are position-stable | `judge_reliability.json` `order_stability` | measured: 2.1 percent of outputs changed for Opus, 0.8 for gpt-6.1-sol, 3.0 for Muse | Muse over the 6,006 outputs judged in both orders |
| Judges agree with humans | `agreement.json`, `agreement-swapped.json`, `judge-reliability.json` in `A/research/annotation/` | measured: four-way agreement 41 to 47 percent, kappa 0.25 to 0.29 (Opus 0.29, gpt-6.1-sol 0.27, Muse 0.25); where the frozen rule picks a side it matches the author on 91 percent (Opus), 98.5 (gpt-6.1-sol) and 94 (Muse) of those pairs | The rule calls 72 to 84 of the 150 pairs a tie; the author chose a side on every pair. Test-retest 15 of 15. The packet holds one C–M2 pair |
| Latency and memory on device | `latency.json` | measured (clean sequential pass) | 4B 1.76 to 1.79 s median; 9B 2.88 s |
| Which model to ship | `selection.json`, [SELECTION.md](SELECTION.md) | rule: **keep C**; recommendation (post hoc): M2 | Gate failed by a third of a case |
| The selected-checkpoint rule matters | `checkpoints.json` | observed | Final checkpoint has no more damage than selected in 9 of 11 runs |
