# Writing guide for the write-up session

You write the paper from the files in this folder. You do not run experiments, call APIs, open locked data or change the analysis.

## Rules

1. **Every number comes from a file here** (`results/RESULTS.md`, `results/analysis.json`, `results/stage2/analysis.json`, `data/manifest.json`, the pre-registration, the analysis plan, the amendments) or from the private aggregates EVIDENCE_MAP names under `A/`. If a number is not in a file, it does not go in the paper.
2. **Status words are fixed by `EVIDENCE_MAP.md`.** "Supported" only where the governing rule says so: on the development set, the analysis plan's (adjusted p below 0.05, adjusted interval excludes 0, difference above the seed SD); on the final set, Amendment 1's (every component's 99 percent interval clears its threshold, under both graders). Everything else is "observed", "not supported" or "not tested". Where the graders split, write the split; do not average them or pick one.
3. **No first-of-kind claims.** Existing work covers speech repair, minimal-edit rewriting, contrast sets, LLM judges and public MLX dictation-cleanup models. The contribution is the measured comparison under a locked, multi-vendor, human-calibrated evaluation, on-device.
4. **Say what was exploratory.** The development-set H2 result is exploratory (35 and 27 cases). Anything decided after seeing results is a deviation and goes in the deviation log.
5. **Do not publish private material:** Claude-generated rows, targets, model outputs, case text, per-case scores or weights. Tables are aggregates.
6. **Name the limits** from `LIMITATIONS.md` in the paper's own limitations section, with the same specifics.
7. **Disclose AI assistance** in the research and the writing, as the pre-registration states.
8. **Cite from the scan.** The bibliography and per-paper notes are private (`A/research/literature/scan.md`, `related.bib`); the must-cites are: Mind the Pause; DRES v2; Toward Interactive Dictation;
   Adapting LLMs for Minimal-edit GEC; AlpaGasus; Counterfactually-Augmented Data; Contrast Sets; Distilling Step-by-Step; Gated Delta Networks; PoLL (judge juries).

## Framing

The sealed final set decided five claims and H5 once, under two graders from different vendors; the development set decided H1 to H5 before it.
Pre-registration is what makes null and opposite-direction results credible, so report them as results, with their intervals.

- Lead with what the final set confirmed: supervision beats scale (C4); engine-checked data cuts engine-detected damage (C2);
  the reference key's editing policy moves judged comparisons (C3); and the 4B is non-inferior to Claude Opus 5.5 few-shot
  within the 3-point margin (H5 against Opus).
- Then what it did not confirm, and why that depends on the grader: C1 (M2 against C), C5 (4B against 9B) and H5 against
  Sonnet 5.5 few-shot each pass under gpt-6.1-sol and fail under Sonnet, and the rule needs both. Report the two graders'
  final-set agreement and Sonnet's agreement with the author beside them (FINDINGS 19, 20).
- Then the development-set findings, labelled as such: H1 to H5 not supported on their primary endpoints; on judged pass the
  new data trails the earlier data and re-referencing flips the sign (FINDINGS 5); on engine damage the new data wins
  (supported); every retrained arm beats C by about 3.5 to 3.9 judged points (exploratory). H2 stays exploratory and
  makes no final-set claim.
- Model selection: the pre-registered rule says keep C; M2 is a labelled post-hoc reading; the final set did not confirm
  M2 over C under both graders. The paper recommends no model to ship.
- The contribution is a measured, reproducible, on-device comparison under a locked, multi-vendor, human-calibrated
  evaluation (rule 3). Venue fit follows that frame; verify dates and calls before choosing (PAPER_BRIEF).

## Outline (adapt to the venue; keep the order of argument)

1. Introduction: the product problem (cleanup must not change meaning; the cost of a wrongful edit), the study, the findings in two sentences, the limits in one.
2. Related work: speech repair and disfluency; dictation and post-ASR correction; synthetic data and verifiers; contrast sets and learning when not to edit; LLM judges and human agreement.
3. System and data: the engine and validator, the training pool and its sources, the contrast twins, the verifier filter (cite DATA_CARDS).
4. Study design: arms, seeds, fixed training settings, checkpoint rule, evaluation set, metrics, judges, statistics (cite PREREGISTRATION and ANALYSIS_PLAN; state the deviations).
5. Results: the final-set claims (C1 to C5, H5) with their status words and both graders' intervals; then the development set (the retrained models against the installed one, H1 to H5, the reference-policy analysis); then judge reliability (agreement between vendors, position bias, human agreement, the final graders' agreement); then latency and cost.
6. Model selection: the rule, the gates, the outcome.
7. Limitations and ethics (provenance, release constraints, terms).
8. Conclusion: what a practitioner should do; what remains open.

## Figures and tables to make from `results/`

- Figure: the final-set claim components per grader, with their margins (`results/stage2/analysis.json`).
- Table: arm values with seed spread for the primary judged metric and the programmatic metrics.
- Table: the seven contrasts with differences, percentile and adjusted intervals, Holm p-values and the support decision.
- Figure: per-arm judged pass rate with seed points (M1, M2) and single-run arms marked.
- Figure: validation loss against update for the runs (from the manifest), with selected checkpoints marked.
- Table: judge agreement across vendors and against humans (when annotation exists); position-bias estimate.
- Table: latency (median, p95) and cost per system, with the clean-pass protocol stated.

## Handoff checks before submission

- Re-run `REPRODUCE.md` and confirm the tables are unchanged.
- Re-read `OPEN_DECISIONS.md` and resolve or state each item.
- Verify every citation against the primary source.
