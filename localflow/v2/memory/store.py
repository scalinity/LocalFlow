"""Scoped factual memory over Store.submit, with revision-bound publication.

All public calls are synchronous; call search/index/import/learning from the
existing bounded job service. No network, model inference, or file reads run in
the SQLite writer. Explicit UI writes create independent user evidence. Merely
selecting, accepting or generating transform text never calls remember().
"""

from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path
import re
import time
from uuid import uuid4

import numpy as np

from .embeddings import LocalEmbedding
from .models import (ContextItem, ContextPack, EvidenceRef, RevokedContextError,
                     StaleRevisionError, canonical, digest)
from .sources import (MAX_IMPORT_FILES, approved_root, eligibility,
                      read_approved_file, text_checked)

# Preferences do not expire by age alone; state and external claims do.
DEFAULT_FRESHNESS = {'preference': None, 'workflow': 180 * 86400,
                     'alias': None, 'project_fact': 90 * 86400,
                     'decision': None, 'note': None, 'volatile': 86400,
                     'historical_claim': 7 * 86400}
MAX_RECORDS = 10_000
MAX_CONTEXT_ITEMS = 32
_QUERY_STOP_WORDS = frozenset('a an the is are was were of to in on for and or with '
                            'from be been my i it its this that which what how should '
                            'as by than while even can do does their at only when '
                            'into has have every one through where them rather '
                            'use uses using must'.split())


def _id(prefix):
    return prefix + '_' + uuid4().hex


def _state(db, key):
    return int(db.execute('SELECT value FROM memory_state WHERE key=?', (key,)).fetchone()[0])


def _bump(db):
    db.execute("UPDATE memory_state SET value=value+1 WHERE key='revocation'")
    return _state(db, 'revocation')


def _record(db, record_id):
    row = db.execute('SELECT data FROM memory_records WHERE id=?', (record_id,)).fetchone()
    return json.loads(row[0]) if row else None


def _source(db, source_id):
    row = db.execute('SELECT data, text, revision, status, content_hash FROM memory_sources '
                     'WHERE id=?', (source_id,)).fetchone()
    if not row:
        return None
    return {**json.loads(row[0]), 'text': row[1], 'revision': row[2],
            'status': row[3], 'content_hash': row[4]}


def _write_record(db, record):
    r = record
    db.execute('INSERT INTO memory_records VALUES(?,?,?,?,?,?,?,?,?,?,?) '
               'ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,kind=excluded.kind,'
               'scope_id=excluded.scope_id,subject=excluded.subject,predicate=excluded.predicate,'
               'text=excluded.text,status=excluded.status,valid_until=excluded.valid_until,'
               'updated_at=excluded.updated_at,data=excluded.data',
               (r['id'], r['revision'], r['kind'], r['scope_id'], r['subject'],
                r['key'], r['text'], r['status'], r['valid_until'], r['updated_at'],
                canonical(r)))


# Uses database-current source authority before either ranking path. A source
# revision mismatch invalidates all derived rows rather than trusting old text.
_LIVE = """m.status='active' AND (m.valid_until IS NULL OR m.valid_until>?)
 AND json_extract(m.data, '$.retrieval_enabled')=1
 AND EXISTS (SELECT 1 FROM memory_evidence e WHERE e.memory_id=m.id)
 AND NOT EXISTS (
   SELECT 1 FROM memory_evidence e LEFT JOIN memory_sources s ON s.id=e.source_id
   WHERE e.memory_id=m.id AND (s.id IS NULL OR s.status<>'active'
     OR s.revision<>e.source_revision OR s.content_hash<>e.content_hash
     OR (s.expires_at IS NOT NULL AND s.expires_at<=?)
     OR EXISTS (SELECT 1 FROM job_deletions j WHERE
       j.job_id=s.id OR j.job_id=json_extract(s.data, '$.job_id'))
     OR EXISTS (SELECT 1 FROM memory_exclusions x WHERE
       (x.kind='source' AND x.value=s.id) OR
       (x.kind='project' AND x.value=s.project_id) OR
       (x.kind='app' AND x.value=json_extract(s.data, '$.app_id')))))
 AND NOT EXISTS (SELECT 1 FROM memory_exclusions x
   WHERE x.kind='project' AND x.value=m.scope_id)"""


