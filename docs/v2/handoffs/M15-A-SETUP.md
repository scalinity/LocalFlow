# LocalFlow M15 Automated Cleanup Benchmark Setup

October 1, 2026. State:
`M15_AUTOMATED_CLEANUP_BENCHMARK_READY_TO_INTEGRATE_AFTER_PRE_M15`.
This is preparation evidence, not a full M15/M07/M11 acceptance result.

## Identity and scope

Base main: `5da68360a0e5b1ea9303f799ea5c550db4f210fe`.
Branch: `m15-cleanup-model-benchmark-setup-20261001`; sibling worktree
`LocalFlow-m15-benchmark-setup`. The exact resulting commit is returned in
the owner handoff after commit; no future SHA is invented in this file.
The separately owned pre-M15 branch remained at
`8c08b82f15e75e83fb06bcd5aa2e102c50761903` throughout setup.

Only scripts, harness tests, candidate manifest and additive M15 documentation
changed. Production config/model/engine/validation bytes match the base.
The existing `.gitignore` already excludes `.claude/` and `.codex/`.
No build, installed-app change, clipboard, microphone, live store migration,
pre-M15 edit, merge, push, M16 work or full acceptance corpus occurred.

## Storage and candidates

The established `HF_HOME` is the LocalAI `models` directory; its Hub cache is
`models/hub`. The known LocalAI `.venv/bin/hf` was used directly, from LocalAI,
with exact `--revision`, never `--local-dir`. The control revision came from
`docs/v2/baseline/manifest.json`; missing weights were restored without changing
quantization. Every candidate's complete exact snapshot was absent before the
batch; the CLI downloaded/resumed/reused cache blobs as necessary. Network
transfer bytes are not equated with allocated snapshot bytes.

Total unique-file allocation across the seven snapshots: **70,753,103,872 bytes**
(65.89 GiB). This includes required repository assets and unused bundled vision
or MTP sidecars, not just text weights. Allocation uses each resolved file's
`st_blocks * 512`, deduplicated by real cache blob within a snapshot.
APFS free space and `df` may change independently due to other apps/APFS reclaim;
the public setup result records before/after observations, not an invented exact
download-induced disk delta.

Each Git blob or LFS SHA256 was verified against the pinned Hub metadata.
Qwen3.6's cached `generation_config.json` contained previously altered sampling
values under its original blob name; a pinned `hf --force-download` restored
that metadata file. No weights were modified. No incomplete files remain.

The exact revisions, allocated/logical sizes, roles, architecture, nominal
parameter counts, primary reasoning/sampling modes and runtime requirements
are in `benchmarks/m15-cleanup-candidates.json`. All seven pass compatibility.
The content-free machine-readable setup inventory and final smoke measurements
are in `benchmarks/m15-setup-results.json`.

The Gemma 26B community card labels legacy Gemma terms, whereas Google's official
Gemma 4 license is Apache 2.0. The manifest preserves that discrepancy and cites
the upstream source; packaging must verify attribution/notices. No third-party
implementation is copied into these scripts and no model weights are committed.

A pre-existing legacy `~/.cache/huggingface` directory remains; zero files there
were modified after setup began. No new secondary cache or incorrect
LocalAI `hub/models` layout was created. No model artifacts are in either repo
or benchmark worktree; the active HF configuration is unchanged.

## Benchmark architecture and tests

Contract: `benchmarks/M15-A.md`; additive tasks and M15-AC09/AC10 are in the
canonical M15 section. Runner: `scripts/v2/benchmark_cleanup_candidates.py`.

Track A fans identical frozen Normalized text/protected spans/context through
the official candidate templates. Track B runs actual same-byte WAV Parakeet
inference, normalization, cleanup and validation; it is implemented and tested
with a fake ASR plus real WAV/normalization mechanics, not measured against real
ASR in this setup. Physical microphone/insertion latency remains separate.

The corpus preserves private inputs/references/audio, hashes every asset,
separates human/synthetic denominators and preserves M07-V002's 30/10/20 split.
An inventory found 11 private retained WAV assets; their human/reference/retention
eligibility is unverified. No speech or adjudication was repeated. The private
inventory retains paths/hashes/format/duration; public data contains only counts.

Atomic candidate/case/repetition/track checkpoints skip complete units on resume,
refuse source/runtime/template/corpus drift, and isolate load/OOM/timeout failures.
Raw proposals/outputs/findings are private. Content-free results and report use
allowlists; the tests include nested private-data sentinels. The optional private
blind queue uses source/reference/Output A/Output B and a separate model key.

Deterministic harness: **41/41 pass**, including schema, duplicates, immutable
identity/cache, text fanout/audio/reference hashes, family/holdout separation,
M07 reuse, process failures/timeouts, atomic resume, correction counts,
fallback/usefulness, latency/memory/Pareto, real WAV replay mechanics, blind
queue/privacy and unchanged production defaults.
Owning deterministic regressions also pass: cleanup engine 19 tests;
introduced-list separator checks 12/12; spoken-step validation 31/31.
No full model-backed EV-09 or M15 corpus is claimed from these tests.

All seven were loaded one at a time on the verified M5 Pro / 48 GB reference
Mac. Final smoke uses one tiny synthetic Unicode/numeric input per candidate,
temperature zero, official system/user templates and disabled thinking/MTP.
Load/render/direct output/validator/output-limit metadata/unload are observed.
Baseline/loaded/peak/settled RSS and MLX counters are recorded; allocator active
memory returns to its small runtime baseline after unload and workers exit.
These smoke measurements exclude resident ASR and don't prove production memory
headroom, correction quality, tail latency or packaged offline readiness.

## Metrics and remaining gates

Reference components and reviewed assertions; protected/literal/numeric/
negation/constraint/technical/list/structure behavior; invention/answer checks;
correction opportunities/correct/missed/wrong/over-deleted/residue/rollback;
useful cleanup, rejection, fallback and output-limit rates remain separate.
Timing reports n/failures/p50/p95/p99/max for first-token/generation/validation/
cleanup and actual file replay; cached cold loads are separate. Memory records
RSS and actual allocator counters, never weight size as RAM. Rate intervals
cluster repeated units by family. Pareto fronts are supplemental to hard gates.
Precision and ceiling conditions compare the same corpus without presumed wins.
No promotion is authorized; all eleven conditions in the M15-A contract apply.

Next: make the completed pre-M15 code available on its approved canonical
integration base, integrate this setup independently, adjudicate/freeze eligible
human references and M07-V002 reuse once, restore/verify the pinned Parakeet
condition in the global cache for Track B, then run the authorized automated
comparison with existing M15 sample/repetition rules. Select a finalist using
that evidence, rerun M07-V001/reuse V002, and run the final M11 integrated
qualification against the selected model. Nothing here marks those gates passed.
