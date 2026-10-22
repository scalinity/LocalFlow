# Findings log

Dated, factual, and tied to the generated files. Numbers here are copied from `results/` and must match it; if they differ, `results/` wins.
Development set, 431 cases. "Selected" is the checkpoint chosen by the pre-registered rule; "final" is the last checkpoint.

## 2026-10-16: what the evidence says

1. **Every retrained arm beats C on the primary judged pass rate**, at the selected checkpoint (Opus, original references, `results/RESULTS.md`): C 85.4 percent; M1 89.2 (seed SD 1.1), M2 88.9 (0.7), M3 89.1, A1 90.0, A2 91.6, A2prime 90.0, A3 89.3.
   The exploratory contrasts (outside the pre-declared family, no multiplicity adjustment) put M1, M2 and M3 about 3.5 to 3.9 points above C with intervals that exclude zero. The two base models are far below (71.0 and 71.7 percent).
2. **H1 is not supported on the pre-registered primary endpoint, and the data point the other way.** The earlier data (A2, A2prime) scores the same or higher than the new data on judged pass:
   Opus, selected checkpoints: M2 minus A2prime −1.2 points, M1 minus A2 −2.4 (Holm p 1.0 and 0.17). gpt-6.1-sol, selected: M2 minus A2prime −3.3 (Holm 0.030), M1 minus A2 −3.4 (Holm 0.022), in the direction opposite to H1.
   At the final checkpoint (supplementary, `results/supplementary/final_checkpoints/`): Opus gives A2 and A2prime 94.2 percent against M1 90.0 and M2 89.6 (Holm p 0.0014); gpt-6.1-sol gives 93.7 against 88.6 and 88.4 (M2 minus A2prime −5.3 points, M1 minus A2 −5.2, Holm p 0.001).
3. **The new data wins on the engine's safety metrics.** Engine damage at the selected checkpoint: M2 and M1 0.9 percent against A2prime 5.1 and A2 2.3 (supported under the plan's rule, Holm p 0.0014 and 0.022, as committed; in exact arithmetic the clean form, M1 against A2, has Holm p 0.052 and is not supported, see DEVIATIONS 2026-10-22). No-op preservation: M2 99.1 against A2prime 94.1. At the final checkpoint the gap narrows (engine damage 0.7 against 1.4).
4. **The judges see no safety difference on this development set.** In eight of the nine no-change categories every arm passes 100 percent, and in the ninth (list structure) at least 95 percent (final checkpoints, `results/categories_final.json`).
   All the differences sit in repair categories and long instructions.
5. **The development references follow the earlier label policy.** 76 of the 178 repair references (43 percent) differ from what the new minimal-edit policy produces (`research_normalize_dev.py`; 69 can be normalized, 7 are policy exclusions). They are concentrated where the earlier-data models do better: phrase boundaries, boundary questions, list structure, restriction scope, long instructions.
   Re-referenced to the new policy (supplementary), the Opus judged pass at the final checkpoint is 94.3 to 94.9 percent for every trained arm and 88.6 for C; the earlier-data advantage disappears, and the engine's exact-repair rate favors the new data (63 to 69 percent against 46 to 49; `results/supplementary/normalized_references_selected_engine/` and `normalized_references_final/`).
   At the selected checkpoint with normalized references (`results/supplementary/normalized_references_selected/`), Opus gives M2 minus A2prime +1.8 points (Holm 0.29) and M1 minus A2 +0.5 (Holm 1.0): the sign of H1 flips but no contrast is supported.
   **Neither reference set is policy-neutral.** Which output is right (the earlier policy's more complete repairs, or the new policy's restraint) is a product judgment; human annotation is the tie-breaker.
6. **Contrast rows (H2) show no benefit.** A1 (without contrast rows) is not worse than M1: judged pass 90.0 against 89.2 (Opus, M1 minus A1 −0.8 points, Holm 0.71); gpt-6.1-sol gives M1 minus A1 −1.8 points (Holm 0.022, adjusted interval −3.6 to −0.1, so on that judge A1 is ahead); engine damage is the same. The development set has too few list and question cases to test H2 (35 no-change, 27 repair).
7. **Verifier filtering (H3) shows no benefit.** A3 (vetoed rows unfiltered) matches M1 within seed spread on the primary and damage metrics; no contrast is supported (Opus M1 minus A3 −0.1 points, gpt-6.1-sol +0.5).
8. **The 9B (H4) shows no benefit.** M3 equals M1 on every endpoint (judged pass 89.1 against 89.2) at 1.6 times the latency and 2.1 times the size.
9. **H5 was not tested on this date.** The Claude few-shot systems had not run (cost gate; OPEN_DECISIONS 1). See the 2026-10-17 entry.
10. **Latency and size** (clean sequential pass, `results/latency.json`): every 4B system has median 1.76 to 1.79 s (p95 6.7 to 7.2 s), first token 0.99 s, peak memory 4.3 GB; the 9B 2.88 s (p95 11.3), first token 1.62 s, 6.9 GB.
    Delivered text on every re-run equals the earlier concurrent run on all 431 cases. The base models fall back to the unchanged input on 27.6 percent (4B) and 31.8 percent (9B) of cases; the trained models on 1.9 to 6.5 percent.
