"""Coverage counts only the words a cleanup candidate really dropped.

Source words are aligned onto the candidate in order. A greedy forward
match bound a deleted occurrence of a repeated word to a LATER occurrence
and skipped the cursor past everything in between, so one deleted "then"
was reported as eight missing words and the whole window fell back to the
raw transcript. The alignment is now the longest in-order match.

Run: .venv/bin/python tests/v2/cleanup/test_validation_alignment.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.validation import validate  # noqa: E402

SOURCE = ("I will send the report to the team and then call the client "
          "and then write the notes for the meeting today")


def _coverage(output, source=SOURCE):
    report = validate(source, output)
    return [c for c in report.components if c.name == "coverage"][0]


def test_one_dropped_repeated_word_is_one_missing_word():
    out = ("I will send the report to the team and call the client "
           "and then write the notes for the meeting today")
    cov = _coverage(out)
    assert cov.status == "fail"
    assert cov.detail["missing_words"] == 1, cov.detail
    assert [r["words"] for r in cov.detail["flagged_deletion_ranges"]] == [1]


def test_a_dropped_distinct_word_still_fails():
    out = SOURCE.replace("client ", "")
    cov = _coverage(out)
    assert cov.status == "fail"
    assert cov.detail["missing_words"] == 1, cov.detail


def test_unchanged_text_passes():
    assert _coverage(SOURCE).status == "pass"


def test_article_adjustment_is_not_a_deletion():
    cov = _coverage("Please write an RFC today",
                    source="Please write a RFC today")
    assert cov.status == "pass", cov.detail


if __name__ == "__main__":
    tests = (test_one_dropped_repeated_word_is_one_missing_word,
             test_a_dropped_distinct_word_still_fails,
             test_unchanged_text_passes,
             test_article_adjustment_is_not_a_deletion)
    for test in tests:
        test()
        print("ok ", test.__name__)
    print(f"{len(tests)}/{len(tests)} validation alignment tests passed")
