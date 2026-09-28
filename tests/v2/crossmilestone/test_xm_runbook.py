"""GATE-G03 — the verification runbook's DOM, ids and browser-state
contract, read from docs/v2/VERIFICATION.html itself (cross-milestone
remediation of 340c566; Audit C TEST-GAP-03).

Static: it enumerates the real check articles (never the maintainer
comment's template, never a raw token count), their ids, milestones,
instruction revisions and code stamps, and the page script's storage
namespace and stale-revision rule. It says nothing about any person's
saved statuses: those live only in that person's browser.

Run:
  .venv/bin/python tests/v2/crossmilestone/test_xm_runbook.py [--json OUT]
"""

from __future__ import annotations

import html.parser
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[3]
PAGE = ROOT / "docs" / "v2" / "VERIFICATION.html"
TAGS = {"terminal", "native", "model", "human", "hardware", "privacy"}


class _Checks(html.parser.HTMLParser):
    """Every <article class="check ..."> element (comments are skipped by
    the parser), with its enclosing milestone section."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.section = None
        self.sections = []
        self.checks = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if tag == "section" and "milestone" in classes:
            self.section = a.get("id")
            self.sections.append(self.section)
        if tag == "article" and "check" in classes:
            self.checks.append({**a, "_section": self.section})


def census():
    text = PAGE.read_text(encoding="utf-8")
    p = _Checks()
    p.feed(text)
    by_ms = {}
    for c in p.checks:
        by_ms.setdefault(c.get("data-milestone"), []).append(c["id"])
    key = re.search(r'const KEY = "([^"]+)"', text)
    return {"page": "docs/v2/VERIFICATION.html", "checks": p.checks,
            "sections": p.sections, "by_milestone": by_ms,
            "storage_key": key.group(1) if key else None,
            "stale_rule": bool(re.search(
                r"rec\.rev !== check\.dataset\.rev", text)),
            "text": text}


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def g03_ids_well_formed_unique_and_in_their_section():
    c = census()
    ids = [x.get("id") for x in c["checks"]]
    assert all(ids), "a check article without an id"
    dup = sorted({i for i in ids if ids.count(i) > 1})
    assert not dup, f"duplicate check ids: {dup}"
    for x in c["checks"]:
        m = re.fullmatch(r"(M\d\d)-V(\d{3})", x["id"])
        assert m, f"malformed id {x['id']}"
        assert x.get("data-milestone") == m.group(1) == x["_section"], x
        assert re.fullmatch(rf"{m.group(1)}-r\d+", x.get("data-rev") or ""), x
        assert re.fullmatch(r"[0-9a-f]{7,40}", x.get("data-code") or ""), x
        tags = set((x.get("data-tags") or "").split())
        assert tags and tags <= TAGS, (x["id"], tags)


@case
def g03_numbering_is_stable_per_milestone():
    """ids run V001.. without reuse; a gap is allowed only as a retired
    number (never renumbered), so numbers are strictly increasing."""
    c = census()
    for ms, ids in c["by_milestone"].items():
        nums = [int(i[-3:]) for i in ids]
        assert nums == sorted(nums) and len(set(nums)) == len(nums), \
            (ms, nums)
        assert nums[0] == 1, (ms, nums[:3])


@case
def g03_storage_namespace_and_stale_rule():
    c = census()
    assert c["storage_key"] == "localflow.v2.verification/state@1", \
        c["storage_key"]
    assert c["stale_rule"], ("the page no longer treats a result recorded"
                            " against another instruction revision as stale")


@case
def g03_every_milestone_has_a_section():
    c = census()
    want = [f"M{n:02d}" for n in range(1, 17)]
    missing = [m for m in want[:14] if m not in c["sections"]]
    assert not missing, missing


def main(argv):
    out = None
    if "--json" in argv:
        out = argv[argv.index("--json") + 1]
    results = []
    for fn in CASES:
        try:
            fn()
            status, detail = "PASS", None
        except AssertionError as e:
            status, detail = "FAIL", str(e)[:400]
        results.append({"case": fn.__name__, "status": status,
                        "detail": detail})
        print(f"{status:5}  {fn.__name__}"
              + (f"  — {detail[:160]}" if detail else ""))
    c = census()
    record = {
        "kind": "xm_runbook_census",
        "page": c["page"],
        "total_checks": len(c["checks"]),
        "per_milestone": {m: len(v) for m, v in sorted(
            c["by_milestone"].items())},
        "revisions": {x["id"]: x.get("data-rev") for x in c["checks"]},
        "code_stamps": sorted({x.get("data-code") for x in c["checks"]}),
        "sections": c["sections"],
        "storage_key": c["storage_key"],
        "stale_rule_present": c["stale_rule"],
        "browser_state": "not read: statuses live only in the owner's"
                         " browser (localStorage), never inferred here",
        "results": results}
    print(json.dumps({k: record[k] for k in ("total_checks",
                                             "per_milestone")}))
    if out:
        pathlib.Path(out).write_text(json.dumps(record, indent=1))
    return 0 if all(r["status"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
