"""ADR-0002: selected-text transforms on Claude (offline).

The one model table and the request it builds per model, the reason
codes for every non-answer, the Keychain key handling, the per-transform
model choice in transform_meta, and the Hub's pickers through the real
companion bridge. A fake Anthropic client answers; nothing here reaches
the network.

Run: .venv/bin/python tests/v2/context/run_isolated.py \
    tests/v2/transforms/test_claude_transforms.py
"""

import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve()
for p in (HERE.parents[3], HERE.parent, HERE.parents[1] / "ui",
          HERE.parents[1] / "lifecycle"):
    sys.path.insert(0, str(p))

import anthropic  # noqa: E402
import httpx2  # noqa: E402

import claude_fakes  # noqa: E402
from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2 import transforms as tf  # noqa: E402
from localflow.v2 import transforms_store as tstore  # noqa: E402
from localflow.v2.transforms import claude  # noqa: E402

REQ = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _job(mode="polish", source="so um lets meet at 3pm i think"):
    defn = next(d for d in tf.built_ins() if d.mode == mode)
    return tf.job_for_definition(defn, source)


def test_table_offers_exactly_the_valid_pairs():
    pairs = claude.configurations()
    assert len(pairs) == 17, pairs
    assert claude.reasoning_levels("claude-haiku-5-5") == (
        "off", "low", "medium", "high", "xhigh", "max")
    assert claude.reasoning_levels("claude-sonnet-5-5")[0] == "off"
    assert "off" not in claude.reasoning_levels("claude-opus-5-5")
    assert not claude.is_valid("claude-opus-5-5", "off")
    assert not claude.is_valid("claude-opus-5-5-20260401", "low")
    for mode in ("polish", "concise", "prompt_engineer"):
        assert claude.is_valid(*claude.recommended(mode)), mode
    assert claude.recommended("custom") == claude.recommended("polish")
    print("ok  table: 17 pairs, thinking off only where the model allows")


def test_request_shape_per_model():
    o = claude.request_options("claude-haiku-5-5", "off")
    assert o == {"thinking": {"type": "disabled"},
                 "output_config": {"effort": "high"}}, o  # no fallbacks
    o = claude.request_options("claude-sonnet-5-5", "off")
    assert o["thinking"] == {"type": "between_tools"}  # nothing else in it
    assert o["output_config"] == {"effort": "high"}
    assert o["betas"] == ["server-side-fallback-2026-07-01"] \
        and o["fallbacks"] == "default"
    o = claude.request_options("claude-opus-5-5", "max")
    assert o["thinking"] == {"type": "adaptive"} \
        and o["output_config"] == {"effort": "max"} and o["fallbacks"]
    assert "fallbacks" not in claude.request_options("claude-haiku-5-5",
                                                     "xhigh")
    try:
        claude.request_options("claude-opus-5-5", "off")
        raise AssertionError("invalid pair accepted")
    except ValueError:
        pass
    # The request itself: contract as system, draft as the last user
    # turn, no sampling parameters, no prefill, room for thinking.
    client = claude_fakes.FakeClient("Let's meet at 3 p.m., I think.")
    res = claude_fakes.transformer(client).run(
        _job(), "claude-sonnet-5-5", "medium")
    kw = client.calls[0]
    assert kw["max_tokens"] >= 16000
    assert not {"temperature", "top_p", "top_k"} & set(kw)
    assert kw["messages"][-1]["role"] == "user"
    assert kw["messages"][-1]["content"].startswith("<draft>\n")
    assert kw["system"] == tf.prompts.POLISH_CONTRACT
    assert kw["output_config"]["format"]["schema"] == \
        tf.prompts.TEXT_SCHEMA
    assert res.path == "applied" and res.served_model_id == \
        "claude-sonnet-5-5@medium"
    pe = claude_fakes.FakeClient(claude_fakes.pe_answer("Do X."))
    claude_fakes.transformer(pe).run(_job("prompt_engineer", "do x"),
                                     "claude-haiku-5-5", "low")
    assert pe.calls[0]["output_config"]["format"]["schema"] == \
        tf.prompts.PROMPT_ENGINEER_SCHEMA
    print("ok  request: per-model thinking/effort/fallback; no sampling,"
          " no prefill, max_tokens >= 16000")


