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
    def test_conjunction_dropped_at_a_new_sentence_is_a_defect(self):
        source = 'the samples are in the cold room and before you move them label them'
        target = 'The samples are in the cold room. Before you move them, label them.'
        hit = defects.drops_dictated_word(source, target, [])
        self.assertEqual(hit['dropped'], [{'kind': 'conjunction_at_split', 'words': 'and'}])
        self.assertIsNone(defects.drops_dictated_word(
            source, 'The samples are in the cold room. And before you move them, label them.', []))

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


class TrainingLabelConflictTests(unittest.TestCase):
    def test_every_capture_path_rejects_a_label_defect(self):
        row = {'model_input': 'keep it cold and before you move it label it',
               'target': 'Keep it cold. Before you move it, label it.'}
        self.assertEqual(refinement.training_label_conflict(row)['reason'], 'drops_dictated_word')

    def test_gold_lines_are_anchored_when_offsets_are_not_yet_computed(self):
        source = 'we booked 16 rooms, sorry 17 rooms for the team'
        row = {'case_id': 'c', 'model_input': source, 'target': 'We booked 17 rooms for the team.',
               'gold_lines': ['16 rooms, sorry']}
        self.assertIsNone(refinement.training_label_conflict(row))
        # An unanchored line is left to capture, which records it as a failure.
        self.assertIsNone(refinement.training_label_conflict({**row, 'gold_lines': ['nine rooms, sorry']}))


if __name__ == '__main__':
    unittest.main()
