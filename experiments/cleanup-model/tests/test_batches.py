"""Batch controller: custom_id matching, classification, resume, ambiguous
create adoption and the spend cap. Uses a fake client; no network."""

import datetime as dt
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lfx import batches  # noqa: E402


class FakeBatch:
    def __init__(self, bid, n):
        self.id = bid
        self.processing_status = "in_progress"
        self.created_at = dt.datetime.now(dt.timezone.utc)
        self.request_counts = types.SimpleNamespace(processing=n, succeeded=0, errored=0, canceled=0, expired=0)


class FakeResult:
    def __init__(self, d):
        self._d = d

    def model_dump(self, mode="json"):
        return self._d


def ok(cid, text, stop="end_turn", out_tokens=100):
    return {"custom_id": cid, "result": {"type": "succeeded", "message": {
        "content": [{"type": "text", "text": text}], "stop_reason": stop,
        "usage": {"input_tokens": 1000, "output_tokens": out_tokens,
                  "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}}}


class FakeBatches:
    def __init__(self, behaviour, fail_create=False):
        self.behaviour, self.fail_create = behaviour, fail_create
        self.store, self.creates = {}, 0

    def create(self, requests):
        self.creates += 1
        bid = f"msgbatch_{self.creates}"
        self.store[bid] = (FakeBatch(bid, len(requests)), [r["custom_id"] for r in requests])
        if self.fail_create:
            self.fail_create = False
            raise ConnectionError("socket closed after send")  # ambiguous: batch exists
        return self.store[bid][0]

    def retrieve(self, bid):
        b = self.store[bid][0]
        b.processing_status = "ended"
        return b

    def results(self, bid):
        # Deliberately reversed order: matching must be by custom_id.
        return [FakeResult(self.behaviour(cid)) for cid in reversed(self.store[bid][1])]

    def list(self, limit=50):
        return [b for b, _ in sorted(self.store.values(), key=lambda x: x[0].id, reverse=True)]


def client(fb):
    return types.SimpleNamespace(messages=types.SimpleNamespace(batches=fb))


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        batches.CLAUDE_DIR = self.tmp
        batches.LEDGER = self.tmp / "ledger.json"
        self.reqs = {f"g-{i}": {"model": "m", "max_tokens": 1000, "messages": []} for i in range(4)}

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def wave(self, fb, name="w"):
        return batches.Wave(name, self.reqs, parse=lambda t: json.loads(t)["v"],
                            est_input_tokens=lambda p: 1000, client=client(fb),
                            client_noretry=client(fb), poll_seconds=0, log=lambda *a: None)

    def test_classification_and_custom_id_matching(self):
        def beh(cid):
            base = cid.rsplit("-a", 1)[0]
            return {"g-0": ok(cid, json.dumps({"v": base})),
                    "g-1": ok(cid, "{not json"),
                    "g-2": ok(cid, "", stop="max_tokens"),
                    "g-3": {"custom_id": cid, "result": {"type": "errored", "error": {
                        "type": "error", "error": {"type": "invalid_request_error"}}}}}[base]
        fb = FakeBatches(beh)
        w = self.wave(fb)
        w.submit_pending()
        w.collect()
        self.assertEqual(w.outcomes["g-0"]["value"], "g-0")
        self.assertEqual(w.outcomes["g-1"]["status"], "malformed")
        self.assertEqual(w.outcomes["g-2"]["status"], "truncated")
        self.assertEqual(w.outcomes["g-3"]["status"], "errored_invalid")
        self.assertEqual(w.pending(), ["g-1"])           # only the recoverable one retries

    def test_refusal_and_expired(self):
        fb = FakeBatches(lambda cid: ok(cid, "x", stop="refusal") if cid.startswith("g-0")
                         else {"custom_id": cid, "result": {"type": "expired"}})
        w = self.wave(fb)
        w.submit_pending()
        w.collect()
        self.assertEqual(w.outcomes["g-0"]["status"], "refused")
        self.assertEqual(w.outcomes["g-1"]["status"], "expired")
        self.assertIn("g-1", w.pending())

    def test_resume_does_not_resubmit_successes(self):
        fb = FakeBatches(lambda cid: ok(cid, json.dumps({"v": 1})))
        w = self.wave(fb)
        w.run()
        self.assertEqual(fb.creates, 1)
        w2 = self.wave(fb)                                 # new process, same manifest
        w2.run()
        self.assertEqual(fb.creates, 1)
        self.assertTrue(w2.done())
        with self.assertRaises(RuntimeError):              # changed requests need a new wave name
            batches.Wave("w", {"x": {"max_tokens": 1}}, parse=str, est_input_tokens=lambda p: 1)

    def test_ambiguous_create_adopts_existing_batch(self):
        fb = FakeBatches(lambda cid: ok(cid, json.dumps({"v": 1})), fail_create=True)
        w = self.wave(fb)
        attempt = w.submit_pending()
        self.assertTrue(attempt.get("adopted"))
        self.assertEqual(fb.creates, 1)                    # never blindly re-created
        w.collect()
        self.assertTrue(w.done())

    def test_ledger_cap_blocks_submission(self):
        batches.CONFIG["claude"]["stop_at_usd"] = 0.01
        try:
            fb = FakeBatches(lambda cid: ok(cid, json.dumps({"v": 1})))
            w = self.wave(fb)
            with self.assertRaises(batches.BudgetExceeded):
                w.submit_pending()
            self.assertEqual(fb.creates, 0)
        finally:
            batches.CONFIG["claude"]["stop_at_usd"] = 19.50

    def test_usage_cost(self):
        c = batches.usage_cost({"input_tokens": 1_000_000, "output_tokens": 1_000_000,
                                "cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 0})
        self.assertAlmostEqual(c, 1.00 + 5.00 + 0.05)


if __name__ == "__main__":
    unittest.main()