11. **Judges.** The three vendors agree on the judged pass rate: pairwise observed agreement 93.6 to 94.8 percent, kappa 0.76 (Opus and gpt-6.1-sol), 0.80 (Opus and Muse), 0.75 (gpt-6.1-sol and Muse), Krippendorff alpha 0.77 over all three (`results/judge_reliability.json`). Agreement on the no-flag rate is lower (kappa 0.39 to 0.65) because flags are rare. Muse's pass rates are lower (C 81.7, M1 84.8, M2 84.3, M3 85.2, A2 90.5, A2prime 88.4) but rank the arms the same way: the earlier-data models ahead of the new-data models, all retrained arms ahead of C. Reversing the presentation order changed the judged pass of 2.1 percent of outputs for Opus (86.6 against 87.0 percent pass rate), 0.8 percent for gpt-6.1-sol (87.1 against 87.2) and 3.0 percent for Muse (83.9 against 82.8, over the 6,006 outputs judged in both orders).
12. **Checkpoint rule.** The lowest validation loss fell early (12 to 63 percent of training); the final checkpoint has no more engine damage than the selected one in 9 of 11 runs (`results/checkpoints.json`).

## 2026-10-17: H5 on the development set

From `results/h5_development/analysis.json`: one judge pass showing M2 (seed 0, checkpoint 426) beside the two few-shot systems, under all three judges, every output judged.

13. **H5 is not supported: M2 is noninferior to Opus 5.5 few-shot but not shown noninferior to Sonnet 5.5 few-shot.**
    Judged pass, M2 / Sonnet few-shot / Opus few-shot: Opus judge 90.3 / 88.6 / 81.4 percent; gpt-6.1-sol 88.6 / 88.9 / 81.9; Muse 84.7 / 87.9 / 77.7.
    - Against Opus few-shot, M2 is ahead under every judge (+8.8, +6.7 and +7.0 points); each adjusted interval excludes zero (lower ends +3.7, +2.3 and +1.6), so noninferiority holds.
      H5 registered only noninferiority, so M2's lead is an observation, not a supported superiority claim.
    - Against Sonnet few-shot the differences are +1.6 (Opus judge), −0.2 (gpt-6.1-sol) and −3.2 points (Muse). The adjusted intervals' lower ends are −3.02, −4.64 and −8.35 against the −3.0 margin: the primary judge misses by 0.02 points, and 431 cases leave the intervals about ±4 to 5 points wide.
14. **On the engine's checks M2 is ahead of both few-shot systems** (seed 0): self-correction success 91.3 percent against 62.3 (Sonnet) and 39.1 (Opus); no-op preserved 97.6 against 84.6 and 95.7; repair success 36.2 against 31.6 and 27.1; engine damage 0.7 against 1.9 and 1.2; Opus-judged unwanted edits 0.5 against 1.9 and 2.3.
    Opus-judged semantic damage is lowest for Sonnet few-shot: 0.2 percent against M2's 0.5 and Opus few-shot's 0.9.
    M2 runs on the device with no per-use cost; the few-shot systems' API costs are in the Claude ledger and not yet in `results/`.

## 2026-10-18: Stage 2 on the locked final set

From `results/stage2/analysis.json`. The plan was sealed on 2026-10-17 at 4:47 p.m. EDT (commit 6a40964, `docs/v2/research/seal/FREEZE.json`); the analysis output was written at 1:27 a.m. EDT on 2026-10-18 and committed as 6946892.
Nine systems ran once each on the 955 final cases and were graded by Sonnet 5.5 and gpt-6.1-sol (AMENDMENT-1). A component passes when the lower end of its 99 percent interval (paired bootstrap, 10,000 resamples, seed 20261015) clears its threshold; a claim needs every component. Every output was graded; Opus 5.5 few-shot answered 954 of the 955 cases, the provider refusing one (AMENDMENT-2).

