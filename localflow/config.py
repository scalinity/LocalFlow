"""Configuration loading for LocalFlow."""

import json
import os
import pathlib

DEFAULTS = {
    # STT model (Parakeet V3, multilingual, runs on-device via MLX)
    "model": "mlx-community/parakeet-tdt-0.6b-v3",
    # Hold-to-dictate key: "fn" | "right_option" | "right_command"
    "hotkey": "fn",
    "sample_rate": 16000,
    # Recordings shorter than this are treated as accidental taps
    "min_duration_sec": 0.3,
    # Safety cap — recording auto-stops and transcribes at this length.
    # 0 disables the cap (recording runs until you release the key).
    "max_duration_sec": 0,
    # Append a trailing space so consecutive dictations don't collide
    "append_space": True,
    # Put the previous clipboard contents back after pasting
    "restore_clipboard": True,
    # Input device name substring or index; null = system default
    "input_device": None,
    # Transcript cleanup: "llm" (fillers, self-corrections, formatting via a
    # small local model), "basic" (instant regex filler removal), or "off"
    "cleanup": "llm",
    "cleanup_model": "mlx-community/Qwen3-4B-Instruct-2507-4bit",
    # M07 (Spec S13–S14): which cleanup implementation "llm" mode runs —
    # "v2" = faithful cleanup (complete-block windows, offset-anchored
    # corrections, validation and fallback ladder); "v1" = the original
    # TranscriptCleaner path, kept as the ablation control and fallback.
    "cleanup_implementation": "v2",
    # Write raw and cleaned transcripts to ~/Library/Logs/LocalFlow.log
    # (local only) so cleanup edits can be inspected and debugged
    "log_transcripts": True,
    # V2 retention knobs (Spec S25) — visible and adjustable here; the Hub
    # surfaces them visually from M09. Values are days unless named otherwise.
    "events_retention_days": 14,
    "events_cap_mib": 100,
    "retention_transcript_days": 30,
    "retention_audio_success_days": 7,
    "retention_audio_failed_days": 30,
    "retention_metadata_days": 14,
    "training_buffer_days": 30,
    # M13 (Spec S21): usage analytics retention — usage facts and daily
    # aggregates expire on their own schedule, independent of transcript
    # and audio retention (deleting expired text never empties usage
    # graphs unless usage was explicitly deleted).
    "retention_usage_days": 365,
    # M13 (Spec S21): the reporting timezone for day boundaries — an
    # IANA name; empty means the system's local zone. Changing it
    # re-buckets every usage day at next launch.
    "analytics_timezone": "",
    # M03 (Spec S09): crash-resilient capture. The audio callback journals
    # blocks off-thread so a crash mid-dictation recovers every complete
    # block. false = memory-only capture; crash recovery is then honestly
    # disabled for those dictations, not secretly persisted.
    "capture_journal": True,
    # M03 (Spec S09 engine lifecycle): what a dictation does while the
    # cleanup engine is still loading — "basic" inserts the basic-pass text
    # now (recorded as basic, never as LLM-cleaned); "wait" holds the job
    # until the engine is ready or fails (bounded by cleanup_wait_timeout_sec).
    "cleanup_not_ready_policy": "basic",
    "cleanup_wait_timeout_sec": 120,
    # M03 (Spec S09): optional hands-free dictation. "double_tap" = a quick
    # double-tap of the hold key starts continuous capture; the next tap
    # ends it. "off" keeps hold-to-talk exactly as before.
    "hands_free": "off",
    # M03 (Spec S09): optional hold-to-dictate on a non-primary mouse
    # button — "middle", "right", or null for none.
    "mouse_trigger": None,
    # M04 (Spec S10): typed numeric and spoken-syntax normalization,
    # running between ASR and cleanup. Profile "technical" converts
    # integers/ordinals in technical contexts plus all typed forms;
    # "standard" keeps bare integers as words; "off" skips the stage.
    "normalization_profile": "technical",
    # Locale drives number rendering (separators, symbols, date shape);
    # it belongs to the job, not the machine's location (S10).
    "normalization_locale": "en-US",
    # M05 (Spec S11/S30.1): the Relevant Vocabulary Selector's term
    # budget — the bounded subset offered in one HintSet. Entries beyond
    # the limit are recorded as omissions with a reason, never silently
    # dropped.
    "hint_term_limit": 100,
    # M06 (Spec S12): local destination context. Disabled = identity is
    # never read and dictation runs exactly as before (plain, global
    # vocabulary scope only).
    "context_enabled": True,
    # The bounded post-release finalize deadline in milliseconds (S12
    # suggests 75 as the initial target; a timeout yields a partial
    # snapshot, never a stalled dictation).
    "context_deadline_ms": 75,
    # App bundles for which NO context is read at all — identity records
    # the denial, fields/text/origin/workspace stay unread.
    "context_denied_apps": [],
    # Independent training-context retention (S12): transient context
    # use is separate from retaining snapshot payloads as training
    # evidence. false = no context artifact is written even with
    # collection enabled; the envelope records the redaction.
    "training_retain_context": True,
    # M08 (Spec S29.8): the bounded post-insertion observation window in
    # seconds — how long a certified field is watched for edits to the
    # inserted region. An adjustable collection window, not a limit on
    # dictation or editing; 0 disables observation.
    "outcome_observation_sec": 30,
    # M10 (Spec S15/S17): explicitly configured local skill manifests —
    # files (JSON manifests) or directories (one level of <skill>/
    # SKILL.md, frontmatter identity only). Nothing is scanned beyond
    # these paths, and no skill ever executes during discovery.
    "skill_manifest_paths": [],
    # Workspace-RELATIVE skill directories (e.g. ".claude/skills"),
    # resolved against the active document's directory when a job's
    # context resolves one. Empty = no workspace manifests are read.
    "workspace_skill_dirs": [],
    # M10 (Spec S17): the strictly bounded, name-only listing of the
    # active document's directory that lets "attach file <name>"
    # resolve exact filenames (depth 2, cap 500, hidden entries
    # skipped, no content reads). false = file references surface as
    # review suggestions instead of resolving.
    "developer_workspace_listing": True,
    # M14 (Spec S22): the eligible-words floor before interpretive
    # profile cards render — below it, measured totals only (the S22
    # initial default, a floor for interpretation, not validity).
    "profile_min_words": 2000,
    # M14 (Spec S22): idle profile regeneration interval in minutes; 0
    # disables idle generation (on-demand from the Hub still works).
    # The scheduler never runs while a dictation, insertion or worker
    # job is in flight — profile work yields to dictation.
    "profile_idle_minutes": 30,
    # M14 (Spec S29.9): the seeded representative review stream's
    # Bernoulli percent over eligible jobs. The seed/policy are
    # recorded with every sampling decision.
    "review_sample_percent": 10,
}

