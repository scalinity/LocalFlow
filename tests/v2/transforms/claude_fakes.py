"""Offline stand-ins for the Anthropic client (ADR-0002).

``FakeClient`` answers ``client.beta.messages.stream(**kw)`` from a
script — a text (sent as the ``{"text"}`` structured answer), an object
(sent as JSON, the Prompt Engineer shape), ``Raw(text)`` (sent as is),
a ``(text, stop_reason)`` pair, or an exception to raise — and records
every request. ``claude_supervisor`` is a real WorkerSupervisor (never
spawned) whose transformer uses such a client, so a test drives the
app's real supervisor → Claude module → engine path without a network.
"""

import json
import tempfile
import types

from localflow.v2.supervisor import WorkerSupervisor
from localflow.v2.transforms import claude


class Raw(str):
    """An answer sent exactly as written (not wrapped as JSON)."""


class _Stream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


class FakeClient:
    def __init__(self, *script, model=None):
        self.script = list(script)
        self.model = model
        self.calls = []
        self.beta = types.SimpleNamespace(
            messages=types.SimpleNamespace(stream=self._stream))

    def _stream(self, **kw):
        self.calls.append(kw)
        item = self.script.pop(0) if self.script else ""
        if isinstance(item, BaseException):
            raise item
        stop = "end_turn"
        if isinstance(item, tuple):
            item, stop = item
        if isinstance(item, Raw):
            text = str(item)
        elif isinstance(item, str):
            text = json.dumps({"text": item}) if item else ""
        else:
            text = json.dumps(item)
        message = types.SimpleNamespace(
            stop_reason=stop, model=self.model or kw["model"],
            content=[types.SimpleNamespace(type="thinking", thinking=""),
                     types.SimpleNamespace(type="text", text=text)],
            usage=types.SimpleNamespace(input_tokens=120, output_tokens=40))
        return _Stream(message)


def transformer(client, key="test-key"):
    return claude.Transformer(key_reader=lambda: key,
                              client_factory=lambda k: client)


def claude_supervisor(*script):
    """(supervisor, client): a real, unspawned WorkerSupervisor whose
    transforms answer from ``script``."""
    client = FakeClient(*script)
    sup = WorkerSupervisor(audio_root=tempfile.mkdtemp(), asr_model="fake",
                           transformer=transformer(client))
    return sup, client


def pe_answer(prompt, pairs=(), uncertain=()):
    """A Prompt Engineer answer: the prompt plus its requirement map."""
    return {"prompt": prompt,
            "requirements": [{"source": s, "output": o} for s, o in pairs],
            "uncertain": list(uncertain)}
