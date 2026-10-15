import unittest

from v2 import label_defects as defects
from v2 import refinement


def span(source, text):
    start = source.index(text)
    return [[start, start + len(text)]]


class GoldDeletionKeptTests(unittest.TestCase):
    def test_a_frame_word_the_gold_line_deletes_but_the_target_keeps_is_a_defect(self):
        source = 'start the capture on Tuesday, no, Wednesday and log it'
        target = 'Start the capture on Wednesday and log it.'
        hit = defects.gold_deletion_kept_by_target(source, target, span(source, 'on Tuesday, no,'))
        self.assertEqual(hit['runs'], [{'kept': 'on', 'gold': 'on tuesday no'}])
        self.assertIsNone(defects.gold_deletion_kept_by_target(source, target, span(source, 'Tuesday, no,')))

    def test_a_gold_line_running_past_its_marker_is_a_defect(self):
        source = 'run it on Tuesday, no Wednesday at nine'
        self.assertTrue(defects.gold_deletion_kept_by_target(source, 'Run it on Wednesday at nine.',
                                                             span(source, 'Tuesday, no Wednesday')))

    def test_quantity_detail_retained_after_the_repair_is_not_matched(self):
        source = 'hold 4 liters of dye, no wait, 6 liters today'
        self.assertIsNone(defects.gold_deletion_kept_by_target(source, 'Hold 6 liters of dye today.',
                                                               span(source, '4 liters of dye, no wait,')))


class DroppedWordTests(unittest.TestCase):
    def test_conjunction_dropped_at_a_new_sentence_is_a_defect_and_restorable(self):
        source = 'the samples are in the cold room and before you move them label them'
        target = 'The samples are in the cold room. Before you move them, label them.'
        hit = defects.drops_dictated_word(source, target, [])
        self.assertEqual(hit['dropped'], [{'kind': 'conjunction_at_split', 'words': 'and'}])
        fixed = defects.restore_split_conjunctions(source, target, [])
        self.assertEqual(fixed, 'The samples are in the cold room. And before you move them, label them.')
        self.assertIsNone(defects.drops_dictated_word(source, fixed, []))

    def test_restoration_keeps_words_capitalised_for_themselves(self):
        for source, target, expected in (
                ('the samples are cold and i will move them', 'The samples are cold. I will move them.',
                 'The samples are cold. And I will move them.'),
                ('the deploy failed and github is down', 'The deploy failed. GitHub is down.',
                 'The deploy failed. And GitHub is down.'),
                ('we finish the kiln so monday we ship it', 'We finish the kiln. Monday we ship it.',
                 'We finish the kiln. So Monday we ship it.'),
                ('we told marta and marta agreed', 'We told Marta. Marta agreed.', 'We told Marta. And Marta agreed.'),
                ('keep the van here and a driver will come', 'Keep the van here. A driver will come.',
                 'Keep the van here. And a driver will come.')):
            with self.subTest(target=target):
                self.assertEqual(defects.restore_split_conjunctions(source, target, []), expected)

    def test_restoration_is_refused_when_another_dropped_word_would_remain(self):
        source = 'the samples are cold and before you move them really label them'
        target = 'The samples are cold. Before you move them, label them.'
        self.assertIsNone(defects.restore_split_conjunctions(source, target, []))
        self.assertIsNone(defects.restore_split_conjunctions('keep it cold', 'Keep it cold.', []))
        # A stuttered run has no single dictated form to put back.
        for source in ('keep it cold and and before you move it label it',
                       'keep it cold and then and then before you move it label it'):
            self.assertIsNone(defects.restore_split_conjunctions(source, 'Keep it cold. Before you move it, label it.', []))
        # In a list target the dropped 'and' is the list conversion, not a run-on split.
        self.assertIsNone(defects.restore_split_conjunctions(
            'check the pump and 2 log the reading', '1. Check the pump.\n2. Log the reading.', []))

    def test_a_step_label_takes_its_verb_into_the_list(self):
        for source in ('step 1 is clean the filter step 2 is to dry it', 'step one is clean the filter step two is dry it'):
            with self.subTest(source=source):
                self.assertIsNone(defects.drops_dictated_word(source, '1. Clean the filter\n2. Dry it', []))
        hit = defects.drops_dictated_word('the plan is clean the filter', 'The plan: clean the filter', [])
        self.assertEqual(hit['dropped'], [{'kind': 'other_word', 'words': 'is'}])

    def test_unlisted_correction_is_a_defect(self):
        source = 'write it to the review directory sorry because the other one gets wiped'
        hit = defects.drops_dictated_word(source, 'Write it to the review directory because the other one gets wiped.', [])
        self.assertEqual(hit['dropped'][0]['kind'], 'unlisted_correction')

    def test_permitted_deletions_are_not_defects(self):
        for source, target, offsets, vocabulary in (
                ('the the van is late um and so is the driver', 'The van is late, and so is the driver.', [], ()),
                ('it uses pie proj here', 'It uses PROJ here.', [], [['pie proj', 'PROJ']]),
                ('step 1 open the lid step 2 pour', '1. Open the lid\n2. Pour', [], ()),
                ('use the file slash tmp', 'Use the file /tmp.', [], ()),
                ('we booked 16 rooms, sorry 17 rooms', 'We booked 17 rooms.',
                 span('we booked 16 rooms, sorry 17 rooms', '16 rooms, sorry'), ())):
            with self.subTest(source=source):
                self.assertIsNone(defects.drops_dictated_word(source, target, offsets, vocabulary))


