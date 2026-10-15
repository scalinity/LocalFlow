"""Sequence words between the numbered items of a dictated sequence.

"first close the dome shutter then purge the cryostat line then
recalibrate the guide camera and finally log the dome temperature"
renders as four numbered items, and each "then" stands exactly where one
item ends and the next begins: the numbering carries the order. Only
sequence words ("then", "after that", "next", "last", optionally after
"and") qualify, only inside a source sentence, only between numbered
items, and only when a spoken enumeration marker opens an item. A bare
"and", a "then" inside an item, a sentence that opens with "Then" and a
list with no spoken enumeration still keep every word.

Run: .venv/bin/python -m unittest tests/v2/cleanup/test_sequence_connectives.py
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.cleanup.validation import validate  # noqa: E402


def failures(source, output):
    return {c.name for c in validate(source, output).critical_failures}


class SequenceConnectiveTests(unittest.TestCase):
    def test_sequence_words_between_numbered_items_are_separators(self):
        for source, output in (
            ("Maintenance steps for Thursday first close the dome shutter then purge the "
             "cryostat line then recalibrate the guide camera and finally log the dome "
             "temperature before you lock up.",
             "Maintenance steps for Thursday:\n\n1. Close the dome shutter.\n2. Purge the "
             "cryostat line.\n3. Recalibrate the guide camera.\n4. Log the dome temperature "
             "before you lock up."),
            ("Release steps first tag the version then build the wheels and then upload to "
             "the staging index and last email the team.",
             "Release steps:\n1. Tag the version.\n2. Build the wheels.\n3. Upload to the "
             "staging index.\n4. Email the team."),
        ):
            with self.subTest(source=source):
                self.assertEqual(failures(source, output), set())

    def test_other_connectives_keep_their_words(self):
        for source, output in (
            # No spoken enumeration: the list is the model's own reading.
            ("Close the dome shutter then purge the cryostat line then log the temperature.",
             "1. Close the dome shutter.\n2. Purge the cryostat line.\n3. Log the temperature."),
            # A bare "and" can join two objects of one instruction.
            ("First, do not delete the logs and the backups, then restart the node.",
             "1. Do not delete the logs.\n2. The backups.\n3. Restart the node."),
            # A "then" inside one item is content.
            ("First open the valve then wait a minute, and finally log the reading.",
             "1. Open the valve, wait a minute.\n2. Log the reading."),
            # A sentence that opens with a sequence word is the speaker's prose.
            ("First, rinse the beaker. Then dry it on the rack. After that, label the shelf.",
             "1. Rinse the beaker.\n2. Dry it on the rack.\n3. Label the shelf."),
            # Bullets carry no order.
            ("First close the shutter then purge the line then log the temperature.",
             "- Close the shutter.\n- Purge the line.\n- Log the temperature."),
        ):
            with self.subTest(source=source):
                self.assertIn("coverage", failures(source, output))


if __name__ == "__main__":
    unittest.main()
