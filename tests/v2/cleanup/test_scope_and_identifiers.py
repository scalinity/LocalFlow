"""Keep restrictions attached and explicit identifier corrections intact."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from localflow.v2.cleanup.engine import CleanupEngine, parse_correction_output
from localflow.v2.cleanup.validation import validate, restore_missing_words


def failures(report):
    return {c.name for c in report.critical_failures}


def engine(proposal, corrections="NONE"):
    def generate(prompt, max_tokens):
        text = corrections if "Find the self-corrections" in prompt else proposal
        return {"text": text, "output_tokens": 10, "limit_hit": False, "prompt": prompt}
    return CleanupEngine(generate, model_id="fixture")


class ScopeTests(unittest.TestCase):
    def test_new_boundary_before_trailing_only_is_rejected(self):
        source = "Review the archived photographs only do not touch the negatives"
        wrong = "Review the archived photographs. Only do not touch the negatives."
        self.assertEqual(failures(validate(source, wrong)), {"clause_scope"})
        self.assertTrue(validate(source, "Review the archived photographs only. Do not touch the negatives.").accepted)

    def test_condition_cannot_be_split_inside_only_if(self):
        source = "Release the package only if every check succeeds"
        for output in ("Release the package. Only if every check succeeds.",
                       "Release the package only. If every check succeeds."):
            with self.subTest(output=output):
                self.assertEqual(failures(validate(source, output)), {"clause_scope"})

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

    def test_only_then_cannot_be_separated_by_new_punctuation(self):
        source = "Finish the alignment only then start the recorder"
        for separator in (",", ".", ";", "\n"):
            proposal = "Finish the alignment only" + separator + " then start the recorder."
            with self.subTest(separator=separator):
                self.assertEqual(failures(validate(source, proposal)), {"clause_scope"})
                result = engine(proposal).clean(source)
                self.assertIn("only then", result.text)
                self.assertEqual(result.path, "llm")
        self.assertTrue(validate(source, "Finish the alignment; only then start the recorder.").accepted)


class IdentifierTests(unittest.TestCase):
    def test_exact_identifier_is_not_interchangeable_with_words(self):
        for source, output in (
            ("Use sample_index for the lookup.", "Use sample index for the lookup."),
            ("Keep REGION:6201 unchanged.", "Keep REGION then 6201 unchanged."),
            ("Keep sample_index and sample_index.", "Keep sample_index and sample_index_extra."),
        ):
            with self.subTest(source=source):
                self.assertIn("technical_tokens", failures(validate(source, output)))

    def test_prose_separator_after_path_is_not_part_of_identifier(self):
        source = "Write to /var/data/run_11 and then close the window"
        output = "Write to /var/data/run_11, and then close the window."
        self.assertTrue(validate(source, output).accepted)
        self.assertIn("technical_tokens",
                      failures(validate(source, output.replace("run_11,", "run_110,"))))
        self.assertIn("technical_tokens",
                      failures(validate(source, output.replace("run_11,", "run_11/extra,"))))

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

    def test_identifier_replacement_that_opens_a_clause_is_not_parallel(self):
        # "no worker_b is running" negates a new clause; deleting
        # "worker_a, no" would drop that negation with the old value.
        for source, deletion, wrong in (
            ("Restart worker_a, no worker_b is running.", "worker_a, no",
             "Restart worker_b is running."),
            ("Restart worker_1, no worker_2 is running.", "worker_1, no",
             "Restart worker_2 is running."),
            ("Use sample_index, actually, record_cache is slower.", "sample_index, actually",
             "Use record_cache is slower."),
        ):
            with self.subTest(source=source):
                accepted, rejected = parse_correction_output(deletion, source, [])
                self.assertEqual(accepted, [])
                self.assertEqual([r.reason for r in rejected], ["not_parallel"])
                result = engine(wrong, deletion).clean(source)
                self.assertEqual(result.text, source)

    def test_protected_and_ambiguous_identifier_deletions_stay_rejected(self):
        source = "Use sample_index, sorry, record_cache."
        start = source.index("sample_index")
        accepted, rejected = parse_correction_output(
            "sample_index, sorry", source, [(start, start + len("sample_index"), "literal")])
        self.assertEqual(accepted, [])
        self.assertEqual([r.reason for r in rejected], ["protected_span"])
        accepted, rejected = parse_correction_output("sample_index, sorry",
                                                     source + " " + source, [])
        self.assertEqual(accepted, [])
        self.assertEqual([r.reason for r in rejected], ["ambiguous_occurrence"])

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
        # The word before a retained number cannot locate the dropped "then"
        # without risking a split of "REGION 6201", so nothing is restored.
        self.assertIsNone(restore_missing_words(source, output))
        self.assertEqual(engine(output).clean(source).text, source)


if __name__ == "__main__":
    unittest.main()
