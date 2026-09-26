"""M05 remediation — regressions from the independent review round.

The first-pass repair (a164456) was frozen and reviewed by a separate,
read-only reviewer in its own worktree; every finding it reported was
re-run on a164456 before any fix. Each test here fails on a164456 and
passes on the final code (per-test records under
docs/v2/acceptance/M05/remediation/). ``R*`` tests come from the
reviewer; ``A*`` tests are defects the author found while the review ran.

Pure-Python tests run directly; the panel test uses the declared
non-native shims (tests/v2/lifecycle/native_shims.py) — portable
orchestration evidence, never native AppKit evidence.

Run: .venv/bin/python tests/v2/vocabulary/test_m05_review_round.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from m05_helpers import (  # noqa: E402
    TempStore,
    V,
    panel,
)


# ---------------------------------------------------------------------------
# A1 — the panel tells the user how selection actually works
# ---------------------------------------------------------------------------

def test_A1_panel_listing_describes_the_real_selection_method():
    # The listing said "click a line to select", but the listing is a
    # read-only text field: selection is the entry's line number typed
    # into Test phrase (a stable entry id from then on, AUDIT-08).
    with TempStore() as t:
        t.vs.add_entry("Parakeet", [], approved=True)
        ctl = panel(t.vs)
        header = ctl.listing.v.splitlines()[0]
        ctl.phrase.v = "1"
        ctl.runSandbox_(None)
        selected = ctl.sandbox.v
    assert "click a line" not in header, header
    assert "line number" in header and "Test" in header, header
    assert selected.startswith("selected: Parakeet"), selected
    print("ok  A1 panel listing names the real selection method (line"
          " number in Test phrase)")


# ---------------------------------------------------------------------------
# A2 — a disposition never contradicts itself
# ---------------------------------------------------------------------------

def _hint_set(n=2):
    ents = [V.VocabularyEntry(entry_id=f"E{i}", canonical=f"Term{i}",
                              approved=True, verification="explicit")
            for i in range(n)]
    return V.RelevantVocabularySelector().select(V.VocabularySnapshot(ents))


def test_A2_qualified_disposition_is_not_ignored_with_a_reason():
    from localflow.v2 import capabilities as caps
    hs = _hint_set()
    unq = caps.hint_disposition(None, hs)
    assert unq["ignored"] is True and unq["offered_terms"] == 2
    assert unq["ignored_reason"] == "disabled_until_qualified"
    assert unq["accepted_terms"] == 0
    manifest = caps.asr_capability_manifest(
        "qualified-adapter", model_revision="synthetic-rev",
        runtime={"runtime": "synthetic"})
    manifest["capabilities"]["contextual_biasing"] = {
        "supported": True, "reason": "synthetic_test",
        "evidence": "synthetic qualification record",
        "qualified_identity": {
            "adapter": manifest["adapter"],
            "model_id": "qualified-adapter",
            "model_revision": "synthetic-rev",
            "runtime": {"runtime": "synthetic"}}}
    assert caps.biasing_qualified(manifest)
    q = caps.hint_disposition(manifest, hs)
    assert q["offered_terms"] == 2 and q["ignored"] is False, q
    # Not ignored → no ignored reason; acceptance is the adapter's to
    # report after decoding, never a fabricated zero.
    assert q["ignored_reason"] is None, q
    assert q["accepted_terms"] is None, q
    none = caps.hint_disposition(manifest, None)
    assert none["offered_terms"] == 0 and none["ignored"] is False
    assert none["ignored_reason"] is None
    print("ok  A2 hint disposition: unqualified → ignored"
          " (disabled_until_qualified); qualified → not ignored, no reason,"
          " acceptance not fabricated")


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}"[:700])
    import os
    sys.stdout.flush()
    if failed:
        print(f"{failed} of {len(tests)} M05 review-round tests FAILED")
        os._exit(1)
    print(f"all {len(tests)} M05 review-round tests passed")
    os._exit(0)


if __name__ == "__main__":
    main()
