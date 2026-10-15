import unittest

from v2 import policy_score
from v2.score import aggregate, synthetic


def case(source, target, cid='case', **fields):
    return {'case_id': cid, 'origin': 'synthetic', 'model_input': source, 'target': target,
            'is_noop': source == target, **fields}


class PolicyRepairTests(unittest.TestCase):
    def assertPolicy(self, source, target, output, expected):
        scored = policy_score.score(case(source, target), output)
        self.assertIs(scored['policy_repair'], expected)
        return scored

    def test_a_optional_comma_and_required_boundary(self):
        row = case('okay so the build passed', 'Okay, so the build passed.')
        scored = synthetic(row, 'Okay so the build passed.', True)
        self.assertIs(scored['policy_repair'], True)
        self.assertIs(scored['reference_repair'], False)

    def test_b_blank_line_in_a_noop_is_an_invented_break(self):
        scored = policy_score.score(case('A. B.', 'A. B.'), 'A.\n\nB.')
        self.assertIsNone(scored['policy_repair'])
        self.assertEqual(scored['invented_breaks'], 1)
        self.assertEqual(scored['extra_format_edits'], 1)

    def test_c_question_mark_is_required_when_the_label_asks(self):
        self.assertPolicy('can you check it', 'Can you check it?', 'Can you check it.', False)

    def test_d_unresolved_correction_fails_the_word_check(self):
        scored = self.assertPolicy('assign 4 rooms sorry 6 rooms', 'assign 6 rooms', 'assign 4 rooms', False)
        self.assertIs(scored['words_ok'], False)

    def test_e_optional_comma_may_be_omitted(self):
        self.assertPolicy('Run the batch then inspect it', 'Run the batch, then inspect it.',
                          'Run the batch then inspect it.', True)

    def test_f_removing_kept_punctuation_fails(self):
        self.assertPolicy('Run it, then check', 'Run it, then check.', 'Run it then check.', False)

    def test_g_required_boundary_is_satisfied_by_any_mark(self):
        self.assertPolicy('install the resistor then check the supply',
                          'Install the resistor. Then check the supply.',
                          'Install the resistor, then check the supply.', True)

    def test_h_label_paragraph_break_is_not_required(self):
        self.assertPolicy('Check the pump. Then log the reading.', 'Check the pump.\n\nThen log the reading.',
                          'Check the pump. Then log the reading.', True)
        scored = policy_score.score(case('Check the pump. Then log the reading.',
                                         'Check the pump.\n\nThen log the reading.'),
                                    'Check the pump.\n\nThen log the reading.')
        self.assertEqual(scored['invented_breaks'], 1)

    def test_replacing_or_inserting_kept_punctuation_fails(self):
        self.assertPolicy('Run it, then check', 'Run it, then check.', 'Run it; then check.', False)
        self.assertPolicy('run it then check', 'Run it then check.', 'Run it, then check.', False)

    def test_changed_label_punctuation_accepts_source_or_label(self):
        for output, expected in (('Stop; then go.', True), ('Stop, then go.', True), ('Stop: then go.', False)):
            with self.subTest(output=output):
                self.assertPolicy('Stop, then go', 'Stop; then go.', output, expected)

    def test_gaps_inside_edited_regions_are_not_gap_checked(self):
        source = 'Use 30, sorry 35 samples'
        self.assertPolicy(source, 'Use 35 samples.', 'Use 35 samples.', True)
        self.assertPolicy(source, 'Use 35 samples.', 'Use, 35 samples.', True)
        self.assertPolicy(source, 'Use 35 samples.', 'Use? 35 samples.', False)

    def test_extra_format_edits_count_punctuation_changes_the_label_kept(self):
        scored = policy_score.score(case('Keep it, then stop.', 'Keep it, then stop.'), 'Keep it; then stop!')
        self.assertEqual(scored['invented_breaks'], 0)
        self.assertEqual(scored['extra_format_edits'], 2)
        repair = policy_score.score(case('run it then stop', 'Run it, then stop.'), 'Run it, then stop.')
        self.assertEqual(repair['extra_format_edits'], 0)

    def test_missing_output(self):
        self.assertEqual(policy_score.score(case('a b', 'A b.'), None),
                         {'words_ok': False, 'policy_repair': False, 'invented_breaks': None, 'extra_format_edits': None})
        self.assertIsNone(policy_score.score(case('A b.', 'A b.'), None)['policy_repair'])


class PolicyAggregateTests(unittest.TestCase):
    def test_policy_fields_aggregate_by_scope(self):
        long_source = ' '.join(['word'] * 201) + '.'
        cases = [case('A. B.', 'A. B.', 'noop'), case('can you check it', 'Can you check it?', 'repair'),
                 case(long_source, long_source, 'long')]
        rows = [{'case_id': 'noop', 'delivered': 'A.\n\nB.', 'model_only': 'A.\n\nB.'},
                {'case_id': 'repair', 'delivered': 'Can you check it?', 'model_only': None},
                {'case_id': 'long', 'delivered': long_source.replace('word word', 'word.\n\nword', 1),
                 'model_only': long_source}]
        for row in rows:
            row.update(total_cleanup_ms=1, path='llm')
        delivered = aggregate(cases, rows)['synthetic']['delivered']
        self.assertEqual(delivered['policy_repair'], {'value': 1.0, 'n': 1, 'sum': 1})
        # The long fixture is also a no-op, so both scopes count it.
        self.assertEqual(delivered['policy_format']['noop']['invented_breaks'], {'total': 2, 'per_case': 1.0})
        self.assertEqual(delivered['policy_format']['noop']['extra_format_edits'], {'total': 3, 'per_case': 1.5})
        self.assertEqual(delivered['policy_format']['long_over_200'],
                         {'n': 1, 'unavailable': 0, 'invented_breaks': {'total': 1, 'per_case': 1.0},
                          'extra_format_edits': {'total': 2, 'per_case': 2.0}})
        model_only = aggregate(cases, rows)['synthetic']['model_only']
        self.assertEqual(model_only['policy_repair'], {'value': 0.0, 'n': 1, 'sum': 0})
        self.assertEqual(model_only['policy_format']['repair'],
                         {'n': 1, 'unavailable': 1, 'invented_breaks': {'total': 0, 'per_case': None},
                          'extra_format_edits': {'total': 0, 'per_case': None}})


if __name__ == '__main__':
    unittest.main()
