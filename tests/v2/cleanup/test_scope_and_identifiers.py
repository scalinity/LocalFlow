"""Keep restrictions attached and explicit identifier corrections intact."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from localflow.v2.cleanup.engine import CleanupEngine, parse_correction_output
from localflow.v2.cleanup.validation import validate, restore_missing_words


def engine(proposal, corrections="NONE"):
    def generate(prompt, max_tokens):
        text = corrections if "Find the self-corrections" in prompt else proposal
        return {"text": text, "output_tokens": 10, "limit_hit": False, "prompt": prompt}
    return CleanupEngine(generate, model_id="fixture")


class ScopeTests(unittest.TestCase):
    def test_new_boundary_before_trailing_only_is_rejected(self):
        source = "Review the archived photographs only do not touch the negatives"
        wrong = "Review the archived photographs. Only do not touch the negatives."
        self.assertFalse(validate(source, wrong).accepted)
        self.assertTrue(validate(source, "Review the archived photographs only. Do not touch the negatives.").accepted)

    def test_condition_cannot_be_split_inside_only_if(self):
        source = "Release the package only if every check succeeds"
        for output in ("Release the package. Only if every check succeeds.",
                       "Release the package only. If every check succeeds."):
            with self.subTest(output=output):
                self.assertFalse(validate(source, output).accepted)

    def test_legitimate_initial_only_and_only_then_stay_available(self):
        for source, output in (
            ("Only Mira can approve this request.", "Only Mira can approve this request."),
            ("The task is done. Only the archive remains.", "The task is done. Only the archive remains."),
            ("Finish the calibration only then start recording", "Finish the calibration. Only then start recording."),
            ("Use the blue folders only put the others away", "Use the blue folders only. Put the others away."),
        ):
            with self.subTest(source=source):
                self.assertTrue(validate(source, output).accepted)

    def test_engine_retains_other_cleanup_when_reverting_unsafe_boundary(self):
        source = "um review the archived photographs only do not touch the negatives"
        proposal = "Review the archived photographs. Only do not touch the negatives."
        result = engine(proposal).clean(source)
        self.assertEqual(result.text, "Review the archived photographs only do not touch the negatives.")
        self.assertEqual(result.path, "llm")

    def test_scope_repair_does_not_admit_changed_facts(self):
        source = "Review 8 archived photographs only do not touch the negatives"
        proposal = "Review 9 archived photographs. Only do not touch the negatives."
        self.assertEqual(engine(proposal).clean(source).text, source)


class IdentifierTests(unittest.TestCase):
    def test_exact_identifier_is_not_interchangeable_with_words(self):
        for source, output in (
            ("Use sample_index for the lookup.", "Use sample index for the lookup."),
            ("Keep REGION:6201 unchanged.", "Keep REGION then 6201 unchanged."),
            ("Keep sample_index and sample_index.", "Keep sample_index and sample_index_extra."),
        ):
            with self.subTest(source=source):
                self.assertFalse(validate(source, output).accepted)

    def test_identifier_corrections_accept_separators_and_exact_replacements(self):
        for source, deletion, output in (
            ("Rename it sample_index, sorry, record_cache.", "sample_index, sorry", "Rename it record_cache."),
            ("Open draft.md, actually, final.md.", "draft.md, actually", "Open final.md."),
            ("Use version 1.4, no wait, 1.5.", "1.4, no wait", "Use version 1.5."),
        ):
            with self.subTest(source=source):
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertTrue(accepted, rejected)
                result = engine(output, deletion).clean(source)
                self.assertEqual(result.text, output)
                self.assertEqual(result.path, "llm")

    def test_protected_and_ambiguous_identifier_deletions_stay_rejected(self):
        source = "Use sample_index, sorry, record_cache."
        start = source.index("sample_index")
        accepted, _ = parse_correction_output("sample_index, sorry", source,
                                             [(start, start + len("sample_index"), "literal")])
        self.assertFalse(accepted)
        accepted, _ = parse_correction_output("sample_index, sorry", source + " " + source, [])
        self.assertFalse(accepted)

    def test_word_restoration_keeps_identifier_spelling(self):
        source = "Rename the helper to sample_index, sorry, record_cache for the lookup today."
        output = "Rename the helper to record_cache for the lookup today."
        restored, count = restore_missing_words(source, output)
        self.assertIn("sample_index", restored)
        self.assertNotIn("sample index", restored)
        self.assertEqual(count, 2)

    def test_restoration_never_inserts_inside_a_retained_numeric_token(self):
        source = "Set REGION 6201 then save the output for tomorrow."
        output = "Set REGION 6201. Save the output for tomorrow."
        restored = restore_missing_words(source, output)
        self.assertTrue(restored is None or "REGION 6201" in restored[0], restored)


if __name__ == "__main__":
    unittest.main()
