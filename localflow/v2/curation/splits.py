"""Dataset families, versioned split assignment and contamination
checks (V2 M14, Spec S29.11, contracts/dataset_exports.md).

Families own splits: parent audio, crops, retries of one recording and
near-duplicate variants share ``family_id`` (minted per recording by
the M02 pipeline — retries keep the job and its family), and
assignment maps FAMILY → partition, then stamps every member example.
Partitions: ``unassigned``, ``train``, ``validation``, ``frozen_test``.
Tags (``regression``, ``hard_example``, ``short_command``,
``acoustic_challenge``) live in their own table — a tag NEVER changes
partition eligibility (a tagged frozen example stays frozen).

Versioning is append-only: each ``assign``/``mark_exposed`` call mints
a new ``assignment_version``; older versions keep their rows untouched
— an old manifest is never rewritten to claim an untouched test.
Exposure: an inspected held-out family used for tuning moves to
development status (train + exposed + reason) in a NEW version, and
the blind holdout is replenished only with new families.

Assignment policy: deterministic family-level hash of (seed,
family_id) into 80/10/10 train/validation/frozen_test — the spec's
adjustable experiment default. Below the minimum family count
(``MIN_FAMILIES``) everything stays ``unassigned`` with the honest
reason: a split of a handful of families is noise, not a split.

Contamination checks (readiness input): families spanning partitions
within one version (structurally impossible; still verified), exposed
families still marked frozen, and context assembled after capture
(a hint-set artifact written after its example's revision-1 timestamp
would mean an answer was retroactively inserted into "original hints"
— S29.11).
"""

from __future__ import annotations

import hashlib
import json

from .. import ids
from ..store import LIVE_EXAMPLE_STATES, Store

PARTITIONS = ("unassigned", "train", "validation", "frozen_test")
TAGS = ("regression", "hard_example", "short_command",
        "acoustic_challenge")

DEFAULT_POLICY = "family-hash-80-10-10"
DEFAULT_SEED = "localflow-m14-splits-v1"
MIN_FAMILIES = 10

_LIVE_STATES = LIVE_EXAMPLE_STATES


def _family_bucket(seed: str, family_id: str) -> str:
    digest = hashlib.sha256(f"{seed}:{family_id}".encode()).digest()
    draw = int.from_bytes(digest[:8], "big") / float(2 ** 64)
    if draw < 0.8:
        return "train"
    if draw < 0.9:
        return "validation"
    return "frozen_test"


