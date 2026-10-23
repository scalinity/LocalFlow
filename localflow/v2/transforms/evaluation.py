"""Resumable evaluation identities and a conservative paid-call budget.

Unknown submissions keep their reservation: a timeout is not free. This
ledger is development tooling, independent of training collection/runtime.
"""
import contextlib
import fcntl
import hashlib
import json
import pathlib
import uuid

SCORING_REVISION = "intelligence-rubric-1"
RESEARCH_WEIGHTS = {"intent": 25, "clarity": 20, "assumptions": 15,
                    "evidence": 15, "comparison": 10, "decision": 10,
                    "efficiency": 5}
OTHER_WEIGHTS = {"intent": 30, "clarity": 20, "scope": 20,
                 "utility": 20, "efficiency": 10}


def evaluation_identity(*, fixture, split_manifest, compiler, prompt, schema,
                        model, effort, context, validator, judge_prompt,
                        judge_model, judge_schema, role, condition):
    values = dict(locals(), scoring=SCORING_REVISION)
    return hashlib.sha256(json.dumps(values, sort_keys=True,
        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


class BudgetBlocked(Exception):
    pass


class EvalBudget:
    def __init__(self, path, ceiling=25):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ceiling = ceiling

    @contextlib.contextmanager
    def _locked(self):
        with self.path.with_suffix('.lock').open('a+') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if self.path.exists():
                value = json.loads(self.path.read_text())
            else:
                value = {'ceiling_usd': self.ceiling, 'calls': {}}
            yield value
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps(value, indent=2))
            tmp.replace(self.path)

    def reserve(self, upper_bound, *, identity, role):
        if upper_bound <= 0:
            raise ValueError('positive reservation required')
        with self._locked() as value:
            total = sum(c.get('actual_usd') if c.get('actual_usd') is not None
                        else c['reserved_usd'] for c in value['calls'].values())
            if total + upper_bound > value['ceiling_usd']:
                raise BudgetBlocked('blocked: budget')
            token = str(uuid.uuid4())
            value['calls'][token] = {'identity': identity, 'role': role,
                'reserved_usd': upper_bound, 'actual_usd': None,
                'status': 'outcome_unknown'}
            return token

    def settle(self, token, actual_usd, *, status='succeeded'):
        if actual_usd is not None and actual_usd < 0:
            raise ValueError('invalid cost')
        with self._locked() as value:
            call = value['calls'][token]
            if call['actual_usd'] is not None:
                if call['actual_usd'] != actual_usd:
                    raise ValueError('cost already settled')
                return
            call.update(actual_usd=actual_usd, status=status)

    def state(self):
        with self._locked() as value:
            return json.loads(json.dumps(value))