class SentenceBoundaryTests(unittest.TestCase):
    def test_a_sentence_glued_onto_the_last_bullet_is_a_defect(self):
        source = 'Here is the list: the map, the water, and the kit. We leave at six.'
        self.assertTrue(defects.loses_sentence_boundary(
            source, 'Here is the list:\n- the map\n- the water\n- the kit We leave at six.', []))
        self.assertIsNone(defects.loses_sentence_boundary(
            source, 'Here is the list:\n- the map\n- the water\n- the kit\n\nWe leave at six.', []))

    def test_an_abbreviation_period_is_no_sentence_boundary(self):
        for source, target in (('we met Dr. Patel there', 'We met Dr Patel there.'),
                               ('they flew to St. Louis today', 'They flew to St Louis today.')):
            with self.subTest(target=target):
                self.assertIsNone(defects.loses_sentence_boundary(source, target, []))

    def test_a_comma_merge_is_not_matched(self):
        source = 'the calendar showed it as free. But the email said it was taken.'
        self.assertIsNone(defects.loses_sentence_boundary(
            source, 'The calendar showed it as free, but the email said it was taken.', []))


class SequenceWordTests(unittest.TestCase):
    def test_then_made_a_list_number_is_a_defect_but_ordinals_are_not(self):
        source = 'first heat the pan then add the oil then add the onions'
        hit = defects.sequence_words_made_numbers(source, '1. Heat the pan\n2. Add the oil\n3. Add the onions', [])
        self.assertEqual(hit['runs'], ['then', 'then'])
        self.assertIsNone(defects.sequence_words_made_numbers(
            'first heat the pan second add the oil', '1. Heat the pan\n2. Add the oil', []))



class MarkerEndingTests(unittest.TestCase):
    def test_a_gold_line_that_does_not_end_at_a_correction_marker_is_a_defect(self):
        for source, line in (
                ('bring 12 score sheets, uh 14 score sheets', '12 score sheets, uh'),
                ('run it on Tuesday, no Wednesday at nine', 'Tuesday, no Wednesday'),
                ('the cabinet opens on Monday. Sorry. On Tuesday.', 'on Monday. Sorry.')):
            with self.subTest(line=line):
                self.assertEqual(defects.gold_line_not_marker_terminated(source, '', span(source, line))['lines'],
                                 [line])
        source = 'we booked 16 rooms, sorry 17 rooms'
        self.assertIsNone(defects.gold_line_not_marker_terminated(source, '', span(source, '16 rooms, sorry')))


class UnexplainedRewriteTests(unittest.TestCase):
    def test_vocabulary_digit_and_joined_word_conversions_are_explained(self):
        for before, after, vocabulary in (
                ('it uses pie proj here', 'It uses PROJ here.', [['pie proj', 'PROJ']]),
                ('we sampled wgs eighty four', 'We sampled WGS84.', ()),
                ('load the data frame', 'Load the dataframe.', ()),
                ('do these things and check and log', 'Do these things:\n1. Check\n2. Log', ())):
            with self.subTest(after=after):
                self.assertEqual(defects.unexplained_rewrites(before, after, vocabulary), [])

    def test_a_substituted_word_or_a_changed_number_is_not(self):
        self.assertEqual(defects.unexplained_rewrites('ship it on tuesday', 'Ship it on Wednesday.'),
                         [('tuesday', 'wednesday')])
        self.assertEqual(defects.unexplained_rewrites('use 4 bobbins', 'Use 6 bobbins.'), [('4', '6')])

class TrainingLabelConflictTests(unittest.TestCase):
    def test_every_capture_path_rejects_a_label_defect(self):
        row = {'model_input': 'keep it cold and before you move it label it',
               'target': 'Keep it cold. Before you move it, label it.'}
        self.assertEqual(refinement.training_label_conflict(row)['reason'], 'drops_dictated_word')

    def test_a_gold_line_the_parser_never_admits_excludes_the_row(self):
        source = 'bring 12 score sheets, uh 14 score sheets'
        row = {'model_input': source, 'target': 'Bring 14 score sheets.', 'gold_offsets': span(source, '12 score sheets, uh')}
        self.assertEqual(refinement.training_label_conflict(row)['reason'], 'gold_line_not_marker_terminated')

    def test_gold_lines_are_anchored_when_offsets_are_not_yet_computed(self):
        source = 'we booked 16 rooms, sorry 17 rooms for the team'
        row = {'case_id': 'c', 'model_input': source, 'target': 'We booked 17 rooms for the team.',
               'gold_lines': ['16 rooms, sorry']}
        self.assertIsNone(refinement.training_label_conflict(row))
        # An unanchored line is left to capture, which records it as a failure.
        self.assertIsNone(refinement.training_label_conflict({**row, 'gold_lines': ['nine rooms, sorry']}))


if __name__ == '__main__':
    unittest.main()
