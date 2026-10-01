"""Insights — Usage (M13, Spec S21) and Your Voice (M14, S22).

Usage is one report per cohort (range, app, mode), read by HubState in a
single writer op; the page shows its fields as they are — a metric the
service leaves as None stays "not measured", never zero. Your Voice is
the deterministic, local ProfileService snapshot: absent, invalidated
(reason only, never its stale numbers) or current (measured block, and
cards that cite their own evidence). Generate runs off the main thread
under a key; only the newest Generate reports. Excluding evidence names
the snapshot the page rendered.
"""

from __future__ import annotations

from .. import bridge as B
from ..bridge import Enum, Int, Nullable, Str

RANGES = (7, 30, 90, None)


def register(ctl):
    br = ctl.bridge
    st = ctl.state

    @br.command("insights.subview", {"subview": Enum(("usage", "voice"))})
    def subview(p):
        st.select_insights_subview(p["subview"])
        return {}

    @br.command("insights.filters", {
        "range": Nullable(Int(lo=1, hi=90), optional=True),  # null = all time
        "app": Nullable(Str(max_len=300), optional=True),
        "mode": Nullable(Str(max_len=60), optional=True)})
    def filters(p):
        kw = {}
        if "range" in p:
            if p["range"] not in RANGES:
                B.refuse("unknown_range")
            kw["range_days"] = p["range"]
        if "app" in p:
            kw["app"] = p["app"]
        if "mode" in p:
            kw["mode"] = p["mode"]
        st.set_insights_filters(**kw)
        return {}

    @br.command("insights.reload")
    def reload(p):
        st.reload_insights()
        return {}

    @br.command("voice.generate")
    def generate(p):
        prof = st.profile_service
        if prof is None:
            B.unavailable("profile_service_unavailable")
        ctl.notes.pop("voice", None)

        def done(out, err, current):
            if not current:
                return  # a newer Generate owns the note
            if err is not None:
                ctl.notes["voice"] = {"code": "generation_failed",
                                      "reason": type(err).__name__}
            st.reload_insights()
            ctl.request_flush()
        ctl.background.run("voice", prof.compute, done)
        ctl.request_flush()
        return {"started": True}

    @br.command("voice.exclude", {"snapshot_id": Str(max_len=120),
                                  "example_id": Str(max_len=120)})
    def exclude(p):
        prof = st.profile_service
        if prof is None:
            B.unavailable("profile_service_unavailable")
        current = prof.current()
        if not current or current.get("snapshot_id") != p["snapshot_id"]:
            st.reload_insights()
            B.stale("snapshot_changed")
        try:
            prof.exclude_evidence(p["snapshot_id"], p["example_id"])
        except TimeoutError:
            st.reload_insights()
            B.unknown("store_busy")
        except ValueError as e:
            st.reload_insights()
            B.refuse(str(e))
        st.reload_insights()
        return {}


def insights_model(ctl):
    v = ctl.state.views["insights"]
    data = v.get("data")
    out = {"loading": bool(v.get("loading")), "error": v.get("error"),
           "subview": v.get("subview", "usage"), "range": v.get("range"),
           "app": v.get("app"), "mode": v.get("mode"),
           "note": ctl.notes.get("voice"),
           "voice_running": "voice" in ctl.background.running}
    if data is None or data.get("subview") != out["subview"]:
        out["data"] = None
        return out
    if data.get("subview") == "voice":
        out["data"] = {"profile": _profile(data.get("profile")),
                       "profile_reason": data.get("profile_reason")}
        return out
    s = data.get("summary") or {}
    out["data"] = {
        "summary": {k: s.get(k) for k in (
            "reporting_timezone", "day_start", "day_end", "dictations",
            "dictations_with_text", "outcomes", "raw_words", "final_words",
            "capture_seconds", "wpm", "wpm_denominator", "wpm_excluded",
            "fallback_jobs", "fallback_rate", "cleanup_fallback",
            "dictionary_hits", "snippet_hits", "transforms",
            "transform_words", "repastes", "future_dated",
            "range_first_day", "range_last_day",
            "mixed_word_count_versions")},
        "latency": {k: {kk: (s.get("latency") or {}).get(k, {}).get(kk)
                        for kk in ("n", "p50", "p95")}
                    for k in ("asr", "cleanup", "end_to_end")},
        "daily": [{k: d.get(k) for k in ("day", "dictations", "final_words",
                                          "capture_seconds", "transforms")}
                  for d in data.get("daily") or ()],
        "per_app": [{k: a.get(k) for k in ("key", "app", "dictations",
                                            "final_words", "capture_seconds")}
                    for a in data.get("per_app") or ()],
        "per_mode": [{k: m.get(k) for k in ("mode", "dictations",
                                             "final_words")}
                     for m in data.get("per_mode") or ()],
        "apps": [{"key": a.get("key"), "label": a.get("label")}
                 for a in data.get("apps") or ()],
        "modes": list(data.get("modes") or ()),
        "undated": data.get("undated"),
        "legacy": None if not data.get("legacy") else {
            k: data["legacy"].get(k) for k in ("rows", "cleaned_words",
                                               "first_instant",
                                               "last_instant")},
    }
    return out


def _profile(p):
    if not p:
        return None
    m = p.get("measured") or {}
    hist = m.get("hour_histogram")
    return {
        "snapshot_id": p.get("snapshot_id"),
        "state": p.get("state"),
        "invalidated_reason": p.get("invalidated_reason"),
        "computed_at_utc": p.get("computed_at_utc"),
        "source_example_count": p.get("source_example_count"),
        "coverage": p.get("coverage"),
        "measured": {} if p.get("state") != "current" else {
            "eligible_examples": m.get("eligible_examples"),
            "eligible_words": m.get("eligible_words"),
            "min_words_threshold": m.get("min_words_threshold"),
            "excluded": m.get("excluded"),
            "utterance_words": m.get("utterance_words"),
            "frequent_phrases": [{"phrase": f.get("phrase"),
                                  "count": f.get("count")}
                                 for f in (m.get("frequent_phrases") or ())
                                 ][:6],
            "technical_terms": [{"term": t.get("term"),
                                 "dictations": t.get("dictations")}
                                for t in (m.get("technical_terms") or ())][:8],
            "corrections_by_kind": m.get("corrections_by_kind"),
            "self_corrections": m.get("self_corrections"),
            "app_usage": [{"app": name, "dictations": n} for name, n in
                          sorted((m.get("app_usage") or {}).items(),
                                 key=lambda kv: -kv[1])][:8]
            if isinstance(m.get("app_usage"), dict) else None,
            "hours_unknown": m.get("hours_unknown"),
            "hour_histogram": list(hist) if isinstance(hist, list) else None,
            "requested_transforms": m.get("requested_transforms"),
            "interpretive_note": m.get("interpretive_note"),
            "usage_redacted": bool(m.get("usage_redacted")),
        },
        "cards": [] if p.get("state") != "current" else [
            {"card_id": c.get("card_id"), "title": c.get("title"),
             "statement": c.get("statement"),
             "evidence": list(c.get("evidence_example_ids") or ())[:5],
             "coverage": c.get("coverage")}
            for c in p.get("cards") or ()],
    }


READ_MODELS = {"insights": insights_model}