class MemoryStore:
    def __init__(self, store, *, clock=None, embedding=None, freshness=None):
        self.store = store
        self.clock = clock or getattr(store, 'now_fn', time.time)
        from .embeddings import MiniLMEmbedding
        self.embedding = embedding if embedding is not None else MiniLMEmbedding()
        self.freshness = {**DEFAULT_FRESHNESS, **(freshness or {})}

    def _run(self, fn):
        # Preserve domain exception types across Store's content-free error
        # boundary while rolling back this operation before returning an error.
        def op(db):
            db.execute('SAVEPOINT memory_operation')
            try:
                result = fn(db)
            except Exception as error:
                db.execute('ROLLBACK TO memory_operation')
                db.execute('RELEASE memory_operation')
                return False, error
            db.execute('RELEASE memory_operation')
            return True, result
        ok, result = self.store.submit(op)
        if not ok:
            raise result
        return result

    def revision(self):
        return self._run(lambda db: _state(db, 'revocation'))

    def projects(self):
        def op(db):
            result = [dict(zip(('id', 'name', 'root', 'revision', 'created_at'), row))
                      for row in db.execute('SELECT * FROM memory_projects ORDER BY name,id')]
            for project in result:
                project['roots'] = [r[0] for r in db.execute(
                    'SELECT root FROM memory_roots WHERE project_id=? ORDER BY root', (project['id'],))]
            return result
        return self._run(op)

    def create_project(self, name, root):
        name = text_checked(name, max_length=160)
        root = str(approved_root(root))
        project = {'id': _id('project'), 'name': name, 'root': root,
                   'revision': 1, 'created_at': self.clock()}
        def op(db):
            old = db.execute('SELECT project_id FROM memory_roots WHERE root=?', (root,)).fetchone()
            if old:
                return old[0]
            db.execute('INSERT INTO memory_projects VALUES(?,?,?,?,?)', tuple(project.values()))
            db.execute('INSERT INTO memory_roots VALUES(?,?)', (project['id'], root))
            _bump(db)
            return project['id']
        return self._run(op)

    def approve_root(self, project_id, root, *, expected_revision):
        """Explicitly associate another worktree without conflating live paths."""
        root = str(approved_root(root))
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError('expected_revision_required')
        def op(db):
            self._check_project(db, project_id)
            revision = db.execute('SELECT revision FROM memory_projects WHERE id=?', (project_id,)).fetchone()[0]
            if revision != expected_revision:
                raise StaleRevisionError('stale_project_revision')
            owner = db.execute('SELECT project_id FROM memory_roots WHERE root=?', (root,)).fetchone()
            if owner:
                if owner[0] != project_id:
                    raise ValueError('root_already_associated')
                return revision
            if db.execute('SELECT COUNT(*) FROM memory_roots WHERE project_id=?', (project_id,)).fetchone()[0] >= 8:
                raise ValueError('approved_root_limit')
            db.execute('INSERT INTO memory_roots VALUES(?,?)', (project_id, root))
            db.execute('UPDATE memory_projects SET revision=revision+1 WHERE id=?', (project_id,))
            _bump(db)
            return revision + 1
        return self._run(op)

    def resolve_project(self, *, path=None):
        """Only a verified document/workspace path identifies a project.

        No app/window-title/last-used fallback. Distinct worktrees keep their
        resolved paths; the caller may explicitly select a shared project ID.
        """
        if path is None:
            return None
        resolved = Path(path).resolve(strict=True)
        matches = [(p['id'], root) for p in self.projects() for root in p['roots']
                   if resolved.is_relative_to(Path(root))]
        return max(matches, key=lambda p: len(p[1]))[0] if matches else None

    @staticmethod
    def _check_project(db, project_id):
        if project_id is not None and not db.execute(
                'SELECT 1 FROM memory_projects WHERE id=?', (project_id,)).fetchone():
            raise ValueError('unknown_project')

    def learning(self):
        return bool(self._run(lambda db: _state(db, 'learning')))

    def set_learning(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('learning_must_be_boolean')
        def op(db):
            db.execute("UPDATE memory_state SET value=? WHERE key='learning'", (int(enabled),))
            _bump(db)
            if not enabled:
                db.execute('DELETE FROM memory_dirty')
            return enabled
        return self._run(op)

    def add_source(self, text, *, kind='user_instruction', author_role='user',
                   project_id=None, source_id=None, expected_revision=None,
                   confidence_label='high', independent_key=None, expires_at=None,
                   app_id=None, job_id=None, secure=False, denied=False, quoted=False,
                   temporary=False, sensitive=False, path=None):
        """Register host-attributed activity, never a model-supplied role.

        A stable source_id should be the existing dictation/job ID. This makes
        copies of a source one observation and lets expire_source invalidate it.
        """
        text = text_checked(text)
        if kind not in {'explicit_user', 'user_instruction', 'user_dictation',
                        'manual_correction', 'imported_note', 'project_file',
                        'model_output', 'selection', 'third_party'}:
            raise ValueError('invalid_source_kind')
        if author_role not in {'user', 'approved_document', 'model', 'third_party', 'unknown'}:
            raise ValueError('invalid_author_role')
        if confidence_label not in {'high', 'low', 'uncertain'}:
            raise ValueError('invalid_confidence')
        if expires_at is not None and (type(expires_at) not in (int, float) or not math.isfinite(expires_at)):
            raise ValueError('invalid_source_expiry')
        if app_id is not None:
            app_id = text_checked(app_id, max_length=300)
        if job_id is not None:
            job_id = text_checked(job_id, max_length=300)
        if any(type(v) is not bool for v in (secure, denied, quoted, temporary, sensitive)):
            raise ValueError('invalid_source_flags')
        sid, content_hash = source_id or _id('source'), digest(text)
        source = dict(id=sid, kind=kind, author_role=author_role,
                      project_id=project_id, confidence_label=confidence_label,
                      independent_key=independent_key or content_hash, app_id=app_id, job_id=job_id,
                      secure=secure, denied=denied, quoted=quoted, temporary=temporary,
                      sensitive=sensitive, path=path, expires_at=expires_at)
        permitted, _ = eligibility(source)
        # Excluded content is never retained, even as a proposal.
        if secure or denied:
            raise ValueError('denied_source')
        def op(db):
            self._check_project(db, project_id)
            if db.execute('SELECT 1 FROM job_deletions WHERE job_id=? OR job_id=?',
                          (sid, job_id)).fetchone():
                raise RevokedContextError('deleted_source')
            old = _source(db, sid)
            if old and old['content_hash'] == content_hash and all(
                    old.get(k) == v for k, v in source.items()):
                return sid
            if old and expected_revision != old['revision']:
                raise StaleRevisionError('stale_source_revision')
            if not old and db.execute('SELECT COUNT(*) FROM memory_sources').fetchone()[0] >= 20_000:
                raise ValueError('memory_source_capacity_reached')
            suppressed = db.execute('SELECT 1 FROM memory_suppressed WHERE '
                                    'source_id=? AND content_hash=?', (sid, content_hash)).fetchone()
            revision = old['revision'] + 1 if old else 1
            status = 'active' if permitted and not suppressed else 'excluded'
            db.execute('INSERT INTO memory_sources VALUES(?,?,?,?,?,?,?,?) '
                       'ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,text=excluded.text,'
                       'content_hash=excluded.content_hash,project_id=excluded.project_id,'
                       'status=excluded.status,expires_at=excluded.expires_at,data=excluded.data',
                       (sid, revision, text if not suppressed else '', content_hash,
                        project_id, status, expires_at, canonical(source)))
            rev = _bump(db)
            if old:
                self._invalidate_linked(db, sid, 'stale')
            if status == 'active' and _state(db, 'learning') and eligibility(source, automatic=True)[0]:
                db.execute('INSERT OR REPLACE INTO memory_dirty VALUES(?,?,?)', (sid, revision, rev))
            return sid
        return self._run(op)

    def read_source(self, source_id):
        def op(db):
            source = _source(db, source_id)
            if not source or not self._source_current(db, source):
                return None
            return source
        return self._run(op)

    def refresh_files(self, *, project_id=None, source_ids=None, limit=32):
        """Recheck a bounded set of approved files; never expand or crawl roots.

        Changed/missing files lose authority until an explicit reimport. Reads
        happen off the writer; the revocation itself is serialized with jobs.
        """
        if type(limit) is not int or not 1 <= limit <= 64:
            raise ValueError('invalid_file_refresh_limit')
        selected = set(source_ids) if source_ids is not None else None
        if selected is not None and len(selected) > 512:
            raise ValueError('file_refresh_limit')
        projects = {p['id']: p for p in self.projects()}
        sql = (
            "SELECT id,data,content_hash FROM memory_sources WHERE status='active' "
            "AND json_extract(data,'$.kind')='project_file' AND project_id IS ?")
        params = [project_id]
        if selected is not None:
            if not selected:
                return 0
            sql += ' AND id IN (' + ','.join('?' for _ in selected) + ')'
            params.extend(sorted(selected))
        rows = self._run(lambda db: db.execute(sql + ' ORDER BY id LIMIT ?',
                                              (*params, limit)).fetchall())
        refreshed = 0
        for sid, raw, content_hash in rows:
            if selected is not None and sid not in selected:
                continue
            if refreshed == limit:
                break
            refreshed += 1
            source = json.loads(raw)
            project = projects.get(source['project_id'])
            try:
                if not project:
                    raise ValueError('unknown_project')
                roots = [root for root in project['roots']
                         if Path(source['path']).is_relative_to(Path(root))]
                if not roots:
                    raise ValueError('outside_approved_root')
                _, text = read_approved_file(max(roots, key=len), source['path'])
                changed = digest(text) != content_hash
            except (OSError, ValueError):
                changed = True
            if changed:
                self.expire_source(sid, reason='expired')
        return refreshed

    def _source_current(self, db, source):
        if source['status'] != 'active' or (source.get('expires_at') is not None
                                           and source['expires_at'] <= self.clock()):
            return False
        if db.execute('SELECT 1 FROM job_deletions WHERE job_id=? OR job_id=?',
                      (source['id'], source.get('job_id'))).fetchone():
            return False
        return not db.execute('SELECT 1 FROM memory_exclusions WHERE '
                              "(kind='source' AND value=?) OR (kind='project' AND value=?) "
                              "OR (kind='app' AND value=?)",
                              (source['id'], source['project_id'], source.get('app_id'))).fetchone()

    def remember(self, text, *, kind='note', project_id=None, subject='user', key=None,
                 user_pinned=False, valid_until=None, record_id=None):
        """Deliberate Remember UI action; creates independent user evidence."""
        return self._remember(text, kind=kind, project_id=project_id, subject=subject,
                              key=key, user_pinned=user_pinned, valid_until=valid_until,
                              record_id=record_id)

    def _remember(self, text, *, kind='note', project_id=None, subject='user', key=None,
                  user_pinned=False, valid_until=None, record_id=None, source_ids=(),
                  automatic=False, expected_revocation=None, status='active',
                  cancelled=lambda: False):
        text = text_checked(text)
        if kind not in self.freshness or type(user_pinned) is not bool:
            raise ValueError('invalid_memory_kind_or_pin')
        subject = text_checked(subject, max_length=200)
        key = text_checked(key, max_length=200) if key is not None else digest(text)
        rid, now = record_id or _id('memory'), self.clock()
        if valid_until is None and self.freshness[kind] is not None:
            valid_until = now + self.freshness[kind]
        if valid_until is not None and (type(valid_until) not in (int, float) or
                                        not math.isfinite(valid_until) or valid_until <= now):
            raise ValueError('invalid_memory_expiry')
        def op(db):
            if cancelled():
                raise RevokedContextError('extraction_cancelled')
            self._check_project(db, project_id)
            if expected_revocation is not None and expected_revocation != _state(db, 'revocation'):
                raise RevokedContextError('revoked_during_extraction')
            if automatic and not _state(db, 'learning'):
                raise RevokedContextError('learning_paused')
            if db.execute('SELECT COUNT(*) FROM memory_records WHERE status<>\'forgotten\'').fetchone()[0] >= MAX_RECORDS:
                raise ValueError('memory_capacity_reached')
            existing = _record(db, rid)
            if existing:
                same = (existing['text'] == text and existing['kind'] == kind and
                        existing['scope_id'] == project_id and existing['subject'] == subject and
                        existing['key'] == key and existing['user_pinned'] == user_pinned)
                if same and existing['status'] != 'forgotten':
                    return existing
                raise ValueError('memory_id_in_use')
            sources = [_source(db, sid) for sid in dict.fromkeys(source_ids)]
            if any(not s or not self._source_current(db, s) or
                   not eligibility(s, automatic=automatic)[0] for s in sources):
                raise RevokedContextError('ineligible_memory_evidence')
            if any(s['project_id'] != project_id for s in sources):
                raise ValueError('cross_scope_evidence')
            if not sources:
                if automatic:
                    raise ValueError('missing_memory_evidence')
                sid = _id('explicit')
                source = dict(id=sid, text=text, revision=1, status='active',
                              content_hash=digest(text), project_id=project_id,
                              kind='explicit_user', author_role='user',
                              confidence_label='high', expires_at=None)
                db.execute('INSERT INTO memory_sources VALUES(?,?,?,?,?,?,?,?)',
                           (sid, 1, text, source['content_hash'], project_id, 'active',
                            None, canonical({k: v for k, v in source.items() if k != 'text'})))
                sources = [source]
            refs = [dict(source_id=s['id'], source_revision=s['revision'],
                         content_hash=s['content_hash'], span_start=0,
                         span_end=len(s['text']), author_role=s['author_role']) for s in sources]
            record = dict(id=rid, revision=1, kind=kind,
                          scope_kind='project' if project_id else 'personal', scope_id=project_id,
                          subject=subject, key=key, text=text,
                          origin=('inferred_pattern' if automatic and len(sources) > 1 else
                                  'observed_user' if automatic else
                                  'imported' if source_ids else 'explicit_user'),
                          status=status, evidence_refs=refs, created_at=now, updated_at=now,
                          last_observed_at=now, last_confirmed_at=None if automatic else now,
                          valid_from=now, valid_until=valid_until, supersedes_id=None,
                          confidence_label='supported' if automatic else 'confirmed',
                          user_pinned=user_pinned, retrieval_enabled=True,
                          policy_revision=_state(db, 'revocation'))
            conflicts = db.execute('SELECT id FROM memory_records WHERE scope_id IS ? '
                                   "AND subject=? AND predicate=? AND status IN ('active','disputed') "
                                   'AND text<>?', (project_id, subject, key, text)).fetchall()
            if conflicts and status == 'active':
                confirmed_conflict = any(_record(db, other_id)['origin'] == 'explicit_user'
                                         for (other_id,) in conflicts)
                record['status'] = 'disputed' if automatic or confirmed_conflict else 'active'
                for (other_id,) in conflicts:
                    other = _record(db, other_id)
                    if automatic and other['origin'] == 'explicit_user':
                        continue
                    self._set_status(db, other_id,
                                     'superseded' if not automatic and not confirmed_conflict else 'disputed', now)
            _write_record(db, record)
            db.execute('INSERT INTO memory_revisions VALUES(?,?,?)', (rid, 1, canonical(record)))
            for ref in refs:
                db.execute('INSERT INTO memory_evidence VALUES(?,?,?,?,?,?)',
                           (rid, ref['source_id'], ref['source_revision'], ref['content_hash'],
                            ref['span_start'], ref['span_end']))
            if record['status'] == 'active':
                db.execute('INSERT INTO memory_fts VALUES(?,?)', (rid, text))
            _bump(db)
            return record
        return self._run(op)

    @staticmethod
    def _set_status(db, rid, status, now):
        record = _record(db, rid)
        if not record:
            return
        record.update(status=status, revision=record['revision'] + 1, updated_at=now)
        _write_record(db, record)
        db.execute('INSERT INTO memory_revisions VALUES(?,?,?)',
                   (rid, record['revision'], canonical(record)))
        db.execute('DELETE FROM memory_fts WHERE memory_id=?', (rid,))
        db.execute('DELETE FROM memory_vectors WHERE memory_id=?', (rid,))

    def _invalidate_linked(self, db, sid, status):
        for (rid,) in db.execute('SELECT memory_id FROM memory_evidence WHERE source_id=?', (sid,)).fetchall():
            record = _record(db, rid)
            if record and record['status'] not in {'forgotten', 'superseded'}:
                self._set_status(db, rid, status, self.clock())

    def list(self, *, project_id=None, include_personal=True, status=None, limit=200):
        if type(include_personal) is not bool or type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError('invalid_memory_filter')
        def op(db):
            self._check_project(db, project_id)
            rows = db.execute('SELECT data FROM memory_records WHERE '
                              '((? IS NOT NULL AND scope_id=?) OR (? AND scope_id IS NULL)) '
                              'ORDER BY updated_at DESC,id LIMIT ?',
                              (project_id, project_id, include_personal, limit)).fetchall()
            result = []
            for row in rows:
                record = json.loads(row[0])
                if record['valid_until'] is not None and record['valid_until'] <= self.clock() and record['status'] == 'active':
                    record['status'] = 'stale'
                if record['status'] == 'active':
                    clause, params = self._live_query(project_id, include_personal)
                    if not db.execute('SELECT 1 FROM memory_records m WHERE m.id=? AND ' + clause,
                                      (record['id'], *params)).fetchone():
                        record['status'] = 'stale'
                if status is None or record['status'] == status:
                    result.append(record)
            return result
        return self._run(op)

    def update(self, record_id, *, expected_revision, text=None, user_pinned=None,
               retrieval_enabled=None, confirm=False):
        """An explicit correction is independent evidence, retained until forgotten.

        The prior revision retains lineage. Same-key disputes are resolved by
        this confirmed correction, not by recency of inferred observations.
        """
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError('expected_revision_required')
        if text is not None:
            text = text_checked(text)
        if any(v is not None and type(v) is not bool for v in (user_pinned, retrieval_enabled)) or type(confirm) is not bool:
            raise ValueError('invalid_memory_flags')
        def op(db):
            r = _record(db, record_id)
            if not r or r['status'] == 'forgotten':
                raise ValueError('memory_not_found')
            if r['revision'] != expected_revision:
                raise StaleRevisionError('stale_memory_revision')
            now = self.clock()
            r.update(revision=r['revision'] + 1, updated_at=now)
            if user_pinned is not None:
                r['user_pinned'] = user_pinned
            if retrieval_enabled is not None:
                r['retrieval_enabled'] = retrieval_enabled
            if text is not None or confirm:
                r['text'] = text if text is not None else r['text']
                sid = _id('explicit')
                content_hash = digest(r['text'])
                data = dict(id=sid, kind='explicit_user', project_id=r['scope_id'],
                            author_role='user', confidence_label='high', expires_at=None)
                db.execute('INSERT INTO memory_sources VALUES(?,?,?,?,?,?,?,?)',
                           (sid, 1, r['text'], content_hash, r['scope_id'], 'active', None, canonical(data)))
                db.execute('DELETE FROM memory_evidence WHERE memory_id=?', (record_id,))
                db.execute('INSERT INTO memory_evidence VALUES(?,?,?,?,?,?)',
                           (record_id, sid, 1, content_hash, 0, len(r['text'])))
                r['evidence_refs'] = [asdict(EvidenceRef(sid, 1, content_hash, 0, len(r['text']), 'user'))]
                r.update(status='active', origin='explicit_user', confidence_label='confirmed',
                         last_confirmed_at=now, last_observed_at=now)
                ttl = self.freshness[r['kind']]
                r['valid_until'] = now + ttl if ttl is not None else None
                for (other,) in db.execute('SELECT id FROM memory_records WHERE scope_id IS ? '
                                           "AND subject=? AND predicate=? AND id<>? AND status IN ('active','disputed')",
                                           (r['scope_id'], r['subject'], r['key'], record_id)).fetchall():
                    self._set_status(db, other, 'superseded', now)
            _write_record(db, r)
            db.execute('INSERT INTO memory_revisions VALUES(?,?,?)', (record_id, r['revision'], canonical(r)))
            db.execute('DELETE FROM memory_fts WHERE memory_id=?', (record_id,))
            db.execute('DELETE FROM memory_vectors WHERE memory_id=?', (record_id,))
            if r['status'] == 'active' and r['retrieval_enabled']:
                db.execute('INSERT INTO memory_fts VALUES(?,?)', (record_id, r['text']))
            _bump(db)
            return r
        return self._run(op)

    def expire_source(self, source_id, *, reason='deleted'):
        if reason not in {'deleted', 'expired', 'excluded'}:
            raise ValueError('invalid_source_revocation')
        def op(db):
            source = _source(db, source_id)
            if not source:
                return False
            db.execute('INSERT OR IGNORE INTO memory_suppressed VALUES(?,?)',
                       (source_id, source['content_hash']))
            db.execute('UPDATE memory_sources SET status=?,text=\'\',revision=revision+1 WHERE id=?',
                       (reason, source_id))
            db.execute('DELETE FROM memory_dirty WHERE source_id=?', (source_id,))
            self._invalidate_linked(db, source_id, 'stale')
            _bump(db)
            return True
        return self._run(op)

    def forget(self, record_id):
        """Remove content, revisions, vectors and pending learning atomically.

        A tombstone retains only ID/revision and suppression hashes. Old frozen
        packs cannot publish. Previously exported documents are not rewritten.
        """
        return self._run(lambda db: self._forget_db(db, record_id))

    def _forget_db(self, db, record_id):
        r = _record(db, record_id)
        if not r or r['status'] == 'forgotten':
            return False
        # Include previous revision lineage, so correction cannot leave
        # deleted personal text in a historical revision/source row.
        sources = set()
        for (data,) in db.execute('SELECT data FROM memory_revisions WHERE memory_id=?', (record_id,)):
            sources.update(ref['source_id'] for ref in json.loads(data)['evidence_refs'])
        for sid in sources:
            source = _source(db, sid)
            if source:
                db.execute('INSERT OR IGNORE INTO memory_suppressed VALUES(?,?)', (sid, source['content_hash']))
                db.execute("UPDATE memory_sources SET text='',status='deleted',revision=revision+1 WHERE id=?", (sid,))
                db.execute('DELETE FROM memory_dirty WHERE source_id=?', (sid,))
                self._invalidate_linked(db, sid, 'stale')
        r = _record(db, record_id)
        r.update(text='', subject='', key='', status='forgotten', evidence_refs=[],
                 revision=r['revision'] + 1, updated_at=self.clock(), retrieval_enabled=False)
        _write_record(db, r)
        db.execute('DELETE FROM memory_revisions WHERE memory_id=?', (record_id,))
        db.execute('DELETE FROM memory_evidence WHERE memory_id=?', (record_id,))
        db.execute('DELETE FROM memory_fts WHERE memory_id=?', (record_id,))
        db.execute('DELETE FROM memory_vectors WHERE memory_id=?', (record_id,))
        _bump(db)
        return True

    def exclude(self, kind, value):
        if kind not in {'source', 'project', 'app'}:
            raise ValueError('invalid_exclusion')
        value = text_checked(value, max_length=300)
        def op(db):
            db.execute('INSERT OR IGNORE INTO memory_exclusions VALUES(?,?)', (kind, value))
            # Indexes are disposable. Clear them now; subsequent rebuilds
            # consult source eligibility before restoring any row.
            db.execute('DELETE FROM memory_vectors')
            db.execute('DELETE FROM memory_fts')
            db.execute('DELETE FROM memory_dirty')
            _bump(db)
        self._run(op)

    def forget_all(self):
        def op(db):
            ids = [r[0] for r in db.execute(
                "SELECT id FROM memory_records WHERE status<>'forgotten'")]
            for rid in ids:
                self._forget_db(db, rid)
            db.execute('INSERT OR IGNORE INTO memory_suppressed '
                       'SELECT id,content_hash FROM memory_sources')
            db.execute("UPDATE memory_sources SET text='',status='deleted',revision=revision+1")
            db.execute('DELETE FROM memory_dirty')
            db.execute("UPDATE memory_state SET value=0 WHERE key='learning'")
            _bump(db)
            return len(ids)
        return self._run(op)

    def import_files(self, project_id, paths):
        if not isinstance(paths, (list, tuple)) or not 1 <= len(paths) <= MAX_IMPORT_FILES:
            raise ValueError('context_file_count_limit')
        project = next((p for p in self.projects() if p['id'] == project_id), None)
        if not project:
            raise ValueError('unknown_project')
        result = []
        for selected in paths:
            candidate = Path(selected)
            if not candidate.is_absolute():
                candidate = Path(project['root']) / candidate
            resolved = candidate.resolve(strict=True)
            roots = [root for root in project['roots'] if resolved.is_relative_to(Path(root))]
            if not roots:
                raise ValueError('outside_approved_root')
            path, text = read_approved_file(max(roots, key=len), str(candidate))
            sid = 'file_' + digest(project_id + ':' + path)
            old = self._run(lambda db: _source(db, sid))
            self.add_source(text, kind='project_file', author_role='approved_document',
                            project_id=project_id, source_id=sid,
                            expected_revision=old['revision'] if old else None, path=path)
            source = self.read_source(sid)
            if source:
                existing = self._run(lambda db: db.execute(
                    'SELECT m.data FROM memory_records m JOIN memory_evidence e '
                    'ON e.memory_id=m.id WHERE e.source_id=? AND e.source_revision=? '
                    "AND m.status='active' LIMIT 1", (sid, source['revision'])).fetchone())
                if existing:
                    record = json.loads(existing[0])
                    if record['valid_until'] is None or record['valid_until'] > self.clock():
                        result.append(record)
                        continue
                # Explicitly selected file import, never a directory scan.
                result.append(self._remember(text, kind='project_fact', project_id=project_id,
                                             subject='project', key=path, source_ids=(sid,)))
        return result

    def learn(self, source_ids, *, text=None, kind='preference', key=None, direct=False,
              expected_revocation=None, cancelled=lambda: False):
        """Admit an extraction against independent, still eligible observations.

        Direct facts must be exact user statements. A paraphrased extraction is
        only a proposal; accepting generated output is never a learning signal.
        """
        if not isinstance(source_ids, (list, tuple)) or not 1 <= len(source_ids) <= 16:
            raise ValueError('bounded_evidence_required')
        snapshot = self.revision() if expected_revocation is None else expected_revocation
        sources = [self.read_source(sid) for sid in dict.fromkeys(source_ids)]
        if not self.learning() or any(not s or not eligibility(s, automatic=True)[0] for s in sources):
            raise RevokedContextError('ineligible_learning_source')
        project_id = sources[0]['project_id']
        if any(s['project_id'] != project_id for s in sources):
            raise ValueError('cross_scope_evidence')
        text = text_checked(text if text is not None else sources[0]['text'])
        exact = any(text == s['text'].strip() for s in sources)
        unambiguous = bool(re.match(r'(?i)^(?:I (?:prefer|use|always|want|avoid)|my project (?:uses|is))\b', text))
        independent = len({s.get('independent_key') or s['content_hash'] for s in sources})
        repeated = all(s['text'].strip() == text for s in sources)
        active = ((direct and exact and unambiguous) or
                  (not direct and repeated and independent >= 2 and unambiguous))
        return self._remember(text, kind=kind, project_id=project_id, key=key,
                              source_ids=tuple(s['id'] for s in sources), automatic=True,
                              expected_revocation=snapshot, status='active' if active else 'proposed',
                              cancelled=cancelled)

    def process_learning(self, *, limit=16, cancelled=lambda: False):
        if type(limit) is not int or not 1 <= limit <= 64:
            raise ValueError('invalid_learning_batch')
        if not self.learning():
            return []
        pending = self._run(lambda db: db.execute(
            'SELECT source_id,source_revision FROM memory_dirty ORDER BY rowid LIMIT ?', (limit,)).fetchall())
        result = []
        for sid, revision in pending:
            if cancelled() or not self.learning():
                break
            source = self.read_source(sid)
            if source and source['revision'] == revision:
                # Intentionally narrow local extraction. Other activity remains
                # an episode; no fabricated AI-inferred biography is persisted.
                if re.match(r'(?i)^I prefer\b', source['text']):
                    result.append(self.learn([sid], direct=True, cancelled=cancelled))
            self._run(lambda db, sid=sid, revision=revision: db.execute(
                'DELETE FROM memory_dirty WHERE source_id=? AND source_revision=?', (sid, revision)).rowcount)
        return result

    def _live_query(self, project_id, include_personal):
        return ('(' + _LIVE + ') AND ((? IS NOT NULL AND m.scope_id=?) OR (? AND m.scope_id IS NULL))',
                (self.clock(), self.clock(), project_id, project_id, include_personal))

    def index_pending(self, *, project_id=None, include_personal=True, limit=64,
                      cancelled=lambda: False):
        if type(limit) is not int or not 1 <= limit <= 256:
            raise ValueError('invalid_index_batch')
        clause, params = self._live_query(project_id, include_personal)
        def pending(db):
            self._check_project(db, project_id)
            return _state(db, 'revocation'), db.execute(
                'SELECT m.id,m.revision,m.text FROM memory_records m LEFT JOIN memory_vectors v '
                'ON v.memory_id=m.id WHERE ' + clause +
                ' AND (v.memory_id IS NULL OR v.revision<>m.revision OR v.implementation<>?) '
                'ORDER BY m.id LIMIT ?', (*params, self.embedding.implementation, limit)).fetchall()
        revocation, rows = self._run(pending)
        indexed = 0
        for rid, revision, text in rows:
            if cancelled():
                break
            vector = self.embedding.encode(text)
            if vector is None:
                break
            payload = np.asarray(vector, dtype='<f4').tobytes()
            def publish(db):
                if cancelled() or _state(db, 'revocation') != revocation:
                    return False
                current_clause, current_params = self._live_query(project_id, include_personal)
                if not db.execute('SELECT 1 FROM memory_records m WHERE m.id=? AND m.revision=? AND ' + current_clause,
                                  (rid, revision, *current_params)).fetchone():
                    return False
                db.execute('INSERT OR REPLACE INTO memory_vectors VALUES(?,?,?,?)',
                           (rid, revision, self.embedding.implementation, payload))
                db.execute('DELETE FROM memory_fts WHERE memory_id=?', (rid,))
                db.execute('INSERT INTO memory_fts VALUES(?,?)', (rid, text))
                return True
            indexed += bool(self._run(publish))
        return indexed

    def search(self, query, *, project_id=None, include_personal=True, enabled=True,
               token_budget=6000, limit=5, current_instructions='', cancelled=lambda: False):
        if type(enabled) is not bool or type(include_personal) is not bool:
            raise ValueError('invalid_context_policy')
        if type(limit) is not int or not 1 <= limit <= MAX_CONTEXT_ITEMS:
            raise ValueError('invalid_context_limit')
        if type(token_budget) is not int or not 0 <= token_budget <= 12000:
            raise ValueError('invalid_context_budget')
        if not isinstance(current_instructions, str) or len(current_instructions) > 32000:
            raise ValueError('invalid_current_instructions')
        if not enabled or token_budget == 0:
            return ContextPack(project_id, revocation_revision=self.revision(), current_instructions=current_instructions)
        query = text_checked(query, max_length=8000)
        if cancelled():
            raise RevokedContextError('retrieval_cancelled')
        self.refresh_files(project_id=project_id)
        self.index_pending(project_id=project_id, include_personal=include_personal, cancelled=cancelled)
        vector = self.embedding.encode(query)
        clause, params = self._live_query(project_id, include_personal)
        terms = [term for term in re.findall(r'\w+', query.lower(), flags=re.UNICODE)
                 if term not in _QUERY_STOP_WORDS][:32]
        fts_query = ' OR '.join('"' + t.replace('"', '""') + '"' for t in terms)
        def read(db):
            self._check_project(db, project_id)
            revocation = _state(db, 'revocation')
            lexical = db.execute('SELECT m.id FROM memory_fts JOIN memory_records m '
                                 'ON m.id=memory_fts.memory_id WHERE memory_fts MATCH ? AND ' + clause +
                                 ' ORDER BY bm25(memory_fts),m.id LIMIT 256', (fts_query, *params)).fetchall() if terms else []
            vectors = db.execute('SELECT m.id,v.vector FROM memory_vectors v JOIN memory_records m '
                                 'ON m.id=v.memory_id AND m.revision=v.revision WHERE ' + clause +
                                 ' AND v.implementation=? ORDER BY m.id LIMIT ?',
                                 (*params, self.embedding.implementation, MAX_RECORDS)).fetchall() if vector is not None else []
            omitted = db.execute("SELECT id,status FROM memory_records WHERE status IN ('disputed','stale') "
                                 'AND ((? IS NOT NULL AND scope_id=?) OR (? AND scope_id IS NULL)) ORDER BY id LIMIT 64',
                                 (project_id, project_id, include_personal)).fetchall()
            live_count = db.execute('SELECT COUNT(*) FROM memory_records m WHERE ' + clause,
                                    params).fetchone()[0]
            pinned = db.execute('SELECT m.id FROM memory_records m WHERE ' + clause +
                                " AND m.scope_id=? AND json_extract(m.data,'$.user_pinned')=1 "
                                'ORDER BY m.updated_at DESC,m.id LIMIT 8', (*params, project_id)).fetchall()
            return revocation, lexical, vectors, omitted, live_count, pinned
        revocation, lexical, vectors, omitted, live_count, pinned = self._run(read)
        semantic = []
        if vector is not None and vectors:
            matrix = np.stack([np.frombuffer(blob, dtype='<f4') for _, blob in vectors])
            scores = matrix @ vector
            semantic = [(vectors[i][0], float(scores[i])) for i in np.argsort(-scores, kind='stable')[:256]
                        if scores[i] >= 0.25]
        ranks, reasons = {}, {}
        for label, ranking in (('lexical', [(r[0], 1.0) for r in lexical]), ('semantic', semantic)):
            for rank, (rid, _) in enumerate(ranking, 1):
                # Frozen selection chose cosine priority (weight 0). FTS
                # still supplies exact-term fallback for unindexed records
                # and is the explicit degraded mode when vectors are absent.
                if label == 'semantic':
                    ranks[rid] = ranking[rank - 1][1]
                else:
                    ranks[rid] = -1 + 1 / (60 + rank)
                reasons.setdefault(rid, []).append(label)
        for (rid,) in pinned:
            ranks[rid] = ranks.get(rid, 0) + 1
            reasons.setdefault(rid, []).append('pinned_project_context')
        ordered = sorted(ranks, key=lambda rid: (-ranks[rid], rid))[:128]
        def fetch(db):
            if _state(db, 'revocation') != revocation:
                raise RevokedContextError('revoked_during_retrieval')
            return [_record(db, rid) for rid in ordered]
        rows = self._run(fetch)
        items, seen, used = [], set(), 0
        for r in rows:
            if cancelled():
                raise RevokedContextError('retrieval_cancelled')
            if not r or digest(r['text']) in seen:
                continue
            item = ContextItem(r['id'], r['revision'], r['text'], r['kind'], r['scope_id'],
                               tuple(EvidenceRef(**ref) for ref in r['evidence_refs']),
                               '+'.join(reasons[r['id']]), r['updated_at'], r['confidence_label'])
            # UTF-8 bytes of the full serialized item conservatively bound
            # tokens, including provenance. Never split a fact to make it fit.
            cost = len(canonical(asdict(item)).encode('utf-8'))
            if used + cost > token_budget:
                omitted.append((r['id'], 'context_budget'))
                continue
            seen.add(digest(r['text']))
            used += cost
            items.append(item)
            if len(items) == limit:
                break
        mode = ('lexical_degraded' if vector is None else
                'semantic_partial+lexical' if len(vectors) < live_count else 'semantic+lexical')
        from .workspaces import read_workspace
        from .models import WorkspaceIdentity
        project = next((p for p in self.projects() if p['id'] == project_id), None)
        workspaces = tuple(WorkspaceIdentity(**identity, observed_at=self.clock()) for root in project['roots']
                           if (identity := read_workspace(root)) is not None) if project else ()
        pack = ContextPack(project_id, tuple(items), revocation, mode, tuple(omitted),
                           current_instructions, workspaces=workspaces)
        self.assert_current(pack)
        return pack

    def _assert_current(self, db, pack):
        if not isinstance(pack, ContextPack):
            raise RevokedContextError('invalid_context_pack')
        if not pack.items and pack.retrieval_mode == 'off':
            self._check_project(db, pack.project_id)
            return True
        if pack.revocation_revision != _state(db, 'revocation'):
            raise RevokedContextError('revoked_context_revision')
        self._check_project(db, pack.project_id)
        for item in pack.items:
            record = _record(db, item.id)
            if not record or record['revision'] != item.revision or record['text'] != item.text:
                raise RevokedContextError('changed_context_record')
            if (item.scope_id != record['scope_id'] or item.kind != record['kind'] or
                    item.updated_at != record['updated_at'] or
                    item.confidence_label != record['confidence_label']):
                raise RevokedContextError('changed_context_metadata')
            if record['scope_id'] is not None and record['scope_id'] != pack.project_id:
                raise RevokedContextError('cross_scope_context')
            if tuple(EvidenceRef(**ref) for ref in record['evidence_refs']) != item.evidence_refs:
                raise RevokedContextError('fabricated_evidence_reference')
            clause, params = self._live_query(pack.project_id, True)
            if not db.execute('SELECT 1 FROM memory_records m WHERE m.id=? AND ' + clause,
                              (item.id, *params)).fetchone():
                raise RevokedContextError('ineligible_context_record')
        return True

    def assert_current(self, pack):
        """Check before disclosure. Already transmitted requests cannot be erased."""
        self.refresh_files(project_id=pack.project_id, source_ids=[
            ref.source_id for item in pack.items for ref in item.evidence_refs])
        return self._run(lambda db: self._assert_current(db, pack))

    def publish_if_current(self, pack, publish):
        """Validate and write a draft/suggestion in ONE existing writer operation.

        publish(db) must only perform its bounded SQLite writes, and never call
        Store.submit or a provider. Returning from assert_current and writing in
        a later submission leaves a deletion race; use this publication method.
        """
        self.refresh_files(project_id=pack.project_id, source_ids=[
            ref.source_id for item in pack.items for ref in item.evidence_refs])
        def op(db):
            self._assert_current(db, pack)
            return publish(db)
        return self._run(op)
