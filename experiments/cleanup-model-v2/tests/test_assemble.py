import json
import unittest
from unittest.mock import patch

from v2 import assemble, strict_score
from v2.refinement_data import correction_offsets
from v2.strict_score import correction_anchor
from localflow.v2.cleanup.engine import Window


class Tokenizer:
    def encode(self, text, add_special_tokens=False):
        return text.split()


def capture(pair, **options):
    """Run the real engine through capture with a whitespace tokenizer."""
    with patch('lfx.capture.tokenizer', return_value=Tokenizer()), \
            patch('lfx.capture.render_with', return_value=lambda messages: json.dumps(messages)):
        return assemble.capture(pair, **options)


def pair(source, target, gold_lines=(), **fields):
    return {'pair_id': 'p', 'family_id': 'f', 'split': 'train', 'raw_input': source, 'model_input': source,
            'target': target, 'gold_lines': list(gold_lines), **fields}


def unwidened(text, span, cursor):
    """The engine before b2f5175 did not widen a span over a repeated "every"."""
    return span


FREQUENCY = pair('Upload the list every 10 minutes, sorry every 20 minutes, unless the browser is idle.',
                 'Upload the list every 20 minutes, unless the browser is idle.', ['10 minutes, sorry'])


class CreatedRepeatTests(unittest.TestCase):
    def test_answer_dropping_a_correction_created_repeat_is_detected(self):
        window = 'the list every 10 minutes, sorry every 20 minutes'
        self.assertTrue(assemble.removes_created_repeat(window, 'the list every every 20 minutes',
                                                        'The list every 20 minutes.'))
        # Retained repeats, authorized stutter words and source repeats are not this case.
        self.assertFalse(assemble.removes_created_repeat(window, 'the list every every 20 minutes',
                                                         'The list every every 20 minutes.'))
        self.assertFalse(assemble.removes_created_repeat('on the passenger side, I mean actually the freight side',
                                                         'on the the freight side', 'On the freight side.'))
        self.assertFalse(assemble.removes_created_repeat('very very hot, sorry warm', 'very very warm', 'Very warm.'))
        self.assertFalse(assemble.removes_created_repeat('every, every 20 minutes', 'every, every 20 minutes',
                                                         'Every 20 minutes.'))

    def test_capture_omits_rows_that_teach_dropping_a_created_repeat(self):
        captured = capture(dict(FREQUENCY))
        main = [c for c in captured['calls'] if c['role'] == 'main']
        self.assertEqual([c['completion'] for c in main], [FREQUENCY['target']])
        with patch('localflow.v2.cleanup.engine._include_repeated_frame', unwidened):
            with self.assertRaisesRegex(ValueError, 'correction_created_repeat'):
                capture(dict(FREQUENCY))



def windows(source, *starts):
    bounds = [0, *starts, len(source)]
    return [Window(a, b, source[a:b]) for a, b in zip(bounds, bounds[1:])]


def split(source, target, seam):
    """Window targets for a two-window source cut at the first occurrence of seam."""
    parts = windows(source, source.index(seam) + len(seam))
    return assemble.window_targets({'model_input': source, 'target': target}, parts)


class WindowTargetTests(unittest.TestCase):
    def test_repair_next_to_a_boundary_is_cut_inside_the_unchanged_run(self):
        source = 'check the pump\n\nthen log it'
        self.assertEqual(list(split(source, 'Check the pump.\n\nThen log it.', '\n\n').values()),
                         ['Check the pump.', 'Then log it.'])

    def test_deletion_at_a_boundary_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'unaligned_window_boundary'):
            split('check the pump um\n\nthen log it', 'Check the pump.\n\nThen log it.', '\n\n')

    def test_repeated_word_mapped_to_another_occurrence_is_refused(self):
        # The matcher maps the second window's "the" to the retained "the",
        # which would teach the first window to drop "the" after "Keep".
        source = 'Keep the um\n\nthe box sits on the shelf by the door near the stairs.'
        with self.assertRaisesRegex(ValueError, 'unaligned_window_boundary'):
            split(source, 'Keep the box sits on the shelf by the door near the stairs.', '\n\n')

    def test_list_block_opening_the_second_window_is_refused(self):
        # Whether the label keeps the dash (first window would end with it) or
        # drops it (second window would learn to delete it), the cut is unsafe.
        for target in ('Buy these things:\n\n- Milk\n- Eggs', 'Buy these things:\n\nMilk\nEggs'):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'unaligned_window_boundary'):
                split('Buy these things\n\n- milk\n- eggs', target, '\n\n')

    def test_label_marker_before_the_cut_is_refused(self):
        for target in ('Buy these things:\n\n- Milk and eggs.', 'Buy these things:\n\n"Milk and eggs."'):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'unaligned_window_boundary'):
                split('Buy these things\n\nmilk and eggs', target, '\n\n')
        self.assertEqual(list(split('He said "stop"\n\nthen left', 'He said "stop."\n\nThen left.', '\n\n').values()),
                         ['He said "stop."', 'Then left.'])

    def test_capture_rejects_a_window_without_a_planned_target(self):
        with patch.object(assemble, 'window_targets', return_value={(0, 1): 'x'}):
            with self.assertRaisesRegex(ValueError, 'window_plan_mismatch'):
                capture(pair('Keep this.', 'Keep this.'))


