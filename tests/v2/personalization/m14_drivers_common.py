"""The M14 corpus driver protocol (shared by every m14_drivers_*.py).

A driver binds one frozen corpus entry (case ``LF-M14-Cnnn``, stateful
probe ``LF-M14-Snnn`` or metamorphic relation ``LF-M14-MRnnn``) to the
current production APIs, builds its synthetic world through
``m14_world``, applies exactly the entry's delta, runs the named
operation and grades the entry's own predicate with an INDEPENDENT
oracle — literal values, raw rows, file bytes or counts the driver
established itself, never the production function under test.

Statuses:

- ``PASS`` — the predicate held and the positive companion (a same-shape
  eligible control) behaved as expected;
- ``FAIL`` — the predicate did not hold (a product defect or a driver
  bug — the runner records the note; adjudication decides which);
- ``INVALID`` — the seam or positive companion was never reached (a
  probe whose barrier never fired, an empty control) — never a pass;
- ``NOT_APPLICABLE`` — only with the adopted decision id that makes the
  entry inapplicable (``decision=``); never a pass;
- ``NATIVE`` / ``BENCH`` — graded from the native / benchmark record
  supplied to the runner (``NATIVE`` / ``BENCH`` dicts below);
- ``ERROR`` — the runner records any exception (a driver that could not
  reach the product), never the defect it failed to reach.

``grading`` says how a PASS was earned: ``semantic`` (observed behavior
met the authored expectation), ``decision`` (graded under the named
m14-policy-r1 decision), ``native`` / ``benchmark`` (from the supplied
record), ``structural`` (the seam cannot exist in production — the
witness records why).
"""

from __future__ import annotations

import json

DRIVERS: dict = {}     # case id -> fn(entry) -> result
PROBES: dict = {}      # stateful probe id -> fn(entry) -> result
RELATIONS: dict = {}   # metamorphic relation id -> fn(entry) -> result

# Records the runner loads for native/benchmark-graded entries.
NATIVE: dict = {}
BENCH: dict = {}

DECISIONS_VERSION = "m14-policy-r1"


def result(status, observed=None, *, witness=None, grading="semantic",
           decision=None, note=None, reached=None):
    return {"status": status, "observed": observed, "witness": witness,
            "grading": grading, "decision": decision, "note": note,
            "reached": reached}


def check(conds: dict, observed=None, **kw):
    """PASS when every named semantic condition holds; the failed ones
    are named in the note."""
    failed = [k for k, ok in conds.items() if not ok]
    note = kw.pop("note", None)
    return result("FAIL" if failed else "PASS", observed,
                  note=("failed: " + ", ".join(failed)) if failed
                  else note, **kw)


def invalid(why, observed=None, **kw):
    return result("INVALID", observed, note=why, **kw)


def not_applicable(decision, why, observed=None):
    return result("NOT_APPLICABLE", observed, grading="decision",
                  decision=f"{DECISIONS_VERSION}:{decision}", note=why)


def drives(*ids):
    """Register a driver for cases, probes or relations by id prefix."""
    def deco(fn):
        for i in ids:
            reg = PROBES if "-S" in i else RELATIONS if "-MR" in i \
                else DRIVERS
            if i in reg:
                raise KeyError(f"{i} bound twice")
            reg[i] = fn
        return fn
    return deco


def dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, default=str)
