"""Resumable Message Batches controller with a spend ledger.

Every wave persists its requests, stable custom_ids and returned batch ids
before and after each API call, so a crash or rerun resumes without buying a
request twice. Results are matched by custom_id, never by output order.
"""

from __future__ import annotations

import fcntl
import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from .common import ART, CONFIG, read_json, sha256_json, utc_now, write_json

CLAUDE_DIR = ART / "claude"
LEDGER = CLAUDE_DIR / "ledger.json"

# Terminal per-request states. "succeeded" means a parsed, valid value.
FINAL_OK = "succeeded"
RECOVERABLE = {"errored_recoverable", "expired", "canceled", "malformed", "not_created"}
NON_RECOVERABLE = {"errored_invalid", "refused", "truncated"}
MAX_ATTEMPTS = 3          # first try + at most two retries


def price() -> dict:
    return CONFIG["claude"]["price_batch"]


def usage_cost(usage: dict) -> float:
    p = price()
    return (usage.get("input_tokens", 0) * p["input"]
            + (usage.get("cache_creation_input_tokens") or 0) * p["cache_write"]
            + (usage.get("cache_read_input_tokens") or 0) * p["cache_read"]
            + usage.get("output_tokens", 0) * p["output"]) / 1e6


def max_charge(est_input_tokens: int, max_tokens: int) -> float:
    """Upper bound for one request: inputs priced at the uncached rate, every
    allowed output token billed."""
    p = price()
    return (est_input_tokens * max(p["input"], p["cache_write"]) + max_tokens * p["output"]) / 1e6


# ---------------------------------------------------------------- ledger

@contextmanager
def ledger_lock():
    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CLAUDE_DIR / ".ledger.lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def ledger() -> dict:
    return read_json(LEDGER, {"entries": {}, "reservations": {}})


def ledger_totals(led: dict | None = None) -> dict:
    led = led or ledger()
    actual = sum(e.get("actual_usd", 0.0) for e in led["entries"].values())
    outstanding = sum(e["max_usd"] for e in led["entries"].values() if e["state"] == "outstanding")
    reserved = sum(led.get("reservations", {}).values())
    tokens = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}
    for e in led["entries"].values():
        for k, v in e.get("usage", {}).items():
            tokens[k] = tokens.get(k, 0) + v
    return {"actual_usd": actual, "outstanding_max_usd": outstanding,
            "reserved_usd": reserved, "tokens": tokens}


def set_reservation(name: str, usd: float) -> None:
    with ledger_lock():
        led = ledger()
        led.setdefault("reservations", {})[name] = usd
        write_json(LEDGER, led)


def _reserve(key: str, max_usd: float, purpose: str, ignore_reservation: str | None) -> None:
    stop = CONFIG["claude"]["stop_at_usd"]
    with ledger_lock():
        led = ledger()
        if key in led["entries"]:
            raise RuntimeError(f"ledger entry {key} already exists")
        t = ledger_totals(led)
        reserved = sum(v for k, v in led.get("reservations", {}).items() if k != ignore_reservation)
        projected = t["actual_usd"] + t["outstanding_max_usd"] + reserved + max_usd
        if projected > stop:
            raise BudgetExceeded(
                f"{key}: projected ${projected:.2f} (actual {t['actual_usd']:.2f} + outstanding "
                f"{t['outstanding_max_usd']:.2f} + reserved {reserved:.2f} + new {max_usd:.2f}) "
                f"exceeds stop ${stop:.2f}")
        led["entries"][key] = {"state": "outstanding", "max_usd": max_usd, "purpose": purpose,
                               "created": utc_now()}
        write_json(LEDGER, led)


def _settle(key: str, actual_usd: float, usage: dict, state: str = "settled") -> None:
    with ledger_lock():
        led = ledger()
        e = led["entries"].setdefault(key, {"max_usd": 0.0, "purpose": "?", "created": utc_now()})
        e.update(state=state, actual_usd=actual_usd, usage=usage, settled=utc_now())
        write_json(LEDGER, led)