ROOT = pathlib.Path(__file__).resolve().parent.parent


def user_override_path() -> pathlib.Path:
    return pathlib.Path.home() / "Library" / "Application Support" / \
        "LocalFlow" / "config.json"


def load(path=None) -> dict:
    """First match wins: explicit path, $LOCALFLOW_CONFIG, user override
    in Application Support, then the config.json shipped next to the code."""
    candidates = [
        path,
        os.environ.get("LOCALFLOW_CONFIG"),
        pathlib.Path.home() / "Library" / "Application Support" / "LocalFlow" / "config.json",
        ROOT / "config.json",
    ]
    cfg = dict(DEFAULTS)
    for c in candidates:
        if not c:
            continue
        p = pathlib.Path(c)
        if p.exists():
            try:
                cfg.update(json.loads(p.read_text()))
            except (json.JSONDecodeError, OSError) as e:
                print(f"[localflow] ignoring bad config {p}: {e}")
            break
    return cfg


# ---- retention policy validation (M02 remediation, M02-AUDIT-19) --------

# Store retention knobs: config key -> (store retention key, lo, hi) in
# days. Zero is NOT "keep nothing": a zero/negative window would make
# fresh content immediately purgeable, so it is rejected like any other
# out-of-range value. The upper bound (100 years) keeps every expiry
# instant representable. An invalid value falls back to its default and
# is reported (content-free: key name + reason) — never a startup crash
# and never a destructive interpretation.
RETENTION_BOUNDS = {
    "retention_transcript_days": ("transcript", 1, 36500),
    "retention_audio_success_days": ("audio_success", 1, 36500),
    "retention_audio_failed_days": ("audio_failed", 1, 36500),
    "retention_metadata_days": ("metadata", 1, 36500),
    "training_buffer_days": ("training_buffer", 1, 36500),
    "retention_usage_days": ("usage", 1, 36500),
}
EVENT_RETENTION_BOUNDS = {
    "events_retention_days": (1, 3650),
    "events_cap_mib": (1, 1024 * 1024),
}


