"""Report safety: embedded JSON cannot close its script element, transcripts are
rendered as text, and the page loads nothing from the network."""

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lfx.report import esc_json  # noqa: E402

TEMPLATE = (Path(__file__).resolve().parents[1] / "lfx" / "report_template.html").read_text()
EVIL = 'He said "</script><img src=x onerror=alert(1)>" & <!-- then   left'


class ReportTests(unittest.TestCase):
    def test_embedded_json_cannot_break_out(self):
        html = TEMPLATE.replace("__DATA__", esc_json({"cases": [{"input": EVIL}]}))
        block = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', html, re.S).group(1)
        self.assertNotIn("<", block)
        self.assertNotIn(">", block)
        self.assertEqual(json.loads(block)["cases"][0]["input"], EVIL)
        # exactly the template's own two script elements remain
        self.assertEqual(html.count("</script>"), 2)

    def test_no_network_resources(self):
        self.assertIsNone(re.search(r'<(script|link|img|iframe)[^>]+(src|href)="(https?:)?//', TEMPLATE))
        self.assertNotIn("@import", TEMPLATE)
        self.assertNotIn("fonts.googleapis", TEMPLATE)
        self.assertNotIn("fetch(", TEMPLATE)

    def test_transcripts_only_via_text_nodes(self):
        # innerHTML/outerHTML/insertAdjacentHTML are never used for data.
        self.assertIsNone(re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write", TEMPLATE))

    def test_built_report_if_present(self):
        p = Path(__file__).resolve().parents[3] / "reports" / "localflow-cleanup-comparison" / "index.html"
        if not p.exists():
            self.skipTest("report not built yet")
        html = p.read_text()
        self.assertEqual(html.count("</script>"), 2)
        block = re.search(r'id="report-data">(.*?)</script>', html, re.S).group(1)
        data = json.loads(block)
        self.assertIn("decision", data)
        self.assertNotRegex(html, r"sk-ant-[A-Za-z0-9_-]{10,}")
        # Public copy: no absolute user paths, no third-party transcripts.
        self.assertNotIn("/Users/", html)
        real = [c for c in data["cases"] if c["src"] in ("disfluencyspeech", "fleurs")]
        self.assertTrue(real and all(c.get("redacted") and c["input"] is None for c in real))
        self.assertTrue(all(o["mo"] is None and o["dl"] is None for c in real for o in c["out"].values()))


if __name__ == "__main__":
    unittest.main()