class BudgetExceeded(RuntimeError):
    pass


class AmbiguousBatch(RuntimeError):
    pass


# ---------------------------------------------------------------- results

def classify(result: dict, parse: Callable[[str], object]) -> dict:
    """Map one raw batch result (dict form) to a per-request outcome."""
    rtype = result["result"]["type"]
    if rtype == "succeeded":
        msg = result["result"]["message"]
        usage = msg.get("usage") or {}
        stop = msg.get("stop_reason")
        out = {"usage": {k: usage.get(k) or 0 for k in
                         ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                          "cache_read_input_tokens")},
               "stop_reason": stop}
        if stop == "refusal":
            return {**out, "status": "refused", "detail": msg.get("stop_details")}
        if stop == "max_tokens":
            return {**out, "status": "truncated"}
        text = "".join(b.get("text", "") for b in msg.get("content", []) if b.get("type") == "text")
        try:
            value = parse(text)
        except Exception as exc:  # parse failures are data, never crashes
            return {**out, "status": "malformed", "detail": f"{type(exc).__name__}: {exc}"[:300]}
        return {**out, "status": FINAL_OK, "value": value}
    if rtype == "errored":
        err = json.dumps(result["result"].get("error", {}))
        status = "errored_invalid" if "invalid_request" in err else "errored_recoverable"
        return {"status": status, "detail": err[:300], "usage": {}}
    if rtype in ("canceled", "expired"):
        return {"status": rtype, "usage": {}}
    return {"status": "malformed", "detail": f"unknown result type {rtype}", "usage": {}}


def _usage_tokens(u: dict) -> dict:
    return {"input": u.get("input_tokens", 0), "output": u.get("output_tokens", 0),
            "cache_write": u.get("cache_creation_input_tokens", 0),
            "cache_read": u.get("cache_read_input_tokens", 0)}


# ---------------------------------------------------------------- wave

