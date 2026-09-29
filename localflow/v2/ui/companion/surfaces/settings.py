"""Settings — the Hub's data and privacy controls (training-evidence
collection, retention windows, usage analytics) with the AppKit Hub's
outcome rules (hub.py ``_settings_call``):

- a returned refusal, failure or unknown outcome is kept as the Settings
  note and rendered instead of reloading over it;
- an unknown outcome reloads (the result is checked when it finishes and
  the note is reconciled);
- any other outcome clears the note and reloads.

The retention knobs keep the Hub's client rule (whole days, low end
clamped to 1) and the usage knob reaches the coordinator's strict
validator unclamped. Delete All Usage requires the page's explicit
confirmation flag — the page shows the Hub's warning before sending it.
"""

from __future__ import annotations

from .. import bridge as B
from ..bridge import Bool, Enum, Str

RETENTION_KEYS = ("transcript", "audio_success", "audio_failed", "metadata",
                  "training_buffer")

NOTED = ("refused", "invalid", "not_saved", "not_persisted", "failed",
         "not_started", "unavailable", "outcome_unknown")


def register(ctl):
    br = ctl.bridge
    st = ctl.state
    coord = ctl.coordinator

    def call(what, fn, *args):
        if coord is None:
            B.unavailable()
        try:
            out = fn(*args) or {}
        except Exception as e:
            # Nothing changed on screen; the type only (content-free).
            ctl.notes["settings"] = {"what": what, "code": "exception",
                                     "reason": type(e).__name__}
            ctl.request_flush()
            B.refuse("exception", {"type": type(e).__name__})
        outcome = out.get("outcome")
        if outcome in NOTED:
            ctl.notes["settings"] = {"what": what, "code": outcome,
                                     "reason": out.get("reason_code")
                                     or outcome}
            if outcome == "outcome_unknown":
                st.reload_current()
                ctl.request_flush()
                B.unknown("outcome_unknown")
            ctl.request_flush()
            B.refuse(outcome, {"reason": out.get("reason_code")})
        ctl.notes.pop("settings", None)
        st.reload_current()
        return out

    @br.command("settings.collection",
                {"state": Enum(("enabled", "paused", "disabled"))})
    def collection(p):
        call("collection", coord.hubSetCollection if coord else None,
             p["state"])
        return {"state": p["state"]}

    @br.command("settings.retention",
                {k: Str(max_len=12) for k in RETENTION_KEYS})
    def retention(p):
        try:
            values = [max(1, int(p[k].strip())) for k in RETENTION_KEYS]
        except ValueError:
            B.refuse("not_whole_days")
        call("retention", coord.hubApplyRetention if coord else None,
             values)
        return {"applied": dict(zip(RETENTION_KEYS, values))}

    @br.command("settings.usage_retention", {"value": Str(max_len=12)})
    def usage_retention(p):
        if coord is None or not hasattr(coord, "hubApplyUsageRetention"):
            B.unavailable()
        out = call("usage_retention", coord.hubApplyUsageRetention,
                   p["value"])
        return {"outcome": out.get("outcome"),
                "days": out.get("days"),
                "pending_expiry": out.get("pending_expiry")}

    @br.command("settings.delete_all_usage", {"confirmed": Bool()})
    def delete_all_usage(p):
        if not p["confirmed"]:
            B.refuse("confirmation_required")
        if coord is None or not hasattr(coord, "hubDeleteAllUsage"):
            B.unavailable()
        out = call("delete_usage", coord.hubDeleteAllUsage)
        return {"outcome": out.get("outcome"),
                "facts_deleted": out.get("facts_deleted")}

    def usage_reconciled(result):
        # Only the usage deletion that said "not known yet" is reconciled
        # by this result (an unrelated unknown note is left as it is).
        note = ctl.notes.get("settings") or {}
        if note.get("code") == "outcome_unknown" \
                and note.get("what") == "delete_usage":
            ctl.notes["settings"] = {"what": note.get("what"),
                                     "code": "reconciled",
                                     "reason": result}
            if st.selected_view == "settings":
                st.reload_current()
            ctl.request_flush()
    ctl.usage_reconciled_hooks.append(usage_reconciled)
