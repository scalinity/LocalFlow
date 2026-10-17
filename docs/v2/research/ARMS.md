# Cleanup-model study arms

LocalFlow is a local dictation app. Its v2 cleanup model learns from TRAIN
rows normalized and captured through a deterministic rule engine and validator.
These are planned training conditions, not completed runs or quality results.
The lead session builds each dataset and owns training and the live dashboard.

| Arm | Base model | Adapter initialization | Training dataset |
| --- | --- | --- | --- |
| M2 | Qwen3.5 4B | Continue C | Full merged v2, `consolidated/dataset-v2-merged` |
| M1 | Qwen3.5 4B | Fresh adapter | Same full merged v2 dataset as M2 |
| M3 | Qwen3.5 9B | Fresh adapter | Same full merged v2 dataset as M2 |
| A1 | Qwen3.5 4B | Fresh adapter | Full merged v2 minus the `contrast` source |
| A2 | Qwen3.5 4B | Fresh adapter | Earlier consolidated-c set, `consolidated/dataset` |
| A2prime | Qwen3.5 4B | Continue C | Same earlier consolidated-c set as A2 |
| A3 | Qwen3.5 4B | Fresh adapter | Full merged v2 with every captured call retained for vetoed TRAIN rows |

Dataset paths are relative to the private
`experiments/cleanup-model-v2/artifacts/` directory. Keep both existing datasets
frozen. Build A1 and A3 in separate directories under `consolidated/arms/`.
Neither switch changes the serving engine or its validator.

## Dataset differences

The merged reference was built at `11aa1e410051ae388aa847a99c126d469bd03c5e`
with `--consistent`: exact rows keep their calls; vetoed rows supervise only
calls whose prompts and targets agree. Its recorded counts are 10,360 collected
TRAIN rows and 9,897 captured rows. Its freeze-file SHA256 is
`6a180c7bcee65dcef1abd74b72302e1cdb42d59de94e48bd3231419e8b77d032`.
These are existing build records; the ablation implementation does not rebuild
or replace that reference.

A1 adds `--exclude-source contrast`. Exclusions happen after collection,
normalization, source precedence and deduplication, so older or duplicate rows
cannot take the removed rows' places. Against the merged reference,
`train.jsonl` must lose exactly the 324 case IDs with
`consolidated_origin == "contrast"`, with every other row unchanged. The merged
build captured 322 of those rows: `train_captures.jsonl` should therefore lose
exactly those 322 captures, leaving 9,575, while collected TRAIN output has
10,036 rows. These are expectations for the lead to verify, not new measurements.

A3 adds `--unfiltered-vetoed` to the merged build command. It retains every
captured call for a vetoed TRAIN row, including calls that fail agreement
filtering. TRAIN case IDs and labels stay the same. Exact-row captures stay
identical; capture differences may occur only for rows whose engine oracle is
not exact. A vetoed row that previously had no agreeing calls may enter
`train_captures.jsonl` when it has unfiltered calls, so its captured-row count
need not equal M1's. Vetoed rows no longer carry agreeing-call supervision
annotations or a `partial` capture marker. Label defects and capture errors
remain excluded. Validation and replay files stay unchanged for both arms.

A2 and A2prime use the earlier set as frozen, without recapturing it. That set
differs in labels, capture sources, supervision and size; this comparison does
not isolate row count alone. M1/M2 and A2/A2prime compare adapter initialization
within their respective datasets. A1 and A3 compare to M1, holding fresh 4B
initialization fixed.

## Run identity and training length

Use the [experiment README](../../../experiments/cleanup-model-v2/README.md#research-ablation-builds)
for exact build commands, freeze metadata and runner checks. Commit the capture
sources and push the research branch before the lead builds an ablation.
The run commit must contain those sources and CUDA fix `f77b43a`.

Dataset identity arguments do not choose adapter initialization. The current
private `full_run.sh` continues C for `MODEL=4b`; the lead needs a fresh-adapter
invocation for M1, A1, A2 and A3. `v2.consolidate train --base` selects a fresh
adapter on the supplied local base, including a 4B base. M3 uses a fresh 9B base.
Changing the cloud runner belongs to the lead, outside the build switches.

Training makes one pass over the selected training examples. Examples are
captured calls after the trainer's corrections-role and `NONE` sampling caps,
not simply captured rows. Calls are grouped by tokenized instruction-prefix
key into accumulation blocks of at most eight. For group sizes `n_g`, the
planned update count is `sum(ceil(n_g / 8))`. Different arms can have different
update counts even with the same epoch count. Record each dataset freeze,
captured-row count, sampled-example count, prefix-group block count and actual
completed updates in the pre-registration/run record. The README names the
source functions and output records; no arm's run length is claimed measured
before the lead prepares or runs it.
