import unittest
from v2.refinement_data import COUNTS, DOMAINS, plan


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


if __name__ == '__main__':
    unittest.main()
