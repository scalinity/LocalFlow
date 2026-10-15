import json
import unittest
from unittest.mock import patch

from v2 import assemble


class Tokenizer:
    def encode(self, text, add_special_tokens=False):
        return text.split()


def capture(pair):
    """Run the real engine through capture with a whitespace tokenizer."""
    with patch('lfx.capture.tokenizer', return_value=Tokenizer()), \
            patch('lfx.capture.render_with', return_value=lambda messages: json.dumps(messages)):
        return assemble.capture(pair)


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


if __name__ == '__main__':
    unittest.main()
