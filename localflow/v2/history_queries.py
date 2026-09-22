"""History and Home query layer (V2 M09, Spec S19/S08, contract hub.md).

Read-only assembly over the single-writer store: every query is one
``Store.submit`` op on the writer thread (the sanctioned read path — the
discipline forbids a second connection), returning fully materialized
plain data so nothing crosses threads lazily.

Honesty rules carried here:

- The four lineage stages (source → normalized → cleaned → transformed)
  are returned as distinct entries keyed by role; nothing flattens them
  into one ambiguous field (M09-AC01). A stage with no artifact says so
  with a reason, never an empty string pretending to be the text.
- Records without a usable capture instant (legacy log imports) group
  under the explicit ``Undated`` label and never acquire a date (S21).
- Purged/expired artifacts report ``purged``; missing audio reports why
  (M09-AC02). Unknown app is ``None``, displayed as unknown.
"""

from __future__ import annotations

import datetime as dt
import json

UNDATED = "Undated"

# Cleanup paths that can appear in an applied-output artifact's meta
# (contracts/cleanup.md). The mode filter only accepts these — the value
# is spliced into a JSON meta match, so it comes from a fixed vocabulary.
MODES = ("llm", "llm_partial", "llm_fallback_normalized", "basic", "raw",
         "basic_empty_input", "legacy")

_TEXT_ROLES = ("raw_transcript", "normalized_text", "applied_output",
               "cleaned_transcript")


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _local_date(iso: str | None, tz: dt.timezone) -> str | None:
    if not iso:
        return None
    try:
        t = dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=dt.timezone.utc).astimezone(tz)
    except ValueError:
        return None
    return t.strftime("%Y-%m-%d")


