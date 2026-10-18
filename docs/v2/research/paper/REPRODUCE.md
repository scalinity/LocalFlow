# Reproducing the tables

All commands run from a checkout of the results branch with the private artifacts directory linked in
(`experiments/cleanup-model-v2/artifacts`). Python is the repository `.venv`.

## Code and data identities

- Training commit for the main arms (M1, M2, M3, A1, A3, M1/M2 seeds): `ba2895c23c7dcc879d3a63b164281b1bb82850dd` on `origin/codex/cleanup-research-integrated`.
- Training commit for A2 and A2prime (earlier data): `f77b43acba87ed3f7065e30f241aa2a499841135`.
- Main dataset freeze SHA-256: `6a180c7bcee65dcef1abd74b72302e1cdb42d59de94e48bd3231419e8b77d032` (9,897 captured rows). Every run's dataset hash is in `data/manifest.json`.
- Seeds: `LFX_SEED` = 1 or 2 for seeds 1 and 2; unset or 0 for seed 0 (identical to the pre-seed trainer, tested bitwise).
- Hyperparameters: learning rate 3e-5, one pass over the arm's data, eight evenly spaced checkpoints, bf16 bases, A100 SXM, chunked Gated DeltaNet (`LFX_EVAL_GDN=chunked`), CUDA graphs and TF32 off.
- Export and evaluation: a checkpoint is fused into the bf16 base, quantized to 4-bit (affine, group 64) as C was, then evaluated on the 431 development cases with the current merged engine (`v2.training export`, `v2.evaluate`, `v2.score`; see the READMEs in `experiments/cleanup-model-v2`).

## Regenerating

```sh
export PYTHONPATH=experiments/cleanup-model-v2:experiments/cleanup-model
PY=.venv/bin/python
$PY experiments/cleanup-model-v2/tools/research_manifest.py docs/v2/research/paper/data/arms.json docs/v2/research/paper/data/manifest.json
$PY experiments/cleanup-model-v2/tools/research_analysis.py docs/v2/research/paper/data/arms.json \
    --out-dir docs/v2/research/paper/results --private-dir "$A/research/results" \
    --judge anthropic=$A/judge/dev-main-anthropic/verdicts.jsonl \
    --judge openai=$A/judge/openai/dev-main-openai/verdicts.jsonl \
    --judge openrouter=$A/judge/openrouter/dev-main-openrouter/verdicts.jsonl
$PY experiments/cleanup-model-v2/tools/research_latency.py docs/v2/research/paper/results
$PY experiments/cleanup-model-v2/tools/research_reliability.py docs/v2/research/paper/results/judge_reliability.json \
    --judge anthropic=$A/judge/dev-main-anthropic/verdicts.jsonl --judge openai=$A/judge/openai/dev-main-openai/verdicts.jsonl \
    --judge openrouter=$A/judge/openrouter/dev-main-openrouter/verdicts.jsonl \
    --swapped anthropic=$A/judge/dev-swap-anthropic/verdicts.jsonl --swapped openai=$A/judge/openai/dev-swap-openai/verdicts.jsonl \
    --swapped openrouter=$A/judge/openrouter/dev-swap-openrouter/verdicts.jsonl
$PY experiments/cleanup-model-v2/tools/research_select.py docs/v2/research/paper/results/analysis.json \
    docs/v2/research/paper/results/latency.json docs/v2/research/paper/data/sizes.json docs/v2/research/paper/results/selection.json
$PY experiments/cleanup-model-v2/tools/research_report.py docs/v2/research/paper/results
```

H5 on the development set (pre-registered; its own judge pass shows M2 seed 0 beside the two few-shot systems, see DEVIATIONS):

```sh
$PY experiments/cleanup-model-v2/tools/research_analysis.py docs/v2/research/paper/data/arms_h5.json \
    --out-dir docs/v2/research/paper/results/h5_development \
    --judge anthropic=$A/judge/dev-h5-anthropic/verdicts.jsonl \
    --judge openai=$A/judge/openai/dev-h5-openai/verdicts.jsonl \
    --judge openrouter=$A/judge/openrouter/dev-h5-openrouter/verdicts.jsonl
```

