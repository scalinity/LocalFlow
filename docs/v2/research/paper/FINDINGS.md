# Findings log

Dated, factual, and tied to the generated files. Numbers here are copied from `results/` and must match it; if they differ, `results/` wins.
Development set, 431 cases. "Selected" is the checkpoint chosen by the pre-registered rule; "final" is the last checkpoint.

## 2026-10-16: what the evidence says

1. **Every retrained arm beats C on the primary judged pass rate**, at the selected checkpoint (Opus, original references, `results/RESULTS.md`): C 85.4 percent; M1 89.2 (seed SD 1.1), M2 88.9 (0.7), M3 89.1, A1 90.0, A2 91.6, A2prime 90.0, A3 89.3.
   The exploratory contrasts (outside the pre-declared family, no multiplicity adjustment) put M1, M2 and M3 about 3.5 to 3.9 points above C with intervals that exclude zero. The two base models are far below (71.0 and 71.7 percent).
2. **H1 is not supported on the pre-registered primary endpoint, and the data point the other way.** The earlier data (A2, A2prime) scores the same or higher than the new data on judged pass:
   Opus, selected checkpoints: M2 minus A2prime −1.2 points, M1 minus A2 −2.4 (Holm p 1.0 and 0.17). gpt-6.1-sol, selected: M2 minus A2prime −3.3 (Holm 0.030), M1 minus A2 −3.4 (Holm 0.022), in the direction opposite to H1.
   At the final checkpoint (supplementary, Opus, `results/supplementary/final_checkpoints/`): A2 and A2prime 94.2 percent against M1 90.0 and M2 89.6, Holm p 0.0014.
3. **The new data wins on the engine's safety metrics.** Engine damage at the selected checkpoint: M2 and M1 0.9 percent against A2prime 5.1 and A2 2.3 (supported under the plan's rule, Holm p 0.0014 and 0.022). No-op preservation: M2 99.1 against A2prime 94.1. At the final checkpoint the gap narrows (engine damage 0.7 against 1.4).
4. **The judges see no safety difference on this development set.** In eight of the nine no-change categories every arm passes 100 percent, and in the ninth (list structure) at least 95 percent (final checkpoints, `results/categories_final.json`).
   All the differences sit in repair categories and long instructions.
5. **The development references follow the earlier label policy.** 76 of the 178 repair references (43 percent) differ from what the new minimal-edit policy produces (`research_normalize_dev.py`; 69 can be normalized, 7 are policy exclusions). They are concentrated where the earlier-data models do better: phrase boundaries, boundary questions, list structure, restriction scope, long instructions.
   Re-referenced to the new policy (supplementary), the Opus judged pass at the final checkpoint is 94.3 to 94.9 percent for every trained arm and 88.6 for C; the earlier-data advantage disappears, and the engine's exact-repair rate favors the new data (63 to 69 percent against 46 to 49; `results/supplementary/normalized_references_selected_engine/` and `normalized_references_final/`).
   At the selected checkpoint with normalized references (`results/supplementary/normalized_references_selected/`), Opus gives M2 minus A2prime +1.8 points (Holm 0.29) and M1 minus A2 +0.5 (Holm 1.0): the sign of H1 flips but no contrast is supported.
   **Neither reference set is policy-neutral.** Which output is right (the earlier policy's more complete repairs, or the new policy's restraint) is a product judgment; human annotation is the tie-breaker.
6. **Contrast rows (H2) show no benefit.** A1 (without contrast rows) is not worse than M1: judged pass 90.0 against 89.2 (Opus, M1 minus A1 −0.8 points, Holm 0.71); gpt-6.1-sol gives M1 minus A1 −1.8 points (Holm 0.022, adjusted interval −3.6 to −0.1, so on that judge A1 is ahead); engine damage is the same. The development set has too few list and question cases to test H2 (35 no-change, 27 repair).
7. **Verifier filtering (H3) shows no benefit.** A3 (vetoed rows unfiltered) matches M1 within seed spread on the primary and damage metrics; no contrast is supported (Opus M1 minus A3 −0.1 points, gpt-6.1-sol +0.5).
8. **The 9B (H4) shows no benefit.** M3 equals M1 on every endpoint (judged pass 89.1 against 89.2) at 1.6 times the latency and 2.1 times the size.
9. **H5 is not tested.** The Claude few-shot systems did not run (cost gate; OPEN_DECISIONS 1).
10. **Latency and size** (clean sequential pass, `results/latency.json`): every 4B system has median 1.76 to 1.79 s (p95 6.7 to 7.2 s), first token 0.99 s, peak memory 4.3 GB; the 9B 2.88 s (p95 11.3), first token 1.62 s, 6.9 GB.
    Delivered text on every re-run equals the earlier concurrent run on all 431 cases. The base models fall back to the unchanged input on 27.6 percent (4B) and 31.8 percent (9B) of cases; the trained models on 1.9 to 6.5 percent.
11. **Judges.** The three vendors agree on the judged pass rate: pairwise observed agreement 93.6 to 94.8 percent, kappa 0.76 (Opus and gpt-6.1-sol), 0.80 (Opus and Muse), 0.75 (gpt-6.1-sol and Muse), Krippendorff alpha 0.77 over all three (`results/judge_reliability.json`). Agreement on the no-flag rate is lower (kappa 0.39 to 0.65) because flags are rare. Muse's pass rates are lower (C 81.7, M1 84.8, M2 84.3, M3 85.2, A2 90.5, A2prime 88.4) but rank the arms the same way: the earlier-data models ahead of the new-data models, all retrained arms ahead of C. Reversing the presentation order changed the judged pass of 2.1 percent of outputs for Opus (86.6 against 87.0 percent pass rate), 0.8 percent for gpt-6.1-sol (87.1 against 87.2) and 3.0 percent for Muse (83.9 against 82.8, over the 6,006 outputs judged in both orders).
12. **Checkpoint rule.** The lowest validation loss fell early (12 to 63 percent of training); the final checkpoint has no more engine damage than the selected one in 9 of 11 runs (`results/checkpoints.json`).

## Model selection

See [SELECTION.md](SELECTION.md). The pre-registered rule returns **keep C**, failing one gate by a third of a case; the paper should say that, and say what a noninferiority reading would recommend.

## Operational notes the write-up should not hide

- Every judge column is its forward-order run, as planned (`judge_runs` in `results/analysis.json`); the reversed-order runs supply order stability. gpt-6.1-sol's forward run was collected a day late, after its collecting process stopped on a transport error (DEVIATIONS).
- In Muse's swapped-order pass, 17 of 1,439 distinct outputs remain unjudged after both recovery rounds; order stability for Muse is computed over the outputs judged in both orders.
- Two judge processes ended while requests were in flight; one OpenRouter request's response was lost and its cost was written off by hand at its maximum ($0.002). See DEVIATIONS.
- The OpenRouter (Meta Muse) judge hits its output limit on its first pass for most outputs and needs recovery requests; its verdicts are reported as a third column when complete.
