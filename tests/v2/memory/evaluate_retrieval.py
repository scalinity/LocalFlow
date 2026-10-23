"""Selection/final retrieval evaluation without changing fixture labels.

Selection chooses from a predefined generic ranking grid. A final run requires
an explicit frozen weight. The original technical corpus remains regression.
Run: .venv/bin/python tests/v2/memory/evaluate_retrieval.py --split selection
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from localflow.v2.memory.embeddings import LocalEmbedding, MiniLMEmbedding
from localflow.v2.memory.store import _QUERY_STOP_WORDS
from retrieval_cases import CASES
from retrieval_holdout import FINAL, SELECTION

FIXTURE_SHA256 = '630a7371c2ff0357d8563cd75b029ed0b4da9af63e9fd1543cd7061fad8bf53c'
WEIGHTS = (0.0, 0.05, 0.1, 0.2, 0.35)


def evaluate(embedding, cases, weights):
    vectors, timings = [], []
    for _, text, _ in cases:
        vector = embedding.encode(text)
        if vector is None:
            raise RuntimeError('embedding_unavailable: ' + str(embedding.unavailable_reason))
        vectors.append(vector)
    matrix = np.stack(vectors)
    reports = {w: {'hits': 0, 'reciprocal_rank': 0.0, 'misses': []} for w in weights}
    old_rrf_hits = 0
    with sqlite3.connect(':memory:') as db:
        db.execute("CREATE VIRTUAL TABLE corpus USING fts5(text, tokenize='porter unicode61')")
        db.executemany('INSERT INTO corpus(rowid,text) VALUES(?,?)',
                       [(i + 1, text) for i, (_, text, _) in enumerate(cases)])
        for target, (label, _, query) in enumerate(cases):
            start = time.perf_counter()
            query_vector = embedding.encode(query)
            scores = matrix @ query_vector
            terms = [term for term in re.findall(r'\w+', query.lower()) if term not in _QUERY_STOP_WORDS][:32]
            lexical = [r[0] - 1 for r in db.execute('SELECT rowid FROM corpus WHERE corpus MATCH ? '
                                                   'ORDER BY bm25(corpus),rowid',
                                                   (' OR '.join('"' + t + '"' for t in terms),))] if terms else []
            lexical_scores = np.zeros(len(cases), dtype=np.float32)
            old_scores = np.zeros(len(cases), dtype=np.float32)
            for rank, index in enumerate(lexical, 1):
                lexical_scores[index] = 1 / rank
                old_scores[index] += 1 / (60 + rank)
            for rank, index in enumerate(np.argsort(-scores, kind='stable'), 1):
                if scores[index] >= 0.25:
                    old_scores[index] += 1 / (60 + rank)
            old_rrf_hits += target in np.argsort(-old_scores, kind='stable')[:5]
            for weight, report in reports.items():
                order = np.argsort(-(scores + weight * lexical_scores), kind='stable')
                rank = int(np.where(order == target)[0][0]) + 1
                report['hits'] += rank <= 5
                report['reciprocal_rank'] += 1 / rank
                if rank > 5:
                    report['misses'].append({'label': label, 'rank': rank})
            timings.append((time.perf_counter() - start) * 1000)
    for report in reports.values():
        report['recall_at_5'] = report['hits'] / len(cases)
        report['mrr'] = report.pop('reciprocal_rank') / len(cases)
    return {'queries': len(cases), 'rankings': reports,
            'old_rrf_recall_at_5': old_rrf_hits / len(cases),
            'p50_ms': float(np.median(timings)), 'p95_ms': float(np.percentile(timings, 95)),
            'implementation': embedding.implementation}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--split', required=True, choices=['selection', 'final', 'regression'])
    parser.add_argument('--weight', type=float)
    parser.add_argument('--model-dir')
    parser.add_argument('--encoder', choices=['apple', 'minilm'], default='minilm')
    args = parser.parse_args()
    actual = hashlib.sha256(Path(__file__).with_name('retrieval_holdout.py').read_bytes()).hexdigest()
    if actual != FIXTURE_SHA256:
        raise RuntimeError('frozen_fixture_changed')
    if args.split != 'selection' and args.weight is None:
        parser.error('final/regression require a frozen --weight')
    embedding = MiniLMEmbedding(model_dir=args.model_dir) if args.encoder == 'minilm' else LocalEmbedding()
    cases = {'selection': SELECTION, 'final': FINAL, 'regression': CASES}[args.split]
    report = evaluate(embedding, cases, WEIGHTS if args.split == 'selection' else [args.weight])
    report.update(split=args.split, fixture_sha256=actual)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if max(r['recall_at_5'] for r in report['rankings'].values()) >= 0.9 else 1


if __name__ == '__main__':
    raise SystemExit(main())