15. **Supported:** C2, C3, C4, and H5 against Opus 5.5 few-shot.
    - C2: A2prime minus M2 engine damage +5.1 points (99 percent interval +3.2 to +7.1). The rule engine's own check, so it measures conformance to the engine (LIMITATIONS 1).
    - C3: the rewritten-key shift toward the new data is +3.8 points under Sonnet (+2.1 to +5.7) and +2.3 under gpt-6.1-sol (+1.1 to +3.7). The rewrite changed 168 of the 955 references (`A/refinement/final-rewritten.record.json`).
    - C4: M2 minus the untuned 9B +14.8 points under Sonnet (+10.8 to +19.0) and +15.4 under gpt-6.1-sol (+11.8 to +19.1), against a +5.0 margin.
    - H5 against Opus few-shot: M2 minus Opus few-shot +1.3 under Sonnet (−1.6 to +4.0) and +5.5 under gpt-6.1-sol (+2.4 to +8.5), against the −3.0 margin. With the refused case set against the claim: −1.5 to +4.1 and +2.5 to +8.6. Non-inferiority only was registered.
16. **Not supported; each passes under gpt-6.1-sol and fails under Sonnet, and the rule needs both:**
    - C1: M2 minus C judged pass +0.5 under Sonnet (−1.5 to +2.6) and +5.5 under gpt-6.1-sol (+3.5 to +7.9). Its engine-damage component passes: C minus M2 +0.9 (0.0 to +2.0) against −1.0.
    - C5: M1 minus M3 −1.9 under Sonnet (−3.8 to −0.1) and 0.0 under gpt-6.1-sol (−1.6 to +1.6), against −2.0.
    - H5 against Sonnet few-shot: −1.6 under Sonnet (−4.6 to +1.5) and +0.8 under gpt-6.1-sol (−1.7 to +3.4), against −3.0. Sonnet grades its own family's answers here (LIMITATIONS 2).
    "Not supported" means the planned test did not pass, not that the opposite holds.
17. **Per-system values** (judged pass under Sonnet / gpt-6.1-sol; engine damage): C 88.4 / 83.7, 1.5 percent; M2 88.9 / 89.2, 0.5; A2prime 88.0 / 89.2, 5.7; M1 87.4 / 89.1, 0.5; A2 92.0 / 91.4, 1.7; M3 89.3 / 89.1, 0.7; untuned 9B 74.1 / 73.8, 6.1; Sonnet few-shot 90.5 / 88.4, 2.9; Opus few-shot 87.6 / 83.8, 0.6 (954 cases).
    M2 left 98.0 percent of the 559 no-change cases unchanged, against C's 99.6 (reported, not tested).
18. **Model selection on the final set.** The final set did not confirm M2 over C under both graders (C1). The development rule's outcome (keep C) and the post-hoc reading (M2) stand as they were (SELECTION.md).

## 2026-10-21: Sonnet against the human annotations, and the two final graders against each other

19. **Sonnet 5.5 against the author** (AMENDMENT-2 item 3; `A/research/annotation/agreement-sonnet.json`, the pre-registered rule and population, all 150 pairs, no verdict missing): accuracy 43.3 percent (65 of 150), kappa 0.19. The rule calls 59 pairs a tie; where it picks a side, Sonnet matches the author on 65 of 91 (71 percent).
    The three development judges, recomputed in the same file and identical to `agreement.json`: Opus 47.3 percent, kappa 0.29, sided 71 of 78; gpt-6.1-sol 43.3 percent, kappa 0.27, sided 65 of 66; Muse 41.3 percent, kappa 0.25, sided 62 of 66.
    The rule was fixed before any final answer existed, so this result cannot change a claim; it describes how far Sonnet's verdicts follow the author's on development outputs.
20. **The two final graders agree less than the development judges did** (post hoc, DEVIATIONS; `A/research/results/stage2-judge-reliability.json`): on judged pass over the 8,594 graded final outputs, observed agreement 87.7 percent and kappa 0.46, against kappa 0.76 for Opus and gpt-6.1-sol on development. Pass rates over those outputs: Sonnet 87.4 percent, gpt-6.1-sol 86.4.

## Model selection

See [SELECTION.md](SELECTION.md). The pre-registered rule returns **keep C**, failing one gate by a third of a case; the paper should say that, and say what a noninferiority reading would recommend.

## Operational notes the write-up should not hide

- Every judge column is its forward-order run, as planned (`judge_runs` in `results/analysis.json`); the reversed-order runs supply order stability. gpt-6.1-sol's forward run was collected a day late, after its collecting process stopped on a transport error (DEVIATIONS).
- In Muse's swapped-order pass, 17 of 1,439 distinct outputs remain unjudged after both recovery rounds; order stability for Muse is computed over the outputs judged in both orders.
- Two judge processes ended while requests were in flight; one OpenRouter request's response was lost and its cost was written off by hand at its maximum ($0.002). See DEVIATIONS.
- The OpenRouter (Meta Muse) judge hits its output limit on its first pass for most outputs and needs recovery requests; its verdicts are reported as a third column when complete.
