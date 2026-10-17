import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v2.data import plan
from v2.assemble import Dedup, window_targets
from v2.score import aggregate, punctuation, real, synthetic
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

    def test_punctuation_only_denominator_excludes_word_repairs(self):
        case={'model_input':'Can you check this.', 'target':'Can you check this?', 'is_noop':False}
        score=synthetic(case,case['target'],True)
        self.assertTrue(score['punctuation_only_repaired'])
        self.assertFalse(synthetic(case,case['model_input'],True)['punctuation_only_repaired'])
        self.assertFalse(synthetic(case,None,False)['punctuation_only_repaired'])
        case={'model_input':'Use three samples.', 'target':'Use four samples.', 'is_noop':False}
        score=synthetic(case,case['target'],True)
        self.assertTrue(score['punctuation_repaired'])
        self.assertIsNone(score['punctuation_only_repaired'])
        case={'model_input':'Keep this.', 'target':'Keep this.', 'is_noop':True}
        self.assertIsNone(synthetic(case,case['target'],True)['punctuation_only_repaired'])


    def test_missing_outputs_count_as_failures(self):
        noop={'case_id':'n','model_input':'Keep this.','target':'Keep this.','is_noop':True}
        scored=synthetic(noop,None,False)
        self.assertEqual((scored['noop_preserved'],scored['unnecessary_edit'],scored['correction_success']),(False,True,None))
        repair={'case_id':'r','model_input':'Use 30, sorry 35 samples.','target':'Use 35 samples.',
                'gold_lines':['30, sorry'],'is_noop':False}
        scored=synthetic(repair,None,False)
        self.assertEqual((scored['noop_preserved'],scored['unnecessary_edit'],scored['correction_success']),(None,None,False))
        audio={'case_id':'a','model_input':'keep this','source':'fleurs','lexical_reference':'keep this'}
        self.assertIs(real(audio,None)['unauthorized_edit'],True)

    def test_aggregate_requires_the_complete_paired_population(self):
        cases=[{'case_id':c,'origin':'synthetic','model_input':'Keep this.','target':'Keep this.','is_noop':True}
               for c in ('a','b')]
        rows=[{'case_id':'a','delivered':'Keep this.','model_only':'Keep this.'},
              {'case_id':'b','delivered':'Keep this.','model_only':None}]
        for row in rows:
            row.update(total_cleanup_ms=1,path='llm')
        model_only=aggregate(cases,rows)['synthetic']['model_only']
        self.assertEqual(model_only['noop_preserved'],{'value':0.5,'n':2,'sum':1})
        self.assertEqual(model_only['unnecessary_edit'],{'value':0.5,'n':2,'sum':1})
        self.assertEqual(model_only['unavailable'],1)
        for subset_rows in (rows[:1],rows+[{**rows[0],'case_id':'extra'}]):
            with self.assertRaisesRegex(ValueError,'complete case population'):
                aggregate(cases,subset_rows)
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            aggregate(cases,rows+[rows[0]])

if __name__=='__main__':unittest.main()