FILLER = ' '.join(['The visiting team arrives on Friday morning and stays through Sunday evening.'] * 9)
FIRST = 'We booked 16 rooms, sorry 17 rooms, for the visiting team. ' + FILLER
CORRECTION = 'Then assign 6 rooms, sorry 7 rooms, to the volunteers. ' + FILLER
LINE = '6 rooms, sorry'


class CorrectionAnchorTests(unittest.TestCase):
    def test_anchor_is_word_bounded_unique_and_respects_the_cursor(self):
        source = FIRST + ' ' + CORRECTION
        start = source.index('assign 6') + len('assign ')
        self.assertEqual(correction_anchor(source, LINE), (start, start + len(LINE)))
        for text, line, reason in (('Use 5, no 6 and 5, no 7.', '5, no', 'ambiguous'),
                                   ('Use 15, no 6.', '5, no', 'missing'), ('Use 5.', '', 'empty'), ('Use 5.', None, 'empty')):
            with self.subTest(text=text, line=line), self.assertRaisesRegex(ValueError, reason):
                correction_anchor(text, line)
        # Starting the search mid-text does not hide the word character before the cursor.
        with self.assertRaisesRegex(ValueError, 'missing'):
            correction_anchor('a6', '6', 1)

    def test_labels_capture_and_strict_scoring_anchor_lines_identically(self):
        source = 'We booked 16 rooms, sorry about the notice. Assign 6 rooms, sorry 7 rooms, to the volunteers.'
        target = 'We booked 16 rooms, sorry about the notice. Assign 7 rooms to the volunteers.'
        start = source.index('Assign 6') + len('Assign ')
        expected = [[start, start + len(LINE)]]
        self.assertEqual(correction_offsets({'case_id': 'fixture', 'model_input': source, 'gold_lines': [LINE]}), expected)
        issues = []
        self.assertEqual(strict_score._correction_spans({'gold_lines': [LINE]}, source, issues), [tuple(expected[0])])
        self.assertEqual(issues, [])
        captured = pair(source, target, [LINE])
        capture(captured)
        self.assertEqual(captured['gold_offsets'], expected)

    def test_each_corrections_window_is_answered_with_its_own_lines(self):
        # "6 rooms, sorry" is also a substring of the first window's line.
        source = FIRST + '\n\n' + CORRECTION
        target = (FIRST.replace('16 rooms, sorry 17 rooms,', '17 rooms') + '\n\n'
                  + CORRECTION.replace('6 rooms, sorry 7 rooms,', '7 rooms'))
        captured = capture(pair(source, target, ['16 rooms, sorry', LINE]))
        corrections = [(c['window'][0], c['completion']) for c in captured['calls'] if c['role'] == 'corrections']
        self.assertEqual(corrections, [(0, '16 rooms, sorry'), (source.index('Then assign'), LINE)])

    def test_train_capture_applies_the_training_label_conflict_rule(self):
        with self.assertRaisesRegex(ValueError, 'ambiguous_repeated_negation_deletion'):
            capture(pair('The service is not not up.', 'The service is not up.'))
        validation = {**pair('The service is not not up.', 'The service is not up.'), 'split': 'validation'}
        self.assertEqual(capture(validation)['split'], 'validation')


# A correct label whose gold line the engine does not admit, so the cleanup input keeps the corrected words.
INVOICE = pair('Send the invoice to the finance team in Berlin, actually to the legal team.',
               'Send the invoice to the legal team.', ['to the finance team in Berlin, actually'])
DYE = pair('Mix 4 liters of dye, no wait 6 liters for the warp.', 'Mix 6 liters of dye for the warp.',
           ['4 liters of dye, no wait'])


