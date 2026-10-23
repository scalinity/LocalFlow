"""Integration with the separately implemented memory domain, synthetic only."""

from __future__ import annotations

import json
import io
import hashlib
import pathlib
import sys
import tempfile
import time
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.store import Store
from localflow.v2.transforms_store import TransformStore
from localflow.v2.transforms.conversations import INTELLIGENCE_MIGRATIONS
from localflow.v2.transforms.intelligence import IntelligenceService, memory_callbacks
from localflow.v2.ui.companion.bridge import Bridge
from localflow.v2.ui.companion.surfaces.intelligence import register
from localflow.v2.memory.embeddings import MiniLMEmbedding

try:
    from localflow.v2.memory import MEMORY_MIGRATIONS, MemoryStore
except ModuleNotFoundError:
    MemoryStore = None


class LexicalFixture:
    implementation = "synthetic-lexical-fixture"

    def encode(self, text):
        return None


@unittest.skipIf(MemoryStore is None, "memory domain has not been integrated")
class MemoryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        cache = patch.object(MiniLMEmbedding, 'cache_dir', return_value=self.root / 'search-model')
        cache.start()
        self.addCleanup(cache.stop)
        checksums = patch.object(MiniLMEmbedding, 'artifact_sha256', {
            'model.onnx': hashlib.sha256(b'synthetic-model').hexdigest(),
            'tokenizer.json': hashlib.sha256(b'synthetic-tokenizer').hexdigest()})
        checksums.start()
        self.addCleanup(checksums.stop)
        self.store = Store(self.root / "db", artifacts_dir=self.root / "artifacts",
                           backup_dir=self.root / "backups")
        self.store.submit(lambda db: [db.execute(s) for s in
                                     [*MEMORY_MIGRATIONS, *INTELLIGENCE_MIGRATIONS]])
        self.memory = MemoryStore(self.store, embedding=LexicalFixture())
        self.transforms = TransformStore(self.store)
        self.transforms.seed_built_ins()
        self.service = IntelligenceService(self.store, self.transforms, object(),
                                           **memory_callbacks(self.memory))
        self.bridge = Bridge()
        self.clipboard = []
        register(SimpleNamespace(bridge=self.bridge, spec={"intelligence_service": self.service,
            "memory_service": self.memory}, state=SimpleNamespace(reload_transforms=lambda: None),
            coordinator=SimpleNamespace(hubCopyText=lambda text: self.clipboard.append(text))))

    def tearDown(self):
        self.service.close()
        self.store.close()
        self.temp.cleanup()

    def call(self, command, payload):
        return self.bridge.handle(json.dumps({"bridge_version": 1, "request_id": "test:1",
                                              "command": command, "payload": payload}))

    def finish(self, job_id):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            job = self.service.read_job(job_id)
            if job["status"] not in ("pending", "running"):
                return job
            time.sleep(0.01)
        self.fail("job did not settle")

    def project(self, name):
        root = self.root / name
        root.mkdir()
        return self.memory.create_project(name, str(root))

    def test_context_scope_pinning_exclusion_and_memory_off(self):
        a, b = self.project("Project A"), self.project("Project B")
        first = self.memory.remember("The encoder is serial.", kind="project_fact", project_id=a)
        other = self.memory.remember("The encoder is parallel.", kind="project_fact", project_id=b)
        callbacks = memory_callbacks(self.memory)
        common = dict(query="encoder", use_memory=False, purpose="transform")
        pack_a = callbacks["assemble_context"](project_id=a, **common)
        pack_b = callbacks["assemble_context"](project_id=b, **common)
        self.assertEqual([i["id"] for i in pack_a["items"]], [first["id"]])
        self.assertEqual([i["id"] for i in pack_b["items"]], [other["id"]])
        off = callbacks["assemble_context"](project_id=None, **common)
        self.assertFalse(off["items"])
        excluded = callbacks["assemble_context"](project_id=a,
            excluded_context_ids=[first["id"]], **common)
        self.assertFalse(excluded["items"])
        pinned = callbacks["assemble_context"](query="unrelated", project_id=a, use_memory=False,
            purpose="refinement", pinned_context_ids=[first["id"]])
        self.assertEqual(pinned["items"][0]["reason"], "pinned_by_user")
        with self.assertRaisesRegex(ValueError, "pinned_context_unavailable"):
            callbacks["assemble_context"](project_id=a, pinned_context_ids=[other["id"]], **common)

    def test_bridge_memory_create_edit_cas_forget_and_retry(self):
        payload = {"text": "Prefer concise reports.", "kind": "preference",
                   "scope_kind": "personal", "scope_id": None, "operation_token": "remember:1"}
        first = self.call("memories.remember", payload)
        self.assertEqual(first["status"], "success", first)
        self.assertEqual(first, self.call("memories.remember", payload))
        memory = first["result"]["memory"]
        self.assertTrue(memory["updated_at"].endswith(("-04:00", "-05:00")))
        changed = self.call("memories.update", {"memory_id": memory["id"],
            "expected_revision": 1, "changes": {"text": "Prefer detailed reports."}})
        self.assertEqual(changed["status"], "success", changed)
        stale = self.call("memories.forget", {"memory_id": memory["id"], "expected_revision": 1})
        self.assertEqual(stale["status"], "stale", stale)
        removed = self.call("memories.forget", {"memory_id": memory["id"], "expected_revision": 2})
        self.assertEqual(removed["status"], "success", removed)
        pending = self.call("memories.search", {"query": "reports", "limit": 100})
        self.assertEqual(pending["status"], "success", pending)
        done = self.finish(pending["result"]["job_id"])
        self.assertEqual(done["status"], "succeeded", done)
        self.assertEqual(done["result"]["memories"], [])

    def test_context_preview_job_revokes_cached_result(self):
        project_id = self.project("Project")
        memory = self.memory.remember("The encoder is serial.", project_id=project_id)
        pending = self.call("context.preview", {"query": "encoder", "project_id": project_id,
            "use_memory": False, "pinned_context_ids": [memory["id"]]})
        self.assertEqual(pending["status"], "success", pending)
        done = self.finish(pending["result"]["job_id"])
        self.assertEqual(done["status"], "succeeded", done)
        self.assertEqual(done["result"]["items"][0]["id"], memory["id"])
        self.memory.forget(memory["id"])
        revoked = self.service.read_job(done["job_id"])
        self.assertEqual(revoked["error"], "context_revoked")
        self.assertIsNone(revoked["result"])

    def test_copy_uses_existing_native_coordinator(self):
        session = self.service.create_session("A synthetic prompt.", "copy:session")
        result = self.call("prompt_sessions.copy", {"session_id": session["id"], "expected_revision": 1})
        self.assertEqual(result["status"], "success", result)
        self.assertEqual(self.clipboard, ["A synthetic prompt."])

    def grounded_session(self):
        memory = self.memory.remember('The synthetic project uses CedarDB.')
        pack = memory_callbacks(self.memory)['assemble_context'](
            query='CedarDB', project_id=None, use_memory=True, purpose='refinement')
        session = self.service.create_session('Investigate the project.', 'grounded:session')
        session = self.service.sessions.append(session['id'], session['revision'],
            'Investigate the project using CedarDB.', kind='assistant', context=pack,
            validate=self.service.validate_pack)['session']
        # A later refinement might retrieve no memory while retaining its
        # predecessor's grounded assertion in the canonical prompt body.
        session = self.service.sessions.append(session['id'], session['revision'],
            'Investigate CedarDB.', kind='assistant', context={})['session']
        return session, memory

    def test_forgotten_ancestor_context_cannot_be_copied_or_refined(self):
        session, memory = self.grounded_session()
        self.memory.forget(memory['id'])
        copied = self.call('prompt_sessions.copy', {'session_id': session['id'],
            'expected_revision': session['revision']})
        self.assertEqual(copied['status'], 'refusal', copied)
        self.assertEqual(copied['reason_code'], 'context_revoked')
        self.assertEqual(self.clipboard, [])
        with self.assertRaisesRegex(ValueError, 'context_revoked'):
            self.service.refine(session['id'], session['revision'], 'Make it shorter.')
        with self.assertRaisesRegex(ValueError, 'context_revoked'):
            self.service.select_revision(session['id'], session['revision'], session['canonical_revision'])
        view = self.service.session_view(session['id'])
        self.assertEqual(view['prompt'], session['prompt'])  # Saved documents are not silently rewritten.
        for revision in view['revisions'][1:]:
            self.assertEqual(revision['context']['items'], [])
            self.assertTrue(revision['context']['warnings'])
            self.assertEqual(revision['result'], {})
        original = self.service.select_revision(session['id'], session['revision'], 1)
        copied = self.call('prompt_sessions.copy', {'session_id': original['id'],
            'expected_revision': original['revision']})
        self.assertEqual(copied['status'], 'success', copied)
        self.assertEqual(self.clipboard, [session['source']])

    def test_deliberate_manual_revision_remains_independent_of_earlier_memory(self):
        session, memory = self.grounded_session()
        changed = self.service.edit(session['id'], session['revision'],
                                    'Investigate the database I explicitly named.')['session']
        self.memory.forget(memory['id'])
        copied = self.call('prompt_sessions.copy', {'session_id': changed['id'],
            'expected_revision': changed['revision']})
        self.assertEqual(copied['status'], 'success', copied)
        self.assertEqual(self.clipboard, [changed['prompt']])

    def test_refinement_rechecks_inherited_context_before_provider_admission(self):
        session, memory = self.grounded_session()
        real_context = self.service._context
        def revoke(*args, **kwargs):
            result = real_context(*args, **kwargs)
            self.memory.forget(memory['id'])
            return result
        provider = SimpleNamespace(run=unittest.mock.Mock(side_effect=AssertionError('provider_admitted_revoked_source')))
        self.service.transformer = provider
        with patch.object(self.service, '_context', side_effect=revoke):
            started = self.service.refine(session['id'], session['revision'], 'Make it shorter.')
            done = self.finish(started['job_id'])
        self.assertEqual(done['error'], 'context_revoked', done)
        provider.run.assert_not_called()

    def test_refinement_rechecks_inherited_context_on_the_publication_writer(self):
        session, memory = self.grounded_session()
        append = self.service.sessions.append
        def revoke(*args, **kwargs):
            self.memory.forget(memory['id'])
            return append(*args, **kwargs)
        with patch.object(self.service, '_run_preview', return_value={'output': 'A revised grounded prompt.'}), \
                patch.object(self.service.sessions, 'append', side_effect=revoke):
            started = self.service.refine(session['id'], session['revision'], 'Make it shorter.')
            done = self.finish(started['job_id'])
        self.assertEqual(done['error'], 'context_revoked', done)
        self.assertEqual(self.service.sessions.read(session['id'])['revision'], session['revision'])

    def test_completed_refinement_poll_does_not_redisclose_revoked_context(self):
        session, memory = self.grounded_session()
        started = self.service.jobs.start('refinement', lambda ctx: {
            'session': session, 'revision_id': session['canonical_revision']})
        self.assertEqual(self.finish(started['job_id'])['status'], 'succeeded')
        self.memory.forget(memory['id'])
        done = self.service.read_job(started['job_id'])
        self.assertEqual(done['error'], 'context_revoked', done)
        self.assertIsNone(done['result'])

    def test_inherited_grounding_changes_task_identity_even_with_same_text(self):
        from test_intelligence_backend import FakeProvider
        self.memory.remember('The synthetic project uses CedarDB.')
        self.memory.remember('The synthetic project uses LanternDB.')
        assemble = memory_callbacks(self.memory)['assemble_context']
        packs = [assemble(query=name, project_id=None, use_memory=True, purpose='refinement')
                 for name in ('CedarDB', 'LanternDB')]
        self.assertNotEqual(packs[0]['items'], packs[1]['items'])
        self.service.transformer = FakeProvider()
        definition = self.service._definition('builtin:prompt_engineer')
        policy = self.service._policy(None, False, 'auto')
        keys = []
        for pack in packs:
            context = SimpleNamespace(validators=[], progress=lambda phase: None,
                                      check=lambda: None, cancelled=lambda: False)
            result = self.service._run_preview(definition, 'Investigate the project.', policy,
                context, pack={}, source_contexts=(pack,))
            keys.append(result['task_key'])
        self.assertNotEqual(*keys)

    def test_real_eligible_observations_suggest_and_revoke(self):
        project_id = self.project("Project")
        self.memory.set_learning(True)
        first = self.memory.add_source("Write a bug report from these debugging notes.",
            project_id=project_id, independent_key="episode:1")
        self.memory.add_source("Write a bug report from these debugging notes.",
            project_id=project_id, independent_key="episode:1")
        self.assertFalse(any(s["personalized"] for s in self.service.suggestions.refresh(project_id)))
        second = self.memory.add_source("Make this crash report reproducible.",
            project_id=project_id, independent_key="episode:2")
        self.memory.add_source("A quoted bug report from someone else.",
            project_id=project_id, quoted=True)
        patterns = self.service.patterns(project_id)
        self.assertEqual(len(patterns), 2)
        self.assertIn(second, {p["source_id"] for p in patterns})
        candidates = self.service.suggestions.refresh(project_id)
        self.assertEqual(candidates[0]["category"], "bug_report")
        self.assertTrue(candidates[0]["personalized"])
        self.memory.expire_source(candidates[0]["evidence"][0]["source_id"])
        self.assertFalse(any(s["personalized"] for s in self.service.suggestions.list(project_id)))

    def test_embedding_status_is_passive_and_setup_has_no_caller_path(self):
        self.memory.embedding = MiniLMEmbedding(self.root / 'search-model')
        with patch('urllib.request.urlopen', side_effect=AssertionError('status_started_network')):
            reply = self.call('memories.embedding_status', {})
        self.assertEqual(reply['status'], 'success', reply)
        self.assertFalse(reply['result']['installed'])
        self.assertFalse(self.memory.embedding._attempted)
        refused = self.call('memories.setup_embedding', {'model_dir': '/unapproved'})
        self.assertNotEqual(refused['status'], 'success', refused)

    def test_embedding_setup_downloads_off_ui_reports_progress_and_reloads_failed_encoder(self):
        old = MiniLMEmbedding(self.root / 'search-model')
        old._attempted = True
        old.unavailable_reason = 'local_embedding_model_not_downloaded'
        self.memory.embedding = old
        ui_thread = threading.get_ident()
        calls = []

        class Response(io.BytesIO):
            def __init__(self, data):
                super().__init__(data)
                self.headers = {'Content-Length': str(len(data))}

        def download(url, **kwargs):
            self.assertNotEqual(threading.get_ident(), ui_thread)
            self.assertIn(MiniLMEmbedding.revision, url)
            calls.append(url)
            return Response(b'synthetic-model' if url.endswith('.onnx') else b'synthetic-tokenizer')

        def validate(candidate, text, **kwargs):
            self.assertEqual((candidate.model_dir / 'model.onnx').read_bytes(), b'synthetic-model')
            self.assertEqual((candidate.model_dir / 'tokenizer.json').read_bytes(), b'synthetic-tokenizer')
            candidate._session = object()  # Deliberate fake inference; real download/job/store path.
            return [1.0] * candidate.dimensions

        with patch('urllib.request.urlopen', side_effect=download), patch.object(MiniLMEmbedding, 'encode', validate):
            started = self.call('memories.setup_embedding', {})
            self.assertEqual(started['status'], 'success', started)
            done = self.finish(started['result']['job_id'])
        self.assertEqual(done['status'], 'succeeded', done)
        self.assertEqual(len(calls), 2)
        self.assertTrue(done['result']['ready'])
        self.assertIsNot(self.memory.embedding, old)
        self.assertTrue(any(e['phase'].startswith('Downloading search model') for e in done['events']))
        self.assertIn('Checking semantic search locally', [e['phase'] for e in done['events']])
        self.assertFalse(self.memory.learning())
        self.assertEqual(self.memory.list(), [])

    def test_embedding_setup_cancel_removes_partial_download_and_keeps_previous_encoder(self):
        old = MiniLMEmbedding(self.root / 'search-model')
        old.model_dir.mkdir()
        (old.model_dir / 'model.onnx').write_bytes(b'previous-model')
        self.memory.embedding = old
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        class Response(io.BytesIO):
            headers = {'Content-Length': '100'}
            def read(self, count=-1):
                entered.set()
                if not release.wait(3):
                    raise AssertionError('cancel_test_not_released')
                return super().read(count)

        with patch('urllib.request.urlopen', return_value=Response(b'x' * 100)):
            started = self.call('memories.setup_embedding', {})
            job_id = started['result']['job_id']
            self.assertTrue(entered.wait(2), 'download did not start')
            cancelled = self.call('intelligence.cancel', {'job_id': job_id})
            self.assertEqual(cancelled['result']['status'], 'cancelled')
            release.set()
            self.service.jobs._queue.join()
        self.assertEqual(self.finish(job_id)['status'], 'cancelled')
        self.assertIs(self.memory.embedding, old)
        self.assertEqual((old.model_dir / 'model.onnx').read_bytes(), b'previous-model')
        self.assertEqual([p.name for p in old.model_dir.iterdir()], ['model.onnx'])

    def test_embedding_validation_failure_does_not_replace_existing_encoder(self):
        old = MiniLMEmbedding(self.root / 'search-model')
        self.memory.embedding = old
        def refuse(candidate, text, **kwargs):
            candidate.unavailable_reason = 'local_embedding_model_unavailable'
            return None
        with patch.object(MiniLMEmbedding, 'download', return_value={}), patch.object(MiniLMEmbedding, 'encode', refuse):
            started = self.call('memories.setup_embedding', {})
            done = self.finish(started['result']['job_id'])
        self.assertEqual(done['status'], 'failed', done)
        self.assertEqual(done['error'], 'local_embedding_model_unavailable')
        self.assertIs(self.memory.embedding, old)

    def test_setup_can_cancel_while_previous_encoder_is_busy(self):
        old = MiniLMEmbedding(self.root / 'search-model')
        self.memory.embedding = old
        validated = threading.Event()
        def download(staged, **kwargs):
            staged.mkdir()
            for name in MiniLMEmbedding.artifacts:
                (staged / name).write_bytes(b'candidate')
        def validate(candidate, text, **kwargs):
            candidate._session = object()
            validated.set()
            return [1.0] * candidate.dimensions
        old._lock.acquire()
        try:
            with patch.object(MiniLMEmbedding, 'download', side_effect=download), patch.object(MiniLMEmbedding, 'encode', validate):
                started = self.call('memories.setup_embedding', {})
                job_id = started['result']['job_id']
                self.assertTrue(validated.wait(2))
                self.service.jobs.cancel(job_id)
                deadline = time.monotonic() + 2
                while self.service.jobs._queue.unfinished_tasks and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertEqual(self.service.jobs._queue.unfinished_tasks, 0)
        finally:
            old._lock.release()
        self.assertIs(self.memory.embedding, old)
        self.assertFalse(old.model_dir.exists())
        self.assertFalse(list(self.root.glob('.search-setup-*')))

    def test_corrupt_complete_cache_is_repaired_only_after_validation(self):
        old = MiniLMEmbedding(self.root / 'search-model')
        old.model_dir.mkdir()
        (old.model_dir / 'model.onnx').write_bytes(b'bad-model')
        (old.model_dir / 'tokenizer.json').write_bytes(b'bad-tokenizer')
        self.memory.embedding = old
        def download(staged, **kwargs):
            staged.mkdir()
            (staged / 'model.onnx').write_bytes(b'good-model')
            (staged / 'tokenizer.json').write_bytes(b'good-tokenizer')
        def validate(candidate, text, **kwargs):
            if (candidate.model_dir / 'model.onnx').read_bytes() == b'bad-model':
                candidate.unavailable_reason = 'local_embedding_model_unavailable'
                return None
            # Nothing is exposed at the live location during staged validation.
            self.assertEqual((old.model_dir / 'model.onnx').read_bytes(), b'bad-model')
            self.assertEqual((candidate.model_dir / 'tokenizer.json').read_bytes(), b'good-tokenizer')
            candidate._session = object()
            return [1.0] * candidate.dimensions
        with patch.object(MiniLMEmbedding, 'download', side_effect=download) as fetched, patch.object(MiniLMEmbedding, 'encode', validate):
            started = self.call('memories.setup_embedding', {})
            done = self.finish(started['result']['job_id'])
        self.assertEqual(done['status'], 'succeeded', done)
        self.assertEqual(fetched.call_count, 1)
        self.assertEqual((old.model_dir / 'model.onnx').read_bytes(), b'good-model')
        self.assertEqual((old.model_dir / 'tokenizer.json').read_bytes(), b'good-tokenizer')
        self.assertFalse(list(old.model_dir.parent.glob('.search-setup-*')))

    def test_failed_cache_publication_restores_previous_generation(self):
        old = MiniLMEmbedding(self.root / 'search-model')
        old.model_dir.mkdir()
        (old.model_dir / 'model.onnx').write_bytes(b'previous-model')
        self.memory.embedding = old
        def download(staged, **kwargs):
            staged.mkdir()
            (staged / 'model.onnx').write_bytes(b'new-model')
            (staged / 'tokenizer.json').write_bytes(b'new-tokenizer')
        def validate(candidate, text, **kwargs):
            candidate._session = object()
            return [1.0] * candidate.dimensions
        real_rename = pathlib.Path.rename
        def rename(path, target):
            if path.name == 'model' and target == old.model_dir:
                raise OSError('synthetic_publish_failure')
            return real_rename(path, target)
        with patch.object(MiniLMEmbedding, 'download', side_effect=download), patch.object(MiniLMEmbedding, 'encode', validate), patch.object(pathlib.Path, 'rename', rename):
            started = self.call('memories.setup_embedding', {})
            done = self.finish(started['result']['job_id'])
        self.assertEqual(done['status'], 'failed', done)
        self.assertIs(self.memory.embedding, old)
        self.assertEqual((old.model_dir / 'model.onnx').read_bytes(), b'previous-model')
        self.assertFalse(list(old.model_dir.parent.glob('.search-setup-*')))


if __name__ == "__main__":
    unittest.main(verbosity=2)
