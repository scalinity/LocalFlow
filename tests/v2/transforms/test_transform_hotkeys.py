"""Physical shortcut preferences; no events posted to the desktop."""
import pathlib
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_transform_definitions import Env
from localflow.v2 import transform_hotkeys as H


def refused(fn):
    try:
        fn()
    except ValueError:
        return
    raise AssertionError("accepted invalid/conflicting binding")


def test_defaults_and_reassignment():
    with Env() as e:
        e.ts.seed_built_ins()
        for tid, code in H.DEFAULTS.items():
            before = e.ts.revisions_of(tid)
            assert e.ts.hotkeys()[tid]["binding"] == {"key_code": code, "modifiers": ["option"]}
            binding = {"key_code": 8, "modifiers": ["control", "option"]}
            e.ts.set_hotkey(tid, binding)
            assert e.ts.hotkeys()[tid]["source"] == "user"
            assert e.ts.revisions_of(tid) == before
            e.ts.set_hotkey(tid, None)
            assert e.ts.hotkeys()[tid]["binding"] is None
            e.ts.set_hotkey(tid, None, reset=True)
            assert e.ts.hotkeys()[tid]["binding"]["key_code"] == code


def test_default_chords_reusable_and_reset_conflicts():
    with Env() as e:
        e.ts.seed_built_ins()
        for tid, code in H.DEFAULTS.items():
            e.ts.set_hotkey(tid, None)
            other = e.ts.add_transform(name="Synthetic", mode="custom", prompt="Tidy")
            binding = {"key_code": code, "modifiers": ["option"]}
            e.ts.set_hotkey(other.transform_id, binding)
            refused(lambda: e.ts.set_hotkey(tid, None, reset=True))
            assert e.ts.hotkeys()[other.transform_id]["binding"] == binding
            e.ts.set_hotkey(other.transform_id, None)
            e.ts.set_hotkey(tid, None, reset=True)


def test_restart_preserves_clear_override_and_revisions():
    from localflow.v2.transforms_store import TransformStore
    with Env() as e:
        e.ts.seed_built_ins()
        before = e.ts.revisions_of("builtin:polish")
        e.ts.set_hotkey("builtin:polish", {"key_code": 35, "modifiers": ["option", "control"]})
        e.ts.set_hotkey("builtin:concise", None)
        expected = e.ts.hotkeys()
        e.ts = TransformStore(e.store)
        e.ts.seed_built_ins()
        assert e.ts.hotkeys() == expected
        assert e.ts.revisions_of("builtin:polish") == before


def test_custom_validation_and_lifecycle():
    with Env() as e:
        e.ts.seed_built_ins()
        a = e.ts.add_transform(name="A", mode="custom", prompt="Tidy")
        b = e.ts.add_transform(name="B", mode="custom", prompt="Tidy")
        chord = {"key_code": 15, "modifiers": ["option", "shift"]}
        e.ts.set_hotkey(a.transform_id, chord)
        refused(lambda: e.ts.set_hotkey(b.transform_id, chord))
        for invalid in ({"key_code": 0, "modifiers": []}, {"key_code": 58, "modifiers": ["option"]}, {"key_code": True, "modifiers": ["option"]}, {"key_code": 0, "modifiers": ["fn"]}):
            refused(lambda: e.ts.set_hotkey(b.transform_id, invalid))
        e.ts.set_enabled(a.transform_id, False)
        assert a.transform_id not in e.ts.active_hotkeys().values()
        e.ts.set_hotkey(b.transform_id, chord)
        refused(lambda: e.ts.set_enabled(a.transform_id, True))
        assert not e.ts.definition(a.transform_id).enabled
        e.ts.set_hotkey(b.transform_id, None)
        e.ts.set_enabled(a.transform_id, True)
        assert a.transform_id in e.ts.active_hotkeys().values()
        e.ts.delete_transform(a.transform_id)
        assert a.transform_id not in e.ts.active_hotkeys().values()


def test_consumption_repeat_and_release():
    runs = []
    router = H.ShortcutRouter(runs.append)
    router.replace({(18, ("option",)): "builtin:polish"})
    assert router.handle("down", 18, ("option",))
    assert router.handle("down", 18, ("option",), repeat=True)
    assert runs == ["builtin:polish"]
    # Modifier released before key-up still cannot leak the paired event.
    assert router.handle("up", 18, ())
    assert not router.handle("down", 19, ("option",))
    assert not router.handle("down", 18, ("option", "fn"))
    router.replace({})
    assert not router.handle("down", 18, ("option",))


def test_repeated_replace_has_one_registration_map():
    runs = []
    router = H.ShortcutRouter(runs.append)
    for _ in range(12):
        router.replace({(18, ("option",)): "builtin:polish"})
    assert len(router.bindings) == 1
    router.handle("down", 18, ("option",))
    assert len(runs) == 1


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print("ok", test.__name__)
    print(f"{len(tests)}/{len(tests)} passed")
