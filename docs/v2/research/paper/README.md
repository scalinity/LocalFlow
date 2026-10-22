# Paper kit: LocalFlow cleanup-model study

Everything a writing session needs, and nothing it must not publish. A future session writes the paper from these files;
it does not run experiments and does not invent numbers.

| File | What it is |
|---|---|
| [PAPER_BRIEF.md](PAPER_BRIEF.md) | The question, the contribution as the evidence allows it, venues and dates |
| [FINDINGS.md](FINDINGS.md) | Dated findings, each tied to a generated file |
| [SELECTION.md](SELECTION.md) | The model-selection rule, its outcome and a labeled post-hoc recommendation |
| [EVIDENCE_MAP.md](EVIDENCE_MAP.md) | Each claim, the file that supports it and its status |
| [results/RESULTS.md](results/RESULTS.md) | Generated tables for the development set (arm values, seed spread, contrasts, latency, development cost). Never edited by hand. It does not cover Stage 2 |
| [results/stage2/analysis.json](results/stage2/analysis.json) | The Stage 2 analysis on the locked final set: every claim's components, estimates, 99 percent intervals and outcomes, and per-system values. No generated report exists for it; FINDINGS and EVIDENCE_MAP quote it |
| [LIMITATIONS.md](LIMITATIONS.md) | Validity threats found while running the study |
| [REPRODUCE.md](REPRODUCE.md) | Commits, hashes and commands that regenerate every table |
| [OPEN_DECISIONS.md](OPEN_DECISIONS.md) | Decisions that belong to the author, with the cost of each |
| [WRITING_GUIDE.md](WRITING_GUIDE.md) | Rules and an outline for the write-up session |
| [data/](data/) | Run manifest and arm labels (aggregates, no case text) |

Related, one level up: [PREREGISTRATION.md](../PREREGISTRATION.md), [ANALYSIS_PLAN.md](../ANALYSIS_PLAN.md),
[DATA_CARDS.md](../DATA_CARDS.md), [ARMS.md](../ARMS.md).

Private material the kit refers to but this repository does not contain (it holds Claude-generated text or
case text): the training datasets, per-case scores, model outputs, judge verdicts and the literature scan with
its bibliography, under `experiments/cleanup-model-v2/artifacts/` in the main checkout. The judge–human agreement
files (`research/annotation/agreement*.json`) and the final graders' agreement (`research/results/stage2-judge-reliability.json`)
are aggregates kept there beside the verdicts they read.