class Wave:
    """One logical set of requests (e.g. ``gen-test``). ``requests`` maps a
    base id to Messages params; attempts get ``-a{n}`` suffixes."""

    def __init__(self, name: str, requests: dict[str, dict], parse: Callable[[str], object],
                 est_input_tokens: Callable[[dict], int], client=None, client_noretry=None,
                 purpose: str = "generation", poll_seconds: int = 60,
                 reservation: str | None = None, log=print):
        self.name, self.requests, self.parse = name, requests, parse
        self.est_input_tokens = est_input_tokens
        self.client, self.client_noretry = client, client_noretry
        self.purpose, self.poll_seconds, self.log = purpose, poll_seconds, log
        self.reservation = reservation
        self.dir = CLAUDE_DIR / name
        self.manifest_path = self.dir / "manifest.json"
        self.outcomes_path = self.dir / "outcomes.json"
        req_hash = sha256_json(requests)
        self.manifest = read_json(self.manifest_path)
        if self.manifest is None:
            self.dir.mkdir(parents=True, exist_ok=True)
            write_json(self.dir / "requests.json", requests)
            self.manifest = {"name": name, "created": utc_now(), "request_hash": req_hash,
                             "request_count": len(requests), "attempts": []}
            self._save()
        elif self.manifest["request_hash"] != req_hash:
            raise RuntimeError(f"wave {name}: requests changed since the manifest was written; "
                               "use a new wave name instead of altering a submitted one")
        self.outcomes = read_json(self.outcomes_path, {})

    def _save(self):
        write_json(self.manifest_path, self.manifest)

    def _save_outcomes(self):
        write_json(self.outcomes_path, self.outcomes)

    # -- state helpers
    def pending(self) -> list[str]:
        """Base ids that still need a (re)submission."""
        inflight = {b for a in self.manifest["attempts"] if a["state"] in ("creating", "ambiguous", "submitted")
                    for b in a["base_ids"]}
        out = []
        for base in self.requests:
            o = self.outcomes.get(base)
            if base in inflight:
                continue
            if o is None or (o["status"] in RECOVERABLE and o.get("attempts", 1) < MAX_ATTEMPTS):
                out.append(base)
        return out

    def done(self) -> bool:
        return not self.pending() and not any(
            a["state"] in ("creating", "ambiguous", "submitted") for a in self.manifest["attempts"])

    def values(self) -> dict:
        return {b: o["value"] for b, o in self.outcomes.items() if o["status"] == FINAL_OK}

    def status_counts(self) -> dict:
        counts: dict = {}
        for base in self.requests:
            s = self.outcomes.get(base, {}).get("status", "pending")
            counts[s] = counts.get(s, 0) + 1
        return counts

    # -- submission
    def submit_pending(self, limit: int | None = None) -> dict | None:
        bases = self.pending()[: limit or None]
        if not bases:
            return None
        n = len(self.manifest["attempts"]) + 1
        key = f"{self.name}#a{n}"
        reqs, max_usd = [], 0.0
        for base in bases:
            attempt_no = self.outcomes.get(base, {}).get("attempts", 0) + 1
            cid = f"{base}-a{attempt_no}"
            assert len(cid) <= 64 and all(c.isalnum() or c in "-_" for c in cid), cid
            params = self.requests[base]
            reqs.append({"custom_id": cid, "params": params})
            max_usd += max_charge(self.est_input_tokens(params), params["max_tokens"])
        _reserve(key, max_usd, self.purpose, self.reservation)
        attempt = {"attempt": n, "ledger_key": key, "state": "creating", "created_local": time.time(),
                   "created": utc_now(), "base_ids": bases, "custom_ids": [r["custom_id"] for r in reqs],
                   "max_usd": max_usd}
        self.manifest["attempts"].append(attempt)
        self._save()
        try:
            batch = self.client_noretry.messages.batches.create(requests=reqs)
        except Exception as exc:
            if _definitive_rejection(exc):
                attempt["state"] = "rejected"
                attempt["error"] = f"{type(exc).__name__}"
                self._save()
                _settle(key, 0.0, {}, state="rejected")
                raise
            attempt["state"] = "ambiguous"
            attempt["error"] = f"{type(exc).__name__}"
            self._save()
            self.log(f"[{self.name}] create was ambiguous ({type(exc).__name__}); resolving by listing")
            self._resolve_ambiguous(attempt)
            return attempt
        attempt.update(state="submitted", batch_id=batch.id)
        self._save()
        self.log(f"[{self.name}] submitted {len(reqs)} requests as {batch.id} (max ${max_usd:.2f})")
        return attempt

    def _resolve_ambiguous(self, attempt: dict, waits=(0, 120, 180)) -> None:
        for delay in waits:
            if delay:
                time.sleep(delay)
            matches = []
            for b in self.client.messages.batches.list(limit=50):
                created = b.created_at.timestamp()
                if created < attempt["created_local"] - 300:
                    break
                counts = b.request_counts
                total = (counts.processing + counts.succeeded + counts.errored
                         + counts.canceled + counts.expired)
                if total == len(attempt["custom_ids"]) and not self._known_batch(b.id):
                    matches.append(b.id)
            if len(matches) == 1:
                attempt.update(state="submitted", batch_id=matches[0], adopted=True)
                self._save()
                self.log(f"[{self.name}] adopted batch {matches[0]} after ambiguous create")
                return
            if len(matches) > 1:
                raise AmbiguousBatch(f"{self.name}: {len(matches)} batches match an ambiguous create; "
                                     "stopping instead of guessing")
        attempt["state"] = "not_created"
        self._save()
        _settle(attempt["ledger_key"], 0.0, {}, state="not_created")
        self.log(f"[{self.name}] no batch exists for the ambiguous create; safe to resubmit")

    def _known_batch(self, batch_id: str) -> bool:
        for d in CLAUDE_DIR.glob("*/manifest.json"):
            m = read_json(d)
            if any(a.get("batch_id") == batch_id for a in m.get("attempts", [])):
                return True
        return False

    # -- collection
    def collect(self, wait: bool = True) -> bool:
        """Poll every submitted attempt; collect ended ones. Returns True when
        nothing is in flight."""
        for attempt in self.manifest["attempts"]:
            if attempt["state"] in ("creating", "ambiguous"):
                self._resolve_ambiguous(attempt)
            if attempt["state"] != "submitted":
                continue
            while True:
                b = self.client.messages.batches.retrieve(attempt["batch_id"])
                if b.processing_status == "ended":
                    break
                if not wait:
                    return False
                rc = b.request_counts
                self.log(f"[{self.name}] {attempt['batch_id']} {b.processing_status}: "
                         f"processing={rc.processing} succeeded={rc.succeeded} errored={rc.errored}")
                time.sleep(self.poll_seconds)
            self._ingest(attempt)
        return all(a["state"] not in ("creating", "ambiguous", "submitted") for a in self.manifest["attempts"])

    def _ingest(self, attempt: dict) -> None:
        raw_path = self.dir / f"results-{attempt['batch_id']}.jsonl"
        if not raw_path.exists():
            lines = []
            for r in self.client.messages.batches.results(attempt["batch_id"]):
                lines.append(json.dumps(r.model_dump(mode="json"), ensure_ascii=False))
            raw_path.write_text("\n".join(lines) + "\n")
        expected = {cid: base for cid, base in zip(attempt["custom_ids"], attempt["base_ids"])}
        seen, total_usage, cost = set(), {}, 0.0
        for line in raw_path.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            cid = r["custom_id"]
            if cid not in expected:
                raise RuntimeError(f"{self.name}: result for unexpected custom_id {cid}")
            seen.add(cid)
            base = expected[cid]
            o = classify(r, self.parse)
            prev = self.outcomes.get(base, {})
            o["attempts"] = prev.get("attempts", 0) + 1
            o["custom_id"], o["batch_id"] = cid, attempt["batch_id"]
            o["history"] = prev.get("history", []) + [{"custom_id": cid, "status": o["status"]}]
            if prev.get("status") != FINAL_OK:
                self.outcomes[base] = o
            cost += usage_cost(o.get("usage", {}))
            for k, v in _usage_tokens(o.get("usage", {})).items():
                total_usage[k] = total_usage.get(k, 0) + v
        for cid, base in expected.items():
            if cid not in seen:           # no result row at all: treat as not processed
                prev = self.outcomes.get(base, {})
                if prev.get("status") != FINAL_OK:
                    self.outcomes[base] = {"status": "errored_recoverable", "detail": "missing_result",
                                           "attempts": prev.get("attempts", 0) + 1, "usage": {},
                                           "history": prev.get("history", []) + [{"custom_id": cid, "status": "missing"}]}
        self._save_outcomes()
        attempt.update(state="collected", collected=utc_now(), actual_usd=cost, usage=total_usage)
        self._save()
        _settle(attempt["ledger_key"], cost, total_usage)
        self.log(f"[{self.name}] collected {attempt['batch_id']}: ${cost:.3f}, statuses {self.status_counts()}")

    def run(self, chunk: int | None = None) -> dict:
        """Submit, wait and retry recoverable failures until done."""
        while True:
            self.collect(wait=True)
            if self.done():
                break
            if self.submit_pending(limit=chunk) is None and self.done():
                break
        return self.status_counts()


def _definitive_rejection(exc: Exception) -> bool:
    """A 4xx status response means the API refused to create anything."""
    status = getattr(exc, "status_code", None)
    return status is not None and 400 <= int(status) < 500 and int(status) not in (408, 409, 429)
