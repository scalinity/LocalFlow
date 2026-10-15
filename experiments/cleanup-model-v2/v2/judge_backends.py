"""Other-vendor judges: bounded spend, durable requests, and no implicit retry.

Clients are constructed lazily, after the data and budget checks. Tests inject
clients. Unknown submission/billing state retains its reservation and stops.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path

from .common import ART, CONFIG, ROOT, read_json, write_json, utc_now, sha256_text

MODELS = {"openai": "gpt-6.1-sol", "openrouter": "meta/muse-spark-1.3-contributor"}
CAPS = {"openai": 40.0, "openrouter": 5.0}
PRICES = {"openai": {"input": 1.0, "output": 5.0},
          "openrouter": {"input": 0.10, "output": 0.20}}
KEYS = {"openai": "JUDGES_OPENAI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}


class BudgetExceeded(RuntimeError):
    pass


class UnresolvedSubmission(RuntimeError):
    pass


class APIError(RuntimeError):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__(f"Judge HTTP status {status_code}; response body withheld")


def api_key(backend):
    """Environment first, then the same repo-relative .env as lfx.common."""
    variable = KEYS[backend]
    if os.environ.get(variable):
        return os.environ[variable]
    env_path = Path(CONFIG["paths"]["env_file"]).expanduser()
    if not env_path.is_absolute():
        env_path = ROOT / env_path
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip().removeprefix("export ").strip()
            key, sep, value = line.partition("=")
            if sep and key.strip() == variable:
                value = value.strip().strip('"').strip("'")
                if value:
                    return value
    raise RuntimeError(f"Missing {variable}")


def request_params(params, backend):
    """Translate the envelope only; system text and the blinded view are exact."""
    body = {"model": params["model"],
            "messages": [{"role": "system", "content": params["system"][0]["text"]},
                         *params["messages"]],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "cleanup_verdicts", "strict": True,
                "schema": params["output_config"]["format"]["schema"]}}}
    if backend == "openai":
        body.update(max_completion_tokens=params["max_tokens"], reasoning_effort="low", store=False)
    else:
        body.update(max_tokens=params["max_tokens"], provider={"require_parameters": True})
    return body


def input_tokens(params):
    # One token per UTF-8 byte plus schema/protocol headroom, as in data.wave.
    return len(json.dumps(params, ensure_ascii=False).encode("utf-8")) + 1500


def charge(backend, usage):
    return (usage["input_tokens"] * PRICES[backend]["input"] +
            usage["output_tokens"] * PRICES[backend]["output"]) / 1e6


def estimate(backend, params):
    return charge(backend, {"input_tokens": input_tokens(params),
                            "output_tokens": params.get("max_completion_tokens", params.get("max_tokens"))})


@contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def totals(ledger, backend):
    entries = [e for e in ledger["entries"].values() if e["backend"] == backend]
    return {"actual_usd": sum(e.get("actual_usd", 0) for e in entries),
            "reserved_usd": sum(e["max_usd"] for e in entries if e["state"] == "reserved"),
            "outstanding_usd": sum(e["max_usd"] for e in entries if e["state"] == "outstanding")}


class HTTPClient:
    """Fixed vendor endpoints, no redirects, SDK retries, or logged credentials."""
    def __init__(self, backend):
        self.base = {"openai": "https://api.openai.com/v1",
                     "openrouter": "https://openrouter.ai/api/v1"}[backend]
        self.key = api_key(backend)

    def _request(self, method, path, body=None, content_type="application/json", raw=False):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Authorization": "Bearer " + self.key,
                                              "Content-Type": content_type})
        try:
            with urllib.request.build_opener(NoRedirect).open(req, timeout=120) as response:
                data = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise APIError(exc.code) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise UnresolvedSubmission("Judge transport failed; response state unknown") from None
        return data if raw else json.loads(data)

    def upload(self, rows):
        boundary = "judge" + uuid.uuid4().hex
        payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nbatch\r\n"
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"judge.jsonl\"\r\n"
                f"Content-Type: application/jsonl\r\n\r\n{payload}\r\n--{boundary}--\r\n").encode()
        return self._request("POST", "/files", body, f"multipart/form-data; boundary={boundary}")["id"]

    def create_batch(self, file_id, metadata):
        return self._request("POST", "/batches", {"input_file_id": file_id,
                             "endpoint": "/v1/chat/completions", "completion_window": "24h",
                             "metadata": metadata})

    def list_batches(self):
        after = None
        while True:
            page = self._request("GET", "/batches?limit=100" + ("&after=" + urllib.parse.quote(after) if after else ""))
            yield from page["data"]
            if not page.get("has_more"):
                break
            after = page["last_id"]

    def retrieve(self, batch_id):
        return self._request("GET", "/batches/" + urllib.parse.quote(batch_id, safe=""))

    def results(self, batch):
        rows = []
        for field in ("output_file_id", "error_file_id"):
            if batch.get(field):
                data = self._request("GET", "/files/" + urllib.parse.quote(batch[field], safe="") + "/content", raw=True)
                rows.extend(json.loads(line) for line in data.splitlines() if line.strip())
        return rows

    def complete(self, params):
        return self._request("POST", "/chat/completions", params)


class OtherWave:
    def __init__(self, name, requests, parse, backend, *, root=None, client=None,
                 poll_seconds=30, log=print):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", name):
            raise ValueError("Judge name must contain only letters, digits, underscores and hyphens")
        if backend not in MODELS or any(p["model"] != MODELS[backend] for p in requests.values()):
            raise ValueError("No approved price for this judge model")
        self.backend, self.name, self.parse = backend, name, parse
        self.requests = {rid: request_params(p, backend) for rid, p in requests.items()}
        self.hash = sha256_text(json.dumps(self.requests, sort_keys=True, ensure_ascii=False))
        self.root = Path(root) if root is not None else ART / "judge"
        self.dir = self.root / backend / name
        self.ledger_path = self.root / "ledger-other.json"
        self.manifest_path = self.dir / "manifest.json"
        self.outcomes_path = self.dir / "outcomes.json"
        self.client, self.poll_seconds, self.log = client, poll_seconds, log
        with locked(self.dir / ".wave.lock"):
            self.manifest = read_json(self.manifest_path)
            if self.manifest is None:
                self.manifest = {"backend": backend, "name": name, "request_hash": self.hash,
                                 "prices_per_million": PRICES[backend], "cap_usd": CAPS[backend],
                                 "created": utc_now(), "attempts": []}
                write_json(self.dir / "requests.json", self.requests)
                self._save()
            if self.manifest["request_hash"] != self.hash:
                raise RuntimeError("Judge requests changed; use a new name")
            self.outcomes = read_json(self.outcomes_path, {})

    def _save(self):
        write_json(self.manifest_path, self.manifest)

    def _ledger(self):
        return read_json(self.ledger_path, {"entries": {}})

    def _check(self, ledger, amount):
        t = totals(ledger, self.backend)
        projected = sum(t.values()) + amount
        if projected > CAPS[self.backend] + 1e-12:
            raise BudgetExceeded(f"{self.backend}: projected ${projected:.6f} exceeds cap ${CAPS[self.backend]:.2f}")

    def _reserve(self, attempt):
        with locked(self.root / ".ledger-other.lock"):
            ledger = self._ledger()
            key = attempt["key"]
            if key not in ledger["entries"]:
                self._check(ledger, attempt["max_usd"])
                ledger["entries"][key] = {"backend": self.backend, "state": "reserved",
                                           "max_usd": attempt["max_usd"], "created": utc_now()}
                write_json(self.ledger_path, ledger)

    def _entry(self, attempt, **fields):
        with locked(self.root / ".ledger-other.lock"):
            ledger = self._ledger()
            ledger["entries"][attempt["key"]].update(fields)
            write_json(self.ledger_path, ledger)

    def _client(self):
        if self.client is None:
            self.client = HTTPClient(self.backend)
        return self.client

    def _submit(self, attempt):
        client = self._client()
        rows = [{"custom_id": rid, "method": "POST", "url": "/v1/chat/completions",
                 "body": self.requests[rid]} for rid in attempt["ids"]]
        if self.backend == "openai" and not attempt.get("file_id"):
            # Uploads cannot trigger inference. A lost upload can safely repeat.
            attempt["file_id"] = client.upload(rows)
            self._save()
        attempt["state"] = "creating"
        self._entry(attempt, state="outstanding")
        self._save()
        try:
            if self.backend == "openai":
                batch = client.create_batch(attempt["file_id"], {"judge_key": attempt["key"], "request_hash": self.hash})
                attempt.update(state="submitted", batch_id=batch["id"])
            else:
                body = client.complete(rows[0]["body"])
                write_json(self.dir / attempt["raw_file"], [{"custom_id": attempt["ids"][0],
                           "response": {"status_code": 200, "body": body}}])
                attempt["state"] = "received"
            self._save()
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status is not None and 400 <= status < 500 and status not in (408, 409, 429):
                attempt["state"] = "rejected"
                self._entry(attempt, state="settled", actual_usd=0, usage={})
            else:
                attempt["state"] = "ambiguous"
            self._save()
            raise UnresolvedSubmission(f"{self.backend}: submission {attempt['state']}; inspect manifest before resuming") from None

    def _collect(self, attempt):
        raw_path = self.dir / attempt["raw_file"]
        if raw_path.exists():
            attempt["state"] = "received"
        if attempt["state"] in ("creating", "ambiguous"):
            matches = []
            if self.backend == "openai":
                matches = [b for b in self._client().list_batches()
                           if b.get("metadata", {}).get("judge_key") == attempt["key"]
                           and b.get("metadata", {}).get("request_hash") == self.hash]
            if len(matches) != 1:
                raise UnresolvedSubmission("Submission unresolved; reservation retained, no automatic re-submission")
            attempt.update(state="submitted", batch_id=matches[0]["id"])
            self._save()
        if attempt["state"] == "submitted":
            while True:
                batch = self._client().retrieve(attempt["batch_id"])
                if batch["status"] in ("completed", "failed", "expired", "cancelled"):
                    break
                time.sleep(self.poll_seconds)
            rows = self._client().results(batch)
            write_json(raw_path, rows)
            attempt["state"] = "received"
            self._save()
        if attempt["state"] != "received":
            return
        rows = read_json(raw_path)
        ids = [r["custom_id"] for r in rows]
        if len(ids) != len(set(ids)) or set(ids) != set(attempt["ids"]):
            raise UnresolvedSubmission("Incomplete or duplicate batch results; reservation retained")
        usage = {"input_tokens": 0, "output_tokens": 0}
        outcomes = {}
        for row in rows:
            response = row.get("response") or {}
            if not 200 <= response.get("status_code", 0) < 300:
                # Only explicit per-request errors prove no completion was billed.
                if not row.get("error") and not response.get("status_code"):
                    raise UnresolvedSubmission("Unknown result billing; reservation retained")
                outcomes[row["custom_id"]] = {"status": "errored", "usage": {}}
                continue
            body = response["body"]
            u = body.get("usage") or {}
            if any(type(u.get(k)) is not int or u[k] < 0 for k in ("prompt_tokens", "completion_tokens")):
                raise UnresolvedSubmission("Missing token usage; reservation retained")
            for source, target in (("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens")):
                usage[target] += u[source]
            outcome = {"usage": u, "model": body.get("model"), "response_id": body.get("id")}
            try:
                choice = body["choices"][0]
                if choice["message"].get("refusal"):
                    outcome["status"] = "refused"
                elif choice.get("finish_reason") != "stop":
                    outcome["status"] = "truncated"
                else:
                    outcome.update(status="succeeded", value=self.parse(choice["message"]["content"]))
            except (IndexError, KeyError, TypeError, ValueError):
                outcome["status"] = "malformed"
            outcomes[row["custom_id"]] = outcome
        actual = charge(self.backend, usage)
        self._entry(attempt, state="settled", actual_usd=actual, usage=usage, settled=utc_now())
        self.outcomes.update(outcomes)
        write_json(self.outcomes_path, self.outcomes)
        attempt.update(state="collected", actual_usd=actual, usage=usage)
        self._save()
        if actual > attempt["max_usd"] + 1e-12:
            raise BudgetExceeded("Returned usage exceeded reservation; stopped before further submissions")

    def run(self, chunk=200):
        with locked(self.dir / ".wave.lock"):
            self.manifest = read_json(self.manifest_path)
            self.outcomes = read_json(self.outcomes_path, {})
            for attempt in self.manifest["attempts"]:
                if attempt["state"] == "prepared":
                    self._reserve(attempt)
                    self._submit(attempt)
                self._collect(attempt)
                if attempt["state"] == "rejected":
                    raise UnresolvedSubmission("Definitively rejected request; use a new corrected wave name")
            pending = [rid for rid in self.requests if rid not in self.outcomes]
            amount = sum(estimate(self.backend, self.requests[rid]) for rid in pending)
            self.log(json.dumps({"backend": self.backend, "pending_requests": len(pending),
                                 "estimate_max_usd": amount, "cap_usd": CAPS[self.backend]}))
            with locked(self.root / ".ledger-other.lock"):
                self._check(self._ledger(), amount)
            size = max(1, chunk) if self.backend == "openai" else 1
            for offset in range(0, len(pending), size):
                ids = pending[offset:offset + size]
                number = len(self.manifest["attempts"]) + 1
                attempt = {"key": f"{self.backend}:{self.name}:{number}:{self.hash[:16]}",
                           "state": "prepared", "ids": ids, "raw_file": f"results-{number}.json",
                           "max_usd": sum(estimate(self.backend, self.requests[rid]) for rid in ids)}
                self.manifest["attempts"].append(attempt)
                self._save()
                self._reserve(attempt)
                self._submit(attempt)
                self._collect(attempt)
        return self.outcomes