class HistoryQueryService:
    """All reads through the store's writer thread; safe to call from any
    thread (the Hub calls from its query thread, never the UI callback)."""

    def __init__(self, store, tz: dt.timezone | None = None):
        self.store = store
        self.tz = tz if tz is not None else dt.datetime.now().astimezone().tzinfo

    # ---- History list ---------------------------------------------------

    def search(self, text=None, app=None, mode=None, limit=200) -> dict:
        """Searchable date/app/mode history. Returns
        ``{"groups": [{label, rows}], "total": n}`` — groups in date
        order (newest first), ``Undated`` last (S21)."""
        if mode is not None and mode not in MODES:
            raise ValueError(f"unknown mode filter {mode!r}")
        rows = self.store.submit(lambda conn: self._search_op(
            conn, text, app, mode, int(limit)))
        return self._grouped(rows)

    def _search_op(self, conn, text, app, mode, limit):
        out = []
        # -- V2 jobs ----------------------------------------------------
        clauses, params = [], []
        if text:
            # A subquery (not a materialized IN-list): a common-substring
            # search matching most of a 50k+ store would otherwise blow
            # the bound-parameter limit and pay an O(matches) parse per
            # query (review finding).
            pat = f"%{_like_escape(text)}%"
            clauses.append(
                "j.job_id IN (SELECT DISTINCT job_id FROM artifacts WHERE"
                " job_id IS NOT NULL AND purged=0 AND role IN (?,?,?)"
                " AND content_text LIKE ? ESCAPE '\\')")
            params += [*_TEXT_ROLES[:3], pat]
        if app:
            pat = f"%{_like_escape(app)}%"
            clauses.append("(t.app_name LIKE ? ESCAPE '\\' OR t.app_bundle"
                           " LIKE ? ESCAPE '\\')")
            params += [pat, pat]
        if mode is not None and mode != "legacy":
            # The cleanup path lives in the applied artifact's meta JSON;
            # json_extract is exact where a LIKE on the serialized text
            # would couple to json.dumps spacing.
            clauses.append("j.job_id IN (SELECT a.job_id FROM artifacts a"
                           " WHERE a.role='applied_output' AND a.purged=0"
                           " AND a.job_id IS NOT NULL AND json_extract("
                           "a.meta_json, '$.cleanup_path') = ?)")
            params.append(mode)
        if mode == "legacy":
            clauses.append("0")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params2 = list(params)
        sql = ("SELECT j.job_id, j.captured_at_utc, j.time_quality, j.state,"
               " j.state_reason, t.app_name, t.app_bundle FROM jobs j LEFT"
               f" JOIN job_targets t ON t.job_id = j.job_id{where}"
               " ORDER BY j.captured_at_utc IS NULL, j.captured_at_utc DESC,"
               " j.rowid DESC LIMIT ?")
        params2.append(limit)
        for (job_id, captured, tq, state, reason, app_name, app_bundle) \
                in conn.execute(sql, params2).fetchall():
            arts = self._job_artifacts(conn, job_id)
            raw = arts.get("raw_transcript")
            applied = arts.get("applied_output")
            out.append({
                "kind": "job", "id": job_id, "date_iso": captured,
                "date": _local_date(captured, self.tz),
                "time_quality": tq or "unknown",
                "app": app_name or app_bundle,
                "mode": (applied or {}).get("mode") if applied else None,
                "state": state, "state_reason": reason,
                "preview": self._preview(raw, applied),
                "has_audio": bool((arts.get("original_audio") or {})
                                  .get("present")),
            })
        # -- legacy analytics rows (dated, app known) --------------------
        if mode in (None, "legacy"):
            clauses, params = [], []
            if text:
                pat = f"%{_like_escape(text)}%"
                clauses.append("(raw_text LIKE ? ESCAPE '\\' OR cleaned_text"
                               " LIKE ? ESCAPE '\\')")
                params += [pat, pat]
            if app:
                clauses.append("(app_name LIKE ? ESCAPE '\\' OR app_bundle"
                               " LIKE ? ESCAPE '\\')")
                params += [f"%{_like_escape(app)}%"] * 2
            where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            sql = ("SELECT id, captured_at_utc, app_name, app_bundle, kind,"
                   " raw_text, cleaned_text FROM legacy_dictations"
                   f"{where} ORDER BY ts DESC LIMIT ?")
            params.append(limit)
            for (rid, captured, app_name, app_bundle, kind, raw, cleaned) \
                    in conn.execute(sql, params).fetchall():
                out.append({
                    "kind": "legacy_db", "id": f"legacy-db:{rid}",
                    "date_iso": captured, "date": _local_date(captured,
                                                              self.tz),
                    "time_quality": "known", "app": app_name or app_bundle,
                    "mode": "legacy", "state": "imported",
                    "state_reason": None,
                    "preview": self._preview(
                        {"present": True, "text": raw},
                        {"present": True, "text": cleaned}),
                    "has_audio": False,
                })
        # -- legacy log pairs (unknown date → Undated) --------------------
        # They carry no destination app, so any app filter excludes them.
        if mode in (None, "legacy") and not app:
            clauses, params = ["a.stage = 'legacy_log'"], []
            if text:
                clauses.append("a.content_text LIKE ? ESCAPE '\\'")
                params.append(f"%{_like_escape(text)}%")
            # The cleaned child carries the import bookkeeping; its parent
            # is the raw half of the same utterance pair.
            sql = ("SELECT a.artifact_id, a.parent_artifact_id, a.role,"
                   " a.content_text FROM artifacts a"
                   f" WHERE {' AND '.join(clauses)} AND a.role IN (?,?)"
                   " ORDER BY a.rowid LIMIT ?")
            params += ["cleaned_transcript", "raw_transcript", limit * 2]
            pairs: dict = {}
            for (aid, parent, role, content) in conn.execute(
                    sql, params).fetchall():
                key = parent if role == "cleaned_transcript" else aid
                slot = pairs.setdefault(key, {})
                slot[role] = (aid, content)
            for key, slot in pairs.items():
                raw = slot.get("raw_transcript")
                cleaned = slot.get("cleaned_transcript")
                aid = (cleaned or raw)[0]
                out.append({
                    "kind": "legacy_log", "id": aid,
                    "date_iso": None, "date": None,
                    "time_quality": "unknown", "app": None,
                    "mode": "legacy", "state": "imported",
                    "state_reason": None,
                    "preview": self._preview(
                        {"present": raw is not None,
                         "text": raw[1] if raw else None},
                        {"present": cleaned is not None,
                         "text": cleaned[1] if cleaned else None}),
                    "has_audio": False,
                })
        dated_rows = [r for r in out if r["date"]]
        undated = [r for r in out if not r["date"]]
        dated_rows.sort(key=lambda r: (r["date"], str(r["id"])),
                        reverse=True)
        # The limit applies to the merged result, not per section.
        return (dated_rows + undated)[:limit] if limit else \
            dated_rows + undated

    @staticmethod
    def _preview(raw, applied):
        art = applied if applied and applied.get("text") else raw
        if not art or not art.get("present"):
            return None
        text = art["text"] or ""
        return text[:140] + ("…" if len(text) > 140 else "")

    def _job_artifacts(self, conn, job_id):
        """The roles History displays for one job, in one pass."""
        arts = {}
        for (aid, role, stage, purged, content, meta_json, cpath,
             created) in conn.execute(
                "SELECT artifact_id, role, stage, purged, content_text,"
                " meta_json, content_path, created_at_utc FROM artifacts"
                " WHERE job_id=? AND role IN (?,?,?,?,?) ORDER BY rowid",
                (job_id, "raw_transcript", "normalized_text",
                 "applied_output", "original_audio",
                 "cleaned_transcript")).fetchall():
            entry = {"artifact_id": aid, "stage": stage, "purged": bool(purged),
                     "created_at_utc": created}
            if role == "original_audio":
                entry["present"] = not purged and content is None and bool(cpath)
                entry["has_file"] = bool(cpath) and not purged
            else:
                entry["present"] = not purged
                entry["text"] = None if purged else content
            arts.setdefault(role, entry)
            if role == "applied_output" and not purged:
                try:
                    entry["mode"] = json.loads(meta_json or "{}").get(
                        "cleanup_path")
                except ValueError:
                    entry["mode"] = None
        return arts

    def _grouped(self, rows):
        groups: dict = {}
        order = []
        for r in rows:
            label = r["date"] if r["date"] else UNDATED
            if label not in groups:
                groups[label] = []
                order.append(label)
            groups[label].append(r)
        dated = [l for l in order if l != UNDATED]
        dated.sort(reverse=True)
        return {"groups": [{"label": l, "rows": groups[l]}
                           for l in dated + ([UNDATED] if UNDATED in groups
                                             else [])],
                "total": len(rows)}

    # ---- History detail -------------------------------------------------

    def job_detail(self, job_id) -> dict | None:
        """One job's full detail: lineage stages kept distinct (AC01),
        insertion outcome, audio availability with reasons (AC02)."""
        def op(conn):
            row = conn.execute(
                "SELECT job_id, captured_at_utc, time_quality, timezone,"
                " utc_offset_minutes, state, state_reason, attempt,"
                " released_at_utc FROM jobs WHERE job_id=?",
                (job_id,)).fetchone()
            if row is None:
                return None
            detail = dict(zip(
                ("job_id", "captured_at_utc", "time_quality", "timezone",
                 "utc_offset_minutes", "state", "state_reason", "attempt",
                 "released_at_utc"), row))
            detail["kind"] = "job"
            tgt = conn.execute(
                "SELECT app_name, app_bundle FROM job_targets WHERE"
                " job_id=?", (job_id,)).fetchone()
            detail["app"] = (tgt[0] or tgt[1]) if tgt else None
            arts = self._job_artifacts(conn, job_id)
            raw = arts.get("raw_transcript")
            normalized = arts.get("normalized_text")
            applied = arts.get("applied_output") or arts.get(
                "cleaned_transcript")
            audio = arts.get("original_audio")
            detail["lineage"] = [
                {"stage": "source", "label": "Source (raw transcript)",
                 "artifact": raw},
                {"stage": "normalized", "label": "Normalized",
                 "artifact": normalized},
                {"stage": "cleaned", "label": "Cleaned (applied output)",
                 "artifact": applied},
                # Transforms are M11; the slot is honest absence, never a
                # flattened copy of the cleaned text.
                {"stage": "transformed", "label": "Transformed",
                 "artifact": None,
                 "reason": "not_applicable_until_M11"},
            ]
            if audio is None:
                detail["audio"] = {"available": False,
                                   "reason": "no_audio_artifact"}
            elif audio.get("purged"):
                detail["audio"] = {"available": False, "reason": "purged"}
            elif not audio.get("has_file"):
                detail["audio"] = {"available": False,
                                   "reason": "payload_missing"}
            else:
                detail["audio"] = {"available": True,
                                   "artifact_id": audio["artifact_id"]}
            ins = conn.execute(
                "SELECT state, method, reason_code, inserted_chars,"
                " created_at_utc FROM insertions WHERE job_id=? ORDER BY"
                " rowid DESC LIMIT 1", (job_id,)).fetchone()
            detail["insertion"] = (dict(zip(
                ("state", "method", "reason_code", "inserted_chars",
                 "created_at_utc"), ins)) if ins else None)
            return detail
        return self.store.submit(op)

    def legacy_detail(self, artifact_id) -> dict | None:
        """A legacy log pair's detail (raw + cleaned halves)."""
        def op(conn):
            row = conn.execute(
                "SELECT artifact_id, role, content_text, purged,"
                " parent_artifact_id FROM artifacts WHERE artifact_id=?",
                (artifact_id,)).fetchone()
            if row is None:
                return None
            _aid, role, content, purged, parent = row
            other_role = ("raw_transcript"
                          if role == "cleaned_transcript"
                          else "cleaned_transcript")
            other_key = parent if role == "cleaned_transcript" \
                else artifact_id
            other = conn.execute(
                "SELECT content_text, purged FROM artifacts WHERE"
                " artifact_id=? AND role=?", (other_key, other_role)).fetchone()
            cleaned_id = artifact_id if role == "cleaned_transcript" \
                else other_key

            def half(c, p):
                return {"present": bool(c) and not p,
                        "text": None if p else c,
                        "purged": bool(p)}
            raw = (half(content, purged) if role == "raw_transcript"
                   else (half(other[0], other[1]) if other
                         else {"present": False, "text": None,
                               "purged": False}))
            cleaned = (half(content, purged)
                       if role == "cleaned_transcript"
                       else (half(other[0], other[1]) if other
                             else {"present": False, "text": None,
                                   "purged": False}))
            return {"kind": "legacy_log", "id": artifact_id,
                    "time_quality": "unknown", "audio":
                        {"available": False, "reason": "legacy_no_audio"},
                    "insertion": None,
                    "lineage": [
                        {"stage": "source", "label": "Source (raw)",
                         "artifact": raw},
                        {"stage": "cleaned", "label": "Cleaned",
                         "artifact": cleaned},
                    ]}
        return self.store.submit(op)

    # ---- Home -----------------------------------------------------------

    def home_summary(self) -> dict:
        """Content-free Home cards: today's count (local day), totals,
        last dictation. No word/WPM analytics — those are M13's usage_facts;
        counts of jobs are honest store facts. The day boundary is
        computed as a UTC instant and compared in SQL (ISO-Z strings
        sort lexicographically) so the pass stays O(index), not
        O(all rows) in Python."""
        def op(conn):
            local_midnight = dt.datetime.now(self.tz).replace(
                hour=0, minute=0, second=0, microsecond=0)
            boundary = local_midnight.astimezone(
                dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            today_count = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE captured_at_utc >= ?",
                (boundary,)).fetchone()[0]
            total = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE captured_at_utc IS NOT"
                " NULL").fetchone()[0]
            last = conn.execute(
                "SELECT captured_at_utc, state FROM jobs WHERE"
                " captured_at_utc IS NOT NULL ORDER BY captured_at_utc"
                " DESC LIMIT 1").fetchone()
            legacy = conn.execute(
                "SELECT COUNT(*) FROM legacy_dictations").fetchone()[0]
            return {
                "today_count": today_count,
                "total_jobs": total,
                "legacy_rows": legacy,
                "last_dictation": ({"date_iso": last[0], "state": last[1]}
                                   if last else None),
            }
        return self.store.submit(op)
