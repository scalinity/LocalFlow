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
- Lineage is the job's CURRENT attempt: the stage artifacts its latest
  training envelope names (the per-attempt manifest), or — for a job
  without one — the artifacts of its highest recorded attempt. A stage
  missing from that attempt is absent, never borrowed from an earlier
  attempt; a purged stage says purged.
- A transform's output carries its recorded decision (path, reason,
  applied); the final text is the transform output only when it was
  applied, else the cleaned output.
- Records without a usable capture instant (legacy log imports,
  malformed or zone-less timestamps) group under the explicit
  ``Undated`` label and never acquire a date (S21). Dated rows are
  ordered newest first by their actual instant across every source,
  ties broken by source (V2 job, legacy database) then id, and the
  limit applies once to the merged list.
- Local dates use the real local zone (IANA, with its historical DST
  transitions), not the current UTC offset.
- A job removed by delete-everywhere leaves History at once (list,
  filters and detail); its job row survives only as the operational
  record until metadata pruning.
- Purged/expired artifacts report ``purged``; missing audio reports why
  (M09-AC02). Unknown app is ``None``, displayed as unknown.
"""

from __future__ import annotations

import datetime as dt
import json
import zoneinfo

from . import ids

UNDATED = "Undated"

# Cleanup paths that can appear in an applied-output artifact's meta
# (contracts/cleanup.md). The mode filter only accepts these — the value
# is spliced into a JSON meta match, so it comes from a fixed vocabulary.
MODES = ("llm", "llm_partial", "llm_fallback_normalized", "basic", "raw",
         "basic_empty_input", "legacy")

_TEXT_ROLES = ("raw_transcript", "normalized_text", "applied_output",
               "cleaned_transcript")
_LINEAGE_ROLES = ("raw_transcript", "normalized_text", "applied_output",
                  "original_audio", "cleaned_transcript", "transform_output")
_KIND_RANK = {"job": 0, "legacy_db": 1, "legacy_log": 2}
_IN_CHUNK = 500  # bound on bound parameters per IN list


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# The same instant in SQL, for each source's cut under the limit: only
# a value ending in an explicit zone (Z or ±HH:MM, as parse_instant
# requires) names one; anything else sorts after every dated row.
_JOB_INSTANT = ("(CASE WHEN j.captured_at_utc GLOB '*Z' OR"
                " j.captured_at_utc GLOB '*[+-][0-9][0-9]:[0-9][0-9]'"
                " THEN julianday(j.captured_at_utc) END)")


def parse_instant(iso) -> dt.datetime | None:
    """An aware instant from a stored timestamp: the writer's
    ``...sss Z`` form, whole-second ``Z``, or an explicit RFC 3339
    offset (``±HH:MM``). A zone-less or malformed value names no
    instant (None) — never a guessed zone, today or a file time."""
    if not iso or not isinstance(iso, str):
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return dt.datetime.strptime(iso, fmt).replace(
                tzinfo=dt.timezone.utc)
        except ValueError:
            pass
    if not (iso.endswith("Z") or (len(iso) >= 6 and iso[-6] in "+-"
                                  and iso[-3] == ":")):
        return None  # no explicit zone: the SQL cut's rule too
    try:
        t = dt.datetime.fromisoformat(iso)
    except ValueError:
        return None
    return t if t.tzinfo is not None else None


def _local_date(iso, tz) -> str | None:
    t = parse_instant(iso)
    return t.astimezone(tz).strftime("%Y-%m-%d") if t else None


def default_zone():
    """The real local zone with its DST history (the IANA zone the
    system names); a fixed current offset only when no zone name is
    observable."""
    name = ids.local_zone_name()
    if name:
        try:
            return zoneinfo.ZoneInfo(name)
        except (ValueError, zoneinfo.ZoneInfoNotFoundError):
            pass
    return dt.datetime.now().astimezone().tzinfo


def _chunks(seq, n=_IN_CHUNK):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _meta(meta_json) -> dict:
    try:
        out = json.loads(meta_json or "{}")
    except ValueError:
        return {}
    return out if isinstance(out, dict) else {}


def final_text(detail) -> str | None:
    """The text a History detail shows as what was actually inserted:
    the transform output when its recorded decision says applied, else
    the cleaned output — of the CURRENT attempt, as ``job_detail`` /
    ``legacy_detail`` / ``legacy_db_detail`` resolved it. A final stage
    that is gone yields None; an earlier stage is never a substitute.
    History's Copy/Paste Again and the Scratchpad transfer share this
    one rule (M12-AUDIT-14)."""
    if not detail:
        return None
    stages = {s["stage"]: s for s in detail.get("lineage") or []}

    def text(name):
        art = (stages.get(name) or {}).get("artifact")
        return art["text"] if art and art.get("present") \
            and art.get("text") else None
    if detail.get("final_stage") == "transformed":
        return text("transformed")
    return text("cleaned")


class HistoryQueryService:
    """All reads through the store's writer thread; safe to call from any
    thread (the Hub calls from its query thread, never the UI callback)."""

    def __init__(self, store, tz=None):
        self.store = store
        self.tz = tz if tz is not None else default_zone()

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
        # 0 = no limit; SQLite reads a negative LIMIT as unbounded.
        sql_limit = limit if limit > 0 else -1
        # -- V2 jobs ----------------------------------------------------
        # Delete-everywhere removes a job from History immediately (the
        # row itself waits for metadata pruning as an operational record).
        clauses = ["j.job_id NOT IN (SELECT job_id FROM job_deletions)"]
        params = []
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
                           " AND a.job_id IS NOT NULL AND json_valid("
                           "a.meta_json) AND json_extract(a.meta_json,"
                           " '$.cleanup_path') = ?)")
            params.append(mode)
        if mode == "legacy":
            clauses.append("0")
        where = f" WHERE {' AND '.join(clauses)}"
        sql = ("SELECT j.job_id, j.captured_at_utc, j.time_quality, j.state,"
               " j.state_reason, t.app_name, t.app_bundle FROM jobs j LEFT"
               f" JOIN job_targets t ON t.job_id = j.job_id{where}"
               f" ORDER BY {_JOB_INSTANT} IS NULL, {_JOB_INSTANT} DESC,"
               " j.job_id LIMIT ?")
        job_rows = conn.execute(sql, [*params, sql_limit]).fetchall()
        manifests = self._manifests(conn, [r[0] for r in job_rows])
        for (job_id, captured, tq, state, reason, app_name, app_bundle) \
                in job_rows:
            arts, _info = self._job_artifacts(conn, job_id,
                                              manifests.get(job_id))
            raw = arts.get("raw_transcript")
            applied = arts.get("applied_output")
            instant = parse_instant(captured)
            out.append({
                "kind": "job", "id": job_id, "date_iso": captured,
                "date": _local_date(captured, self.tz),
                "_t": instant.timestamp() if instant else None,
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
                   f"{where} ORDER BY ts DESC, CAST(id AS TEXT) LIMIT ?")
            params.append(sql_limit)
            for (rid, captured, app_name, app_bundle, kind, raw, cleaned) \
                    in conn.execute(sql, params).fetchall():
                instant = parse_instant(captured)
                out.append({
                    "kind": "legacy_db", "id": f"legacy-db:{rid}",
                    "date_iso": captured,
                    "date": _local_date(captured, self.tz),
                    "_t": instant.timestamp() if instant else None,
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
        # A pair's identity is its root (raw) artifact whichever half
        # matched the search; both retained halves are hydrated after.
        # Pairs sort after every row above, so only the room left under
        # the limit can ever appear; nothing is fetched beyond it.
        room = limit - len(out) if limit > 0 else None  # None: no limit
        if mode in (None, "legacy") and not app and \
                (room is None or room > 0):
            clauses, params = ["a.stage = 'legacy_log'",
                               "a.role IN (?,?)"], \
                ["cleaned_transcript", "raw_transcript"]
            if text:
                clauses.append("a.content_text LIKE ? ESCAPE '\\'")
                params.append(f"%{_like_escape(text)}%")
            sql = ("SELECT CASE WHEN a.role='cleaned_transcript' AND"
                   " a.parent_artifact_id IS NOT NULL THEN"
                   " a.parent_artifact_id ELSE a.artifact_id END AS root,"
                   " MIN(a.rowid) AS first FROM artifacts a"
                   f" WHERE {' AND '.join(clauses)} GROUP BY root"
                   " ORDER BY first LIMIT ?")
            roots = [root for (root, _first) in conn.execute(
                sql, [*params, room if room is not None else -1])
                .fetchall()]
            halves = self._legacy_halves_many(conn, roots)
            for root in roots:
                raw, cleaned = halves[root]
                out.append({
                    "kind": "legacy_log", "id": root,
                    "date_iso": None, "date": None, "_t": None,
                    "time_quality": "unknown", "app": None,
                    "mode": "legacy", "state": "imported",
                    "state_reason": None,
                    "preview": self._preview(raw, cleaned),
                    "has_audio": False,
                })
        dated = [r for r in out if r["date"] and r["_t"] is not None]
        undated = [r for r in out if not (r["date"] and r["_t"] is not None)]
        for r in undated:
            r["date"] = None
        dated.sort(key=lambda r: (-r["_t"], _KIND_RANK[r["kind"]],
                                  str(r["id"])))
        merged = dated + undated
        # The limit applies once, to the merged result (0 = no limit).
        if limit:
            merged = merged[:limit]
        for r in merged:
            r.pop("_t", None)
        return merged

    @staticmethod
    def _preview(raw, applied):
        art = applied if applied and applied.get("text") else raw
        if not art or not art.get("present"):
            return None
        text = art["text"] or ""
        return text[:140] + ("…" if len(text) > 140 else "")

    # ---- current-attempt lineage -----------------------------------------

    def _manifests(self, conn, job_ids):
        """{job_id: envelope} — each job's latest example's latest
        revision (the per-attempt manifest), fetched in bounded batches."""
        out = {}
        for chunk in _chunks(list(job_ids)):
            marks = ",".join("?" * len(chunk))
            for job_id, env_json in conn.execute(
                    "SELECT e.job_id, r.envelope_json FROM"
                    " training_examples e JOIN training_revisions r ON"
                    " r.revision_id = e.latest_revision_id WHERE"
                    f" e.job_id IN ({marks}) ORDER BY e.rowid",
                    chunk).fetchall():
                try:
                    out[job_id] = json.loads(env_json)
                except ValueError:
                    continue
        return out

    def _job_artifacts(self, conn, job_id, manifest=None):
        """({role: entry}, info) for the job's CURRENT attempt."""
        entries = {}
        order = []
        for (aid, role, stage, purged, content, meta_json, cpath,
             created) in conn.execute(
                "SELECT artifact_id, role, stage, purged, content_text,"
                " meta_json, content_path, created_at_utc FROM artifacts"
                f" WHERE job_id=? AND role IN ({','.join('?' * 6)})"
                " ORDER BY rowid", (job_id, *_LINEAGE_ROLES)).fetchall():
            meta = _meta(meta_json)
            entry = {"artifact_id": aid, "stage": stage,
                     "purged": bool(purged), "created_at_utc": created,
                     "_role": role, "_attempt": meta.get("attempt")}
            if role == "original_audio":
                entry["present"] = not purged and content is None \
                    and bool(cpath)
                entry["has_file"] = bool(cpath) and not purged
            else:
                entry["present"] = not purged
                entry["text"] = None if purged else content
            if role == "applied_output" and not purged:
                entry["mode"] = meta.get("cleanup_path")
            if role == "transform_output":
                entry["_path"] = meta.get("path")
            entries[aid] = entry
            order.append(entry)
        if manifest is not None:
            arts = manifest.get("artifact_ids") or {}
            norm = ((manifest.get("normalization") or {})
                    .get("artifact_ids") or {})
            tf = manifest.get("transform") or {}
            wanted = {"raw_transcript": arts.get("source_text"),
                      "normalized_text": norm.get("normalized_text"),
                      "applied_output": arts.get("applied_output"),
                      "original_audio": arts.get("original_audio"),
                      "transform_output": (tf.get("artifact_ids")
                                           or {}).get("output")}
            chosen = {role: entries[aid] for role, aid in wanted.items()
                      if aid and aid in entries}
            info = {"source": "manifest",
                    "attempt": manifest.get("attempt"),
                    "transform": ({"path": tf.get("path"),
                                   "reason": tf.get("reason"),
                                   "applied": bool(tf.get("applied"))}
                                  if tf.get("path") else None)}
        else:
            tagged = [e["_attempt"] for e in order
                      if isinstance(e["_attempt"], int)]
            current = max(tagged) if tagged else None
            chosen = {}
            seen = {}
            for e in order:
                role = e["_role"]
                # Audio is per job (one capture, reused by a retry).
                if current is not None and role != "original_audio" \
                        and e["_attempt"] != current:
                    continue
                seen[role] = seen.get(role, 0) + 1
                chosen[role] = e  # newest within the chosen attempt
            tf_entry = chosen.get("transform_output")
            info = {"source": "attempt_group" if current is not None
                    else "artifacts", "attempt": current,
                    "ambiguous_attempts": current is None and any(
                        n > 1 for r, n in seen.items()
                        if r != "original_audio"),
                    # History's own transform artifact is written only
                    # for a transform applied before insertion.
                    "transform": ({"path": tf_entry.get("_path")
                                   or "applied", "reason": None,
                                   "applied": True}
                                  if tf_entry is not None else None)}
        for e in chosen.values():
            for k in ("_role", "_attempt", "_path"):
                e.pop(k, None)
        return chosen, info

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
        """One job's full detail: current-attempt lineage stages kept
        distinct (AC01), the transform decision, insertion outcome,
        audio availability with reasons (AC02). None once the job was
        deleted everywhere."""
        def op(conn):
            if conn.execute("SELECT 1 FROM job_deletions WHERE job_id=?",
                            (job_id,)).fetchone():
                return None
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
            manifest = self._manifests(conn, [job_id]).get(job_id)
            arts, info = self._job_artifacts(conn, job_id, manifest)
            raw = arts.get("raw_transcript")
            normalized = arts.get("normalized_text")
            applied = arts.get("applied_output") or arts.get(
                "cleaned_transcript")
            audio = arts.get("original_audio")
            decision = info.get("transform")
            transformed = arts.get("transform_output")
            detail["lineage_attempt"] = info.get("attempt")
            detail["lineage_source"] = info.get("source")
            detail["lineage_ambiguous"] = bool(
                info.get("ambiguous_attempts"))
            applied_tf = bool(decision and decision.get("applied"))
            detail["lineage"] = [
                {"stage": "source", "label": "Source (raw transcript)",
                 "artifact": raw},
                {"stage": "normalized", "label": "Normalized",
                 "artifact": normalized},
                {"stage": "cleaned", "label": "Cleaned (applied output)",
                 "artifact": applied},
                # M11: the transform stage is real — an artifact when a
                # transform ran on this job with its recorded decision,
                # honest absence otherwise (never a flattened copy of
                # the cleaned text).
                {"stage": "transformed", "label": "Transformed",
                 "artifact": transformed, "decision": decision,
                 "reason": None if transformed else (
                     "output_unavailable" if applied_tf
                     else "not_applicable")},
            ]
            # What was actually inserted follows the recorded decision:
            # an applied transform's output — even when it no longer
            # resolves (then there is no final text, never the cleaned
            # text in its place) — else the cleaned output.
            detail["final_stage"] = "transformed" if applied_tf \
                else "cleaned"
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

    @staticmethod
    def _half(content, purged):
        return {"present": bool(content) and not purged,
                "text": None if purged else content,
                "purged": bool(purged)}

    def _legacy_halves(self, conn, root):
        """(raw, cleaned) halves of the legacy pair rooted at ``root``
        (a raw artifact, or a parentless cleaned one). An absent half is
        None — never synthesized."""
        return self._legacy_halves_many(conn, [root])[root]

    def _legacy_halves_many(self, conn, roots):
        """{root: (raw, cleaned)} for a page of pair roots in a fixed
        number of statements: parent_artifact_id is not indexed, so a
        per-root child lookup would scan the artifacts table once per
        row (the 50k-store browse cost)."""
        rows = {}
        for chunk in _chunks(roots):
            marks = ",".join("?" * len(chunk))
            for aid, role, content, purged, parent in conn.execute(
                    "SELECT artifact_id, role, content_text, purged,"
                    " parent_artifact_id FROM artifacts WHERE artifact_id"
                    f" IN ({marks})", chunk).fetchall():
                rows[aid] = (role, content, purged, parent)
        raw_roots = [a for a, v in rows.items()
                     if v[0] != "cleaned_transcript"]
        parents = [v[3] for v in rows.values()
                   if v[0] == "cleaned_transcript" and v[3]]
        children, parent_raws = {}, {}
        for chunk in _chunks(raw_roots):
            marks = ",".join("?" * len(chunk))
            for parent, content, purged in conn.execute(
                    "SELECT parent_artifact_id, content_text, purged FROM"
                    " artifacts WHERE role='cleaned_transcript' AND"
                    f" parent_artifact_id IN ({marks}) ORDER BY rowid",
                    chunk).fetchall():
                children.setdefault(parent, (content, purged))
        for chunk in _chunks(parents):
            marks = ",".join("?" * len(chunk))
            for aid, content, purged in conn.execute(
                    "SELECT artifact_id, content_text, purged FROM artifacts"
                    f" WHERE role='raw_transcript' AND artifact_id IN"
                    f" ({marks})", chunk).fetchall():
                parent_raws[aid] = (content, purged)
        out = {}
        for root in roots:
            row = rows.get(root)
            if row is None:
                out[root] = (None, None)
                continue
            role, content, purged, parent = row
            if role == "cleaned_transcript":
                praw = parent_raws.get(parent) if parent else None
                out[root] = ((self._half(*praw) if praw else None),
                             self._half(content, purged))
            else:
                child = children.get(root)
                out[root] = (self._half(content, purged),
                             self._half(*child) if child else None)
        return out

    def legacy_detail(self, artifact_id) -> dict | None:
        """A legacy log pair's detail (raw + cleaned halves). Accepts the
        pair's root id (what History lists) or either half's id."""
        def op(conn):
            row = conn.execute(
                "SELECT role, parent_artifact_id FROM artifacts WHERE"
                " artifact_id=?", (artifact_id,)).fetchone()
            if row is None:
                return None
            role, parent = row
            root = parent if role == "cleaned_transcript" and parent \
                else artifact_id
            raw, cleaned = self._legacy_halves(conn, root)
            absent = {"present": False, "text": None, "purged": False}
            return {"kind": "legacy_log", "id": root,
                    "time_quality": "unknown", "audio":
                        {"available": False, "reason": "legacy_no_audio"},
                    "insertion": None,
                    "lineage": [
                        {"stage": "source", "label": "Source (raw)",
                         "artifact": raw or absent},
                        {"stage": "cleaned", "label": "Cleaned",
                         "artifact": cleaned or absent},
                    ]}
        return self.store.submit(op)

    def legacy_db_detail(self, row_id) -> dict | None:
        """An imported legacy database row's detail: its retained raw and
        cleaned text, known date and app — jobless and without audio."""
        try:
            rid = int(str(row_id).split(":", 1)[1])
        except (IndexError, ValueError):
            return None

        def op(conn):
            row = conn.execute(
                "SELECT id, captured_at_utc, app_name, app_bundle, raw_text,"
                " cleaned_text FROM legacy_dictations WHERE id=?",
                (rid,)).fetchone()
            if row is None:
                return None
            _id, captured, app_name, app_bundle, raw, cleaned = row
            return {"kind": "legacy_db", "id": f"legacy-db:{rid}",
                    "captured_at_utc": captured, "time_quality": "known",
                    "app": app_name or app_bundle,
                    "audio": {"available": False,
                              "reason": "legacy_no_audio"},
                    "insertion": None,
                    "lineage": [
                        {"stage": "source", "label": "Source (raw)",
                         "artifact": self._half(raw, False)},
                        {"stage": "cleaned", "label": "Cleaned",
                         "artifact": self._half(cleaned, False)},
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
