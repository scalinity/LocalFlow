"""M01 remediation: baseline probe orchestration and attribution
(M01-AUDIT-09).

Uses injected fake ASR/cleanup objects to test ONLY the probe's own logic:
which implementation the configuration selects, how success / failure /
skip / fallback are recorded, run bindings, early-failure reporting and
report publication. These fakes are never evidence that MLX inference or
the real models work — that is the model-backed check M01-V008 in
docs/v2/VERIFICATION.html (PENDING_LOCAL_VERIFICATION).

Needs numpy (the ASR stage builds its synthetic input with it).

Run: .venv/bin/python tests/v2/test_baseline_probe.py
"""

import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))

import scripts.v2.baseline_probe as probe  # noqa: E402

CALLS = []


class FakeTranscriber:
    fail = False

    def __init__(self, model_id):
        self.model_id = model_id
        self.load_error = None

    def load(self):
        CALLS.append(("asr.load", self.model_id))
        if FakeTranscriber.fail:
            raise RuntimeError("synthetic Metal failure")

    def transcribe(self, audio):
        assert len(audio) == 48000
        return ""


class FakeV1:
    ready = True
    path = "llm"

    def __init__(self, mode, model_id):
        CALLS.append(("v1.init", mode, model_id))
        self.llm_ready = threading.Event()
        self.load_failed = False
        self.last_path = "raw"
        self.last_fallback_reason = None

    def load(self):
        if FakeV1.ready:
            self.llm_ready.set()
        else:
            self.load_failed = True

    def clean(self, text):
        self.last_path = FakeV1.path
        self.last_fallback_reason = None if FakeV1.path == "llm" \
            else "piece_failed_checks"
        return text


class FakeResult:
    def __init__(self, path):
        self.path = path
        self.fallback_reason = None if path == "llm" else "validation_failed"
        self.prompt_revision = "fake"


class FakeRunner:
    path = "llm"

    def __init__(self, model_id):
        CALLS.append(("v2.init", model_id))
        self.template_revision = "tmpl:fake"

    def load(self):
        pass

    def engine(self):
        class E:
            def clean(self_inner, text, **kw):
                return FakeResult(FakeRunner.path)
        return E()


@contextlib.contextmanager
def configured(td, cfg):
    """Isolate config resolution: empty HOME, LOCALFLOW_CONFIG -> cfg."""
    td = pathlib.Path(td)
    home = td / "home"
    home.mkdir(exist_ok=True)
    cfg_path = td / "cfg.json"
    cfg_path.write_text(json.dumps(cfg))
    saved = {k: os.environ.get(k) for k in ("HOME", "LOCALFLOW_CONFIG")}
    os.environ["HOME"] = str(home)
    os.environ["LOCALFLOW_CONFIG"] = str(cfg_path)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def run(td, cfg, *extra):
    CALLS.clear()
    out = pathlib.Path(td) / "out"
    with configured(td, cfg), contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()) as err:
        rc = probe.main(["--output-dir", str(out), *extra],
                        asr_factory=FakeTranscriber, v1_factory=FakeV1,
                        v2_factory=FakeRunner)
    report = json.loads((out / "probe.json").read_text()) \
        if (out / "probe.json").exists() else None
    return rc, report, err.getvalue()


def reset():
    FakeTranscriber.fail = False
    FakeV1.ready, FakeV1.path = True, "llm"
    FakeRunner.path = "llm"


def test_configured_v2_runs_the_v2_engine():
    reset()
    with tempfile.TemporaryDirectory() as td:
        rc, r, _ = run(td, {"cleanup": "llm", "cleanup_implementation": "v2"})
    assert rc == 0, r
    assert [c[0] for c in CALLS] == ["asr.load", "v2.init"], CALLS
    sel = r["cleanup_selection"]
    assert sel["configured_implementation"] == "v2"
    assert sel["probed_implementation"] == "v2"
    assert sel["role"] == "configured implementation"
    cleanup = r["stages"][1]
    assert "CleanupEngine" in cleanup["implementation"]
    assert cleanup["template_revision"] == "tmpl:fake"
    assert r["summary"] == {"stages_requested": 2, "stages_ok": 2,
                            "stages_failed": 0, "stages_skipped": 0,
                            "runs_ok": 4, "fallback_runs": 0}
    assert r["config"]["matches_runtime_load"] is True
    assert r["bindings"]["source"]["head_commit"]
    assert r["bindings"]["config"]["effective_source"] == \
        "environment_LOCALFLOW_CONFIG"
    for role in ("asr", "cleanup"):
        assert r["bindings"]["model_cache_at_run"][role]["loaded"] is None
    print("ok  configured v2 -> V2 engine probed; bindings recorded")


