"""A repeated frame preposition before a like complement marks a correction."""
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


class RepeatedFrameComplementTests(unittest.TestCase):
    def test_a_repeated_frame_replaces_its_complement(self):
        for source, proposal, deleted, target in (
            ("Keep the old index file on the NAS, no on the spare disk, until Friday.",
             "on the NAS, no", "on the NAS, no",
             "Keep the old index file on the spare disk, until Friday."),
            ("Then flush with ethanol, actually with isopropanol, and log the pressure.",
             "with ethanol, actually", "with ethanol, actually",
             "Then flush with isopropanol, and log the pressure."),
            # The frame before a value-only proposal goes with it.
            ("Hand over the key to Priya, sorry, to Marcus, and tell him the code.",
             "Priya, sorry", "to Priya, sorry",
             "Hand over the key to Marcus, and tell him the code."),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([deleted], []))
                self.assertTrue(_has_correction_marker(source))
                result = clean(source, target, proposal)
                self.assertEqual(result.text, target)
                self.assertEqual(result.path, "llm")

    def test_other_repeated_prepositions_are_not_corrections(self):
        for source, proposal in (
            # An apology's own complement.
            ("Thanks for the help, sorry for the delay.", "for the help, sorry"),
            # A yes/no contrast.
            ("Say yes to the first, no to the second.", "to the first, no"),
            # "as" keeps its closed rule.
            ("Treat it as suspect, actually, as soon as the bank confirms.",
             "as suspect, actually"),
            # An infinitive is not a complement like a noun phrase.
            ("I have to go, sorry, to the store first.", "to go, sorry"),
            # An open replacement stays ambiguous.
            ("Power the winch by motor, sorry, by pulley handle since the battery died.",
             "by motor, sorry"),
            # The old complement goes on into a clause.
            ("Put it on the shelf and stay, sorry, on the desk.",
             "on the shelf and stay, sorry"),
        ):
            with self.subTest(proposal=proposal):
                self.assertEqual(reasons(proposal, source), ([], ["not_parallel"]))
        for source in ("Thanks for the help, sorry for the delay.",
                       "Say yes to the first, no to the second."):
            with self.subTest(source=source):
                self.assertFalse(_has_correction_marker(source))


if __name__ == "__main__":
    unittest.main()
