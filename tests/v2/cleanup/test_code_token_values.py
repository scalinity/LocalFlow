"""Two code tokens of one shape around a marker are a value correction."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.engine import CleanupEngine, _has_correction_marker, parse_correction_output


def clean(source, target, proposal):
    def generate(prompt, max_tokens):
        return {"text": proposal if "Find the self-corrections" in prompt else target,
                "output_tokens": 20, "limit_hit": False}
    return CleanupEngine(generate, model_id="fixture").clean(source)


def reasons(proposal, source):
    accepted, rejected = parse_correction_output(proposal, source, [])
    return [c.delete for c in accepted], [r.reason for r in rejected]


class CodeTokenValueTests(unittest.TestCase):
    def test_a_code_token_takes_a_like_shaped_replacement(self):
        for source, proposal, target in (
            ("The output file is named peaks_final.csv, no peaks_merged.csv, and it lands "
             "in results.", "peaks_final.csv, no",
             "The output file is named peaks_merged.csv, and it lands in results."),
            # A flag replacement may meet a clause link instead of punctuation.
            ("Run the check with the flag --dry-run, sorry, --verbose before signing it off.",
             "--dry-run, sorry",
             "Run the check with the flag --verbose before signing it off."),
            ("The rebuild runs on node-b, sorry, node-c, and holds the catalog.",
             "node-b, sorry", "The rebuild runs on node-c, and holds the catalog."),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([proposal], []))
                self.assertTrue(_has_correction_marker(source))
                result = clean(source, target, proposal)
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")

    def test_other_code_token_pairs_are_not_value_corrections(self):
        for source, proposal in (
            # The separators differ.
            ("Save it as notes_v2.txt, sorry, notes-final, and send it.", "notes_v2.txt, sorry"),
            # The replacement goes on into a clause.
            ("Restart worker_a, sorry, worker_b crashed overnight.", "worker_a, sorry"),
            # The replacement opens a predicate.
            ("Chart number RX-4471, sorry, RX-4417 is the correct one.", "RX-4471, sorry"),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([], ["not_parallel"]))


if __name__ == "__main__":
    unittest.main()
