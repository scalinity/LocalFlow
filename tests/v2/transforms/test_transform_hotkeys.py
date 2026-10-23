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


def test_menu_preference_migration_once():
    with Env() as e:
        e.ts.seed_built_ins()
        e.ts.update_transform("builtin:polish", shortcut="p")
        original = e.ts.revisions_of("builtin:polish")
        assert e.ts.hotkeys()["builtin:polish"] == {"source": "user", "binding": {"key_code": 35, "modifiers": ["command"]}}
        e.ts.set_hotkey("builtin:polish", None)
        e.ts.seed_built_ins()
        assert e.ts.hotkeys()["builtin:polish"]["binding"] is None
        assert e.ts.revisions_of("builtin:polish") == original


def test_restart_reopens_database():
    from localflow.v2 import store as S
    from localflow.v2.transforms_store import TransformStore
    with Env() as e:
        e.ts.seed_built_ins()
        e.ts.set_hotkey("builtin:polish", {"key_code": 35, "modifiers": ["control", "option"]})
        e.ts.set_hotkey("builtin:concise", None)
        expected = e.ts.hotkeys()
        e.store.close()
        e.store = S.Store(e.tmp / "v2.db", artifacts_dir=e.tmp / "arts", backup_dir=e.tmp / "bk")
        e.ts = TransformStore(e.store)
        e.ts.seed_built_ins()
        assert e.ts.hotkeys() == expected
        assert len(e.ts.active_hotkeys()) == 2


def test_bridge_builtin_and_custom_preferences():
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ui"))
    from test_companion_bridge import CWorld
    with CWorld() as w:
        w.select("transforms")
        svc = w.ctl.spec["transforms_service"]
        before = svc.revisions_of("builtin:polish")
        reply = w.host.send("transforms.update", {"transform_id": "builtin:polish", "changes": {"hotkey": None}})
        assert reply["status"] == "success", reply
        assert svc.revisions_of("builtin:polish") == before
        form = {"name": "Synthetic", "mode": "custom", "prompt": "Tidy", "shortcut": None, "auto_apply": False, "target_profiles": [], "hotkey": {"key_code": 18, "modifiers": ["option"]}}
        reply = w.host.send("transforms.add", form)
        assert reply["status"] == "success", reply
        assert w.host.send("transforms.reset_hotkey", {"transform_id": "builtin:polish"})["status"] == "refusal"
        assert w.host.send("transforms.update", {"transform_id": "builtin:polish", "changes": {"hotkey": {"key_code": True, "modifiers": ["option"]}}})["status"] == "refusal"
        assert w.host.send("transforms.record_shortcut", {"active": True})["status"] == "success"


def test_active_input_source_and_restart_key_state():
    from unittest.mock import patch
    from localflow.transform_hotkey import TransformHotkeyListener
    listener = TransformHotkeyListener(lambda *_: None, lambda *_: None)
    with patch('localflow.transform_hotkey.current_input_is_layout', return_value=True):
        listener.refresh_input_source()
        assert listener.review_eligible
    with patch('localflow.transform_hotkey.current_input_is_layout', return_value=False):
        listener.refresh_input_source()
        assert not listener.review_eligible
    listener.review.physical.update((36, 76))
    listener.review.consumed.update((36, 76))
    with patch('localflow.transform_hotkey.Q.CGEventSourceKeyState', side_effect=lambda state, key: key == 76):
        listener._reconcile_review_keys()
    assert listener.review.physical == listener.review.consumed == {76}


