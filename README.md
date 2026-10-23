# LocalFlow

### Private, on-device dictation for macOS, with a cleanup model fine-tuned for the job

![Python 3.14](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![macOS](https://img.shields.io/badge/macOS-Apple%20Silicon-black?logo=apple&logoColor=white)
![MLX](https://img.shields.io/badge/MLX-0.31-F7931E)
![Parakeet](https://img.shields.io/badge/ASR-Parakeet%20TDT%200.6B%20v3-76B900?logo=nvidia&logoColor=white)
![Qwen3.5 LoRA](https://img.shields.io/badge/Cleanup-Qwen3.5--4B%20LoRA-6A5ACD)
![Svelte 5](https://img.shields.io/badge/Svelte-5-FF3E00?logo=svelte&logoColor=white)
![Network](https://img.shields.io/badge/Network-none%20at%20runtime-2E7D32)

**LocalFlow** is a menu-bar dictation app for Apple Silicon Macs. You hold a key, speak and release, and the text appears at the cursor in whatever app is in front. Speech recognition (NVIDIA's Parakeet TDT 0.6B v3), number and syntax normalization, LLM cleanup, rewriting transforms, history and analytics all run on the Mac through Apple's MLX. At runtime the worker is forced offline. The cleanup step removes filler sounds, resolves spoken self-corrections ("at 3, no wait, 4") and fixes punctuation. Every model proposal passes a deterministic validator before it is used, and if the validator rejects a proposal, the user gets their own words back rather than a confident paraphrase.

The engineering bet is that a small local model can be both faithful and useful if it is held to an explicit contract and checked against it. That bet now includes a model of its own: a Qwen3.5-4B fine-tuned on 6,393 examples rendered through LocalFlow's real cleanup engine. Its LoRA training ran on one Mac in 72 minutes, and it was compared with the incumbent under decision rules frozen before any candidate output existed. On the frozen synthetic test set it resolves 96% of self-corrections, against 14% for the stock model. It also cuts the model's own meaning changes from 8.4% to 0.4%.

---

## Table of Contents

- [Motivation](#motivation)
- [How It Works](#how-it-works)
- [The Self-Fine-Tuned Cleanup Model](#the-self-fine-tuned-cleanup-model)
- [The Clean-Mode Contract](#the-clean-mode-contract)
- [Safety & Correctness](#safety--correctness)
- [Architecture](#architecture)
- [Technical Highlights](#technical-highlights)
- [Tech Stack](#tech-stack)
- [Project Scale](#project-scale)
- [Development](#development)
- [Roadmap](#roadmap)

---

## Motivation

Dictation is the fastest way to get words out of a head and into a computer, and the best dictation tools send every word to a server to get there. That is a poor trade for the things people actually dictate, such as messages to family, prompts for coding agents, drafts of research and notes about health. LocalFlow is a personal-use alternative that keeps the whole path on the machine: audio, transcripts, cleanup, history and the evidence used to improve it.

The hard part is not recognition. Parakeet transcribes well on a laptop GPU. The hard part is cleanup. Raw speech is full of "um", restarts and "no wait, make that Thursday". A language model asked to tidy it will happily also answer the question you dictated, round a number, drop a "not", or rewrite your voice into its own. Small on-device models do this more often than large ones. LocalFlow therefore treats the model as a proposer and the contract as the authority. A model proposal is shipped only if a deterministic validator can show that it removed only what the contract allows and kept everything else.

---

## How It Works

### Capture

Holding Fn starts recording; pressing any other key cancels the dictation (so Fn shortcuts keep working), and taps shorter than 0.3 s are ignored. Right Option, Right Command, a double-tap hands-free mode and the middle or right mouse button are optional triggers.

- **Recorder:** `sounddevice` at 16 kHz mono float32 in 50 ms blocks, with an adaptive level meter driving the floating pill (recording, processing, transforming, failed).
- **Crash-resilient journal (`localflow/v2/capture_journal.py`):** blocks are written off the audio thread to a per-job file. Each block carries a CRC32 and the file closes with a SHA-256 footer, so a crash mid-sentence recovers every complete block. Recovered files are classified as `finalized_verified`, `unfinalized`, `torn_tail`, `torn_footer` or `corrupt`, never guessed at.

### Speech recognition

- **Model:** Parakeet TDT 0.6B v3 via `parakeet-mlx`, pinned to a revision and running on the Metal GPU.
- **No intermediate files:** the microphone buffer is fed straight into the model's log-mel front end, with no ffmpeg and no temp files.
- **Long audio:** dictations over 90 s are decoded in 60 s chunks with 15 s of overlap and token-merged, so long dictations neither truncate nor duplicate at the seams.
- **Honest capabilities (`localflow/v2/capabilities.py`):** contextual biasing is declared `disabled_until_qualified`, rather than half-enabled.

### Normalization

`localflow/v2/normalize/` runs between recognition and cleanup.

- **What it does:** turns spoken numbers, times, money, units and code syntax into typed spans with an edit ledger in code-point offsets ("twelve thirty" becomes `12:30`, "dash dash force" becomes `--force`).
- **Precedence:** literal escapes, then protected syntax, then snippets, then typed numeric grammar, then vocabulary, then prose.
- **Behaviour:** the stage is deterministic and idempotent. Its spans are passed to cleanup as protected spans the model may not change.
- **Speed:** p95 is 4.3 ms on a 500-word input, against a 25 ms budget (`docs/v2/handoffs/M04.md`).

### Cleanup engine

`localflow/v2/cleanup/engine.py` makes two kinds of model call, both greedy and with thinking disabled.

1. **Corrections pass.** It runs only when a correction marker such as "no wait", "I mean", "scratch that" or "sorry" is heard. The model lists the verbatim spans to delete, one per line. Each span is resolved to exact offsets, limited to 6 words, and must pass the parser's evidence check.
2. **Main pass.** The model writes the cleaned text for each complete block of up to 200 words. It gets the contract, 20 worked examples and a JSON payload holding the transcript, protected spans and destination hints.

If generation hits its output limit, the window is split and retried once. Each failure falls back down a recorded ladder: `llm`, `llm_partial`, `llm_fallback_normalized`, `basic`, `raw`.

### Destination awareness

At the moment the key is pressed, `localflow/v2/context/` reads the frontmost app, its window and, through Accessibility, the focused field.

- **Timing:** the read finishes within a 75 ms deadline. The measured added delay is 40.5 ms at p95.
- **Exclusions:** secure fields and denied apps are never read, and browser URLs are cut down to their origin.
- **Rules:** the result selects a destination profile (`messaging`, `email`, `documents`, `ai_prompt`, `coding`, `terminal`…). Profiles change formatting and few-shot examples, never the contract.

### Insertion

`localflow/v2/insertion/` inserts through one serialized queue.

- **Methods, in order:** it first tries Accessibility selected-text replacement, then a clipboard transaction whose ownership generation means a copy you make mid-dictation always wins. Multi-line text into a terminal becomes copy-only.
- **No synthetic Return:** dictation never adds one, so it cannot submit a form or run a command.
- **Recorded outcomes:** each insertion is recorded as `confirmed`, `posted_unverified`, `target_changed`, `saved_not_inserted` or `failed`.

### Transforms, vocabulary and history

- **Transforms:** Polish, Concise and Prompt Engineer (Option+1/2/3) rewrite a selection with the same local model. A requirement-atom coverage map fails closed, and an uncertain result is marked `needs_review` instead of being applied.
- **Dictionary and snippets:** scoped vocabulary, so "cube control" becomes `kubectl` only where the dictionary says so. Text snippets with `{{placeholders}}` never execute anything.
- **History and insights:** one SQLite database, owned by a single writer thread, holds jobs, transcripts, audio artifacts with retention timers, delete-everywhere tombstones and usage analytics such as weighted WPM. The event log never contains transcript text.
- **Training evidence:** collection is opt-in. A curation pipeline classifies examples with abstention, samples 10% for review, splits by family and exports a portable, checksummed dataset with an offline validator.

### Companion

The Hub is a Svelte 5 app served inside a single `WKWebView` through a private `lfhub://` scheme, with a strict CSP, blocked http(s) and an allow-listed, versioned JS bridge. Its pages are Home, History, Dictionary, Snippets, Styles, Transforms, Scratchpad, Insights, Models, Settings and Diagnostics.

---

## The Self-Fine-Tuned Cleanup Model

LocalFlow's cleanup model has always been an off-the-shelf instruct model: `Qwen3-4B-Instruct-2507`, 4-bit. That model follows instructions well, but the job is unusual, because the contract is mostly about what *not* to do. The open question was whether the newer Qwen3.5-4B would be better as it comes, or only once it had been taught LocalFlow's contract. The experiment in [`experiments/cleanup-model/`](experiments/cleanup-model/) answers that end to end, and the results page is [`reports/localflow-cleanup-comparison/index.html`](reports/localflow-cleanup-comparison/index.html). It is self-contained and opens from disk with no network.

| | Model | What it is |
| --- | --- | --- |
| **A** | `mlx-community/Qwen3-4B-Instruct-2507-4bit` | The incumbent and the repository default |
| **B** | `mlx-community/Qwen3.5-4B-4bit` | Qwen3.5-4B, untuned, same 4-bit recipe as C |
| **C** | `local/LocalFlow-Cleanup-Qwen3.5-4B-4bit` | Qwen3.5-4B with a LoRA trained for LocalFlow's two cleanup calls, fused and quantized |

### Training data from the real engine

**Generation.** Claude Sonnet 5.5 wrote dictation *families* through the Message Batches API, in structured JSON. Each family holds a clean target, its critical facts, a noisy ASR-style version, the corrections it contains and the changes that are allowed. The prompt embeds LocalFlow's contract text verbatim, so targets stay inside what the product is allowed to deliver. Each family covers one of these categories: casual messages, coding-agent instructions, software terms, academic writing, molecular biology, spoken lists, single and multiple self-corrections, technical literals and questions that must stay questions. About 30% are already-clean inputs that must come back unchanged.

**Capture mode.** Every pair is then run through LocalFlow's own `CleanupEngine`, with a stand-in model that answers with the gold text. A gold is accepted only if all of these hold:

- the engine selects every gold correction;
- the validator passes it with no salvage;
- the delivered text equals the gold byte for byte.

So the model trains on exactly the prompts production renders, for both call roles and every destination profile, and never on an answer the product would refuse to ship.

**Gates and leakage.**
- Deterministic gates check that facts survive, that corrected-away values are gone, that the ending is kept and that the length stays in band.
- A separate Claude pass verified 100% of test and validation pairs and most of the training set.
- Splits were assigned per family *before* generation.
- Near-duplicates (word 5-gram Jaccard ≥ 0.6) were removed across splits and against the prompt's own examples.

**Volume and cost.**
- **Kept:** 5,238 main-pass and 1,155 corrections-pass training examples, plus 466 frozen test pairs and 400 validation pairs.
- **Rejected:** the gates turned away about 2,000 candidates. The two largest causes were "the engine's correction parser would not accept the gold deletion" (458) and "the validator rejected the gold" (442).
- **Spend:** $16.21 of a $20 cap. A spend ledger refuses any batch whose worst-case charge, added to outstanding requests, would pass $19.50.

### Training Qwen3.5 on a laptop

Qwen3.5-4B is a hybrid model: 24 of its 32 layers are Gated DeltaNet linear attention. In mlx-lm 0.31.3 the training path runs that recurrence as a Python loop over every token, which put 3,500-token prompts at days per epoch. Two pieces of work made it practical:

- **A chunked gated-delta rule (`lfx/gdn_chunked.py`).** It processes chunks of 64 tokens, uses forward substitution for the in-chunk inverse, computes in fp32 inside each chunk and carries state between chunks. It is patched in only while training; inference keeps the stock Metal kernel. It matches mlx-lm's reference on CPU for both outputs and gradients, and stays within 1% of the inference kernel on a 3,500-token sequence.
- **Prefix-cached training.** About 97% of every example is the same system prompt and few-shot turns. That shared prefix is run forward under the current weights at each update, and gradients flow through each example's own payload and response. The loss is exact, and training is about 6× faster.

**Settings**
- LoRA rank 16 (scale 2.0) on all 32 layers: the attention projections, the linear-attention projections and the MLP.
- One pass over 6,393 examples, 803 optimizer updates.
- Loss on response tokens only.

**Run.** It took 72 minutes on an M5 Pro at a median of about 4,700 tokens/s. Validation loss fell from 0.078 to 0.006.

**Checkpoint choice.** Checkpoints were converted to 4-bit and compared on validation output, preservation first: fewest meaning changes, then untouched already-clean inputs, then repair success. Loss alone never decided.

**Export.** The adapter was fused into the bf16 base and quantized with the same recipe as B. Tokenizer and chat-template files were copied verbatim from the base, and fusing was checked against base plus adapter: the same top token at 100% of positions.

### How it was judged

Every model ran the same 1,086 cases through LocalFlow's real engine and validator. The recordings were transcribed once by LocalFlow's own Parakeet path.

| Set | Cases | Source |
| --- | --- | --- |
| Synthetic test pairs | 466 | Claude-generated |
| DisfluencySpeech recordings | 250 | Real conversational speech |
| FLEURS English recordings | 250 | Real read speech |
| LocalFlow's hand-written fidelity fixtures | 80 | Product test suite |
| Long multi-window dictations | 40 | Joined synthetic cases |

- **Frozen before any output.** The test set, references, metric code and decision rules were hashed at 2026-10-12T01:05Z, before any candidate produced output, and they did not change afterwards.
- **Model output kept apart from delivered text.** The validator's fallback hides damage, so the two are scored separately.
- **Runtime fidelity.** A, B and C each gave 50/50 byte-identical outputs inside LocalFlow's production interpreter.

| Frozen test result | A · current | B · Qwen3.5 untuned | C · LocalFlow-tuned |
| --- | ---: | ---: | ---: |
| Needed repairs delivered correctly (297 cases) | 63.6% | 53.2% | **98.3%** |
| Self-corrections resolved (76 cases) | 14.5% | 11.8% | **96.1%** |
| Already-clean input left untouched by the model (169) | 57.4% | 52.7% | **97.6%** |
| Model output that changed meaning, before validation (466) | 8.4% | 15.0% | **0.4%** |
| Windows the validator had to reject (466) | 16.7% | 28.3% | **0.2%** |
| WER on conversational audio (DisfluencySpeech) | 5.08% | 5.89% | **4.05%** |
| WER on read audio (FLEURS) | 6.48% | 6.50% | **6.41%** |
| LocalFlow fixtures passed, delivered (80) | 97.5% | 96.3% | 97.5% |
| Blinded judge: meaning preserved (240) | 90.0% | 82.9% | **99.2%** |
| Median warm cleanup | **1.48 s** | 1.63 s | 1.62 s |
| Cold load | **1.1 s** | 1.6 s | 1.6 s |
| Size on disk | **2.26 GB** | 3.03 GB | 2.37 GB |

**Outcome: consider C.**
- **C met all ten frozen checks:** meaning preserved against A on synthetic, real-audio and fixture slices; a delivered repair gain whose 95% lower bound is +29 points; and speed within 1.25× of A at p95.
- **B failed seven of the ten checks.**
- **Why only "consider".** The rules allow a tuned model "consider", never an automatic switch. That is because C learned from the same generator that wrote the synthetic test set, which is why the gates require the slices Claude did not write: two public audio sets and LocalFlow's own fixtures.

**Limits, stated in the report**
- **Hands-off on real transcripts:** C leaves 45% of conversational transcripts unchanged, against 24% for A. Fillers go, but a comma Parakeet got wrong often stays wrong.
- **Slower first token:** about 0.17 s slower than A.
- **Not tested on your voice:** none of the real audio is the owner's voice.

**Using it.** The repository default stays A, because C's weights are not published. On a machine that has C:
- Link its folder into the Hugging Face cache.
- Set `"cleanup_model": "local/LocalFlow-Cleanup-Qwen3.5-4B-4bit"` in `~/Library/Application Support/LocalFlow/config.json`.
- Restart the app. Removing the key rolls back.

The report carries all three commands, each verified when the report is built. `experiments/cleanup-model/run.py all` reruns or resumes the whole pipeline and never buys a finished batch twice.

---

## The Clean-Mode Contract

The contract text lives in `localflow/v2/cleanup/prompts.py`, versioned by content hash. Every rule is enforced in code as well as in the prompt:

| Rule | How it is enforced |
| --- | --- |
| **Remove pure filler sounds** | Only `um uh erm ehm hmm mhm`, function-word stutters and phrase-initial interjections are authorized deletions; every other dropped word fails `coverage` |
| **Resolve explicit self-corrections** | A separate corrections call proposes verbatim spans; spans are offset-anchored, capped at 6 words and checked for evidence; a rejected window rolls its deletions back |
| **Keep the replacement and everything after it** | `coverage` and ending checks; a missing ending is its own metric |
| **Never change numbers, names, negation or hedges** | `numeric_values` (value, sign, unit, time identity), `negation_coverage`, `uncertainty_coverage`, `technical_tokens` |
| **Dictated questions and instructions are content** | `novelty` rejects any content word appearing more often than in the source, which catches answers; nothing inserted ever ends in Return |
| **Protected spans survive verbatim** | Normalization's typed spans and `literal_spans` pass through as protected tokens |
| **Format only what was spoken as structure** | `structure` checks list markers and numbering against the source |

---

## Safety & Correctness

### Deterministic validation

`validate()` in `localflow/v2/cleanup/validation.py` composes ten deterministic components. The heuristic findings (`names`, some `structure` cases) are recorded but cannot reject. A rejected window ships the normalized source unchanged, so a bad model output degrades to "less cleaned", never "wrong". A window whose only failure is up to 8 dropped words (at most 10% of the window) has them restored and is revalidated, and that salvage is recorded.

### Privacy

- **Network:** audio, transcripts, cleanup, transforms, history and training evidence stay on the Mac. The one exception is opt-in: with an Anthropic key in the Keychain, Your Voice's written profile sends a sample of recent raw dictations (text, time, app) to the Claude API at each word milestone or on Write ([ADR-0001](docs/v2/decisions/ADR-0001-your-voice-written-profile.md)). The worker's environment forces `HF_HUB_OFFLINE=1`, so a launching shell cannot turn the network back on, and hub telemetry is disabled.
- **Logs:** the event log never contains transcript text or exception messages; the transcript log is local and optional.
- **Context:** context collection never reads secure fields and skips denied apps.

### Isolation

MLX runs in a fresh worker subprocess. It is started with `Popen` and never forked from the AppKit process, and it talks over length-framed JSON pipes. Generation and attempt numbers discard stale replies. A fatal fault gets one automatic retry, and three consecutive deaths with no successful stage trip a circuit breaker instead of a crash loop.

### Verification practice

- **Mutation checks:** 11 scripts (`scripts/v2/*_mutation_check.py`) apply exact faults to a `git archive` copy and require the tests to catch them. The cross-milestone run killed 88 of 88.
- **Isolated test runner:** `tests/v2/context/run_isolated.py` blocks real Accessibility calls, synthetic events and the real pasteboard during tests.
- **Fidelity suites:** `tests/v2/fidelity/` holds the hand-written cases the fine-tuned model was also measured on.

---

## Architecture

```
                 ┌──────────────────────────────────────────┐
                 │   LocalFlow.app, AppKit parent process   │
                 │                                          │
                 │  Hotkeys + capture journal (CRC32/block) │
                 │  Context snapshot (AX, 75 ms deadline)   │
                 │  Insertion queue (AX, clipboard txn)     │
                 │  SQLite store (single writer thread)     │
                 │  Menu bar, pill overlay, Hub window      │
                 └─────────┬──────────────────────┬─────────┘
                           │                      │
            length-framed JSON over pipes   lfhub:// scheme + bridge
                           │                      │
          ┌────────────────▼─────────┐  ┌─────────▼─────────────────┐
          │ MLX worker (subprocess)  │  │ Companion Hub (WKWebView) │
          │                          │  │                           │
          │ Parakeet TDT 0.6B v3     │  │ Svelte 5 + TypeScript     │
          │ Normalization engine     │  │ History, Dictionary,      │
          │ Cleanup engine+validator │  │ Transforms, Insights,     │
          │ Qwen cleanup model       │  │ Models, Settings          │
          │ Transforms               │  │ strict CSP, no http(s)    │
          └────────────────┬─────────┘  └───────────────────────────┘
                           │
          ┌────────────────▼──────────────────────────────┐
          │ Local disk only                               │
          │ v2.db, event logs, Hugging Face cache offline │
          └───────────────────────────────────────────────┘
```

**Process model.** A small compiled C launcher starts the Python app, because LaunchServices rejects script executables. The parent owns everything that touches the user's session: keys, audio, Accessibility, the pasteboard and the database. It holds no MLX state. The worker owns every model, so a GPU fault or out-of-memory kill costs one dictation, not the app.

**Data.** One SQLite database (`~/Library/Application Support/LocalFlow/v2.db`) holds history, vocabulary, analytics and training evidence. Daily JSONL event logs rotate at 10 MiB. Models live in the Hugging Face cache and are read offline.

**Bundle.** `scripts/build_app.sh` produces a self-contained `LocalFlow.app` with a copy of the code, the virtualenv and `config.json`, plus a `BUILD.json` stamp recording the git revision and whether the tree was dirty. A per-user override in Application Support survives rebuilds.

---

## Technical Highlights

- **Model as proposer, validator as authority:** the contract is enforced by ten deterministic components, and a rejected window falls back to the user's own normalized words.
- **Corrections as their own call:** the model lists deletions instead of rewriting, so "10, no wait, 10:30" is resolved by offsets the engine can check, not by trusting prose.
- **Training on exact production prompts:** training data comes from the engine's own rendering, with gold accepted only if the engine would deliver it byte for byte, so no prose completion is ever fed to a call that expects an edit list.
- **A chunked gated-delta rule for MLX:** it made Qwen3.5's linear-attention layers trainable at 3,500-token context on a laptop, and was checked for gradients against the reference.
- **Prefix-cached LoRA:** the shared few-shot prefix runs forward under the current weights, and only each example's own suffix carries gradients. The loss is exact and training is about 6× faster.
- **Decision rules frozen before any output:** test hashes and rules were fixed before the first candidate generated a word. The fine-tuned model was required to pass on data its teacher never wrote.
- **A spend-capped batch controller:** custom ids are stable across resumes, failures are classified and retried only when recoverable, an ambiguous create is adopted rather than paid for twice, and nothing is submitted past the worst-case cap.
- **Complete-block windows:** cleanup windows of up to 200 words replace the original 35- to 50-word chunks. In the M07 ablation this took long-input p50 from 4,187 ms to 2,393 ms and assertions from 106/120 to 115/120.
- **Typed normalization with an edit ledger:** offsets survive every rewrite, so protected spans and fact checks still line up after "twelve dollars" becomes "$12".
- **Crash-resilient capture:** per-block CRC32 and a SHA-256 footer, with the audio callback never touching disk.
- **No synthetic Return, ever:** dictated text cannot submit, send or execute.
- **Clipboard transactions with ownership generations:** if you copy something mid-dictation, LocalFlow notices and leaves your clipboard alone.
- **Context in a 75 ms budget:** asynchronous Accessibility reads are bound to the target process and finalized partial on timeout.
- **Long audio without seams:** 60 s chunks with 15 s of overlap, token-merged.

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| **Speech recognition** | Parakeet TDT 0.6B v3 via `parakeet-mlx` 0.5.2 |
| **Cleanup model** | Qwen3-4B-Instruct-2507 4-bit (default); LocalFlow-tuned Qwen3.5-4B 4-bit (local) |
| **ML runtime** | MLX 0.31.2 and `mlx-lm` 0.31.3 on the Apple silicon GPU |
| **Tokenizers** | `transformers` 5.10.4 (pinned below 5.11) |
| **Native app** | Python 3.14, PyObjC 12.2.1 (Cocoa, Quartz, ApplicationServices, WebKit) |
| **Audio** | `sounddevice` 0.5.5, NumPy 2.4.6 |
| **Storage** | SQLite (single writer thread), JSONL event logs |
| **Companion UI** | Svelte 5.57, TypeScript 6.0, Vite 8.3, hosted in `WKWebView` |
| **Launcher** | Small C executable compiled by `scripts/build_app.sh` |
| **Fine-tuning** | `mlx-lm` LoRA trainer with a custom chunked gated-delta rule |
| **Synthetic data** | Claude Sonnet 5.5 via the Message Batches API (official `anthropic` SDK) |
| **Evaluation audio** | DisfluencySpeech (Apache-2.0), FLEURS en_us (CC-BY-4.0) |

---

## Project Scale

| Metric | Count |
| --- | --- |
| Python modules in `localflow/` | 110 (about 59,600 lines) |
| Test files / test functions | 194 / 1,198 |
| Mutation-check scripts | 11 |
| Benchmark scripts | 14 |
| Spec requirements / evaluation suites | 33 / 22 |
| Milestones | 16 (M01–M16) |
| Contract documents (`docs/v2/contracts/`) | 27 |
| Companion UI source files (Svelte, TypeScript) | 68 |
| Cleanup-model experiment | about 6,400 lines, 49 unit tests |
| Fine-tuning examples | 6,393 |
| Frozen evaluation cases per model | 1,086 |
| Claude Batch API spend for the experiment | $16.21 |
| Git commits | 300+ |

---

## Development

### Prerequisites

| Requirement | Notes |
| --- | --- |
| Apple Silicon Mac | MLX runs on the Metal GPU |
| Homebrew Python 3.14 | `.venv` is created from it |
| About 5 GB of disk for models | Parakeet and the cleanup model, downloaded once |

### Setup

```sh
/opt/homebrew/bin/python3 -m venv .venv
.venv/bin/pip install parakeet-mlx mlx-lm "transformers<5.11" sounddevice \
    pyobjc-framework-Cocoa pyobjc-framework-Quartz \
    pyobjc-framework-ApplicationServices pyobjc-framework-WebKit \
    "anthropic>=1.14" onnxruntime==1.31.0
# transformers stays below 5.11: newer versions changed AutoTokenizer.register
# and crash mlx-lm at import, which silently disables LLM cleanup
.venv/bin/python scripts/warmup.py   # downloads the model and checks transcription
./run.sh                              # run from source
```

Your Voice's written profile is optional. To enable it, store an Anthropic API key in the login Keychain; `security` prompts for the key, so it never appears in your shell history:

```sh
security add-generic-password -U -s LocalFlow -a INSIGHTS_ANTHROPIC_API_KEY -w
```

### The app bundle

```sh
scripts/build_app.sh                                   # builds and installs /Applications/LocalFlow.app
scripts/build_app.sh --output /absolute/path/LocalFlow.app   # builds elsewhere, leaves the installed app alone
```

The bundle embeds the code, the virtualenv and `config.json`, so rebuild after changing either. Per-user settings belong in `~/Library/Application Support/LocalFlow/config.json`, which survives rebuilds. Common keys:

| Key | Default | Meaning |
| --- | --- | --- |
| `hotkey` | `"fn"` | `"fn"`, `"right_option"` or `"right_command"` |
| `hands_free` | `"off"` | `"double_tap"` starts continuous capture; the next tap ends it |
| `mouse_trigger` | `null` | `"middle"` or `"right"` mouse button as a hold-to-dictate key |
| `cleanup` | `"llm"` | `"llm"`, `"basic"` (regex filler removal) or `"off"` |
| `cleanup_model` | `mlx-community/Qwen3-4B-Instruct-2507-4bit` | any mlx-lm chat model in the local cache |
| `normalization_profile` | `"technical"` | `"technical"`, `"standard"` or `"off"` |
| `input_device` | `null` | microphone name substring or index |
| `log_transcripts` | `true` | keep raw and cleaned text plus the last 5 recordings' audio locally for debugging |

### Permissions

Grant these to **LocalFlow** (or to your terminal when using `./run.sh`) under System Settings, Privacy & Security, then quit and reopen the app:

| Permission | Why |
| --- | --- |
| **Microphone** | Recording (macOS asks on the first dictation) |
| **Accessibility** | Global Fn detection, context and pasting |
| **Input Monitoring** | Some macOS versions also gate key monitoring on this |

Grants are tied to the bundle's ad-hoc signature. If dictation transcribes but does not paste after installing a rebuilt bundle, remove and re-add LocalFlow under Accessibility, or run `tccutil reset Accessibility com.danny.localflow`. The text stays on the clipboard in the meantime, and `~/Library/Logs/LocalFlow.log` says why. Setting System Settings, Keyboard, "Press 🌐 key to" to "Do Nothing" stops Fn from also opening the emoji picker.

### Tests

Tests are plain scripts, not pytest: run each `test_*.py` with `.venv/bin/python` from its own directory. Suites that touch the companion, Hub or insertion refuse to start outside `tests/v2/context/run_isolated.py`, which blocks real Accessibility calls and the real pasteboard. The model-backed fidelity suites require a perfect score and currently fail by design; `docs/v2/STATUS.json` records the same numbers. The cleanup-model experiment's own tests live in `experiments/cleanup-model/tests/`.

---

## Roadmap

| Direction | Description |
| --- | --- |
| **Cleanup-model qualification (M15)** | Compare challengers with the incumbent on an owner-reviewed corpus of real dictations; the fine-tuned C enters as a challenger |
| **Training on your own dictations** | Retrain C from consented, curated real evidence (the export pipeline already exists) instead of synthetic pairs |
| **Release hardening (M16)** | Staged build, swap and rollback, a 500-job soak, offline verification and a release manifest |
| **ASR challenger** | Evaluate Qwen3-ASR-1.7B against Parakeet on the same harness |
| **Contextual biasing** | Feed dictionary terms into recognition once qualified (currently `disabled_until_qualified`) |
| **Meetings and notetaking** | Long-form capture, planned for V2.x |

---

## License

Personal project. No license is granted; all rights reserved. Model weights and datasets keep their own licenses: Parakeet TDT 0.6B v3 is CC-BY-4.0, Qwen3 and Qwen3.5 are Apache-2.0, DisfluencySpeech is Apache-2.0 and FLEURS is CC-BY-4.0.

---

<p align="center">
  <em>Speech becomes text on the machine that heard it, and the model that cleans it was taught to change only what you meant to change.</em>
</p>
