"""Selected-text transforms on Claude (ADR-0002).

Polish, Concise, Prompt Engineer and custom transforms run on the
Anthropic Messages API from the app process; the local worker and its
GPU lock are not involved. ``MODELS`` is the one table of models and
reasoning levels: the engine, the Hub and scripts/v2's evaluation all
read it, so nothing can offer a combination the API rejects.

The selected text is sent to Anthropic. The key is read from the login
Keychain (service LocalFlow, account TRANSFORMS_ANTHROPIC_API_KEY)
through /usr/bin/security and is never logged, emitted or stored. With
no key, no SDK or no network the transform reports why; it never falls
back to the local cleanup model.
"""

from __future__ import annotations

import subprocess
import threading
import time

KEYCHAIN_SERVICE = "LocalFlow"
KEYCHAIN_ACCOUNT = "TRANSFORMS_ANTHROPIC_API_KEY"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS = 32000
EFFORTS = ("low", "medium", "high", "xhigh", "max")
CAPABILITY_VERIFIED_ON = "2026-10-22"
# Thinking off is accepted only at effort high or below; it is sent at
# high, the most thorough level that allows it.
OFF_EFFORT = "high"

# model id → what the API accepts for it. ``thinking_off`` is the one
# request shape that turns thinking off (None: it cannot be turned off);
# ``fallbacks`` says whether the server-side refusal fallback exists.
MODELS = {
    "claude-haiku-5-5": {
        "label": "Haiku 5.5", "thinking_off": {"type": "disabled"},
        "fallbacks": False, "usd_per_mtok": (0.10, 0.50)},
    "claude-sonnet-5-5": {
        "label": "Sonnet 5.5", "thinking_off": {"type": "between_tools"},
        "fallbacks": True, "usd_per_mtok": (2.00, 10.00)},
    "claude-opus-5-5": {
        "label": "Opus 5.5", "thinking_off": None,
        "fallbacks": True, "usd_per_mtok": (4.00, 20.00)},
}
REASONING_LABELS = {"off": "Thinking off", "low": "Low", "medium": "Medium",
                    "high": "High", "xhigh": "Extra high", "max": "Max"}

# Polish/Concise retain ADR-0002's execution selections. Prompt engineering
# uses the intelligence evaluation's separate selection and frozen holdout;
# definition authoring and memory extraction have their own bounded roles.
# Custom transform execution retains Polish's selection.
RECOMMENDED = {
    "polish": ("claude-opus-5-5", "medium"),
    "concise": ("claude-opus-5-5", "high"),
    "prompt_engineer": ("claude-sonnet-5-5", "xhigh"),
}
ROLE_RECOMMENDED = {
    "definition_authoring": ("claude-sonnet-5-5", "medium"),
    "memory_extraction": ("claude-haiku-5-5", "off"),
}


def reasoning_levels(model: str) -> tuple:
    spec = MODELS[model]
    return (("off",) if spec["thinking_off"] else ()) + EFFORTS


def configurations() -> list[tuple[str, str]]:
    """Every valid (model, reasoning) pair, in table order."""
    return [(m, r) for m in MODELS for r in reasoning_levels(m)]


def is_valid(model, reasoning) -> bool:
    return isinstance(model, str) and isinstance(reasoning, str) \
        and model in MODELS and reasoning in reasoning_levels(model)


def recommended(mode: str) -> tuple[str, str]:
    return RECOMMENDED.get(mode, RECOMMENDED["polish"])


def served_label(model, reasoning):
    """``model@reasoning`` — the provenance one model_id column holds."""
    return f"{model}@{reasoning}" if model else None


def request_options(model: str, reasoning: str) -> dict:
    """The thinking/effort/fallback fields for one valid pair."""
    if not is_valid(model, reasoning):
        raise ValueError(f"invalid model/reasoning pair: {model}/{reasoning}")
    spec = MODELS[model]
    if reasoning == "off":
        opts = {"thinking": dict(spec["thinking_off"]),
                "output_config": {"effort": OFF_EFFORT}}
    else:
        opts = {"thinking": {"type": "adaptive"},
                "output_config": {"effort": reasoning}}
    if spec["fallbacks"]:
        opts.update(betas=[FALLBACK_BETA], fallbacks="default")
    return opts


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    i, o = MODELS[model]["usd_per_mtok"]
    return (input_tokens * i + output_tokens * o) / 1e6


