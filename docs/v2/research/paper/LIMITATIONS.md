# Limitations and validity threats

Each item is a fact about this study, with where it came from. A paper states them plainly.

1. **Engine-defined metrics are circular for engine-labeled data.** Training rows and the programmatic scores both come from the
   rule engine and validator. Programmatic results show conformance, not quality. The judges and the human subset exist for this reason.
2. **The data author and a judge share a vendor.** Claude wrote the training targets and Claude Opus judges. Two other vendors
   (OpenAI, Meta via OpenRouter) judge the same outputs; the judge-agreement tables are the evidence for or against bias.
3. **Few seeds.** Only M1 and M2 have three seeds (0, 1, 2). Every other arm is one run; their seed spread is borrowed from M1 or M2
   under the plan's reference-SD rule. The seed changes data order, fresh-adapter initialization and dropout; it does not change the data.
4. **The development set is small for H2.** 62 list and question cases, of which 35 need no change and 27 need repair; one case is
   about 3 points. The development-set H2 result is exploratory. A confirmatory test needs a larger set (OPEN_DECISIONS).
5. **Twin and family dependence.** Cases come in families; the case-level bootstrap treats cases as independent.
6. **M1 versus A2 tests a bundle.** The new data differs from the earlier data in parser, validator, labels and contrast rows together;
   only A1 (without contrast rows) and A3 (vetoed rows unfiltered) isolate single factors.
7. **Checkpoint selection used the development set's validation calls** (160 calls drawn from development cases), and the development
   set also decides the winner. The locked final set is the unbiased check and is opened once, after the freeze.
8. **Training numerics.** Training ran on A100 GPUs with the chunked Gated DeltaNet path (MLX 0.31.1 on CUDA); evaluation runs on a Mac in 4-bit.
   The chunked path matched the stock path on the first 20 updates (loss within 1.7 percent, gradient-norm ratio 1.00); it was not compared over all updates.
9. **Concurrent evaluations.** The first evaluation pass ran up to six Mac jobs at once, so its latency fields are unusable. Latency comes only from the
   sequential clean pass. Cloud systems' API time is not comparable with on-device time.
10. **Evaluation volume reduced from the plan.** The pre-registration asks for programmatic metrics on all eight checkpoints of every run.
    Compute time allowed the selected checkpoint of every run and the final checkpoint of one run (M2 seed 0). Recorded as a deviation.
11. **One domain, one author's data.** Synthetic dictation-style text produced by a Claude pipeline for one product; no claim about other domains or languages.
12. **Known engine limits.** For example the engine treats "May" and "Will" as auxiliary verbs and prepositional "after" as a dependent-clause marker,
    so some corrections are rejected and the text is delivered unchanged (a missed correction in the safe direction).
13. **Provenance.** Claude outputs are training targets. An Anthropic Help Center reply is informal guidance only and not authorization to release Claude-generated rows, targets or weights.
14. **Provider terms and data flow.** OpenRouter's Meta Contributor tier may use prompts to improve Meta's products, so only synthetic development cases go to it.
15. **Most development cases do not separate the systems.** On the seven-system check made before judging (M1, M2, A1, A2, A2prime, A3 at seed 0 and C), all systems returned the same text on 287 of 431 cases,
    and a random pair of systems returned identical text 83 percent of the time. Differences between systems come from about a third of the cases, and a
    uniform random human-annotation pair is trivially tied about four times in five. The pair builder has an opt-in `--differing-only` mode for this reason; using it departs from the uniform draw in the pre-registration and is recorded as a deviation.
16. **The checkpoint rule favors early checkpoints.** For every arm the lowest validation loss fell at 11 to 62 percent of training (updates 199 to 1,065 of 1,591 to 1,704), and the final checkpoint is as good or better on the programmatic metrics in 9 of 11 runs.
    The pre-registered analysis uses the selected checkpoint; the final-checkpoint analysis is a supplementary, post-hoc robustness check. Where the two disagree the paper says so (see `results/RESULTS.md`).
17. **A rate that rewards completeness and a rate that rewards restraint can disagree.** The judged pass rate (primary endpoint) counts a case as passed only if cleanup is complete or unnecessary and no flag is raised; models trained on the earlier data complete more repairs and also break more, so the new data's gain shows on the flag and damage metrics, not on the pass rate (see RESULTS).
