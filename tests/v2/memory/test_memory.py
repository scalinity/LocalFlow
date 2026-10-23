"""Memory unit/integration tests using the real single-writer Store.

Run: .venv/bin/python -m unittest discover -s tests/v2/memory -v
No desktop capture, provider requests, downloads, or external insertion.
"""

from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np

from localflow.v2.memory import (ContextPack, MEMORY_MIGRATIONS, MemoryStore,
                                RevokedContextError, StaleRevisionError)
from localflow.v2.memory.embeddings import LocalEmbedding, MiniLMEmbedding
from localflow.v2.memory.sources import read_approved_file
from localflow.v2.store import Store, _MIGRATIONS
from retrieval_cases import CASES


class UnavailableEmbedding:
    implementation = 'unavailable-fixture'
    def encode(self, text):
        return None


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.migration = patch.dict(_MIGRATIONS, {15: MEMORY_MIGRATIONS})
        self.migration.start()
        self.now = [100000.0]
        self.store = Store(self.root / 'test.db', now_fn=lambda: self.now[0],
                           backup_dir=self.root / 'backups')
        self.memory = MemoryStore(self.store, embedding=UnavailableEmbedding())
        for name in ('one', 'two'):
            (self.root / name).mkdir()
        self.one = self.memory.create_project('Same name', self.root / 'one')
        self.two = self.memory.create_project('Same name', self.root / 'two')

    def tearDown(self):
        self.store.close()
        self.migration.stop()
        self.temp.cleanup()

    def count(self, table, where='1', params=()):
        return self.store.submit(lambda db: db.execute(
            'SELECT COUNT(*) FROM ' + table + ' WHERE ' + where, params).fetchone()[0])

    def test_cold_start_and_pause_are_useful(self):
        self.assertFalse(self.memory.learning())
        self.assertEqual(self.memory.search('brief').items, ())
        r = self.memory.remember('I prefer brief responses.', kind='preference')
        self.memory.set_learning(False)
        pack = self.memory.search('brief')
        self.assertEqual([r['id']], [i.id for i in pack.items])
        self.assertEqual('lexical_degraded', pack.retrieval_mode)
        self.assertEqual((), self.memory.search('brief', enabled=False).items)
        self.assertEqual([], self.memory.process_learning())
        self.assertEqual(0, self.count('memory_dirty'))
        self.assertEqual((), self.memory.search('brief', include_personal=False).items)
        self.assertEqual([], self.memory.list(include_personal=False))

    def test_explicit_remember_operation_id_is_idempotent(self):
        first = self.memory.remember('A synthetic remembered fact.', record_id='same-operation')
        second = self.memory.remember('A synthetic remembered fact.', record_id='same-operation')
        self.assertEqual(first, second)
        self.assertEqual(1, self.count('memory_records'))
        with self.assertRaises(ValueError):
            self.memory.remember('Different content.', record_id='same-operation')

    def test_scopes_are_explicit_not_app_or_basename(self):
        one = self.memory.remember('The server uses Python.', project_id=self.one)
        two = self.memory.remember('The server uses Rust.', project_id=self.two)
        self.assertEqual((), self.memory.search('server').items)
        self.assertEqual([one['id']], [i.id for i in self.memory.search('server', project_id=self.one).items])
        self.assertEqual([two['id']], [i.id for i in self.memory.search('server', project_id=self.two).items])
        self.assertEqual(self.one, self.memory.resolve_project(path=self.root / 'one'))
        self.assertIsNone(self.memory.resolve_project())
        with self.assertRaises(ValueError):
            self.memory.search('server', project_id='invented')

    def test_scoped_pack_records_available_git_identity_without_importing_files(self):
        import subprocess
        root = self.root / 'one'
        for args in (('init', '-q'), ('remote', 'add', 'origin', 'git@example.test:team/one.git')):
            subprocess.run(['/usr/bin/git', '-C', str(root), *args], check=True, capture_output=True)
        self.memory.remember('The server uses Python.', project_id=self.one)
        pack = self.memory.search('server', project_id=self.one)
        self.assertEqual(len(pack.workspaces), 1)
        self.assertEqual(pack.workspaces[0].remote, 'example.test/team/one')
        self.assertEqual(pack.workspaces[0].root, str(root.resolve()))
        self.assertEqual(pack.workspaces[0].observed_at, self.now[0])
        self.assertEqual(ContextPack.from_dict(pack.to_dict()), pack)
        self.assertEqual(self.count('memory_sources'), 1)
        self.assertFalse(self.memory.search('server', project_id=self.two).workspaces)

    def test_conflict_correction_and_stale_revision(self):
        old = self.memory.remember('The backend uses Python.', project_id=self.one, key='stack')
        new = self.memory.remember('The backend uses Rust.', project_id=self.one, key='stack')
        self.assertEqual((), self.memory.search('backend', project_id=self.one).items)
        rows = {r['id']: r for r in self.memory.list(project_id=self.one)}
        self.assertEqual({'disputed'}, {r['status'] for r in rows.values()})
        with self.assertRaises(StaleRevisionError):
            self.memory.update(old['id'], expected_revision=old['revision'], text='The backend uses Go.')
        fixed = self.memory.update(old['id'], expected_revision=rows[old['id']]['revision'],
                                   text='The backend uses Go.')
        self.assertEqual('active', fixed['status'])
        rows = {r['id']: r for r in self.memory.list(project_id=self.one)}
        self.assertEqual('superseded', rows[new['id']]['status'])
        self.assertEqual([old['id']], [i.id for i in self.memory.search('backend', project_id=self.one).items])
        self.assertGreaterEqual(self.count('memory_revisions', 'memory_id=?', (old['id'],)), 3)

    def test_type_specific_expiry_and_current_instructions(self):
        self.memory.remember('I prefer long answers.', kind='preference')
        self.memory.remember('The current branch is feature-a.', kind='volatile')
        self.now[0] += 86401
        self.assertEqual((), self.memory.search('branch').items)
        pack = self.memory.search('answers', current_instructions='Keep this answer short.')
        self.assertEqual('Keep this answer short.', pack.current_instructions)
        self.assertIn('current-instructions-win', pack.policy)
        self.assertEqual(1, len(pack.items))
        self.assertEqual(1, len(self.memory.list(status='stale')))

    def test_exact_frozen_round_trip_and_fabricated_refs(self):
        self.memory.remember('The queue has one writer.')
        pack = self.memory.search('writer')
        restored = ContextPack.from_dict(json.loads(json.dumps(pack.to_dict())))
        self.assertEqual(pack.fingerprint, restored.fingerprint)
        self.assertTrue(self.memory.assert_current(restored))
        item = pack.items[0]
        fake = replace(item, evidence_refs=(replace(item.evidence_refs[0], source_id='invented'),))
        with self.assertRaises(RevokedContextError):
            self.memory.assert_current(replace(pack, items=(fake,)))
        with self.assertRaises(RevokedContextError):
            self.memory.assert_current(replace(pack, project_id=self.two,
                                               items=(replace(item, scope_id=self.one),)))
        altered = pack.to_dict()
        altered['current_instructions'] = 'different'
        with self.assertRaises(ValueError):
            ContextPack.from_dict(altered)

    def test_learning_sources_and_consent(self):
        sid = self.memory.add_source('I prefer concise answers.', source_id='dictation-1')
        with self.assertRaises(RevokedContextError):
            self.memory.learn([sid], direct=True)
        self.memory.set_learning(True)
        for index, kwargs in enumerate((
                {'kind': 'model_output'}, {'author_role': 'model'},
                {'quoted': True}, {'author_role': 'third_party'},
                {'confidence_label': 'low'}, {'confidence_label': 'uncertain'},
                {'kind': 'selection'}, {'temporary': True}, {'sensitive': True})):
            sid = self.memory.add_source('I prefer detailed answers.', source_id='bad-' + str(index), **kwargs)
            with self.assertRaises(RevokedContextError, msg=str(kwargs)):
                self.memory.learn([sid], direct=True)
        for kwargs in ({'denied': True}, {'secure': True}):
            with self.assertRaises(ValueError):
                self.memory.add_source('Protected content.', **kwargs)
        good = self.memory.add_source('I prefer brief replies.', source_id='dictation-2')
        learned = self.memory.process_learning()
        self.assertEqual([good], [r['evidence_refs'][0]['source_id'] for r in learned])
        self.assertEqual('observed_user', learned[0]['origin'])
        # An invented model paraphrase remains a proposal, not truth.
        proposal = self.memory.learn([good], text='I prefer lengthy replies.', direct=True)
        self.assertEqual('proposed', proposal['status'])
        self.assertEqual((), self.memory.search('lengthy').items)

    def test_independent_support_and_contradiction(self):
        self.memory.set_learning(True)
        a = self.memory.add_source('I prefer terse replies.', source_id='a')
        b = self.memory.add_source('I prefer terse replies.', source_id='b')
        proposed = self.memory.learn([a, b], key='length')
        self.assertEqual('proposed', proposed['status'])
        c = self.memory.add_source('I prefer terse replies.', source_id='c', independent_key='observation-c')
        d = self.memory.add_source('I prefer terse replies.', source_id='d', independent_key='observation-d')
        active = self.memory.learn([c, d], key='length')
        self.assertEqual('active', active['status'])
        e = self.memory.add_source('I prefer elaborate replies.', source_id='e')
        disputed = self.memory.learn([e], direct=True, key='length')
        self.assertEqual('disputed', disputed['status'])
        self.assertEqual((), self.memory.search('replies').items)

    def test_automatic_conflict_cannot_displace_confirmed_fact(self):
        explicit = self.memory.remember('I prefer terse replies.', kind='preference', key='length')
        self.memory.set_learning(True)
        sid = self.memory.add_source('I prefer elaborate replies.')
        disputed = self.memory.learn([sid], direct=True, key='length')
        self.assertEqual('disputed', disputed['status'])
        self.assertEqual([explicit['id']], [i.id for i in self.memory.search('replies').items])

    def test_correction_becomes_independent_then_forget_purges_history(self):
        self.memory.set_learning(True)
        sid = self.memory.add_source('I prefer cyan.', source_id='speech-source')
        r = self.memory.learn([sid], direct=True)
        fixed = self.memory.update(r['id'], expected_revision=1, text='I prefer magenta.')
        self.memory.expire_source(sid)
        self.assertEqual([r['id']], [i.id for i in self.memory.search('magenta').items])
        pack = self.memory.search('magenta')
        self.assertTrue(self.memory.forget(r['id']))
        self.assertFalse(self.memory.forget(r['id']))
        self.assertEqual(0, self.count('memory_revisions'))
        self.assertEqual(0, self.count('memory_fts'))
        self.assertEqual(0, self.count('memory_vectors'))
        self.assertEqual(0, self.count('memory_evidence'))
        source = fixed['evidence_refs'][0]['source_id']
        self.assertIsNone(self.memory.read_source(source))
        with self.assertRaises(RevokedContextError):
            self.memory.publish_if_current(pack, lambda db: 'late suggestion')
        # The unchanged history source cannot be re-extracted.
        self.memory.add_source('I prefer cyan.', source_id=sid)
        self.assertIsNone(self.memory.read_source(sid))

    def test_exclusion_rejects_existing_and_future_sources(self):
        self.memory.set_learning(True)
        sid = self.memory.add_source('I prefer tiny paragraphs.', app_id='example.app')
        self.memory.learn([sid], direct=True)
        pack = self.memory.search('paragraphs')
        self.memory.exclude('app', 'example.app')
        self.assertEqual((), self.memory.search('paragraphs').items)
        with self.assertRaises(RevokedContextError):
            self.memory.assert_current(pack)
        future = self.memory.add_source('I prefer bullets.', app_id='example.app')
        with self.assertRaises(RevokedContextError):
            self.memory.learn([future], direct=True)

    def test_imports_limits_secrets_symlinks_and_changes(self):
        root = self.root / 'one'
        (root / 'README.md').write_text('A synthetic project uses Python.')
        records = self.memory.import_files(self.one, ['README.md'])
        again = self.memory.import_files(self.one, ['README.md'])
        self.assertEqual(records[0]['id'], again[0]['id'])
        for name, content in (('.env', 'password=abcdefghijk'),
                              ('key.md', '-----BEGIN PRIVATE KEY-----'),
                              ('binary.md', '\x00binary')):
            (root / name).write_text(content)
            with self.assertRaises(ValueError):
                self.memory.import_files(self.one, [name])
        (self.root / 'outside.md').write_text('Unrelated.')
        (root / 'escape.md').symlink_to(self.root / 'outside.md')
        with self.assertRaises(ValueError):
            self.memory.import_files(self.one, ['escape.md'])
        (root / 'node_modules').mkdir()
        (root / 'node_modules' / 'cache.md').write_text('cached dependency')
        with self.assertRaises(ValueError):
            read_approved_file(str(root), 'node_modules/cache.md')
        with self.assertRaises(ValueError):
            self.memory.import_files(self.one, ['README.md'] * 17)
        (root / 'README.md').write_text('A synthetic project uses Rust.')
        changed = self.memory.import_files(self.one, ['README.md'])
        self.assertNotEqual(records[0]['id'], changed[0]['id'])
        self.assertEqual([changed[0]['id']], [i.id for i in self.memory.search('project', project_id=self.one).items])
        self.memory.forget(changed[0]['id'])
        self.assertEqual([], self.memory.import_files(self.one, ['README.md']))

    def test_context_budget_never_splits_facts(self):
        self.memory.remember('Constraint ' + 'mandatory ' * 100)
        pack = self.memory.search('Constraint', token_budget=100)
        self.assertEqual((), pack.items)
        self.assertIn('context_budget', [reason for _, reason in pack.omitted])
        with self.assertRaises(ValueError):
            self.memory.search('Constraint', limit=100000)

    def test_project_brief_pin_does_not_include_unrelated_personal_facts(self):
        brief = self.memory.remember('This project processes synthetic speech.',
                                     project_id=self.one, user_pinned=True)
        self.memory.remember('A personal note about gardening.', user_pinned=True)
        pack = self.memory.search('unrelated query', project_id=self.one)
        self.assertEqual([brief['id']], [i.id for i in pack.items])
        self.assertIn('pinned_project_context', pack.items[0].reason)

    def test_live_file_change_revokes_frozen_pack_without_reimport(self):
        path = self.root / 'one' / 'README.md'
        path.write_text('The synthetic database is SQLite.')
        self.memory.import_files(self.one, ['README.md'])
        pack = self.memory.search('database', project_id=self.one)
        self.assertEqual(1, len(pack.items))
        path.write_text('The synthetic database is PostgreSQL.')
        with self.assertRaises(RevokedContextError):
            self.memory.publish_if_current(pack, lambda db: 'stale draft')
        self.assertEqual((), self.memory.search('database', project_id=self.one).items)

    def test_additional_approved_worktree_retains_distinct_live_path(self):
        extra = self.root / 'new-worktree'
        extra.mkdir()
        revision = self.memory.approve_root(self.one, extra, expected_revision=1)
        self.assertEqual(2, revision)
        self.assertEqual(self.one, self.memory.resolve_project(path=extra))
        (extra / 'plan.md').write_text('A worktree-specific approved note.')
        imported = self.memory.import_files(self.one, [str(extra / 'plan.md')])
        self.assertEqual(self.one, imported[0]['scope_id'])
        with self.assertRaises(ValueError):
            self.memory.approve_root(self.two, extra, expected_revision=1)
        with self.assertRaises(StaleRevisionError):
            self.memory.approve_root(self.one, extra, expected_revision=1)
        with self.assertRaises(ValueError):
            self.memory.create_project('Too broad', Path.home())

    def test_pin_does_not_confirm_proposal_and_cancel_prevents_learning(self):
        self.memory.set_learning(True)
        sid = self.memory.add_source('A deliberately ambiguous user utterance.')
        proposed = self.memory.learn([sid], text='A proposed personal fact.')
        pinned = self.memory.update(proposed['id'], expected_revision=1, user_pinned=True)
        self.assertEqual('proposed', pinned['status'])
        self.assertEqual((), self.memory.search('personal').items)
        good = self.memory.add_source('I prefer pencil notes.')
        with self.assertRaises(RevokedContextError):
            self.memory.learn([good], direct=True, cancelled=lambda: True)
        self.assertEqual(1, self.count('memory_records'))
        off = self.memory.search('anything', enabled=False)
        self.memory.forget_all()
        self.assertTrue(self.memory.assert_current(off))

    def test_atomic_publication_and_transaction_rollback(self):
        r = self.memory.remember('The fact is current.')
        pack = self.memory.search('fact')
        value = self.memory.publish_if_current(pack, lambda db: db.execute(
            "INSERT INTO memory_state VALUES('synthetic-publication',1)").rowcount)
        self.assertEqual(1, value)
        self.memory.forget(r['id'])
        with self.assertRaises(RevokedContextError):
            self.memory.publish_if_current(pack, lambda db: db.execute(
                "UPDATE memory_state SET value=2 WHERE key='synthetic-publication'"))
        self.assertEqual(1, self.store.submit(lambda db: db.execute(
            "SELECT value FROM memory_state WHERE key='synthetic-publication'").fetchone()[0]))
        empty = self.memory.search('nothing')
        def failed(db):
            db.execute("UPDATE memory_state SET value=3 WHERE key='synthetic-publication'")
            raise ValueError('failed_result')
        with self.assertRaises(ValueError):
            self.memory.publish_if_current(empty, failed)
        self.assertEqual(1, self.store.submit(lambda db: db.execute(
            "SELECT value FROM memory_state WHERE key='synthetic-publication'").fetchone()[0]))

    def test_delete_during_indexing_cannot_restore_vector(self):
        r = self.memory.remember('The synthetic bird sings.')
        entered, release = threading.Event(), threading.Event()
        class BlockingEmbedding:
            implementation = 'synthetic-test-vector'
            def encode(self, text):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError('fixture_wait_timeout')
                return np.ones(8, dtype='<f4') / np.sqrt(8)
        self.memory.embedding = BlockingEmbedding()
        outcomes = []
        worker = threading.Thread(target=lambda: outcomes.append(self.memory.index_pending()))
        worker.start()
        self.assertTrue(entered.wait(5))
        self.memory.forget(r['id'])
        release.set()
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual([0], outcomes)
        self.assertEqual(0, self.count('memory_vectors'))

    def test_expiry_during_indexing_does_not_publish_vector(self):
        self.memory.remember('The synthetic temporary bird sings.', kind='volatile')
        clock = self.now
        class ExpiringEmbedding:
            implementation = 'synthetic-expiry-vector'
            def encode(self, text):
                clock[0] += 86401
                return np.ones(8, dtype='<f4') / np.sqrt(8)
        self.memory.embedding = ExpiringEmbedding()
        self.assertEqual(0, self.memory.index_pending())
        self.assertEqual(0, self.count('memory_vectors'))

    def test_delete_during_extraction_rejects_completion(self):
        self.memory.set_learning(True)
        sid = self.memory.add_source('I prefer quiet rooms.', source_id='pending-extraction')
        rev = self.memory.revision()
        self.memory.expire_source(sid)
        with self.assertRaises(RevokedContextError):
            self.memory._remember('I prefer quiet rooms.', source_ids=(sid,), automatic=True,
                                  expected_revocation=rev)
        self.assertEqual(0, self.count('memory_records'))

    def test_delete_during_retrieval_rejects_snapshot(self):
        r = self.memory.remember('The synthetic meadow is green.')
        original = self.memory._run
        def interleaved(fn):
            result = original(fn)
            if fn.__name__ == 'read':
                self.memory.forget(r['id'])
            return result
        with patch.object(self.memory, '_run', interleaved):
            with self.assertRaises(RevokedContextError):
                self.memory.search('meadow')

    def test_source_expiry_and_pause_revoke_inflight_learning(self):
        self.memory.set_learning(True)
        sid = self.memory.add_source('I prefer quiet rooms.', expires_at=self.now[0] + 10)
        r = self.memory.learn([sid], direct=True)
        pack = self.memory.search('quiet')
        self.now[0] += 11
        self.assertEqual((), self.memory.search('quiet').items)
        with self.assertRaises(RevokedContextError):
            self.memory.assert_current(pack)
        sid2 = self.memory.add_source('I prefer blue ink.')
        rev = self.memory.revision()
        self.memory.set_learning(False)
        with self.assertRaises(RevokedContextError):
            self.memory._remember('I prefer blue ink.', source_ids=(sid2,), automatic=True,
                                  expected_revocation=rev)
        self.assertEqual(1, self.count('memory_records'))

    def test_existing_store_job_deletion_barrier_invalidates_memory(self):
        self.memory.set_learning(True)
        sid = self.memory.add_source('I prefer quiet rooms.', job_id='synthetic-job')
        self.memory.learn([sid], direct=True)
        pack = self.memory.search('quiet')
        self.store.submit(lambda db: db.execute(
            'INSERT INTO job_deletions(job_id,reason,deleted_at_utc) VALUES(?,?,?)',
            ('synthetic-job', 'deleted', '2026-01-01T00:00:00Z')))
        self.assertEqual((), self.memory.search('quiet').items)
        with self.assertRaises(RevokedContextError):
            self.memory.assert_current(pack)
        with self.assertRaises(RevokedContextError):
            self.memory.learn([sid], direct=True)

    def test_delete_everywhere_purges_derived_memory_but_keeps_independent_correction(self):
        self.memory.set_learning(True)
        job_id = 'synthetic-deleted-dictation'
        sid = self.memory.add_source('I prefer quiet rooms.', job_id=job_id)
        derived = self.memory.learn([sid], direct=True)
        corrected_sid = self.memory.add_source('I prefer blue ink.', job_id=job_id)
        corrected = self.memory.learn([corrected_sid], direct=True)
        corrected = self.memory.update(corrected['id'], expected_revision=corrected['revision'],
                                       text='I prefer violet ink.')
        unrelated = self.memory.remember('I prefer wide margins.')

        class FixedEmbedding:
            implementation = 'synthetic-deletion-vector'

            def encode(self, text):
                return np.array([1.0, 0.0], dtype=np.float32)

        self.memory.embedding = FixedEmbedding()
        self.memory.index_pending()
        pack = self.memory.search('quiet')
        self.assertIn(derived['id'], {item.id for item in pack.items})
        self.assertEqual(1, self.count('memory_vectors', 'memory_id=?', (derived['id'],)))

        self.store.delete_everywhere('job', job_id)

        for table in ('memory_fts', 'memory_vectors', 'memory_evidence', 'memory_revisions'):
            self.assertEqual(0, self.count(table, 'memory_id=?', (derived['id'],)), table)
        row = self.store.submit(lambda db: db.execute(
            'SELECT text,data FROM memory_records WHERE id=?', (derived['id'],)).fetchone())
        self.assertEqual('', row[0])
        self.assertEqual('forgotten', json.loads(row[1])['status'])
        self.assertEqual('', json.loads(row[1])['text'])
        self.assertEqual([], json.loads(row[1])['evidence_refs'])
        for source_id in (sid, corrected_sid):
            self.assertEqual(0, self.count('memory_sources', "id=? AND text<>''", (source_id,)))
        # An explicit correction is independent evidence; only its old lineage goes.
        retained = {r['id']: r for r in self.memory.list(status='active')}
        self.assertEqual('I prefer violet ink.', retained[corrected['id']]['text'])
        self.assertIn(unrelated['id'], retained)
        revisions = self.store.submit(lambda db: db.execute(
            'SELECT data FROM memory_revisions WHERE memory_id=?', (corrected['id'],)).fetchall())
        self.assertTrue(revisions)
        self.assertTrue(all('blue ink' not in r[0] for r in revisions))
        with self.assertRaises(RevokedContextError):
            self.memory.assert_current(pack)
        revision = self.memory.revision()
        self.store.delete_everywhere('job', job_id)
        self.assertEqual(revision, self.memory.revision())
        with self.assertRaises(RevokedContextError):
            self.memory.add_source('A late extraction source.', job_id=job_id)
        with self.assertRaises(RevokedContextError):
            self.memory.add_source('A late source keyed by the job.', source_id=job_id)

        self.store.close()
        self.store = Store(self.root / 'test.db', now_fn=lambda: self.now[0])
        self.memory = MemoryStore(self.store, embedding=UnavailableEmbedding())
        self.assertEqual((), self.memory.search('quiet').items)
        self.assertEqual({corrected['id']}, {i.id for i in self.memory.search('violet').items})

    def test_delete_everywhere_rolls_back_memory_cleanup_with_tombstone(self):
        self.memory.set_learning(True)
        sid = self.memory.add_source('I prefer quiet rooms.', job_id='synthetic-rollback')
        record = self.memory.learn([sid], direct=True)

        def fail_after_write(db, job_id, now):
            db.execute('DELETE FROM memory_fts WHERE memory_id=?', (record['id'],))
            raise RuntimeError('synthetic memory cleanup failure')

        with patch('localflow.v2.memory.deletion.purge_job', side_effect=fail_after_write):
            with self.assertRaisesRegex(RuntimeError, 'synthetic memory cleanup failure'):
                self.store.delete_everywhere('job', 'synthetic-rollback')
        self.assertFalse(self.store.job_deleted('synthetic-rollback'))
        self.assertEqual(1, self.count('memory_fts', 'memory_id=?', (record['id'],)))
        self.assertEqual({record['id']}, {i.id for i in self.memory.search('quiet').items})

    def test_delete_everywhere_purges_joint_inference_without_deleting_other_source(self):
        self.memory.set_learning(True)
        deleted = self.memory.add_source('I prefer quiet rooms.', job_id='synthetic-joint')
        retained = self.memory.add_source('I prefer violet ink.', job_id='synthetic-retained')
        independent = self.memory.learn([retained], direct=True)
        combined = self.memory._remember('I prefer quiet rooms and violet ink.',
                                        source_ids=(deleted, retained), automatic=True)
        self.store.delete_everywhere('job', 'synthetic-joint')
        # A remaining source cannot establish every fact in the combined text.
        # Preserve that source and its own memory, not a partly revoked inference.
        self.assertIsNotNone(self.memory.read_source(retained))
        active = {r['id'] for r in self.memory.list(status='active')}
        self.assertIn(independent['id'], active)
        self.assertNotIn(combined['id'], active)
        self.assertEqual(0, self.count('memory_fts', 'memory_id=?', (combined['id'],)))
        self.assertEqual(1, self.count('memory_evidence', 'memory_id=?', (independent['id'],)))

    def test_restart_preserves_records_learning_off_and_forgotten_barrier(self):
        r = self.memory.remember('I prefer violet ink.', kind='preference')
        removed = self.memory.remember('A transient discarded fact.')
        self.memory.forget(removed['id'])
        self.store.close()
        self.store = Store(self.root / 'test.db', now_fn=lambda: self.now[0])
        self.memory = MemoryStore(self.store, embedding=UnavailableEmbedding())
        self.assertFalse(self.memory.learning())
        self.assertEqual([r['id']], [i.id for i in self.memory.search('violet').items])
        self.assertEqual((), self.memory.search('discarded').items)
        self.memory.forget_all()
        self.assertEqual((), self.memory.search('violet').items)
        self.assertEqual(0, self.count('memory_sources', "text<>''"))

    def test_real_local_semantic_quality_and_latency(self):
        self.memory.embedding = MiniLMEmbedding()
        started = time.perf_counter()
        if self.memory.embedding.encode('A synthetic local retrieval check.') is None:
            self.skipTest('Pinned MiniLM CPU model unavailable; lexical tests still run')
        cold_ms = (time.perf_counter() - started) * 1000
        ids = {}
        for key, text, _ in CASES:
            ids[key] = self.memory.remember(text, project_id=self.one, key=key)['id']
            self.memory.remember('Other workspace: ' + text, project_id=self.two, key=key)
        # A stale and a disputed fact must never displace relevant eligible data.
        self.memory.remember('The temporary local branch is stale.', project_id=self.one, kind='volatile')
        self.now[0] += 86401
        self.memory.remember('The disputed audio uses 22000 Hz.', project_id=self.one, key='disputed')
        self.memory.remember('The disputed audio uses 44000 Hz.', project_id=self.one, key='disputed')
        self.memory.index_pending(project_id=self.one)
        timings, hits, semantic_only, leaked = [], 0, 0, 0
        for key, _, query in CASES:
            start = time.perf_counter()
            pack = self.memory.search(query, project_id=self.one, include_personal=False)
            timings.append((time.perf_counter() - start) * 1000)
            hits += ids[key] in {i.id for i in pack.items}
            semantic_only += any(i.id == ids[key] and i.reason == 'semantic' for i in pack.items)
            leaked += sum(i.scope_id != self.one for i in pack.items)
        report = dict(queries=len(CASES), recall_at_5=hits / len(CASES),
                      cross_scope_disclosures=leaked, semantic_only_hits=semantic_only,
                      cold_model_ms=round(cold_ms, 2), p50_ms=round(float(np.median(timings)), 2),
                      p95_ms=round(float(np.percentile(timings, 95)), 2),
                      implementation=self.memory.embedding.implementation)
        print('\nLOCAL_MEMORY_RETRIEVAL ' + json.dumps(report, sort_keys=True))
        self.assertGreaterEqual(hits / len(CASES), 0.90, report)
        self.assertGreater(semantic_only, 0, report)
        self.assertEqual(0, leaked)
        self.assertEqual((), self.memory.search('audio', enabled=False, project_id=self.one).items)