class TransformUnavailable(Exception):
    """A content-free reason the request produced no result; ``model``
    is the model that answered, when one did (a refusal, a cut-off)."""

    def __init__(self, code: str, model=None, usage=None):
        super().__init__(code)
        self.code = code
        self.model = model
        self.usage = usage


def read_api_key():
    """TRANSFORMS_ANTHROPIC_API_KEY from the login Keychain; None when
    absent. /usr/bin/security created the item, so no prompt appears."""
    try:
        done = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s",
             KEYCHAIN_SERVICE, "-a", KEYCHAIN_ACCOUNT, "-w"],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    key = done.stdout.strip() if done.returncode == 0 else ""
    return key or None


def make_client(api_key):
    try:
        import anthropic  # LF-R25 allowlist (ADR-0002)
    except ImportError as e:
        raise TransformUnavailable("sdk_missing") from e
    return anthropic.Anthropic(
        api_key=api_key, max_retries=0,
        timeout=anthropic.Timeout(300.0, connect=5.0))


def call(client, *, model, reasoning, system, messages, schema=None,
         tools=None, max_tokens=MAX_TOKENS) -> dict:
    """One Messages request → {text, model, reasoning, input_tokens,
    output_tokens, latency_ms}. Raises TransformUnavailable with a
    reason code for every outcome that is not a usable answer."""
    import anthropic  # LF-R25 allowlist (ADR-0002)
    opts = request_options(model, reasoning)
    output_config = dict(opts.pop("output_config"))
    if schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": anthropic.transform_schema(schema)}
    if tools:
        opts["tools"] = [{**tool, "strict": True,
            "input_schema": anthropic.transform_schema(tool["input_schema"])}
            for tool in tools]
    t0 = time.monotonic()
    try:
        with client.beta.messages.stream(
                model=model, max_tokens=max_tokens, system=system,
                messages=messages, output_config=output_config,
                **opts) as stream:
            message = stream.get_final_message()
    except (anthropic.AuthenticationError,
            anthropic.PermissionDeniedError) as e:
        raise TransformUnavailable("api_key_rejected") from e
    except anthropic.RateLimitError as e:
        raise TransformUnavailable("rate_limited") from e
    except anthropic.APITimeoutError as e:
        raise TransformUnavailable("timeout") from e
    except anthropic.APIConnectionError as e:
        raise TransformUnavailable("network_unavailable") from e
    except anthropic.BadRequestError as e:
        # A spending cap set on the account answers 400 like a malformed
        # request; no SDK type tells them apart, only the error message.
        if "usage limit" in str(getattr(e, "message", "")).lower():
            raise TransformUnavailable("usage_limit_reached") from e
        raise TransformUnavailable("request_rejected") from e
    except anthropic.APIStatusError as e:
        raise TransformUnavailable(f"api_error_{e.status_code}") from e
    latency_ms = round((time.monotonic() - t0) * 1000.0, 1)
    served = getattr(message, "model", None) or model
    usage = getattr(message, "usage", None)
    measurement = {"model": served, "reasoning": reasoning,
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None),
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", None),
        "latency_ms": latency_ms}
    if message.stop_reason == "refusal":
        raise TransformUnavailable("model_refused", served, measurement)
    if message.stop_reason in ("max_tokens",
                               "model_context_window_exceeded"):
        raise TransformUnavailable("output_limit", served, measurement)
    blocks = list(message.content)
    start = max((i for i, b in enumerate(blocks)
                 if getattr(b, "type", None) == "fallback"), default=-1) + 1
    text = "".join(b.text for b in blocks[start:]
                   if getattr(b, "type", None) == "text")
    usage = getattr(message, "usage", None)
    result = {"text": text,
            "model": getattr(message, "model", None) or model,
            "reasoning": reasoning,
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None),
            "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", None),
            "latency_ms": latency_ms}
    if tools is not None:
        result["tool_calls"] = [{"id": b.id, "name": b.name, "input": b.input}
            for b in blocks if getattr(b, "type", None) == "tool_use"]
        # Continuation is in-memory transport state, never stored or shown.
        result["_continuation"] = [b.model_dump() for b in blocks if hasattr(b, "model_dump")]
        result["stop_reason"] = message.stop_reason
    return result


