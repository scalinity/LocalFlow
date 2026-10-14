import unittest
import copy
from v2.refinement_data import COUNTS, DOMAINS, correction_offsets, plan


class RefinementPlanTests(unittest.TestCase):
    def test_scenarios_and_group_ids_are_disjoint(self):
        plans = {s: plan(s) for s in COUNTS}
        for left in plans:
            for right in plans:
                if left == right:
                    continue
                self.assertFalse(set(DOMAINS[left]) & set(DOMAINS[right]))
                self.assertFalse({p['scenario_family'] for p in plans[left]} &
                                 {p['scenario_family'] for p in plans[right]})
                self.assertFalse({p['contrast_group_id'] for p in plans[left]} &
                                 {p['contrast_group_id'] for p in plans[right]})

    def test_every_contrast_has_repair_and_preservation(self):
        for split, count in COUNTS.items():
            rows = plan(split)
            self.assertEqual(len(rows), count)
            self.assertEqual(rows, plan(split))
            self.assertEqual(len({r['family_id'] for r in rows}), count)
            self.assertEqual(sum(r['is_noop'] for r in rows), count // 2)
            self.assertEqual(sum(r['category'] == 'long_instructions' for r in rows), count // 5)
            for i in range(0, count, 2):
                a, b = rows[i:i+2]
                self.assertEqual(a['contrast_group_id'], b['contrast_group_id'])
                self.assertEqual(a['focus'], b['focus'])
                self.assertFalse(a['is_noop'])
                self.assertTrue(b['is_noop'])

    def test_invalid_plan_cannot_split_siblings(self):
        for count in (0, -2, 3):
            with self.assertRaises(ValueError):
                plan('train', count)
        with self.assertRaises(ValueError):
            plan('unknown', 2)

    def test_correction_offsets_are_exact_ordered_and_do_not_change_labels(self):
        source = 'Use gain_v2, no wait gain_v3 at 09:15, sorry 09:45 tomorrow.'
        row = {'case_id': 'fixture', 'model_input': source,
               'gold_lines': ['gain_v2, no wait', '09:15, sorry'],
               'target': 'Use gain_v3 at 09:45 tomorrow.'}
        original = copy.deepcopy(row)
        offsets = correction_offsets(row)
        self.assertEqual([source[a:b] for a, b in offsets], row['gold_lines'])
        self.assertLess(offsets[0][1], offsets[1][0])
        self.assertEqual(row, original)
        self.assertEqual(correction_offsets({'case_id': 'noop', 'model_input': 'Keep this.'}), [])

    def test_missing_ambiguous_empty_or_partial_word_labels_fail(self):
        for source, lines, reason in [
                ('Use 5 tomorrow.', ['5, no'], 'Missing'),
                ('Use 5, no 6 and 5, no 7.', ['5, no'], 'Ambiguous'),
                ('Use 15, no 6.', ['5, no'], 'Missing'),
                ('Use 5, no 6.', [''], 'Empty'),
                ('Use 5, no 6 and 7, sorry 8.', ['7, sorry', '5, no'], 'Missing')]:
            with self.subTest(source=source, lines=lines), self.assertRaisesRegex(ValueError, reason):
                correction_offsets({'case_id': 'fixture', 'model_input': source, 'gold_lines': lines})

    def test_offsets_keep_valid_corrections_out_of_legacy_damage_counts(self):
        from v2.score import synthetic
        row = {'case_id': 'fixture', 'model_input': 'Use 30, sorry 35 samples tomorrow.',
               'target': 'Use 35 samples tomorrow.', 'gold_lines': ['30, sorry'],
               'obsolete_values': ['30'], 'is_noop': False}
        self.assertTrue(synthetic(row, row['target'], True)['damage'])
        row['gold_offsets'] = correction_offsets(row)
        self.assertFalse(synthetic(row, row['target'], True)['damage'])


if __name__ == '__main__':
    unittest.main()