def test_configured_v1_and_v1_control_override_are_labelled():
    reset()
    with tempfile.TemporaryDirectory() as td:
        rc, r, _ = run(td, {"cleanup": "llm", "cleanup_implementation": "v1"})
    assert rc == 0 and [c[0] for c in CALLS] == ["asr.load", "v1.init"]
    assert r["cleanup_selection"]["role"] == "configured implementation"
    with tempfile.TemporaryDirectory() as td:
        rc, r, _ = run(td, {"cleanup": "llm", "cleanup_implementation": "v2"},
                       "--cleanup-implementation", "v1")
    assert rc == 0 and ("v1.init", "llm",
                        "mlx-community/Qwen3-4B-Instruct-2507-4bit") in CALLS
    sel = r["cleanup_selection"]
    assert sel["selected_by"] == "command-line override"
    assert sel["role"].startswith("V1 control")
    print("ok  V1 is probed only when configured or explicitly as the control")


def test_fallbacks_are_counted_not_hidden():
    reset()
    FakeV1.path = "llm_fallback_basic"
    with tempfile.TemporaryDirectory() as td:
        rc, r, _ = run(td, {"cleanup": "llm", "cleanup_implementation": "v1"})
    assert rc == 0
    runs = r["stages"][1]["runs"]
    assert all(x["fallback"] and x["path"] == "llm_fallback_basic" for x in runs)
    assert r["summary"]["fallback_runs"] == 2
    reset()
    FakeRunner.path = "llm_fallback_normalized"
    with tempfile.TemporaryDirectory() as td:
        rc, r, _ = run(td, {"cleanup": "llm"})
    assert r["summary"]["fallback_runs"] == 2
    assert r["stages"][1]["runs"][0]["fallback_reason"] == "validation_failed"
    print("ok  V1/V2 fallback paths recorded per run and counted")


def test_stage_failures_exit_nonzero_and_still_publish():
    reset()
    FakeTranscriber.fail = True
    with tempfile.TemporaryDirectory() as td:
        rc, r, _ = run(td, {"cleanup": "llm", "cleanup_implementation": "v2"})
    assert rc == 1 and r is not None
    assert r["stages"][0]["status"] == "failed"
    assert "synthetic Metal failure" in r["stages"][0]["error"]
    assert r["stages"][1]["status"] == "ok"  # cleanup still attempted
    assert r["summary"]["stages_failed"] == 1
    reset()
    FakeV1.ready = False
    with tempfile.TemporaryDirectory() as td:
        rc, r, _ = run(td, {"cleanup": "llm", "cleanup_implementation": "v1"})
    assert rc == 1 and r["stages"][1]["status"] == "failed"
    assert "cleanup_engine_failed" in r["stages"][1]["error"]
    print("ok  requested-stage failure -> exit 1, report still written")


def test_skips_are_explicit():
    reset()
    with tempfile.TemporaryDirectory() as td:
        rc, r, _ = run(td, {"cleanup": "basic"})
    assert rc == 0 and [c[0] for c in CALLS] == ["asr.load"]
    assert r["stages"][1]["status"] == "skipped"
    assert "no cleanup model is loaded by design" in r["stages"][1]["reason"]
    with tempfile.TemporaryDirectory() as td:
        rc, r, _ = run(td, {"cleanup": "llm"}, "--skip-models")
    assert rc == 0 and CALLS == []
    assert r["summary"]["stages_requested"] == 0
    assert r["summary"]["stages_skipped"] == 2
    print("ok  skipped stages carry reasons; --skip-models loads nothing")