def _valid_int(value, lo, hi):
    """(int, None) when value is an integral number within [lo, hi];
    otherwise (None, reason). Booleans and non-integral values are
    rejected; integral strings are not guessed at."""
    if isinstance(value, bool) or value is None:
        return None, "not_a_number"
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")) \
                or not value.is_integer():
            return None, "not_an_integer"
        value = int(value)
    if not isinstance(value, int):
        return None, "not_a_number"
    if value < lo or value > hi:
        return None, "out_of_range"
    return value, None


def retention_policy(cfg) -> tuple[dict, list]:
    """The validated store retention map + a list of (key, reason)
    problems. Missing keys use DEFAULTS silently (not a problem)."""
    days, problems = {}, []
    for key, (store_key, lo, hi) in RETENTION_BOUNDS.items():
        default = DEFAULTS[key]
        if key not in cfg:
            days[store_key] = default
            continue
        value, reason = _valid_int(cfg.get(key), lo, hi)
        if reason:
            problems.append((key, reason))
            value = default
        days[store_key] = value
    return days, problems


def event_retention_policy(cfg) -> tuple[dict, list]:
    out, problems = {}, []
    for key, (lo, hi) in EVENT_RETENTION_BOUNDS.items():
        default = DEFAULTS[key]
        if key not in cfg:
            out[key] = default
            continue
        value, reason = _valid_int(cfg.get(key), lo, hi)
        if reason:
            problems.append((key, reason))
            value = default
        out[key] = value
    return out, problems


def context_policy(cfg) -> tuple[dict, list]:
    """The validated M06 privacy controls + (key, reason) problems.
    Read once at startup — a change applies from the next launch, there
    is no hot reload. Every malformed value fails CLOSED: a disable or
    deny request that is not the documented type never becomes
    permission to read or retain (JSON false/lists keep working as
    written). The deadline keeps a configured value only inside
    [0, 250] ms, else its default."""
    problems = []
    enabled = cfg.get("context_enabled", DEFAULTS["context_enabled"])
    if not isinstance(enabled, bool):
        problems.append(("context_enabled", "not_a_boolean"))
        enabled = False
    retain = cfg.get("training_retain_context",
                     DEFAULTS["training_retain_context"])
    if not isinstance(retain, bool):
        problems.append(("training_retain_context", "not_a_boolean"))
        retain = False
    denied = cfg.get("context_denied_apps", DEFAULTS["context_denied_apps"])
    if denied is None:
        denied = []
    if not isinstance(denied, list) or not all(
            isinstance(b, str) and b.strip() for b in denied):
        # The deny intent cannot be honored, so nothing is read at all.
        problems.append(("context_denied_apps", "not_a_list_of_bundle_ids"))
        enabled, denied = False, []
    deadline = cfg.get("context_deadline_ms",
                       DEFAULTS["context_deadline_ms"])
    if isinstance(deadline, bool) or not isinstance(deadline, (int, float)) \
            or deadline != deadline \
            or deadline in (float("inf"), float("-inf")) \
            or not 0 <= deadline <= 250:
        problems.append(("context_deadline_ms", "out_of_range"))
        deadline = DEFAULTS["context_deadline_ms"]
    return ({"context_enabled": enabled, "training_retain_context": retain,
             "context_denied_apps": tuple(b.strip() for b in denied),
             "context_deadline_ms": deadline}, problems)


def validate_retention_value(key, value):
    """One knob from a UI/settings write: the int, or None when invalid."""
    lo, hi = (RETENTION_BOUNDS[key][1:] if key in RETENTION_BOUNDS
              else EVENT_RETENTION_BOUNDS[key])
    value, reason = _valid_int(value, lo, hi)
    return value