Stage 2 on the locked final set (AMENDMENT-1.md, with AMENDMENT-2.md's missing-outcome rule; Sonnet 5.5 and
gpt-6.1-sol decide). The engine scores, the C3 rewritten key and the four grading runs come first; Opus few-shot is
scored case by case inside the analysis, because its refused case leaves a gap `v2.score` does not accept:

```sh
FINAL=$A/refinement/dataset/test.jsonl
NINE="C-merged M2s0-ck426 A2prime-ck199 M1s0-ck426 A2-ck199 M3-ck426 base-9b-prod-prompt sonnet-5-5-fewshot opus-5-5-fewshot"
for R in ${NINE% opus-5-5-fewshot}; do $PY -m v2.score $FINAL final-$R; done
$PY experiments/cleanup-model-v2/tools/research_normalize_dev.py $A/refinement/final-rewritten.jsonl \
    --input $FINAL --changed $A/refinement/final-rewritten-changed.jsonl
$PY -m v2.judge $FINAL $NINE --prefix final --role final --backend anthropic --name final-main-anthropic
$PY -m v2.judge $FINAL $NINE --prefix final --role final --backend openai --confirm-final-eval --name final-main-openai
$PY -m v2.judge $A/refinement/final-rewritten-changed.jsonl $NINE --prefix final --role final --backend anthropic --name final-c3-anthropic
$PY -m v2.judge $A/refinement/final-rewritten-changed.jsonl $NINE --prefix final --role final --backend openai --confirm-final-eval --name final-c3-openai
$PY experiments/cleanup-model-v2/tools/research_analysis.py docs/v2/research/paper/data/arms_stage2.json \
    --out-dir docs/v2/research/paper/results/stage2 --stage2 --prefix final --cases $A/refinement/dataset/test.jsonl \
    --judge anthropic=$A/judge/final-main-anthropic/verdicts.jsonl \
    --judge openai=$A/judge/openai/final-main-openai/verdicts.jsonl \
    --rewritten-judge anthropic=$A/judge/final-c3-anthropic/verdicts.jsonl \
    --rewritten-judge openai=$A/judge/openai/final-c3-openai/verdicts.jsonl
```

Supplementary analyses (post hoc; see DEVIATIONS):

```sh
$PY experiments/cleanup-model-v2/tools/research_normalize_dev.py $A/research/dev-normalized/validation.jsonl
$PY experiments/cleanup-model-v2/tools/research_analysis.py docs/v2/research/paper/data/arms_final.json --out-dir OUT --judge anthropic=$A/judge/dev-final-anthropic/verdicts.jsonl --judge openai=$A/judge/openai/dev-final-openai/verdicts.jsonl
$PY experiments/cleanup-model-v2/tools/research_analysis.py docs/v2/research/paper/data/arms.json --out-dir OUT --cases $A/research/dev-normalized/validation.jsonl --judge anthropic=$A/judge/dev-norm-sel-anthropic/verdicts.jsonl
$PY experiments/cleanup-model-v2/tools/research_categories.py docs/v2/research/paper/data/arms_final.json $A/judge/dev-final-anthropic/verdicts.jsonl OUT.json
$PY experiments/cleanup-model-v2/tools/research_checkpoints.py docs/v2/research/paper/results/checkpoints.json
```

Judge runs used (names under `$A/judge`): `dev-main-*`, `dev-swap-*`, `dev-final-*`, `dev-h5-*`, `dev-norm-sel-anthropic`, `dev-norm-final-anthropic`, with commands `python -m v2.judge CASES SYSTEMS --prefix development --role development --backend B --name NAME [--swap-order]`; and on the final set `final-main-*` and `final-c3-*`, with the commands in the Stage 2 block above. A rerun of the same command resumes.
Every judge run is complete. A run whose collecting process stopped is resumed by rerunning its identical command; check the provider's batch status first, since a batch can finish while its collector is down.

The analysis uses `random.Random(20261015)` and 10,000 resamples; both are fixed by the pre-registration.

## Costs recorded

See `results/RESULTS.md` (cloud GPU, judge APIs). RunPod's billing report lags running pods; the console balance is authoritative.
