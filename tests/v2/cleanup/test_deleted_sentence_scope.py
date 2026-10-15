"""Text an admitted correction deletes no longer shapes the sentences.

A correction may delete across a sentence boundary ("for 15 minutes.
Actually no, 10 minutes"); the boundary goes with the deleted text, and so
does its marker's "no", so the output's single sentence is not a merge
next to a negated sentence. A negation inside the deleted old sentence is
not lost when the restatement carries it in the same place. A boundary
outside the deletion next to a negated sentence, a merge of the sentence
the deletion leaves behind, and a correction that drops a negation still
fail.

Run: .venv/bin/python -m unittest tests/v2/cleanup/test_deleted_sentence_scope.py
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import CleanupEngine  # noqa: E402
from localflow.v2.cleanup.validation import validate  # noqa: E402


def span(source, delete, marker):
    start = source.index(delete)
    return start, start + len(delete), start + delete.rindex(marker)


def clean(source, lines, output):
    def generate(prompt, max_tokens):
        text = "\n".join(lines) if "Find the self-corrections" in prompt else output
        return {"text": text, "output_tokens": 20, "limit_hit": False}
    return CleanupEngine(generate, model_id="fixture").clean(source)


def failures(source, output, delete, marker):
    return {c.name for c in validate(source, output, correction_spans=[span(source, delete, marker)])
            .critical_failures}


class DeletedSentenceScopeTests(unittest.TestCase):
    def test_a_deleted_boundary_and_its_marker_do_not_count(self):
        for source, delete, marker, output in (
            ("Spin at 2,000 g for 15 minutes. Actually no, 10 minutes, the amendment cut it.",
             "15 minutes. Actually no", "Actually no",
             "Spin at 2,000 g for 10 minutes, the amendment cut it."),
            ("Please do not prune the vines until Thursday. Sorry, please do not prune the vines "
             "until Friday.", "Please do not prune the vines until Thursday. Sorry", "Sorry",
             "Please do not prune the vines until Friday."),
        ):
            with self.subTest(source=source):
                self.assertEqual(failures(source, output, delete, marker), set())

    def test_an_admitted_deletion_across_a_semicolon_is_delivered(self):
        # The engine admits a deletion that holds a ";", so this runs end to end.
        source = "Spin the samples for 15 minutes; actually no, 10 minutes, the amendment cut it."
        output = "Spin the samples for 10 minutes, the amendment cut it."
        result = clean(source, ["15 minutes; actually no"], output)
        self.assertEqual((result.path, result.text), ("llm", output))
        source = "Spin the samples for 15 minutes; actually no, 10 minutes; do not open the lid."
        merged = "Spin the samples for 10 minutes, do not open the lid."
        self.assertNotEqual(clean(source, ["15 minutes; actually no"], merged).path, "llm")
        self.assertIn("clause_scope", failures(source, merged, "15 minutes; actually no", "actually no"))

    def test_remaining_scope_still_counts(self):
        for source, delete, marker, output, name in (
            # A boundary outside the deletion, next to a negated sentence.
            ("Spin it for 15 minutes, actually no, 10 minutes. Do not open the lid.",
             "15 minutes, actually no", "actually no",
             "Spin it for 10 minutes, do not open the lid.", "clause_scope"),
            # The sentence the deletion leaves behind keeps its negation.
            ("Do not deploy the old build. Sorry, the new build. Run the tests.",
             "the old build. Sorry", "Sorry", "Do not deploy the new build, run the tests.",
             "clause_scope"),
            # The restatement drops the negation.
            ("Please do not prune the vines until Thursday. Sorry, please prune the vines on "
             "Friday.", "Please do not prune the vines until Thursday. Sorry", "Sorry",
             "Please prune the vines on Friday.", "negation_coverage"),
        ):
            with self.subTest(source=source):
                self.assertIn(name, failures(source, output, delete, marker))


if __name__ == "__main__":
    unittest.main()