def test_every_non_answer_has_a_reason():
    cases = [
        (anthropic.APIConnectionError(request=REQ), "network_unavailable"),
        (anthropic.APITimeoutError(request=REQ), "timeout"),
        (anthropic.AuthenticationError(
            "x", response=httpx2.Response(401, request=REQ), body=None),
         "api_key_rejected"),
        (anthropic.RateLimitError(
            "x", response=httpx2.Response(429, request=REQ), body=None),
         "rate_limited"),
        (anthropic.BadRequestError(
            "x", response=httpx2.Response(400, request=REQ), body=None),
         "request_rejected"),
        (anthropic.BadRequestError(
            "You have reached your specified API usage limits. You will"
            " regain access on 2026-11-01 at 00:00 UTC.",
            response=httpx2.Response(400, request=REQ), body=None),
         "usage_limit_reached"),
        (anthropic.InternalServerError(
            "x", response=httpx2.Response(529, request=REQ), body=None),
         "api_error_529"),
        (("", "refusal"), "model_refused"),
        (("cut", "max_tokens"), "output_limit"),
    ]
    for answer, code in cases:
        client = claude_fakes.FakeClient(answer)
        res = claude_fakes.transformer(client).run(_job(), "claude-opus-5-5",
                                                   "low")
        assert res.path == "fallback_original" and res.output == \
            _job().source, (code, res.path)
        assert res.reason == f"transform_unavailable:{code}", res.reason
    print("ok  reasons: network, timeout, key, rate, usage limit, request,"
          " status, refusal and length each named")


def test_fallback_block_text_is_skipped():
    import types
    client = claude_fakes.FakeClient()

    def stream(**kw):
        msg = types.SimpleNamespace(
            stop_reason="end_turn", model="claude-opus-5",
            content=[types.SimpleNamespace(type="text", text="partial "),
                     types.SimpleNamespace(type="fallback"),
                     types.SimpleNamespace(
                         type="text", text='{"text": "Meet at 3 p.m."}')],
            usage=types.SimpleNamespace(input_tokens=1, output_tokens=1))
        return claude_fakes._Stream(msg)
    client.beta.messages.stream = stream
    res = claude_fakes.transformer(client).run(_job(), "claude-opus-5-5",
                                               "low")
    assert res.output == "Meet at 3 p.m." and res.model == "claude-opus-5"
    print("ok  a server-side fallback's answer is read after its block;"
          " the serving model is recorded")


def test_key_is_read_lazily_and_dropped_when_rejected():
    keys = [None, "k1", "k2"]
    made = []

    def factory(key):
        made.append(key)
        return claude_fakes.FakeClient(
            anthropic.AuthenticationError(
                "x", response=httpx2.Response(401, request=REQ),
                body=None) if key == "k1" else "Meet at three.")
    t = claude.Transformer(key_reader=lambda: keys.pop(0),
                           client_factory=factory)
    r1 = t.run(_job(), "claude-haiku-5-5", "low")
    assert r1.reason == "transform_unavailable:no_api_key" and not made
    assert r1.model is None  # nothing was sent
    r2 = t.run(_job(), "claude-haiku-5-5", "low")
    assert r2.reason == "transform_unavailable:api_key_rejected"
    r3 = t.run(_job(), "claude-haiku-5-5", "low")  # re-read, new client
    assert r3.path == "applied" and made == ["k1", "k2"], made
    # An invalid pair never reaches the API: the recommendation runs.
    c = claude_fakes.FakeClient("Meet at three.")
    r4 = claude_fakes.transformer(c).run(_job(), "claude-opus-5-5", "off")
    assert (r4.model, r4.reasoning) == claude.recommended("polish")
    print("ok  key: read on use, re-read after a miss, dropped on"
          " rejection; invalid pairs never sent")


