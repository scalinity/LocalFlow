"""Diagnostics (contract hub.md "Diagnostics", contracts/events.md): the
shared ordering and redaction of the event view. Export Redacted writes
the window the page last RENDERED (its token), never a newer load not
yet on screen, through the typed allowlist, off the main thread, to a
path chosen in a native save panel; an older export never overwrites a
newer one's report."""

from __future__ import annotations

from .. import bridge as B
from ..bridge import Bool, Enum, Nullable, Str

LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def register(ctl):
    br = ctl.bridge
    st = ctl.state
    panels = ctl.spec.get("file_panels")

    @br.command("diagnostics.filters", {
        "job": Str(max_len=120, optional=True),
        "level": Nullable(Enum(LEVELS), optional=True),
        "utc": Bool(optional=True)})
    def filters(p):
        kw = {}
        if "job" in p:
            kw["job"] = p["job"].strip()
        if "level" in p:
            kw["level"] = p["level"]
        if "utc" in p:
            kw["utc"] = p["utc"]
        st.set_diagnostics_filters(**kw)
        return {}

    @br.command("diagnostics.reload")
    def reload(p):
        st.set_diagnostics_filters()
        return {}

    @br.command("diagnostics.export", {"token": Str(max_len=40)})
    def export(p):
        from .... import diagnostics as diag
        cur = ctl._tokens.get("diagnostics")
        data = st.views["diagnostics"].get("data")
        if cur is None or cur[1] != p["token"] or cur[0] is not data:
            B.stale("window_not_current")
        records = list(data.get("records") or ())
        filters = dict(data.get("filters") or {})
        loaded = data.get("loaded_at_utc")
        path = panels.save_jsonl("localflow-events.jsonl") \
            if panels is not None else _save_panel()
        if not path:
            raise B.Outcome("cancelled", "cancelled")

        def done(n, err, current):
            if not current:
                return
            ctl.notes["diagnostics"] = {
                "code": "export_failed", "type": type(err).__name__} \
                if err is not None else {
                "code": "exported", "count": n, "loaded_at_utc": loaded,
                "filters": filters}
            ctl.request_flush()
        ctl.background.run("diag_export",
                           lambda: diag.redacted_export(records, path), done)
        return {"started": True, "records": len(records)}


def _save_panel():
    from AppKit import NSSavePanel
    panel = NSSavePanel.savePanel()
    panel.setNameFieldStringValue_("localflow-events.jsonl")
    if panel.runModal() != 1 or not panel.URL():
        return None
    return str(panel.URL().path())


def diagnostics_model(ctl):
    v = ctl.state.views["diagnostics"]
    data = v.get("data")
    out = {"loading": bool(v.get("loading")), "error": v.get("error"),
           "job": v.get("job_filter") or "", "level": v.get("level_filter"),
           "utc": bool(v.get("utc")), "note": ctl.notes.get("diagnostics"),
           "running": "diag_export" in ctl.background.running}
    if data is None:
        out["data"] = None
        return out
    out["data"] = {
        "token": ctl.token_for("diagnostics", data),
        "events": list(data.get("events") or ()),
        "count": data.get("count"),
        "timeline": list(data.get("timeline") or ()),
        "skipped_lines": data.get("skipped_lines"),
        "engine": data.get("engine"),
        "filters": data.get("filters"),
        "loaded_at_utc": data.get("loaded_at_utc"),
    }
    return out


READ_MODELS = {"diagnostics": diagnostics_model}