def test_publication_errors_are_reported():
    reset()
    with tempfile.TemporaryDirectory() as td:
        blocker = pathlib.Path(td) / "file"
        blocker.write_text("not a directory")
        with configured(td, {"cleanup": "llm"}), \
                contextlib.redirect_stdout(io.StringIO()) as out, \
                contextlib.redirect_stderr(io.StringIO()) as err:
            rc = probe.main(["--skip-models", "--output-dir",
                             str(blocker / "sub")])
        assert rc == probe.EXIT_NOT_WRITTEN
        assert "not written" in err.getvalue()
        assert json.loads(out.getvalue().split("\nERROR")[0])["run_id"]
        # An existing report is never overwritten.
        existing = pathlib.Path(td) / "existing"
        existing.mkdir()
        (existing / "probe.json").write_text('{"kept": true}')
        with configured(td, {"cleanup": "llm"}), \
                contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            rc = probe.main(["--skip-models", "--output-dir", str(existing)])
        assert rc == probe.EXIT_NOT_WRITTEN
        assert (existing / "probe.json").read_text() == '{"kept": true}'
    print("ok  report publication failure -> exit 3 with the report on stdout")


def test_repo_root_config_and_independent_runtime_oracle():
    reset()
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        other = td / "main-checkout"
        (other / "localflow").mkdir(parents=True)
        (other / "localflow" / "__init__.py").write_text("")
        # A checkout at another commit: its own config.py (defaults select
        # V1 here) and its own load(), which becomes the oracle.
        (other / "localflow" / "config.py").write_text(
            "import json, os, pathlib\n"
            "DEFAULTS = {'model': 'org/asr', 'cleanup': 'llm',\n"
            "            'cleanup_model': 'org/llm', 'hotkey': 'fn',\n"
            "            'cleanup_implementation': 'v1'}\n"
            "ROOT = pathlib.Path(__file__).resolve().parent.parent\n"
            "def load(path=None):\n"
            "    cfg = dict(DEFAULTS)\n"
            "    for c in [path, os.environ.get('LOCALFLOW_CONFIG'),\n"
            "              pathlib.Path.home() / 'Library' / 'Application Support' / 'LocalFlow' / 'config.json',\n"
            "              ROOT / 'config.json']:\n"
            "        if c and pathlib.Path(c).exists():\n"
            "            cfg.update(json.loads(pathlib.Path(c).read_text())); break\n"
            "    return cfg\n")
        (other / "config.json").write_text('{"hotkey": "right_option"}')
        home = td / "home"
        home.mkdir()
        saved = {k: os.environ.get(k) for k in ("HOME", "LOCALFLOW_CONFIG")}
        os.environ["HOME"] = str(home)
        os.environ.pop("LOCALFLOW_CONFIG", None)
        CALLS.clear()
        try:
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                rc = probe.main(["--output-dir", str(td / "out"),
                                 "--repo-root", str(other)],
                                asr_factory=FakeTranscriber, v1_factory=FakeV1,
                                v2_factory=FakeRunner)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        r = json.loads((td / "out" / "probe.json").read_text())
    assert rc == 0, r
    assert r["config"]["hotkey"] == "right_option"
    assert r["config"]["model"] == "org/asr"
    assert r["config"]["matches_runtime_load"] is True, r["config"]
    assert r["cleanup_selection"]["configured_implementation"] == "v1"
    assert ("v1.init", "llm", "org/llm") in CALLS
    assert r["bindings"]["config_checkout"]["checkout"] == str(other.resolve())
    assert r["bindings"]["source"]["checkout"] == str(probe.ROOT)
    print("ok  --repo-root: config from that checkout, oracle = its own load()")


if __name__ == "__main__":
    test_configured_v2_runs_the_v2_engine()
    test_configured_v1_and_v1_control_override_are_labelled()
    test_fallbacks_are_counted_not_hidden()
    test_stage_failures_exit_nonzero_and_still_publish()
    test_skips_are_explicit()
    test_publication_errors_are_reported()
    test_repo_root_config_and_independent_runtime_oracle()
    print("all baseline probe orchestration tests passed (7)")
