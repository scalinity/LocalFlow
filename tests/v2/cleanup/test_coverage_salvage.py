"""A cleanup candidate whose ONLY failure is a few deleted source words is
repaired by putting those exact words back, then validated again in full.

One unapproved deletion ("you know") used to send the whole window back to
the raw transcript, discarding every legitimate edit with it. Candidates
that also add words, change numbers, drop negations or lose more than a few
words are still rejected whole.

Run: .venv/bin/python tests/v2/cleanup/test_coverage_salvage.py
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup import CleanupEngine  # noqa: E402
from localflow.v2.cleanup.validation import (  # noqa: E402
    restore_missing_words, validate)

SOURCE = ("okay so we will ship it you know on friday after the review "
          "and then we will write the notes for the team")
DROPS_FILLER = ("Okay, so we will ship it on Friday after the review, and "
                "then we will write the notes for the team.")


def words(text):
    return re.findall(r"[a-z0-9']+", text.lower())


def engine_for(proposal):
    def gen(prompt, max_tokens):
        text = "NONE" if "Find the self-corrections" in prompt else proposal
        return {"text": text, "output_tokens": 8, "limit_hit": False,
                "prompt": prompt}
    return CleanupEngine(gen, model_id="fake")


def decision_of(res):
    return [o for o in res.observations
            if o.get("kind") == "cleanup_decision"][-1]


def test_restore_puts_the_dropped_words_back_in_place():
    assert validate(SOURCE, DROPS_FILLER).accepted is False
    restored, count = restore_missing_words(SOURCE, DROPS_FILLER)
    assert count == 2
    assert "ship it you know on Friday" in restored, restored
    assert validate(SOURCE, restored).accepted
    # nothing new: every word of the repaired text is a source word
    assert not (set(words(restored)) - set(words(SOURCE)))


def test_nothing_to_restore_returns_none():
    assert restore_missing_words(SOURCE, SOURCE) is None


def test_engine_keeps_the_good_edits_when_only_coverage_failed():
    res = engine_for(DROPS_FILLER).clean(SOURCE)
    assert res.path == "llm", (res.path, res.fallback_reason)
    assert "you know" in res.text and "Friday" in res.text, res.text
    d = decision_of(res)
    assert d["accepted"] is True and d["salvaged_words"] == 2, d


def test_added_word_is_still_rejected_whole():
    proposal = DROPS_FILLER.replace("will ship", "will really ship")
    res = engine_for(proposal).clean(SOURCE)
    assert res.path == "llm_fallback_normalized", res.path
    assert res.text == SOURCE


def test_losing_many_words_is_still_rejected_whole():
    proposal = "Okay, so we will ship it on Friday."
    res = engine_for(proposal).clean(SOURCE)
    assert res.path == "llm_fallback_normalized", res.path
    assert res.text == SOURCE


if __name__ == "__main__":
    tests = (test_restore_puts_the_dropped_words_back_in_place,
             test_nothing_to_restore_returns_none,
             test_engine_keeps_the_good_edits_when_only_coverage_failed,
             test_added_word_is_still_rejected_whole,
             test_losing_many_words_is_still_rejected_whole)
    for test in tests:
        test()
        print("ok ", test.__name__)
    print(f"{len(tests)}/{len(tests)} coverage salvage tests passed")
