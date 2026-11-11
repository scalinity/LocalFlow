"""Opt-in full-engine A/B qualification on the installed cleanup weights.

LOCALFLOW_LOOKUP_PARITY=1 .venv/bin/python -m unittest \
    tests.v2.cleanup.test_lookup_parity

LOCALFLOW_LOOKUP_CASES limits the synthetic cohort for an initial probe.
LOCALFLOW_LOOKUP_REPORT selects an ignored local JSON report path.
No models are downloaded and no personal dictation is read.
"""
import json
import os
import copy
import hashlib
import statistics
from collections import OrderedDict
from pathlib import Path
import time
import unittest
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from localflow.v2.cleanup.model import ModelRunner


@unittest.skipUnless(os.environ.get('LOCALFLOW_LOOKUP_PARITY') == '1',
                     'enable explicitly to run local model inference')
class LookupParityTests(unittest.TestCase):
    def test_full_engine_outputs_and_tokens(self):
        root = Path(__file__).resolve().parents[3]
        config = json.loads((root / 'config.json').read_text())
        model = config['cleanup_model']
        snapshots = Path.home() / '.cache/huggingface/hub' / (
            'models--' + model.replace('/', '--')) / 'snapshots'
        candidates = list(snapshots.iterdir())
        self.assertEqual(len(candidates), 1, 'select exact local model snapshot')
        runner = ModelRunner(str(candidates[0]))
        runner.use_lookup = False
        runner.cache_full_prefix = False
        runner.load()
        candidate = copy.copy(runner)
        candidate.use_lookup = candidate.cache_full_prefix = True
        candidate._prefix_caches = OrderedDict()
        candidate._rendered = candidate._draft = None
        tokens = []
        metrics = []
        def observe(stream, owner):
            def observed(*args, **kwargs):
                call = []
                tokens.append(call)
                for response in stream(*args, **kwargs):
                    call.append(response.token)
                    yield response
                metrics.append({'prefix_tokens': owner.last_prefix_tokens,
                                'prefix_hit': owner.last_prefix_hit,
                                **(owner.lookup_stats or {})})
            return observed
        runner.stream = observe(runner.stream, runner)
        candidate.stream = observe(candidate.stream, candidate)
        cases = json.loads((root / 'tests/v2/fidelity/fixtures_fidelity.json').read_text())['cases']
        limit = int(os.environ.get('LOCALFLOW_LOOKUP_CASES', len(cases)))
        self.assertGreater(limit, 0, 'LOCALFLOW_LOOKUP_CASES must be positive')
        # Spread probes over the existing cohort instead of testing only corrections.
        if limit < len(cases):
            cases = cases[::max(1, len(cases) // limit)][:limit]
        if limit >= len(cases):
            paragraph = ('The night shift checks the boiler gauge every 2 hours and writes '
                         'the reading in the blue log, then confirms the valve is closed '
                         'before handing over. If the pressure is above 3 bar, call the '
                         'engineer and do not restart the pump until the reading settles. ')
            cases.extend([
                {'case_id': 'lookup-multiwindow', 'input': paragraph * 7},
                {'case_id': 'lookup-unicode', 'input': 'Send the café résumé to Zoë in Zürich. Keep 日本語 and €20 exactly.'},
                {'case_id': 'lookup-list', 'input': 'Three tasks for the afternoon first update the report second run the tests third send the results.'}])
        import mlx_lm
        identity = {'model': model, 'snapshot': str(candidates[0]),
                    'config_sha256': hashlib.sha256((candidates[0] / 'config.json').read_bytes()).hexdigest(),
                    'mlx_lm': mlx_lm.__version__}
        rows = []
        failures = []
        for i, case in enumerate(cases):
            spans = []
            for literal in case.get('protected', []):
                offset = case['input'].find(literal)
                if offset >= 0:
                    spans.append((offset, offset + len(literal)))
            outcomes = {}
            row = {'case': case['case_id'], 'order': 'AB' if i % 2 == 0 else 'BA'}
            for enabled in ((False, True) if i % 2 == 0 else (True, False)):
                tokens.clear()
                metrics.clear()
                start = time.perf_counter()
                selected = candidate if enabled else runner
                result = selected.engine().clean(case['input'], protected_spans=spans,
                    destination_profile=case.get('destination_profile'))
                name = 'lookup' if enabled else 'baseline'
                row[name + '_ms'] = round((time.perf_counter() - start) * 1000, 3)
                row[name + '_metrics'] = list(metrics)
                outcomes[name] = (result.to_json(), [list(x) for x in tokens])
            row['same_result'] = outcomes['baseline'][0] == outcomes['lookup'][0]
            row['same_tokens'] = outcomes['baseline'][1] == outcomes['lookup'][1]
            row['baseline_tokens'] = sum(map(len, outcomes['baseline'][1]))
            rows.append(row)
            print(json.dumps(row), flush=True)
            if not row['same_result'] or not row['same_tokens']:
                failures.append(row['case'])
            report = os.environ.get('LOCALFLOW_LOOKUP_REPORT')
            if report:
                summary = {}
                for mode in ('baseline', 'lookup'):
                    values = sorted(r[mode + '_ms'] for r in rows)
                    summary[mode] = {'median_ms': statistics.median(values),
                                     'p95_ms': values[int((len(values) - 1) * .95)]}
                Path(report).write_text(json.dumps({'identity': identity,
                    'summary': summary, 'rows': rows}, indent=2) + '\n')
        self.assertEqual(failures, [], 'full engine/token parity failed')
        coverage = [m for row in rows for m in row['lookup_metrics']]
        for field in ('accepted_tokens', 'replay_rounds', 'full_rounds', 'disabled'):
            self.assertGreater(sum(m.get(field, 0) for m in coverage), 0, field)
        self.assertTrue(any(m['prefix_tokens'] > 0 and m['prefix_hit'] for m in coverage))
        self.assertTrue(any(m['prefix_tokens'] > 0 and m['prefix_hit']
                            and 'drafted_tokens' not in m for m in coverage),
                        'corrections prefix must have a warm hit')
        # Real generation length boundaries, including a final partial token
        # stream. Compare full output text and EOS/length response semantics.
        from localflow.v2.cleanup import prompts
        for budget in (1, 2, 7):
            outputs = []
            for selected in (runner, candidate):
                prompt = selected.render_cached(prompts.build_messages({'transcript': 'Send the résumé to Zoë in Zürich tomorrow.'}))
                outputs.append([(r.text, r.token, r.finish_reason) for r in selected.stream(prompt, budget)])
            self.assertEqual(outputs[0], outputs[1], f'limit {budget}')


if __name__ == '__main__':
    unittest.main()