def test_key_change_and_removal_take_effect_after_success():
    keys = ["k1", "k1", "k2", None]
    made = []

    def factory(key):
        made.append(key)
        return claude_fakes.FakeClient(*["Meet at three."] * 3)
    t = claude.Transformer(key_reader=lambda: keys.pop(0),
                           client_factory=factory)
    assert t.run(_job(), "claude-haiku-5-5", "low").path == "applied"
    assert t.run(_job(), "claude-haiku-5-5", "low").path == "applied"
    assert made == ["k1"]                       # same key: client reused
    assert t.run(_job(), "claude-haiku-5-5", "low").path == "applied"
    assert made == ["k1", "k2"]                 # replaced key: new client
    r = t.run(_job(), "claude-haiku-5-5", "low")
    assert r.reason == "transform_unavailable:no_api_key"  # removed key
    print("ok  key: a replaced or removed key applies on the next run")


def test_shutdown_refuses_new_and_discards_in_flight():
    import threading
    sup, client = claude_fakes.claude_supervisor("Meet at three.")
    started, release = threading.Event(), threading.Event()
    real = client.beta.messages.stream

    def blocked(**kw):
        started.set()
        release.wait(10)
        return real(**kw)
    client.beta.messages.stream = blocked
    client.close = release.set          # closing the client ends the stream
    out = {}

    def run():
        out["msg"] = sup.transform(
            transform_id="builtin:polish", transform_revision=1,
            prompt_revision="p", mode="polish", source="meet at three",
            model="claude-haiku-5-5", reasoning="low")
    t = threading.Thread(target=run)
    t.start()
    assert started.wait(5)
    sup.shutdown()
    t.join(10)
    res = out["msg"]["result"]
    assert res["path"] == "fallback_original", res
    assert res["reason"] == "transform_unavailable:closed_in_flight"
    after = sup.transform(transform_id="builtin:polish", transform_revision=1,
                          prompt_revision="p", mode="polish", source="hi")
    assert after["refused"] == "supervisor_closed", after
    assert len(client.calls) == 1, client.calls  # nothing sent after close
    print("ok  shutdown: a transform after it is refused; one in flight is"
          " discarded")


def test_panel_says_whether_the_text_was_sent():
    from localflow.v2.ui.transforms_panel import served_text
    cases = [
        (("", "refusal"), "claude-opus-5-5 · reasoning low"),
        (("cut", "max_tokens"), "claude-opus-5-5 · reasoning low"),
        (anthropic.APIConnectionError(request=REQ),
         "may have reached Claude · no answer"),
        (anthropic.RateLimitError(
            "x", response=httpx2.Response(429, request=REQ), body=None),
         "sent to Claude · no answer"),
    ]
    for answer, said in cases:
        client = claude_fakes.FakeClient(answer)
        res = claude_fakes.transformer(client).run(_job(), "claude-opus-5-5",
                                                   "low")
        assert served_text(res) == said, (res.reason, served_text(res))
    nokey = claude.Transformer(key_reader=lambda: None).run(
        _job(), "claude-opus-5-5", "low")
    assert served_text(nokey) == "not sent to Claude"
    print("ok  panel: answered, sent, maybe sent and not sent are told"
          " apart")


