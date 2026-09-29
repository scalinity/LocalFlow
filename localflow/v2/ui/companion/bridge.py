"""The companion's Python ↔ JavaScript bridge (pure Python, no AppKit).

One narrow, versioned, allowlisted channel. The web view sends a JSON
envelope ``{bridge_version, request_id, command, payload}``; the bridge
checks the version, looks the command up in its allowlist, validates the
payload against that command's schema BEFORE any production service is
touched, runs the handler and answers ``{request_id, status, result |
reason_code}``. Nothing else crosses: no method names, SQL, paths or
reflection — an unknown command is refused, never resolved.

Statuses mirror the domain's outcome classes: ``success``, ``refusal``
(the service or a guard said no; nothing happened), ``outcome_unknown``
(admitted but unanswered — the write may still land), ``cancelled``,
``stale`` (the item the view acted on is no longer the one on screen),
``unavailable`` (the surface or service is absent) and ``error`` (an
unexpected failure; its reason is the exception TYPE only, content-free).
"""

from __future__ import annotations

import json

BRIDGE_VERSION = 1
MAX_ENVELOPE_BYTES = 2_000_000  # a Scratchpad note edit is the largest payload

STATUSES = ("success", "refusal", "outcome_unknown", "cancelled", "stale",
            "unavailable", "error")


class Outcome(Exception):
    """A typed non-success answer raised from a handler."""

    def __init__(self, status, reason_code=None, result=None):
        if status not in STATUSES or status == "success":
            raise ValueError(f"bad outcome status {status!r}")
        super().__init__(reason_code or status)
        self.status = status
        self.reason_code = reason_code
        self.result = result


def refuse(reason_code, result=None):
    raise Outcome("refusal", reason_code, result)


def stale(reason_code="stale", result=None):
    raise Outcome("stale", reason_code, result)


def unknown(reason_code="outcome_unknown", result=None):
    raise Outcome("outcome_unknown", reason_code, result)


def unavailable(reason_code="unavailable"):
    raise Outcome("unavailable", reason_code)


# ---- payload schemas ------------------------------------------------------------


class SchemaError(ValueError):
    pass


class Field:
    optional = False

    def check(self, name, value):
        raise NotImplementedError


class Str(Field):
    def __init__(self, max_len=10_000, optional=False, allow_empty=True):
        self.max_len, self.optional, self.allow_empty = \
            max_len, optional, allow_empty

    def check(self, name, value):
        if not isinstance(value, str):
            raise SchemaError(f"{name}: not_a_string")
        if len(value) > self.max_len:
            raise SchemaError(f"{name}: too_long")
        if not self.allow_empty and not value:
            raise SchemaError(f"{name}: empty")
        return value


class Int(Field):
    def __init__(self, lo=None, hi=None, optional=False):
        self.lo, self.hi, self.optional = lo, hi, optional

    def check(self, name, value):
        if isinstance(value, bool) or not isinstance(value, int):
            raise SchemaError(f"{name}: not_an_integer")
        if (self.lo is not None and value < self.lo) or \
                (self.hi is not None and value > self.hi):
            raise SchemaError(f"{name}: out_of_range")
        return value


class Bool(Field):
    def __init__(self, optional=False):
        self.optional = optional

    def check(self, name, value):
        if not isinstance(value, bool):
            raise SchemaError(f"{name}: not_a_boolean")
        return value


class Enum(Field):
    def __init__(self, values, optional=False):
        self.values, self.optional = tuple(values), optional

    def check(self, name, value):
        if value not in self.values:
            raise SchemaError(f"{name}: not_allowed")
        return value


class Nullable(Field):
    """``None`` or the wrapped field."""

    def __init__(self, inner, optional=False):
        self.inner, self.optional = inner, optional

    def check(self, name, value):
        return None if value is None else self.inner.check(name, value)


class List(Field):
    def __init__(self, item, max_items=100, optional=False):
        self.item, self.max_items, self.optional = item, max_items, optional

    def check(self, name, value):
        if not isinstance(value, list):
            raise SchemaError(f"{name}: not_a_list")
        if len(value) > self.max_items:
            raise SchemaError(f"{name}: too_many")
        return [self.item.check(f"{name}[{i}]", v)
                for i, v in enumerate(value)]


