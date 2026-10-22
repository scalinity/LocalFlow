# Paper brief

## One-paragraph version

LocalFlow is a local dictation app whose cleanup model rewrites a speech-recognizer transcript into clean text on the
user's machine. The study retrains that model (LoRA fine-tunes of Qwen3.5 4B and 9B) on data produced and checked by
a deterministic rule engine and validator, and measures what each design choice contributes: the new data against the
earlier data, contrast rows that pair "edit here" with "leave alone" twins, verifier filtering of training rows, model size,
and the on-device model against few-shot frontier models. The contribution is a measured, reproducible, device-specific
result with a locked evaluation, three independent judge vendors, a human-calibrated subset, and a pre-registered analysis.
It is **not** a first-of-kind claim: the literature scan found existing speech-repair, minimal-edit and
dictation-cleanup work (see WRITING_GUIDE).

## Hypotheses (from the pre-registration; status lives in EVIDENCE_MAP)

- H1: the new training data beats the earlier data (shipped form: 4B from C; clean form: fresh 4B adapter).
- H2: contrast rows reduce wrongful edits to lists and questions without hurting repair recall. The literature scan rated this the strongest candidate for novelty.
- H3: verifier filtering beats leaving vetoed rows unfiltered. The scan rated this as already shown broadly; here it is a replication in one setting.
- H4: the 9B beats the 4B enough to matter.
- H5: a 4B on-device model approaches few-shot frontier models at a fraction of the cost and latency.

## What the evidence can support, in order of strength

Decided by the analysis plan and Amendment 1, not by this brief: read `results/RESULTS.md` (development set) and `results/stage2/analysis.json` (final set). A claim without a "supported" status in EVIDENCE_MAP
is written as an observation with its interval, or left out.

## Venues and dates (from the literature scan; verify before relying on them)

- ACL 2027 via ARR: January 5, 2027, 6:59 a.m. ET (latest ARR submission; commitment follows).
- Interspeech 2027: February 9, 2027 (paper deadline; cutoff clock unannounced).
- ASLI 2027: April 22, 2027, 7:59 a.m. ET.
- ICML 2027 workshops: dates not found at the time of the scan.
- arXiv: any time after the author and advisor agree; see OPEN_DECISIONS for the release constraints on data and weights.