class ConsistentSupervisionTests(unittest.TestCase):
    def test_an_inconsistent_cleanup_pair_is_never_kept(self):
        row = dict(INVOICE)
        captured = capture(row, consistent_only=True)
        self.assertFalse(row['engine_oracle']['exact'])
        self.assertEqual([(c['role'], c['completion']) for c in captured['calls']],
                         [('corrections', 'to the finance team in Berlin, actually')])
        self.assertEqual([(s['role'], s['kept'], s['why']) for s in row['engine_oracle']['supervision']],
                         [('corrections', True, 'corrections_target_is_gold_lines'),
                          ('main', False, 'input_is_not_label_pre_cleanup')])
        # Without the mode, capture returns every call as before; the build vetoes the row.
        self.assertEqual([c['role'] for c in capture(dict(INVOICE))['calls']], ['corrections', 'main'])

    def test_a_vetoed_row_whose_cleanup_input_is_the_label_pre_cleanup_text_keeps_it(self):
        row = pair('Um the pump is is already primed, and the valve goes in the drawer by the window.',
                   'The pump is already primed, and the valve goes in the drawer by the window.')
        captured = capture(row, consistent_only=True)
        self.assertFalse(row['engine_oracle']['exact'])
        self.assertEqual([(c['role'], c['completion']) for c in captured['calls']], [('main', row['target'])])
        self.assertEqual(row['engine_oracle']['supervision'],
                         [{'role': 'main', 'window': [0, len(row['model_input'])], 'kept': True,
                           'why': 'input_is_label_pre_cleanup'}])

    def test_rows_already_exact_are_captured_exactly_as_before(self):
        source = 'We booked 16 rooms, sorry 17 rooms, for the visiting team.'
        before, after = (pair(source, 'We booked 17 rooms for the visiting team.', ['16 rooms, sorry'])
                         for _ in range(2))
        self.assertEqual(capture(after, consistent_only=True), capture(before))
        self.assertTrue(after['engine_oracle']['exact'])
        self.assertEqual(after, before)

    def test_cleanup_agreement_needs_the_label_pre_cleanup_input_and_no_deleted_word(self):
        source = DYE['model_input']
        offsets = [list(correction_anchor(source, DYE['gold_lines'][0]))]
        window = (0, len(source))
        agree = lambda text, answer: assemble.cleanup_agreement(source, offsets, window, text, answer)
        self.assertEqual(agree('Mix 6 liters for  the warp. ', 'Mix 6 liters for the warp.'),
                         'input_is_label_pre_cleanup')
        # The engine did not retain the detail the label keeps: the target would invent it.
        self.assertEqual(agree('Mix 6 liters for the warp.', DYE['target']), 'target_uses_deleted_words')
        self.assertEqual(agree(source, DYE['target']), 'input_is_not_label_pre_cleanup')
        self.assertEqual(agree('Mix 6 liters of dye for the warp.', DYE['target']), 'input_is_not_label_pre_cleanup')


class DedupTests(unittest.TestCase):
    SOURCE = 'Please check the north pump and log the pressure reading before noon today.'

    def test_a_shared_input_or_target_is_a_duplicate_across_splits(self):
        validation = {'model_input': self.SOURCE, 'target': self.SOURCE}
        train = {'model_input': self.SOURCE,
                 'target': 'Inspect the south compressor, replace its worn gasket, and photograph every gauge.'}
        concat_only = assemble.Dedup()
        concat_only.add(validation['model_input'] + ' ' + validation['target'], 'validation')
        # The concatenation alone does not reveal the shared input.
        self.assertIsNone(concat_only.check(train['model_input'] + ' ' + train['target']))
        idx = assemble.Dedup()
        self.assertIsNone(assemble.admit(idx, validation, 'validation'))
        self.assertEqual(assemble.admit(idx, train, 'train'), 'validation')
        shared_target = {'model_input': 'Lunch moved to the third floor kitchen because the cafe is closed for repairs.',
                         'target': self.SOURCE}
        self.assertEqual(assemble.admit(idx, shared_target, 'train'), 'validation')

    def test_a_pair_never_matches_its_own_input_or_target(self):
        idx = assemble.Dedup()
        self.assertIsNone(assemble.admit(idx, {'model_input': 'okay so the build passed',
                                               'target': 'Okay, so the build passed.'}, 'train'))
        self.assertIsNone(assemble.admit(idx, {'model_input': self.SOURCE, 'target': self.SOURCE}, 'train'))
        self.assertEqual(idx.check(self.SOURCE), 'train')

if __name__ == '__main__':
    unittest.main()
