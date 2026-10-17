"""A long run of one character or one marker word costs linear time.

The engine runs on every dictation, so no transcript may make a marker
regex or the corrections trigger backtrack or rescan without bound.
"""
import time
import unittest

from localflow.v2.cleanup import engine


class DegenerateInputCostTest(unittest.TestCase):
    def assertQuick(self, fn, text, seconds):
        start = time.perf_counter()
        fn(text)
        self.assertLess(time.perf_counter() - start, seconds)

    def test_a_compound_marker_reads_its_separators_as_before(self):
        for text, key in (("Tuesday, no, sorry", "no sorry"), ("Tuesday, no sorry", "no sorry"),
                          ("Tuesday, no  , sorry", "no sorry"), ("Tuesday, no ,sorry", "sorry"),
                          ("Tuesday, no,sorry", "sorry")):
            marker = engine.SPAN_ENDS_WITH_MARKER_RE.search(text)
            self.assertEqual(engine.marker_key(text[marker.start():]), key, text)

    def test_a_long_space_run_after_a_marker_word_is_linear(self):
        # "no" and 20,000 spaces took 3.7 s while the separator could
        # split a run of spaces between two parts.
        for text in ("no" + " " * 20000 + "x", "x no" + " " * 20000 + "wai"):
            self.assertQuick(engine.CORRECTION_MARKER_RE.search, text, 0.5)
            self.assertQuick(engine.SPAN_ENDS_WITH_MARKER_RE.search, text, 0.5)

    def test_a_run_of_bare_markers_is_linear(self):
        # 2,000 "no"s took 6.5 s while each "no" parsed every candidate span
        # before it, though none holds an outdated value.
        text = "no " * 2000
        self.assertQuick(engine._has_correction_marker, text, 1.0)
        self.assertFalse(engine._has_correction_marker(text))


if __name__ == "__main__":
    unittest.main()