class Obj(Field):
    """A nested object with its own strict field set."""

    def __init__(self, fields, optional=False):
        self.fields, self.optional = fields, optional

    def check(self, name, value):
        return validate(value, self.fields, prefix=f"{name}.")


def validate(payload, fields, prefix=""):
    """Strict: every declared field is checked, an undeclared one refuses."""
    if not isinstance(payload, dict):
        raise SchemaError(f"{prefix or 'payload'}: not_an_object")
    extra = set(payload) - set(fields)
    if extra:
        raise SchemaError(f"{prefix}{sorted(extra)[0]}: unexpected_field")
    out = {}
    for name, spec in fields.items():
        if name not in payload:
            if spec.optional:
                continue
            raise SchemaError(f"{prefix}{name}: missing")
        out[name] = spec.check(prefix + name, payload[name])
    return out


# ---- JSON-safe read models -----------------------------------------------------------


def plain(value, _depth=0):
    """Service data → JSON-safe plain data (tuples → lists, bytes dropped,
    anything exotic → its string form). Read models pick their fields
    before this runs; it only guarantees serializability."""
    if _depth > 40:
        return None
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"),
                                                         float("-inf")) \
            else None
    if isinstance(value, dict):
        return {str(k): plain(v, _depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v, _depth + 1) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(plain(v, _depth + 1) for v in value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return None
    return str(value)


def dumps(value) -> str:
    return json.dumps(plain(value), ensure_ascii=False, separators=(",", ":"))


# ---- dispatcher ----------------------------------------------------------------------


class Bridge:
    """Allowlist of commands → (schema, handler). ``handle`` never raises."""

    def __init__(self, on_error=None):
        self._commands = {}
        self.on_error = on_error  # (command, exc_type_name) → None

    def command(self, name, fields=None):
        """Decorator registering ``fn(payload) -> result``."""
        def register(fn):
            if name in self._commands:
                raise ValueError(f"duplicate command {name!r}")
            self._commands[name] = (fields or {}, fn)
            return fn
        return register

    def add(self, name, fields, fn):
        self.command(name, fields)(fn)

    @property
    def commands(self):
        return tuple(sorted(self._commands))

    def handle(self, raw) -> dict:
        request_id = None
        try:
            if not isinstance(raw, str) or len(raw) > MAX_ENVELOPE_BYTES:
                return self._answer(None, "refusal", "bad_envelope")
            try:
                env = json.loads(raw)
            except ValueError:
                return self._answer(None, "refusal", "bad_envelope")
            if not isinstance(env, dict):
                return self._answer(None, "refusal", "bad_envelope")
            request_id = env.get("request_id")
            if not isinstance(request_id, str) or len(request_id) > 64:
                return self._answer(None, "refusal", "bad_envelope")
            if env.get("bridge_version") != BRIDGE_VERSION:
                return self._answer(request_id, "refusal",
                                    "bridge_version_mismatch")
            if set(env) - {"bridge_version", "request_id", "command",
                           "payload"}:
                return self._answer(request_id, "refusal", "bad_envelope")
            command = env.get("command")
            entry = self._commands.get(command) \
                if isinstance(command, str) else None
            if entry is None:
                return self._answer(request_id, "refusal", "unknown_command")
            fields, fn = entry
            try:
                payload = validate(env.get("payload", {}), fields)
            except SchemaError as e:
                return self._answer(request_id, "refusal",
                                    f"invalid_payload:{e}")
            try:
                result = fn(payload)
            except Outcome as o:
                return self._answer(request_id, o.status, o.reason_code,
                                    o.result)
            except Exception as e:  # content-free: the type only
                if self.on_error is not None:
                    try:
                        self.on_error(command, type(e).__name__)
                    except Exception:
                        pass
                return self._answer(request_id, "error", type(e).__name__)
            return self._answer(request_id, "success", None, result)
        except Exception as e:  # never let the web view see a traceback
            return self._answer(request_id, "error", type(e).__name__)

    @staticmethod
    def _answer(request_id, status, reason_code=None, result=None):
        out = {"request_id": request_id, "status": status}
        if reason_code is not None:
            out["reason_code"] = reason_code
        if result is not None:
            out["result"] = plain(result)
        return out
