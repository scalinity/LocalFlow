import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v2.data import plan
from v2.assemble import Dedup, window_targets
from v2.score import punctuation
from localflow.v2.cleanup.engine import plan_windows


class DataAndMetricTests(unittest.TestCase):
    def test_scenarios_do_not_cross_splits(self):
        sets=[{p['scenario_family'] for p in plan(s,3000)} for s in ('test','validation','train')]
        self.assertFalse(sets[0]&sets[1] or sets[0]&sets[2] or sets[1]&sets[2])

    def test_dedup_checks_reference_and_casefold(self):
        d=Dedup();self.assertIsNone(d.add('Keep the cerulean observation register intact.','test'))
        self.assertEqual(d.add('KEEP the cerulean observation register intact.','train'),'test')
        self.assertEqual(d.add('Keep the cerulean observation register intact please.','train'),'test')

    def test_punctuation_metric_not_lexical_only(self):
        self.assertFalse(punctuation('Can you check this.','Can you check this?')['exact'])
        self.assertEqual(punctuation('Can you check this?','Can you check this?')['f1'],1)
        self.assertFalse(punctuation('Do not deploy run tests.','Do not deploy. Run tests.')['exact'])
        self.assertFalse(punctuation('Use 3.5 mL.','Use 35 mL.')['exact'])

    def test_long_targets_cover_complete_text(self):
        source=' '.join(f'Inspect the numbered synthetic sample {i} and preserve its label.' for i in range(50))
        target=source
        windows=plan_windows(source)
        parts=window_targets({'model_input':source,'target':target},windows)
        self.assertGreater(len(windows),1)
        self.assertEqual(' '.join(parts[(w.start,w.end)] for w in windows),target)


if __name__=='__main__':unittest.main()
