"""Reproducible local CPU retrieval timing over 10,000 synthetic memories.

Run from the repo: .venv/bin/python tests/v2/memory/benchmark_scale.py
Uses real OS embeddings, disposable Store tables and Store.submit throughout.
The small labeled corpus is the quality gate; this script measures scale only.
"""

import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from retrieval_cases import CASES
from localflow.v2.memory import MEMORY_MIGRATIONS, MemoryStore
from localflow.v2.memory.embeddings import MiniLMEmbedding
from localflow.v2.memory.models import canonical, digest
from localflow.v2.memory.store import _write_record
from localflow.v2.store import Store, _MIGRATIONS


def main():
    embedding = MiniLMEmbedding()
    if embedding.encode('Synthetic local scale check.') is None:
        print(json.dumps({'status': 'blocked', 'reason': 'local_embedding_unavailable'}))
        return 2
    with tempfile.TemporaryDirectory() as td, patch.dict(_MIGRATIONS, {15: MEMORY_MIGRATIONS}):
        root = Path(td)
        store = Store(root / 'scale.db')
        try:
            memory = MemoryStore(store, embedding=embedding)
            project = memory.create_project('Synthetic scale project', root)
            started = time.perf_counter()
            for batch in range(100):
                rows = []
                for n in range(batch * 100, (batch + 1) * 100):
                    _, sentence, _ = CASES[n % len(CASES)]
                    text = f'Synthetic note {n}: {sentence}'
                    vector = embedding.encode(text)
                    rid, sid = f'scale-memory-{n}', f'scale-source-{n}'
                    hashed = digest(text)
                    source = dict(id=sid, kind='explicit_user', project_id=project,
                                  author_role='user', confidence_label='high', expires_at=None)
                    ref = dict(source_id=sid, source_revision=1, content_hash=hashed,
                               span_start=0, span_end=len(text), author_role='user')
                    record = dict(id=rid, revision=1, kind='note', scope_id=project,
                                  subject='synthetic project', key=str(n), text=text, status='active',
                                  valid_until=None, updated_at=1.0, evidence_refs=[ref],
                                  retrieval_enabled=True, confidence_label='confirmed')
                    rows.append((record, source, vector.tobytes(), hashed))
                def insert(db):
                    for record, source, vector, hashed in rows:
                        db.execute('INSERT INTO memory_sources VALUES(?,?,?,?,?,?,?,?)',
                                   (source['id'], 1, record['text'], hashed, project, 'active', None, canonical(source)))
                        _write_record(db, record)
                        db.execute('INSERT INTO memory_evidence VALUES(?,?,?,?,?,?)',
                                   (record['id'], source['id'], 1, hashed, 0, len(record['text'])))
                        db.execute('INSERT INTO memory_fts VALUES(?,?)', (record['id'], record['text']))
                        db.execute('INSERT INTO memory_vectors VALUES(?,?,?,?)',
                                   (record['id'], 1, embedding.implementation, vector))
                store.submit(insert)
            build_seconds = time.perf_counter() - started
            timings = []
            for _, _, query in CASES:
                start = time.perf_counter()
                pack = memory.search(query, project_id=project, include_personal=False)
                timings.append((time.perf_counter() - start) * 1000)
                assert all(item.scope_id == project for item in pack.items)
            report = dict(records=10_000, queries=len(CASES),
                          build_seconds=round(build_seconds, 2),
                          p50_ms=round(float(np.median(timings)), 2),
                          p95_ms=round(float(np.percentile(timings, 95)), 2),
                          database_mb=round(store.db_path.stat().st_size / 1024**2, 2),
                          implementation=embedding.implementation)
            print('LOCAL_MEMORY_SCALE ' + json.dumps(report, sort_keys=True))
            return 0 if report['p95_ms'] <= 250 else 1
        finally:
            store.close()


if __name__ == '__main__':
    raise SystemExit(main())