class SplitService:
    """Versioned family assignment over the single-writer store."""

    def __init__(self, store: Store, emit=None):
        self.store = store
        self.emit = emit or (lambda *a, **k: None)

    # ---- live families ------------------------------------------------------

    def _live_examples(self, conn):
        latest = conn.execute(
            "SELECT example_id, envelope_json FROM training_revisions"
            " WHERE rowid IN (SELECT MAX(rowid) FROM training_revisions"
            " GROUP BY example_id)").fetchall()
        states = dict(conn.execute(
            "SELECT example_id, state FROM training_examples").fetchall())
        out = []
        for ex_id, payload in latest:
            if states.get(ex_id) not in _LIVE_STATES:
                continue
            env = json.loads(payload)
            out.append((ex_id, env.get("family_id") or "", env))
        return out

    # ---- assignment ----------------------------------------------------------

    def assign(self, *, policy: str = DEFAULT_POLICY,
               seed: str = DEFAULT_SEED) -> dict:
        """Mint a NEW assignment version over the current live
        families. Reassigning with the same policy+seed reproduces the
        same family→partition map (deterministic); the version row
        still advances because membership may have grown."""
        def op(conn):
            examples = self._live_examples(conn)
            families = sorted({fam for _ex, fam, _env in examples
                               if fam})
            version = 1 + (conn.execute(
                "SELECT COALESCE(MAX(assignment_version), 0) FROM"
                " split_assignments").fetchone()[0])
            now = ids.now_utc_iso()
            conn.execute(
                "INSERT INTO split_assignments(assignment_version,"
                " policy, seed, family_count, created_at_utc)"
                " VALUES(?,?,?,?,?)",
                (version, policy, seed, len(families), now))
            partitions = {}
            if len(families) >= MIN_FAMILIES:
                partitions = {fam: _family_bucket(seed, fam)
                              for fam in families}
            assigned = {"train": 0, "validation": 0, "frozen_test": 0,
                        "unassigned": 0}
            exposed_prev = self._exposure_before(conn, version)
            for ex_id, fam, _env in examples:
                partition = partitions.get(fam, "unassigned")
                exposed = 1 if fam in exposed_prev else 0
                if exposed and partition != "unassigned":
                    # Exposure is forward-only: the deterministic hash
                    # would put a once-frozen family straight back into
                    # the blind holdout; an exposed family stays in
                    # development (S29.11).
                    partition = "train"
                conn.execute(
                    "INSERT INTO training_memberships(example_id,"
                    " family_id, assignment_version, partition, exposed,"
                    " exposed_reason, created_at_utc)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (ex_id, fam, version, partition, exposed,
                     exposed_prev.get(fam), now))
                assigned[partition] += 1
            reason = None if partitions else (
                f"insufficient_families:{len(families)}<{MIN_FAMILIES}")
            return {"assignment_version": version, "policy": policy,
                    "seed": seed, "families": len(families),
                    "examples": len(examples), "assigned": assigned,
                    "unassigned_reason": reason}
        out = self.store.submit(op)
        self.emit("splits.assigned", level="INFO",
                  reason_code=out["policy"],
                  detail=f"v{out['assignment_version']}"
                         f" families={out['families']}")
        return out

    def _exposure_before(self, conn, version) -> dict:
        """Every family exposed in ANY earlier version (latest reason
        wins). Exposure is permanent: a family with no live members in
        one version must not lose its flag and hash back into the blind
        holdout when members return."""
        rows = conn.execute(
            "SELECT family_id, exposed_reason FROM training_memberships"
            " WHERE assignment_version < ? AND exposed=1 ORDER BY"
            " assignment_version", (version,)).fetchall()
        return {fam: reason for fam, reason in rows}

    # ---- exposure -------------------------------------------------------------

    def mark_exposed(self, family_ids, reason: str) -> dict:
        """An inspected held-out family used for tuning: it leaves the
        blind holdout in a NEW assignment version (partition 'train',
        exposed=1, the reason recorded) and its examples carry the
        'regression' tag. The previous version's rows are untouched —
        old manifests keep describing what they actually were."""
        families = sorted(set(family_ids))
        if not families:
            raise ValueError("family_ids_required")

        def op(conn):
            prev = conn.execute(
                "SELECT COALESCE(MAX(assignment_version), 0) FROM"
                " split_assignments").fetchone()[0]
            if not prev:
                return {"refused": "no_assignment_exists"}
            # Carry the previous version's map forward, then override
            # the exposed families.
            prev_rows = conn.execute(
                "SELECT example_id, family_id, partition, exposed,"
                " exposed_reason FROM training_memberships WHERE"
                " assignment_version=?", (prev,)).fetchall()
            unknown = set(families) - {r[1] for r in prev_rows}
            if unknown:
                return {"refused": f"unknown_family:{len(unknown)} not"
                                   f" in assignment v{prev}"}
            policy_row = conn.execute(
                "SELECT policy, seed FROM split_assignments WHERE"
                " assignment_version=?", (prev,)).fetchone()
            version = 1 + prev
            now = ids.now_utc_iso()
            conn.execute(
                "INSERT INTO split_assignments(assignment_version,"
                " policy, seed, family_count, created_at_utc)"
                " VALUES(?,?,?,?,?)",
                (version, policy_row[0], policy_row[1],
                 len({r[1] for r in prev_rows}), now))
            moved = 0
            for ex_id, fam, partition, exposed, prev_reason in prev_rows:
                if fam in families:
                    conn.execute(
                        "INSERT INTO training_memberships(example_id,"
                        " family_id, assignment_version, partition,"
                        " exposed, exposed_reason, created_at_utc)"
                        " VALUES(?,?,?,?,?,?,?)",
                        (ex_id, fam, version, "train", 1, reason, now))
                    conn.execute(
                        "INSERT OR IGNORE INTO example_tags(example_id,"
                        " tag, created_at_utc) VALUES(?,?,?)",
                        (ex_id, "regression", now))
                    moved += 1
                else:
                    conn.execute(
                        "INSERT INTO training_memberships(example_id,"
                        " family_id, assignment_version, partition,"
                        " exposed, exposed_reason, created_at_utc)"
                        " VALUES(?,?,?,?,?,?,?)",
                        (ex_id, fam, version, partition, exposed,
                         prev_reason, now))
            return {"assignment_version": version,
                    "families_exposed": len(families),
                    "examples_moved": moved}
        out = self.store.submit(op)
        if out.get("refused"):
            # Raised after the op: an in-op raise surfaces wrapped as a
            # RuntimeError (contracts/store.md).
            raise ValueError(out["refused"])
        self.emit("splits.family_exposed", level="INFO",
                  reason_code=reason,
                  detail=f"families={len(families)}")
        return out

    # ---- reads -----------------------------------------------------------------

    def _current_version_in(self, conn) -> int:
        """Current version INSIDE a writer op (a nested submit here
        would deadlock the writer — contracts/store.md)."""
        return conn.execute(
            "SELECT COALESCE(MAX(assignment_version), 0) FROM"
            " split_assignments").fetchone()[0]

    def current_version(self) -> int:
        return self.store.submit(self._current_version_in) or 0

    def membership(self, example_id: str,
                   version: int | None = None) -> dict | None:
        def op(conn):
            v = version or self._current_version_in(conn)
            if not v:
                return None
            row = conn.execute(
                "SELECT family_id, partition, exposed, exposed_reason"
                " FROM training_memberships WHERE example_id=? AND"
                " assignment_version=?", (example_id, v)).fetchone()
            tags = [r[0] for r in conn.execute(
                "SELECT tag FROM example_tags WHERE example_id=?",
                (example_id,)).fetchall()]
            if row is None:
                return {"example_id": example_id, "assignment_version": v,
                        "family_id": None, "partition": "unassigned",
                        "exposed": False, "exposed_reason": None,
                        "tags": tags}
            return {"example_id": example_id, "assignment_version": v,
                    "family_id": row[0], "partition": row[1],
                    "exposed": bool(row[2]), "exposed_reason": row[3],
                    "tags": tags}
        return self.store.submit(op)

    def summary(self) -> dict:
        def op(conn):
            v = self._current_version_in(conn)
            if not v:
                return {"assignment_version": None,
                        "reason": "no_assignment_yet"}
            row = conn.execute(
                "SELECT policy, seed, family_count, created_at_utc FROM"
                " split_assignments WHERE assignment_version=?",
                (v,)).fetchone()
            by_partition = {}
            for part, n in conn.execute(
                    "SELECT partition, COUNT(*) FROM"
                    " training_memberships WHERE assignment_version=?"
                    " GROUP BY partition", (v,)).fetchall():
                by_partition[part] = n
            exposed = conn.execute(
                "SELECT COUNT(DISTINCT family_id) FROM"
                " training_memberships WHERE assignment_version=? AND"
                " exposed=1", (v,)).fetchone()[0]
            tags = {}
            for tag, n in conn.execute(
                    "SELECT tag, COUNT(*) FROM example_tags GROUP BY tag"
            ).fetchall():
                tags[tag] = n
            return {"assignment_version": v, "policy": row[0],
                    "seed": row[1], "families": row[2],
                    "created_at_utc": row[3],
                    "examples_by_partition": by_partition,
                    "exposed_families": exposed, "tags": tags}
        return self.store.submit(op)

    def family_report(self, version: int | None = None,
                      limit: int = 100) -> list[dict]:
        """Families with their partition and member count (the Splits
        screen's table)."""
        def op(conn):
            v = version or self._current_version_in(conn)
            if not v:
                return []
            rows = conn.execute(
                "SELECT family_id, partition, COUNT(*), MAX(exposed)"
                " FROM training_memberships WHERE assignment_version=?"
                " GROUP BY family_id, partition ORDER BY family_id"
                " LIMIT ?", (v, limit)).fetchall()
            return [{"family_id": r[0], "partition": r[1],
                     "examples": r[2], "exposed": bool(r[3])}
                    for r in rows]
        return self.store.submit(op)

    # ---- tags -----------------------------------------------------------------

    def set_tag(self, example_id: str, tag: str, on: bool = True) -> str:
        if tag not in TAGS:
            raise ValueError(f"unknown tag {tag!r}")

        def op(conn):
            now = ids.now_utc_iso()
            if on:
                conn.execute(
                    "INSERT OR IGNORE INTO example_tags(example_id, tag,"
                    " created_at_utc) VALUES(?,?,?)",
                    (example_id, tag, now))
            else:
                conn.execute(
                    "DELETE FROM example_tags WHERE example_id=? AND"
                    " tag=?", (example_id, tag))
            return tag
        return self.store.submit(op)

    # ---- contamination (E19.4 / M14-AC08) --------------------------------------

    def contamination(self) -> dict:
        def op(conn):
            v = self._current_version_in(conn)
            if not v:
                return {"checked": False,
                        "reason": "no_assignment_yet"}
            # (a) a family spanning partitions within one version —
            # structurally impossible (assignment is family-keyed);
            # verified anyway so a future writer bug surfaces here.
            spanning = conn.execute(
                "SELECT COUNT(*) FROM (SELECT family_id FROM"
                " training_memberships WHERE assignment_version=?"
                " GROUP BY family_id HAVING COUNT(DISTINCT partition) > 1)"
                " ", (v,)).fetchone()[0]
            # (b) exposed families still marked frozen.
            exposed_frozen = conn.execute(
                "SELECT COUNT(DISTINCT family_id) FROM"
                " training_memberships WHERE assignment_version=? AND"
                " exposed=1 AND partition='frozen_test'",
                (v,)).fetchone()[0]
            # (c) context assembled after capture: a hint-set artifact
            # created after the example's FIRST revision (its capture)
            # and referenced by ANY later revision means an answer was
            # retroactively inserted into "original hints" (S29.11).
            # Hints are frozen pre-decode by construction — the check
            # verifies the timestamps, it does not assume.
            late_hints = 0
            checked_hints = 0
            first_rev = {}
            for ex_id, ts in conn.execute(
                    "SELECT example_id, MIN(created_at_utc) FROM"
                    " training_revisions GROUP BY example_id"
            ).fetchall():
                first_rev[ex_id] = ts
            for ex_id, payload in conn.execute(
                    "SELECT example_id, envelope_json FROM"
                    " training_revisions").fetchall():
                env = json.loads(payload)
                hints = (env.get("context") or {}).get(
                    "artifact_ids", {}).get("hint_set")
                if not hints or ex_id not in first_rev:
                    continue
                checked_hints += 1
                art = conn.execute(
                    "SELECT created_at_utc FROM artifacts WHERE"
                    " artifact_id=?", (hints,)).fetchone()
                if art and first_rev[ex_id] and art[0] > first_rev[ex_id]:
                    late_hints += 1
            frozen = conn.execute(
                "SELECT COUNT(DISTINCT family_id) FROM"
                " training_memberships WHERE assignment_version=? AND"
                " partition='frozen_test'", (v,)).fetchone()[0]
            return {
                "checked": True,
                "assignment_version": v,
                "families_spanning_partitions": spanning,
                "exposed_frozen_families": exposed_frozen,
                "frozen_families": frozen,
                "hint_sets_checked": checked_hints,
                "hint_sets_after_capture": late_hints,
                "definition": "families spanning partitions within one"
                              " version, exposed families still frozen,"
                              " and hint artifacts written after their"
                              " example's first revision (S29.11)",
            }
        return self.store.submit(op)