def test_model_choice_lives_beside_the_definition():
    td = pathlib.Path(tempfile.mkdtemp())
    st = store_mod.Store(td / "v2.db", backup_dir=td / "backups")
    try:
        ts = tstore.TransformStore(st)
        ts.seed_built_ins()
        rev = ts.definition("builtin:polish").revision
        c = ts.model_choice("builtin:polish", "polish")
        assert c == {"model": claude.recommended("polish")[0],
                     "reasoning": claude.recommended("polish")[1],
                     "source": "default"}, c
        ts.set_model_choice("builtin:polish", "claude-haiku-5-5", "off")
        c = ts.model_choices()["builtin:polish"]
        assert (c["model"], c["reasoning"], c["source"]) == \
            ("claude-haiku-5-5", "off", "user")
        # A model switch is not a definition revision: the task key stays.
        assert ts.definition("builtin:polish").revision == rev
        for bad in (("claude-opus-5-5", "off"), ("gpt", "low")):
            try:
                ts.set_model_choice("builtin:polish", *bad)
                raise AssertionError(f"accepted {bad}")
            except ValueError:
                pass
        try:
            ts.set_model_choice("missing", "claude-haiku-5-5", "low")
            raise AssertionError("unknown transform accepted")
        except ValueError:
            pass
        # A stored pair the table no longer offers reads as the default.
        st.submit(lambda db: db.execute(
            "UPDATE transform_meta SET value=? WHERE key=?",
            (json.dumps({"model": "claude-opus-5-5", "reasoning": "off"}),
             "model:builtin:polish")))
        assert ts.model_choice("builtin:polish", "polish")["source"] == \
            "default"
        # Malformed stored values read as the default too, never break
        # the listing.
        for bad in ('{"model": [], "reasoning": "low"}', '[1]', 'not json'):
            st.submit(lambda db, v=bad: db.execute(
                "UPDATE transform_meta SET value=? WHERE key=?",
                (v, "model:builtin:polish")))
            assert ts.model_choices()["builtin:polish"]["source"] == \
                "default", bad
        ts.set_model_choice("builtin:polish", "claude-opus-5-5", "high")
        ts.reset_model_choice("builtin:polish")
        assert ts.model_choice("builtin:polish", "polish")["source"] == \
            "default"
    finally:
        st.close()
    print("ok  model choice: a transform_meta preference; validated;"
          " reset returns to the recommendation")


def test_hub_pickers_round_trip():
    from test_companion_bridge import CWorld
    with CWorld() as w:
        w.select("transforms")
        w.ctl.request_flush()
        w.drain()
        view = w.host.latest("transforms")
        models = {m["id"]: [r["value"] for r in m["reasoning"]]
                  for m in view["models"]}
        assert models == {m: list(claude.reasoning_levels(m))
                          for m in claude.MODELS}, models
        row = next(t for t in view["transforms"]
                   if t["transform_id"] == "builtin:concise")
        assert row["recommended"] == list(claude.recommended("concise"))
        assert (row["model"], row["reasoning"]) == tuple(row["recommended"])
        assert row["model_source"] == "default"
        out = w.host.send("transforms.set_model", {
            "transform_id": "builtin:concise", "model": "claude-opus-5-5",
            "reasoning": "xhigh"})
        assert out["status"] == "success", out
        w.ctl.request_flush()
        w.drain()
        row = next(t for t in w.host.latest("transforms")["transforms"]
                   if t["transform_id"] == "builtin:concise")
        assert (row["model"], row["reasoning"], row["model_source"]) == \
            ("claude-opus-5-5", "xhigh", "user")
        out = w.host.send("transforms.set_model", {
            "transform_id": "builtin:concise", "model": "claude-opus-5-5",
            "reasoning": "off"})
        assert out["status"] == "refusal", out
        out = w.host.send("transforms.set_model", {
            "transform_id": "builtin:concise", "model": "claude-3",
            "reasoning": "low"})
        assert out["status"] != "success", out
        assert w.host.send("transforms.reset_model", {
            "transform_id": "builtin:concise"})["status"] == "success"
        w.ctl.request_flush()
        w.drain()
        row = next(t for t in w.host.latest("transforms")["transforms"]
                   if t["transform_id"] == "builtin:concise")
        assert row["model_source"] == "default"
    print("ok  hub: valid pairs from the table, recommended pair named,"
          " set/refuse/reset through the bridge")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"{len(tests)}/{len(tests)} passed")
