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



class MinimalTargetTests(unittest.TestCase):
    def check(self, source, target, expected, changes=None, exclusion=None):
        got, done, excluded = policy_score.minimal_target(source, target)
        self.assertEqual(excluded, exclusion)
        if exclusion is None:
            self.assertEqual(got, expected)
        if changes is not None:
            self.assertEqual(done, changes)

    def test_invented_paragraph_is_reverted_and_repairs_stay(self):
        self.check("Check the seals. then log it", "Check the seals.\n\nThen log it.",
                   "Check the seals. Then log it.", ["invented_paragraph"])

    def test_existing_paragraph_break_is_kept(self):
        self.check("First part.\n\nsecond part", "First part.\n\nSecond part.", "First part.\n\nSecond part.", [])

    def test_opening_discourse_comma_is_reverted(self):
        self.check("okay so the build passed", "Okay, so the build passed.", "Okay so the build passed.",
                   ["opening_discourse_comma"])

    def test_comma_after_a_discourse_word_inside_a_sentence_is_an_optional_gap_comma(self):
        self.check("I said so they left", "I said so, they left.", "I said so they left.", ["optional_gap_comma"])

    def test_optional_gap_comma_is_reverted_and_the_opening_discourse_case_keeps_its_name(self):
        self.check("run the batch then inspect it and log the result",
                   "Run the batch, then inspect it, and log the result.",
                   "Run the batch then inspect it and log the result.", ["optional_gap_comma"] * 2)
        self.check("okay so run the batch then inspect it", "Okay, so run the batch, then inspect it.",
                   "Okay so run the batch then inspect it.", ["opening_discourse_comma", "optional_gap_comma"])

    def test_a_comma_the_label_gave_a_line_break_stays_when_the_break_reverts(self):
        self.check("the pump is primed the valve is closed", "The pump is primed,\n\nthe valve is closed.",
                   "The pump is primed, the valve is closed.", ["invented_paragraph"])

    def test_a_comma_between_touching_words_reverts_to_the_source_gap(self):
        self.check("pay 1 000 euros", "Pay 1,000 euros.", "Pay 1 000 euros.", ["optional_gap_comma"])

    def test_commas_that_set_off_an_addressed_person_stay(self):
        for source, target in (
                ("thanks marta", "Thanks, Marta."),
                ("can you check this sam", "Can you check this, Sam?"),
                ("thanks everyone", "Thanks, everyone."),
                ("marta can you send it", "Marta, can you send it?"),
                ("dr patel can you sign it", "Dr Patel, can you sign it?"),
                ("team the proofs are back", "Team, the proofs are back."),
                ("hi marta can you send it", "Hi Marta, can you send it?"),
                ("okay so priya I need you to check it", "Okay so Priya, I need you to check it."),
                ("hey team the build is green", "Hey team, the build is green."),
                ("I have a question for you Maren about the kiln", "I have a question for you, Maren, about the kiln.")):
            with self.subTest(target=target):
                self.check(source, target, target, [])

    def test_vocative_shapes_seen_in_train_labels_keep_their_comma(self):
        for source, target, expected in (
                ("okay so Priya I wanted to ask you", "Okay, so Priya, I wanted to ask you.",
                 "Okay so Priya, I wanted to ask you."),
                ("quick question for you Dalia, if it fails call me", "Quick question for you, Dalia: if it fails call me.",
                 "Quick question for you, Dalia, if it fails call me."),
                ("okay class let's look at slide twelve", "Okay class, let's look at slide twelve.",
                 "Okay class, let's look at slide twelve.")):
            with self.subTest(target=target):
                self.assertEqual(policy_score.minimal_target(source, target)[0], expected)

    def test_further_addressee_shapes_keep_their_comma(self):
        for source, target in (
                ("good morning marta here is the update", "Good morning Marta, here is the update."),
                ("thank you marta for the notes", "Thank you Marta, for the notes."),
                ("hi there sam can you check it", "Hi there Sam, can you check it?"),
                ("excuse me sam where is it", "Excuse me Sam, where is it?"),
                ("welcome everyone let's start", "Welcome everyone, let's start."),
                ("thanks dr jane smith", "Thanks, Dr Jane Smith."),
                ("thanks sam and marta", "Thanks, Sam and Marta."),
                ("marta and sam can you check this", "Marta and Sam, can you check this?"),
                ("thanks o'brien", "Thanks, O'Brien."),
                ("thanks jean-luc", "Thanks, Jean-Luc."),
                ("thanks mom", "Thanks, mom."),
                ("marta could we move it to friday", "Marta, could we move it to Friday."),
                ("dr. okafor is the term acceptable", "Dr. Okafor, is the term acceptable?")):
            with self.subTest(target=target):
                self.check(source, target, target, [])
        # A title's period ends no sentence, so a name after it is not sentence-initial.
        self.check("the call with Dr. Okonkwo-Reyes and I want them", "The call with Dr. Okonkwo-Reyes, and I want them.",
                   "The call with Dr. Okonkwo-Reyes and I want them.", ["optional_gap_comma"])

    def test_months_that_are_given_names_may_be_addressed(self):
        self.check("thanks june", "Thanks, June.", "Thanks, June.", [])
        self.check("see you may", "See you, May.", "See you, May.", [])
        self.check("in june we ship the kiln", "In June, we ship the kiln.", "In June we ship the kiln.",
                   ["optional_gap_comma"])

    def test_conjunction_introductory_and_list_commas_still_go(self):
        for source, target, expected in (
                ("send it to marta and then call her", "Send it to Marta, and then call her.",
                 "Send it to Marta and then call her."),
                ("after lunch we test the pump", "After lunch, we test the pump.", "After lunch we test the pump."),
                ("in berlin we test the kiln", "In Berlin, we test the kiln.", "In Berlin we test the kiln."),
                ("first open the lid", "First, open the lid.", "First open the lid."),
                ("next tuesday we start", "Next Tuesday, we start.", "Next Tuesday we start."),
                ("above all keep it dry", "Above all, keep it dry.", "Above all keep it dry."),
                ("buy eggs milk and bread", "Buy eggs, milk, and bread.", "Buy eggs milk and bread."),
                ("we use Kubernetes Docker and Helm", "We use Kubernetes, Docker, and Helm.",
                 "We use Kubernetes Docker and Helm.")):
            with self.subTest(target=target):
                self.assertEqual(policy_score.minimal_target(source, target)[0], expected)

    def test_a_sentence_initial_name_that_is_the_subject_loses_its_comma(self):
        self.check("marta is in the office", "Marta, is in the office.", "Marta is in the office.",
                   ["optional_gap_comma"])
        # Asked or told: the name is addressed.
        self.check("marta is the report ready", "Marta, is the report ready?", "Marta, is the report ready?", [])
        self.check("marta will you check it", "Marta, will you check it.", "Marta, will you check it.", [])
        # Names of one list that the sentence is about, unless it asks or says "you".
        self.check("marta sam and I will go", "Marta, Sam and I will go.", "Marta Sam and I will go.",
                   ["optional_gap_comma"])
        self.check("marta sam and I will check it okay", "Marta, Sam and I will check it, okay?",
                   "Marta, Sam and I will check it okay?", ["optional_gap_comma"])

    def test_keep_holds_the_source_gaps_whose_added_comma_stays(self):
        source, target = "run the batch then inspect it and log the result", "Run the batch, then inspect it, and log the result."
        self.assertEqual(policy_score.minimal_target(source, target, keep={3}),
                         ("Run the batch, then inspect it and log the result.", ["optional_gap_comma"], None))
        self.assertEqual(policy_score.minimal_target(source, target, keep=frozenset()),
                         policy_score.minimal_target(source, target))

    def test_the_opening_discourse_revert_is_unconditional(self):
        got = policy_score.minimal_target("okay so run the batch then inspect it",
                                          "Okay, so run the batch, then inspect it.", keep={1, 5})
        self.assertEqual(got, ("Okay so run the batch, then inspect it.", ["opening_discourse_comma"], None))
        # The comma after the name still sets the person off: the greeting form.
        self.check("okay dana these are the notes", "Okay, Dana, these are the notes.",
                   "Okay Dana, these are the notes.", ["opening_discourse_comma"])

    def test_ordinal_words_never_make_a_numbered_list(self):
        listed = ("to reproduce the scheduling error do these steps. first run the job. second check the log.",
                  "To reproduce the scheduling error, do these steps.\n1. Run the job.\n2. Check the log.")
        prose = ("here are the steps for the codec test please follow them in order. first calibrate the headphones. "
                 "second play the reference clip.",
                 "Here are the steps for the codec test, please follow them in order. First, calibrate the "
                 "headphones. Second, play the reference clip.")
        sequence = ("do the following first load the file then reproject it then write it",
                    "Do the following:\n1. Load the file.\n2. Reproject it.\n3. Write it.")
        for source, target in (listed, sequence):
            with self.subTest(target=target):
                self.check(source, target, None, exclusion="ordinals_made_a_numbered_list")
        self.assertIsNone(policy_score.minimal_target(*prose)[2])

    def test_introduced_bullets_and_spoken_step_labels_may_become_lists(self):
        for source, target in (
                ("here is the packing list the tent the stove and the water", "Here is the packing list:\n- The tent\n- The stove\n- The water"),
                ("here is the list first the tent second the stove", "Here is the list:\n- The tent\n- The stove"),
                ("do these steps step one clear the cache step two rebuild it", "Do these steps:\n1. Clear the cache.\n2. Rebuild it.")):
            with self.subTest(target=target):
                self.assertIsNone(policy_score.minimal_target(source, target)[2])

    def test_boundaries_newlines_unaligned_and_replacing_commas_stay(self):
        for source, target, vocabulary in (
                ("check the pump then log it", "Check the pump. Then log it.", ()),
                ("check the pump then log it", "Check the pump,\nthen log it.", ()),
                ("check the pump\nthen log it", "Check the pump, then log it.", ()),
                ("open cooper netties now", "Open Kubernetes, now.", ["Kubernetes"]),
                ("check the pump. then log it", "Check the pump, then log it.", ()),
                ("he said stop the pump", 'He said, "Stop the pump."', ()),
                ("Run the batch, then inspect it.", "Run the batch, then inspect it.", ())):
            with self.subTest(target=target):
                self.assertEqual(policy_score.minimal_target(source, target, vocabulary), (target, [], None))

    def test_label_colon_is_reverted_but_a_long_clause_keeps_its_colon(self):
        self.check("Handover note for housekeeping, the dryer is down",
                   "Handover note for housekeeping: the dryer is down.",
                   "Handover note for housekeeping, the dryer is down.", ["label_colon"])
        long = "We checked every cabinet in the east wing twice over, nothing was missing"
        self.check(long, "We checked every cabinet in the east wing twice over: nothing was missing.",
                   "We checked every cabinet in the east wing twice over: nothing was missing.", [])

    def test_ordinals_made_a_list_are_excluded(self):
        self.check("first clear the cache, second rebuild it", "1. Clear the cache.\n2. Rebuild it.", None,
                   exclusion="ordinals_made_a_list")

    def test_step_labels_may_become_a_list(self):
        self.check("step one clear the cache step two rebuild it", "1. Clear the cache.\n2. Rebuild it.",
                   "1. Clear the cache.\n2. Rebuild it.", [])

    def test_added_words_are_excluded_unless_supplied_vocabulary(self):
        self.check("send report to the team", "Send the report to the team.", None,
                   exclusion="adds_undictated_words:the")
        got, _, excluded = policy_score.minimal_target("open cooper netties", "Open Kubernetes.", ["Kubernetes"])
        self.assertIsNone(excluded)


if __name__ == '__main__':
    unittest.main()
