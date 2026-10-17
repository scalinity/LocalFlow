"""Sequence words between numbered items stay content.

A list rendered from a dictated sequence ("first close the shutter then
purge the line then ...") may not drop its "then", "after that" or
"next": the word can open a condition's consequent ("if the build fails
then roll back"), and a list split there can move an object out of a
prohibition ("do not delete the logs and the db then restart"). Spoken
enumeration markers ("first", "finally") remain the only words a list may
absorb, so every output below fails coverage.

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
    def test_a_numbered_list_keeps_its_sequence_words(self):
        for source, output in (
            ("Maintenance steps for Thursday first close the dome shutter then purge the "
             "cryostat line then recalibrate the guide camera and finally log the dome "
             "temperature before you lock up.",
             "Maintenance steps for Thursday:\n\n1. Close the dome shutter.\n2. Purge the "
             "cryostat line.\n3. Recalibrate the guide camera.\n4. Log the dome temperature "
             "before you lock up."),
            ("First, if the build fails then roll back the release. Second, notify the team.",
             "1. If the build fails\n2. Roll back the release\n3. Notify the team"),
            ("First, if Dr. Lee agrees then roll back the release. Second, notify the team.",
             "1. If Dr. Lee agrees\n2. Roll back the release\n3. Notify the team"),
            ("First do not delete the logs and the db then restart the node.",
             "1. Do not delete the logs.\n2. The db.\n3. Restart the node."),
            ("First run the backup, and if it is still running at 6:30 then cancel the job.",
             "1. Run the backup, and if it is still running at 6:30\n2. Cancel the job."),
            ("First run the migration, and in case it fails then restore the backup.",
             "1. Run the migration, and in case it fails\n2. Restore the backup."),
            ("First try the cache, otherwise then query the database.",
             "1. Try the cache, otherwise\n2. Query the database."),
            ("Kitchen steps first whisk the eggs and milk then bake the cake.",
             "Kitchen steps:\n1. Whisk the eggs milk.\n2. Bake the cake."),
        ):
            with self.subTest(source=source):
                self.assertIn("coverage", failures(source, output))


if __name__ == "__main__":
    unittest.main()
