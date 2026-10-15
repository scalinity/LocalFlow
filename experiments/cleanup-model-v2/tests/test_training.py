import contextlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v2 import training
from v2.common import file_sha256, read_json, write_json, write_jsonl
from lfx import train

SYSTEM = '<|im_start|>system\n{}<|im_end|>\n'
USER = '<|im_start|>user\n{}<|im_end|>\n<|im_start|>assistant\n'


def call(role, rule, payload, completion):
    return {'role': role, 'prompt': SYSTEM.format(rule) + USER.format(payload), 'completion': completion}


def captures(prefix, rule='current rule', n=3, corrections_rule='corrections rule'):
    return [{'pair_id': f'{prefix}-{i}', 'family_id': f'{prefix}-{i:03d}',
             'calls': [call('main', rule, f'{prefix} payload {i}', f'{prefix} answer {i}'),
                       call('corrections', corrections_rule, f'{prefix} window {i}', 'NONE')]}
            for i in range(n)]


def dataset(root, *, validation_rule='current rule', freeze=None, replay=True, n=3):
    data = root / 'dataset'
    write_jsonl(data / 'train_captures.jsonl', captures('train', n=n))
    write_jsonl(data / 'validation_captures.jsonl', captures('validation', rule=validation_rule))
    if replay:
        write_jsonl(data / 'replay_captures.jsonl', captures('replay', n=2) + captures('replay', n=1))
    write_json(data / 'freeze.json', {'files': {}, 'stats': {'replay': {'source': 'fixture replay origin'}},
                                      **(freeze or {})})
    return data


class Tokenizer:
    bos_token = None

    def encode(self, text, add_special_tokens=False):
        return [ord(c) for c in text]

    def convert_tokens_to_ids(self, token):
        return 0


class Model:
    def __init__(self, params):
        self.params = params

    def load_weights(self, path, strict=False):
        pass

    def trainable_parameters(self):
        return self.params

    def eval(self):
        pass


@contextlib.contextmanager
def fake_training(root):
    """Run training.run() without a base model: the loop records what it receives."""
    import mlx.core as mx
    adapter = root / 'adapter'
    adapter.mkdir()
    params = {'w': mx.array([1.0, 2.0])}
    mx.save_safetensors(str(adapter / 'adapters.safetensors'), params)
    received = {}

    def train_loop(model, tok, examples, vexamples, run_dir, **kwargs):
        received.update(examples=examples, **kwargs)
        (run_dir / 'ckpt-00001').mkdir(parents=True)
        return {'updates': len(kwargs.get('blocks') or [])}

    with patch.object(training, 'ART', root), patch.object(training, 'ROOT', root), \
            patch.object(train, 'load_for_training', return_value=(Model(params), Tokenizer())), \
            patch.object(train, 'train_loop', side_effect=train_loop), \
            patch.object(train, 'prefix_cache', return_value=[]), \
            patch.object(train, 'clone_cache', side_effect=lambda cache: cache), \
            patch.object(train, 'cached_response_loss', return_value=(mx.array(0.5), mx.array(2))):
        yield adapter, received


class CheckedDatasetPromptTests(unittest.TestCase):
    def test_validation_capture_sources_must_match_training_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            same = {'prompts.py': 'a' * 64, 'engine.py': 'b' * 64}
            data = dataset(root, freeze={'capture_source_hashes': same, 'validation_capture_source_hashes': dict(same)})
            training.checked_dataset(data, require_current_capture_source=False)
            for validation in ({**same, 'prompts.py': 'c' * 64}, {'prompts.py': 'a' * 64},
                               {**same, 'numbers.py': 'd' * 64}):
                with self.subTest(validation=validation):
                    write_json(data / 'freeze.json', {'files': {}, 'capture_source_hashes': same,
                                                      'validation_capture_source_hashes': validation})
                    with self.assertRaisesRegex(RuntimeError, 'different prompt sources'):
                        training.checked_dataset(data, require_current_capture_source=False)

    def test_validation_prompt_prefixes_must_match_training_prefixes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            training.checked_dataset(dataset(root))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(RuntimeError, 'different prompts from training'):
                training.checked_dataset(dataset(root, validation_rule='rule without the direct-address example'))

    def test_prefix_keys_equal_the_trainer_cache_keys(self):
        caps = captures('train', n=2)
        examples = [{**c, 'prompt': x['prompt'], 'completion': x['completion']} for c in caps for x in c['calls']]
        keys = {train.split_example(Tokenizer(), e)['key'] for e in examples}
        prefixes = training.prompt_prefixes(caps)
        self.assertEqual(set(prefixes), {'main', 'corrections'})
        self.assertEqual(prefixes['main'] | prefixes['corrections'], keys)


class TrainingRunReceiptTests(unittest.TestCase):
    def test_checkpoint_validation_records_whether_prompts_match_training(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = dataset(root)
            with fake_training(root) as (adapter, _):
                training.run('fixture', 3, initial_adapter=adapter, dataset_dir=data)
            record = read_json(root / 'train/fixture/checkpoint-validation.json')
            self.assertIs(record['prompt_matches_training'], True)
            self.assertEqual(record['lowest_loss'], 'ckpt-00001')

    def test_control_run_records_a_validation_prompt_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / 'old'
            write_jsonl(old / 'dataset/train.jsonl', [{'pair_id': f'train-{i}', 'verification': 'PASS'} for i in range(3)])
            write_jsonl(old / 'dataset/train_captures.jsonl', captures('train'))
            write_jsonl(old / 'dataset/validation_captures.jsonl', captures('validation', rule='older rule'))
            with fake_training(root) as (adapter, _), patch.object(training, 'OLD_ART', old):
                training.run('control', 3, control=True, initial_adapter=adapter)
            self.assertIs(read_json(root / 'train/control/checkpoint-validation.json')['prompt_matches_training'], False)


if __name__ == '__main__':
    unittest.main()