def test_native_tap_lifecycle_and_exact_consumption():
    from unittest.mock import patch
    import Quartz as Q
    from localflow.transform_hotkey import TransformHotkeyListener
    reports = []
    runs = []
    listener = TransformHotkeyListener(runs.append, lambda *r: reports.append(r))
    listener.replace({(18, ("option",)): "builtin:polish"})
    with patch.object(Q, "CGEventTapCreate", return_value=None) as create:
        assert listener.start() is False
        assert create.call_args.args[2] == Q.kCGEventTapOptionDefault
        assert reports[-1] == ("unavailable", "event_tap_permission_required")
    # Exercise real CGEvent objects but never post them.
    with patch('localflow.transform_hotkey.AppHelper.callAfter', side_effect=lambda fn, *a: fn(*a)):
        event = Q.CGEventCreateKeyboardEvent(None, 18, True)
        Q.CGEventSetFlags(event, Q.kCGEventFlagMaskAlternate)
        assert listener._event(None, Q.kCGEventKeyDown, event, None) is None
        Q.CGEventSetIntegerValueField(event, Q.kCGKeyboardEventAutorepeat, 1)
        assert listener._event(None, Q.kCGEventKeyDown, event, None) is None
        assert runs == ["builtin:polish"]
        assert listener._event(None, Q.kCGEventKeyUp, event, None) is None
        Q.CGEventSetFlags(event, Q.kCGEventFlagMaskSecondaryFn | Q.kCGEventFlagMaskAlternate)
        assert listener._event(None, Q.kCGEventKeyDown, event, None) is event
    with patch.object(Q, "CGEventTapCreate", return_value=object()) as create, patch.object(Q, "CFMachPortCreateRunLoopSource", return_value=object()), patch.object(Q, "CFRunLoopAddSource") as add, patch.object(Q, "CGEventTapEnable"), patch.object(Q, "CGEventTapIsEnabled", return_value=True), patch.object(Q, "CFRunLoopRemoveSource") as remove, patch.object(Q, "CFMachPortInvalidate") as invalidate:
        listener.start()
        listener.start()
        assert create.call_count == add.call_count == 1
        listener.stop()
        listener.stop()
        assert remove.call_count == invalidate.call_count == 1


def test_internal_note_review_is_scoped_and_refinement_keeps_its_keys():
    import os
    from types import SimpleNamespace
    from unittest.mock import patch
    import Quartz as Q
    from localflow.transform_hotkey import TransformHotkeyListener
    listener = TransformHotkeyListener(lambda *_: None, lambda *_: None)
    actions = []
    listener.review_callback = lambda *a: actions.append(a)
    scope = SimpleNamespace(valid=True)
    listener.review_scope = scope
    front = SimpleNamespace(processIdentifier=lambda: os.getpid())
    workspace = SimpleNamespace(frontmostApplication=lambda: front)
    native = SimpleNamespace(sharedWorkspace=lambda: workspace)
    event = Q.CGEventCreateKeyboardEvent(None, 36, True)
    Q.CGEventSetFlags(event, 0)
    with patch('localflow.transform_hotkey.NSWorkspace', native), patch(
            'localflow.transform_hotkey.AppHelper.callAfter',
            side_effect=lambda fn, *a: fn(*a)):
        # An ordinary Hub/refinement lease never takes its own app's Return.
        listener.review.arm('refinement', os.getpid(), ready=True, enabled=True)
        assert listener._event(None, Q.kCGEventKeyDown, event, None) is event
        assert listener._event(None, Q.kCGEventKeyUp, event, None) is event
        assert not actions
        listener.review.arm('note', os.getpid(), ready=True, enabled=True,
                            internal_editor=True)
        assert listener._event(None, Q.kCGEventKeyDown, event, None) is None
        assert actions == [('accept', 'note')]
        assert listener.review.claim('note')
        assert listener._event(None, Q.kCGEventKeyUp, event, None) is None
        listener.review.arm('changed_focus', os.getpid(), ready=True,
                            enabled=True, internal_editor=True)
        scope.valid = False
        assert listener._event(None, Q.kCGEventKeyDown, event, None) is event
        listener._event(None, Q.kCGEventKeyUp, event, None)
        scope.valid = True
        listener.review_eligible = False  # a live input-method composition
        assert listener._event(None, Q.kCGEventKeyDown, event, None) is event
        assert actions == [('accept', 'note')]


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print("ok", test.__name__)
    print(f"{len(tests)}/{len(tests)} passed")