class MigrationTests(unittest.TestCase):
    def test_upgrade_failure_rollback_retry_idempotence_and_restart(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'upgrade.db'
            with patch.dict(_MIGRATIONS, {}, clear=False):
                for version in list(_MIGRATIONS):
                    if version >= 15:
                        _MIGRATIONS.pop(version)
                store = Store(path)
                store.submit(lambda db: db.execute("INSERT INTO transform_meta VALUES('synthetic-setting','kept')"))
                store.close()
            with patch.dict(_MIGRATIONS, {15: MEMORY_MIGRATIONS + ['INVALID MIGRATION STATEMENT']}):
                with self.assertRaises(sqlite3.DatabaseError):
                    Store(path, backup_dir=Path(td) / 'backups')
            with sqlite3.connect(path) as db:
                self.assertEqual('14', db.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0])
                self.assertEqual(0, db.execute("SELECT count(*) FROM sqlite_master WHERE name='memory_records'").fetchone()[0])
            with patch.dict(_MIGRATIONS, {15: MEMORY_MIGRATIONS}):
                store = Store(path, backup_dir=Path(td) / 'backups')
                self.assertEqual('kept', store.submit(lambda db: db.execute(
                    "SELECT value FROM transform_meta WHERE key='synthetic-setting'").fetchone()[0]))
                def rerun(db):
                    for sql in MEMORY_MIGRATIONS:
                        db.execute(sql)
                store.submit(rerun)
                store.close()
                restarted = Store(path)
                self.assertEqual([], MemoryStore(restarted).projects())
                restarted.close()


if __name__ == '__main__':
    unittest.main()
