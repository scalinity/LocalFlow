# LocalFlow — private, on-device dictation for macOS

A local Wispr Flow alternative. Hold a key, speak, release — your words are typed
into whatever app you're using. Everything runs on-device with NVIDIA's
**Parakeet TDT 0.6B v3** speech model via Apple **MLX**. No audio, text, or
telemetry ever leaves your Mac (network is only used once, to download the model).

While you speak, a floating pill shows a live speech-reactive waveform:

- **Recording** — white bars react to your voice
- **Processing** — bars shimmer while Parakeet transcribes
- Text is then pasted at your cursor and the pill fades out

## Usage

Open **LocalFlow** from /Applications (Spotlight: "LocalFlow"), or run the
live project code from a terminal with `./run.sh`.

A waveform icon appears in the menu bar. **Hold fn (🌐), speak, release.**
The transcription is pasted into the frontmost app.

- Pressing any other key while holding fn cancels (so fn+arrow shortcuts still work).
- Taps shorter than 0.3 s are ignored.
- You can start the next dictation while the previous one is still
  transcribing — nothing is dropped, and pastes land in dictation order.
- Parakeet v3 is multilingual (25 European languages) with automatic punctuation
  and capitalization — no language setting needed.
- Quit from the menu bar icon.

## One-time setup

Already done in this repo (`.venv` created from Homebrew Python 3.14, model
downloaded to `~/.cache/huggingface`). On a fresh machine:

```sh
/opt/homebrew/bin/python3 -m venv .venv
.venv/bin/pip install parakeet-mlx mlx-lm "transformers<5.11" sounddevice \
    pyobjc-framework-Cocoa pyobjc-framework-Quartz \
    pyobjc-framework-ApplicationServices
# transformers is pinned <5.11: newer versions changed AutoTokenizer.register
# and crash mlx-lm at import, silently disabling the LLM cleanup tier
.venv/bin/python scripts/warmup.py   # downloads model + verifies transcription
```

### The app bundle

`scripts/build_app.sh` builds a **self-contained** `LocalFlow.app` in
/Applications: it embeds a copy of the code, the venv, and `config.json`,
so the app never reads from ~/Documents (no Documents-access prompt) and
launches like any normal Mac app. **Re-run the script after changing the
code or config** — the bundle does not track this folder. The launcher is
a small compiled Mach-O binary (LaunchServices rejects script executables).

Logs: `~/Library/Logs/LocalFlow.log` — each dictation logs its audio
diagnostics (duration, input device, voiced %, trailing silence, dropped
blocks) plus stt/cleanup timing, and the audio of the last 5 dictations
is kept in `~/Library/Logs/LocalFlow-audio/` so a bad transcript can be
replayed to tell a capture problem from a transcription problem.
Per-user config override (survives rebuilds):
`~/Library/Application Support/LocalFlow/config.json`.

### Permissions (System Settings → Privacy & Security)

When using **LocalFlow.app**, grant these to **LocalFlow**; when using
`./run.sh`, grant them to your terminal app instead:

| Permission | Why |
|---|---|
| **Microphone** | record your speech (macOS prompts on first dictation) |
| **Accessibility** | global fn-key detection + pasting text (prompts on first launch) |
| **Input Monitoring** | some macOS versions also gate key monitoring on this |

After granting Accessibility/Input Monitoring, quit (menu bar icon → Quit)
and reopen the app — grants only take effect for freshly launched processes.

Note: macOS ties these grants to the launcher binary inside the bundle.
`build_app.sh` produces a byte-identical launcher on every rebuild, so
grants survive rebuilds; but if the launcher C code is ever changed, the
grants go stale — fix with `tccutil reset Accessibility com.danny.localflow`
(and `ListenEvent`), then re-grant. If dictation transcribes but doesn't
paste, this is almost always the cause: the transcript is left on the
clipboard (⌘V to insert) and `~/Library/Logs/LocalFlow.log` explains.

### Recommended

System Settings → Keyboard → **"Press 🌐 key to" → "Do Nothing"**, so holding
fn doesn't also trigger the emoji picker or Apple's dictation.

## Configuration — `config.json`

| Key | Default | Meaning |
|---|---|---|
| `hotkey` | `"fn"` | `"fn"`, `"right_option"`, or `"right_command"` |
| `model` | `mlx-community/parakeet-tdt-0.6b-v3` | any parakeet-mlx compatible HF model |
| `min_duration_sec` | `0.3` | ignore accidental taps shorter than this |
| `max_duration_sec` | `0` | auto-stop safety cap; `0` = no cap |
| `append_space` | `true` | trailing space so consecutive dictations don't collide |
| `restore_clipboard` | `true` | put your old clipboard back after pasting |
| `input_device` | `null` | mic name substring or index; `null` = system default |
| `cleanup` | `"llm"` | `"llm"` = local LLM pass (fillers, self-corrections, formatting), `"basic"` = regex filler removal only, `"off"` |
| `cleanup_model` | Qwen3-4B-Instruct-2507-4bit | any mlx-lm chat model (benchmarked best for this task) |
| `log_transcripts` | `true` | write raw + cleaned transcripts to the local log and keep the last 5 dictations' audio in `~/Library/Logs/LocalFlow-audio/` for debugging |

## Start at login

Already configured — LocalFlow is registered as a Login Item. Manage it
under System Settings → General → Login Items (remove or re-add
/Applications/LocalFlow.app there), or via:

```sh
osascript -e 'tell application "System Events" to make login item at end \
  with properties {path:"/Applications/LocalFlow.app", name:"LocalFlow", hidden:false}'
```

## How it works

```
hold fn ──► sounddevice mic capture (16 kHz mono)
                 │ live level (auto-gain + noise gate)
                 ▼
        floating NSPanel pill (PyObjC, 30 fps reactive bars)
release ──► parakeet-mlx: log-mel → Parakeet TDT 0.6B v3 (MLX, Metal GPU)
                 │ (>90 s audio is chunked and token-merged seamlessly)
                 ▼
        cleanup: regex filler strip → local LLM pass (Qwen3 4B)
        fillers, self-corrections ("3pm no wait 4pm" → "4pm"), punctuation
                 ▼
        clipboard + synthetic ⌘V into frontmost app (old clipboard restored)
```

- `localflow/stt.py` feeds the mic buffer straight into the model's log-mel
  frontend — no ffmpeg, no temp files.
- After the first download, the app sets `HF_HUB_OFFLINE=1` so it never
  touches the network again.
- `scripts/render_pill.py` renders the pill states to PNGs;
  `scripts/warmup.py` re-verifies the whole STT path without a microphone.
