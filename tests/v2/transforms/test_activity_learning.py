"""Opt-in activity provenance and deletion while a model request is in flight."""
import json
import pathlib
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from localflow.stt import Transcriber
from localflow.v2.store import Store
from localflow.v2.memory import MemoryStore
from localflow.v2.transforms.jobs import IntelligenceJobs
from localflow.v2.transforms.learning import ActivityLearning


class Provider:
    def __init__(self, quote='I use a local journal.', gate=None):
        self.calls, self.quote, self.gate = [], quote, gate
        self.started = threading.Event()

    def request(self, *args):
        self.calls.append(args); self.started.set()
        if self.gate is not None:
            self.gate.wait(2)
        return {'text': json.dumps({'facts': [{'quote': self.quote, 'kind': 'workflow'}]}),
            'model': 'claude-haiku-5-5', 'reasoning': 'off', 'input_tokens': 10, 'output_tokens': 10}


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(pathlib.Path(self.temp.name) / 'db')
        self.memory = MemoryStore(self.store)
        self.jobs = IntelligenceJobs(self.store)
        self.provider = Provider()
        self.learning = ActivityLearning(self.memory, SimpleNamespace(jobs=self.jobs), self.provider)

    def tearDown(self):
        self.jobs.close(); self.store.close(); self.temp.cleanup()

    def finish(self, admission):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            result = self.jobs.read(admission['job_id'])
            if result['status'] not in ('running', 'pending'):
                return result
            time.sleep(.01)
        self.fail('job did not settle')

    def observe(self, text='I use a local journal. Help me phrase this request.', **kwargs):
        return self.learning.observe(text, source_id='synthetic:activity:1', kind='user_instruction', **kwargs)

    def test_learning_off_retains_nothing_and_calls_no_provider(self):
        self.assertIsNone(self.observe())
        self.assertEqual([], self.provider.calls)
        self.assertIsNone(self.memory.read_source('synthetic:activity:1'))

    def test_direct_preference_is_local_and_independent_of_training_collection(self):
        self.memory.set_learning(True)
        result = self.finish(self.observe('I prefer concise status updates.'))
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual([], self.provider.calls)
        record = self.memory.list()[0]
        self.assertEqual(record['status'], 'active')
        self.assertTrue(record['evidence_refs'])
        self.assertIsNone(self.observe('I prefer concise status updates.'))

    def test_model_quote_is_proposed_and_confirmation_keeps_independent_evidence(self):
        self.memory.set_learning(True)
        result = self.finish(self.observe())
        self.assertEqual(result['status'], 'succeeded', result)
        self.assertEqual(len(self.provider.calls), 1)
        record = self.memory.list()[0]
        self.assertEqual(record['status'], 'proposed')
        confirmed = self.memory.update(record['id'], expected_revision=record['revision'], confirm=True)
        self.memory.expire_source('synthetic:activity:1')
        self.assertEqual('active', next(r for r in self.memory.list() if r['id'] == confirmed['id'])['status'])

    def test_ineligible_sources_are_never_retained_or_sent(self):
        self.memory.set_learning(True)
        for flags in ({'secure': True}, {'denied': True}, {'quoted': True},
                      {'confidence_label': 'low'}, {'confidence_label': 'uncertain'}):
            self.assertIsNone(self.observe(**flags))
        self.assertEqual([], self.provider.calls)
        self.assertIsNone(self.memory.read_source('synthetic:activity:1'))

    def test_hallucinated_quote_cannot_become_a_record(self):
        self.memory.set_learning(True); self.provider.quote = 'Invented personal fact.'
        result = self.finish(self.observe())
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['error'], 'ungrounded_memory_extraction')
        self.assertEqual([], self.memory.list())

    def test_dictation_kind_is_eligible_and_model_output_is_rejected_before_retention(self):
        self.memory.set_learning(True)
        self.assertIsNone(self.learning.observe('I use a local journal.',
            source_id='model:1', kind='model_output'))
        self.assertIsNone(self.memory.read_source('model:1'))
        admission = self.learning.observe('I use a local journal.',
            source_id='dictation:1', kind='user_dictation')
        self.assertEqual('succeeded', self.finish(admission)['status'])
        self.assertEqual(1, len(self.memory.list()))

    def test_project_fact_without_an_identified_project_is_not_personal_memory(self):
        self.memory.set_learning(True)
        self.provider.request = lambda *_: {'text': json.dumps({'facts': [
            {'quote': 'My project uses a journal.', 'kind': 'project_fact'}]})}
        result = self.finish(self.observe('My project uses a journal.'))
        self.assertEqual('succeeded', result['status'])
        self.assertEqual([], self.memory.list())

    def test_forget_all_during_request_prevents_late_learning(self):
        self.memory.set_learning(True)
        gate = threading.Event(); self.provider.gate = gate
        job = self.observe(); self.assertTrue(self.provider.started.wait(1))
        self.memory.forget_all(); gate.set()
        result = self.finish(job)
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual([], self.memory.list())
        self.assertIsNone(self.memory.read_source('synthetic:activity:1'))
        self.assertIsNone(self.observe())

    def test_real_recognizer_scores_remain_labeled_uncalibrated(self):
        summary = Transcriber.learning_signal([SimpleNamespace(confidence=.95), SimpleNamespace(confidence=.85)])
        self.assertFalse(summary['calibrated'])
        self.assertAlmostEqual(summary['mean'], .9)
        self.assertEqual(summary['minimum'], .85)
        for values in ([], [None], [float('nan')], [1.1], [-.1]):
            self.assertIsNone(Transcriber.learning_signal([SimpleNamespace(confidence=v) for v in values]))


if __name__ == '__main__':
    unittest.main()