class Transformer:
    """The app's transform runner. The key is read on every run and the
    client reused only while the key is unchanged, so adding, replacing
    or removing it in the Keychain takes effect on the next transform.
    ``close`` (the supervisor's shutdown) refuses new transforms and
    closes the client; an answer that arrives afterwards is discarded."""

    def __init__(self, key_reader=read_api_key, client_factory=make_client):
        self._key_reader = key_reader
        self._client_factory = client_factory
        self._client = None
        self._key = None
        self._closed = False
        self._lock = threading.Lock()

    def request(self, system, messages, schema, model=None, reasoning=None, *, max_tokens=MAX_TOKENS):
        model = model or recommended("prompt_engineer")[0]
        reasoning = reasoning or recommended("prompt_engineer")[1]
        if not is_valid(model, reasoning):
            raise TransformUnavailable("unsupported_configuration")
        result = call(self._get_client(), model=model, reasoning=reasoning,
                      system=system, messages=messages, schema=schema, max_tokens=max_tokens)
        if self._closed:
            raise TransformUnavailable("closed_in_flight")
        return result

    def tool_turn(self, system, messages, tools, model=None, reasoning=None, max_tokens=4096):
        model = model or recommended("prompt_engineer")[0]
        reasoning = reasoning or recommended("prompt_engineer")[1]
        if not is_valid(model, reasoning):
            raise TransformUnavailable("unsupported_configuration")
        result = call(self._get_client(), model=model, reasoning=reasoning,
                      system=system, messages=messages, tools=tools,
                      max_tokens=max_tokens)
        if self._closed:
            raise TransformUnavailable("closed_in_flight")
        return result

    def close(self):
        with self._lock:
            self._closed = True
            client, self._client, self._key = self._client, None, None
        if client is not None and hasattr(client, "close"):
            try:
                client.close()
            except Exception:  # noqa: BLE001 — closing is best effort
                pass

    def _get_client(self):
        with self._lock:
            if self._closed:
                raise TransformUnavailable("closed")
            key = self._key_reader()
            if not key:
                self._client = self._key = None
                raise TransformUnavailable("no_api_key")
            if self._client is None or key != self._key:
                self._client, self._key = self._client_factory(key), key
            return self._client

    def run(self, job, model=None, reasoning=None, *, request_guard=None,
            response_observer=None, context_current=None, cancelled=None):
        """Execute one TransformJob → TransformResult (never raises for
        a request failure: the result carries the reason)."""
        from . import engine
        if model is None and reasoning is None:
            model, reasoning = recommended(job.mode)
        elif not is_valid(model, reasoning):
            return engine.TransformResult(job=job, output=job.source,
                path=engine.PATH_FALLBACK_ORIGINAL,
                reason="transform_unavailable:unsupported_configuration",
                validator_revision=engine.VALIDATOR_REVISION)

        def generate(system, messages, schema):
            output_cap = MAX_TOKENS
            if request_guard:
                output_cap = request_guard(system, messages, schema) or MAX_TOKENS
            if cancelled and cancelled():
                raise TransformUnavailable("cancelled")
            if context_current and not context_current(job.context_pack):
                raise TransformUnavailable("context_revoked")
            client = self._get_client()
            try:
                out = call(client, model=model, reasoning=reasoning,
                           system=system, messages=messages, schema=schema, max_tokens=output_cap)
            except TransformUnavailable as e:
                if e.code == "api_key_rejected":
                    with self._lock:
                        self._client = self._key = None
                if self._closed:
                    raise TransformUnavailable("closed_in_flight") from e
                raise
            except Exception as e:
                if self._closed:
                    raise TransformUnavailable("closed_in_flight") from e
                raise
            if self._closed:
                raise TransformUnavailable("closed_in_flight")
            if response_observer:
                response_observer(out)
            return out
        def verify(system, messages, schema):
            output_cap = MAX_TOKENS
            if request_guard:
                output_cap = request_guard(system, messages, schema) or MAX_TOKENS
            if cancelled and cancelled():
                raise TransformUnavailable("cancelled")
            if context_current and not context_current(job.context_pack):
                raise TransformUnavailable("context_revoked")
            from .quality import VERIFIER
            out = self.request(system, messages, schema, *VERIFIER, max_tokens=output_cap)
            if response_observer:
                response_observer(out)
            return out
        return engine.run_transform(job, generate, model=model,
            reasoning=reasoning, verify=verify, context_current=context_current,
            cancelled=cancelled)
