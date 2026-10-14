"""Only a proposed deletion of a bounded incomplete opening is authorized.

Run: .venv/bin/python tests/v2/cleanup/test_incomplete_restarts.py
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup import CleanupEngine  # noqa: E402
from localflow.v2.cleanup.validation import (  # noqa: E402
    STUTTER_WORDS, _AuthCtx, _auth_context, _incomplete_restart_spans,
    restore_missing_words, validate,
)


SOURCE = "The result that we that we should publish is negative."
PROPOSAL = "The result that we should publish is negative."
POSITIVES = (
    (SOURCE, PROPOSAL),
    ("Keep the version which they which they will release tomorrow.",
     "Keep the version which they will release tomorrow."),
    ("The colleague whom I whom I had contacted replied.",
     "The colleague whom I had contacted replied."),
    ("Use the entries that she\tthat she has checked already.",
     "Use the entries that she has checked already."),
)


def context(source, output, **kwargs):
    return _auth_context(source, output, kwargs.get("vocabulary_pairs"), None,
                         kwargs.get("correction_spans"),
                         kwargs.get("protected_positions"))


def engine_for(proposal):
    def generate(prompt, max_tokens):
        text = "NONE" if "Find the self-corrections" in prompt else proposal
        return {"text": text, "output_tokens": 8, "limit_hit": False,
                "prompt": prompt}
    return CleanupEngine(generate, model_id="fake")


class IncompleteRestartTests(unittest.TestCase):
    def test_only_the_first_opening_is_authorized(self):
        for source, proposal in POSITIVES:
            with self.subTest(source=source):
                spans = context(source, proposal).restart_spans
                self.assertEqual(len(spans), 1)
                start, end = spans[0]
                self.assertIn(source[start:end].lower(),
                              ("that we", "which they", "whom i", "that she"))
                self.assertTrue(validate(source, proposal).accepted)
                self.assertIsNone(restore_missing_words(source, proposal))
                result = engine_for(proposal).clean(source)
                self.assertEqual(result.path, "llm")
                self.assertEqual(result.text, proposal)

    def test_unchanged_text_never_loses_its_occurrence_budget(self):
        for source, _ in POSITIVES:
            with self.subTest(source=source):
                self.assertEqual(context(source, source).restart_spans, [])
                self.assertTrue(validate(source, source).accepted)
                self.assertEqual(engine_for(source).clean(source).text, source)

    def test_filler_cleanup_can_accompany_the_one_opening_deletion(self):
        source = "Um, " + SOURCE[0].lower() + SOURCE[1:]
        self.assertTrue(validate(source, PROPOSAL).accepted)
        self.assertEqual(len(context(source, PROPOSAL).restart_spans), 1)
        self.assertEqual(engine_for(PROPOSAL).clean(source).text, PROPOSAL)

    def test_complete_or_ambiguous_repetitions_are_preserved(self):
        cases = (
            ("She had had lunch before the lecture began.",
             "She had lunch before the lecture began."),
            ("We can can peaches in the kitchen today.",
             "We can peaches in the kitchen today."),
            ("We know we know the answer.", "We know the answer."),
            ("The result was very very important.", "The result was very important."),
            ("This is not not allowed.", "This is not allowed."),
            ("Maybe maybe the test will finish.", "Maybe the test will finish."),
            ("The result that we maybe that we should publish is negative.", PROPOSAL),
            ("I meant then, then repeated it.", "I meant then repeated it."),
            ("The result that we should publish, that we should publish, is negative.",
             PROPOSAL),
            ("The thing that had that had gone.", "The thing that had gone."),
            ("The question of who had who had confused everyone.",
             "The question of who had confused everyone."),
            ("The neighbors who had who had bicycles waited outside.",
             "The neighbors who had bicycles waited outside."),
            ("If the printer is busy then then the editor reads the draft.",
             "If the printer is busy then the editor reads the draft."),
            ("If the meeting was then then we missed it.",
             "If the meeting was then we missed it."),
        )
        for source, proposal in cases:
            with self.subTest(source=source):
                self.assertEqual(context(source, proposal).restart_spans, [])
                self.assertFalse(validate(source, proposal).accepted)

    def test_boundaries_and_three_copies_do_not_qualify(self):
        for source in (
            SOURCE.replace("we that", "we, that"),
            SOURCE.replace("we that", "we\nthat"),
            SOURCE.replace("that we that we", "that we that we that we"),
            SOURCE.replace("The result ", ""),
            SOURCE.replace("result that", "result. That"),
            "1. " + SOURCE + "\n2. Keep it.",
            SOURCE.replace("result that", "result 2 that"),
        ):
            proposal = PROPOSAL if not source.startswith("1.") else "1. " + PROPOSAL + "\n2. Keep it."
            with self.subTest(source=source):
                self.assertEqual(context(source, proposal).restart_spans, [])
                self.assertFalse(validate(source, proposal).accepted)

    def test_quotes_apostrophes_and_backticks_exclude_new_authorization(self):
        for opening, closing in (("\"", "\""), ("'", "'"), ("`", "`"),
                                 ("“", "”"), ("‘", "’"), ("\"", "")):
            source = "Keep " + opening + SOURCE + closing
            proposal = "Keep " + opening + PROPOSAL + closing
            with self.subTest(opening=opening, closing=closing):
                self.assertEqual(context(source, proposal).restart_spans, [])
                self.assertFalse(validate(source, proposal).accepted)
        source = "Don't change the title. " + SOURCE
        proposal = "Don't change the title. " + PROPOSAL
        self.assertEqual(context(source, proposal).restart_spans, [])

    def test_protected_occurrences_and_other_authorizations_do_not_overlap(self):
        first = SOURCE.index("that we")
        second = SOURCE.index("that we", first + 1)
        finite = SOURCE.index("should")
        for span in ((first, first + 7), (second, second + 7),
                     (finite, finite + 6)):
            with self.subTest(protected=span):
                self.assertEqual(context(SOURCE, PROPOSAL,
                                         protected_positions=[span]).restart_spans, [])
                self.assertFalse(validate(SOURCE, PROPOSAL,
                                          protected_positions=[span]).accepted)
        for field in ("correction_spans", "vocab_spans", "enum_spans", "numeric_spans"):
            with self.subTest(overlap=field):
                ctx = _AuthCtx(**{field: [(first, first + 7)]})
                self.assertEqual(_incomplete_restart_spans(SOURCE, PROPOSAL, ctx), [])

    def test_second_copy_and_predicate_are_required(self):
        for proposal in (
            "The result should publish is negative.",
            "The result that we publish is negative.",
            "The result that should publish is negative.",
            "The result that we should is negative.",
            "The result that we should publish is positive.",
            "The result that. We should publish is negative.",
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(context(SOURCE, proposal).restart_spans, [])
                self.assertFalse(validate(SOURCE, proposal).accepted)

    def test_a_later_copy_cannot_replace_the_required_occurrence(self):
        source = ("The first result that we that we should publish is negative. "
                  "The second result that we should publish is positive.")
        proposal = ("The first result should publish is negative. "
                    "The second result that we should publish is positive.")
        self.assertEqual(context(source, proposal).restart_spans, [])
        self.assertFalse(validate(source, proposal).accepted)

    def test_removed_opening_words_cannot_fund_new_content(self):
        for tail in (", that we.", ", we that.", " and we know that."):
            proposal = PROPOSAL[:-1] + tail
            with self.subTest(proposal=proposal):
                self.assertEqual(context(SOURCE, proposal).restart_spans, [])
                self.assertFalse(validate(SOURCE, proposal).accepted)

    def test_multiple_deletions_and_partial_identity_bind_separately(self):
        source = SOURCE + " " + POSITIVES[1][0]
        for proposal, count in ((PROPOSAL + " " + POSITIVES[1][1], 2),
                                (PROPOSAL + " " + POSITIVES[1][0], 1),
                                (source, 0)):
            with self.subTest(count=count):
                self.assertEqual(len(context(source, proposal).restart_spans), count)
                self.assertTrue(validate(source, proposal).accepted)

    def test_negations_and_hedges_remain_exact(self):
        source = SOURCE.replace("should publish", "should not publish, perhaps")
        proposal = PROPOSAL.replace("should publish", "should not publish, perhaps")
        self.assertTrue(validate(source, proposal).accepted)
        for changed in (proposal.replace("not ", ""),
                        proposal.replace(", perhaps", ""),
                        proposal.replace("perhaps", "probably")):
            with self.subTest(proposal=changed):
                self.assertFalse(validate(source, changed).accepted)

    def test_single_word_stutter_policy_is_unchanged(self):
        self.assertTrue({"then", "had", "that", "can"}.isdisjoint(STUTTER_WORDS))
        self.assertTrue(validate("Use the the blue folder.", "Use the blue folder.").accepted)


if __name__ == "__main__":
    unittest.main()
