"""Capability fallbacks keep source acquisition separate from replacement."""
import pathlib
import sys
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests/v2/insertion')]
from fixture_target import FixtureTargetApp
from localflow.v2.insertion.selection import capture_selection
from localflow.v2.insertion.service import InsertionService
from localflow.v2.insertion.validation import validate_target
from localflow.v2.integrations.buffers import BufferSnapshot, PendingEdit


class SelectedTextTarget(FixtureTargetApp):
    direct = True
    copy_effect = True

    def attribute(self, el, name):
        if el is self and name == 'AXSelectedText':
            return self.content[slice(*self.selection)] if self.direct else None
        return super().attribute(el, name)

    def string_for_range(self, el, start, length):
        return None

    def post_copy(self):
        if self.copy_effect:
            self.pb.clear_and_write_text(self.content[slice(*self.selection)])
        return True


class CapabilityTests(unittest.TestCase):
    def target(self):
        target = SelectedTextTarget()
        target.content = 'prefix: This is a test prompt :suffix'
        target.selection = (8, 29)
        return target

    def service(self, target):
        return InsertionService(host=target, keyboard=target, pasteboard=target.pb,
            store=None, emit=lambda *a, **k: None, observation_window_sec=0)

    def test_direct_selected_text_is_bound_to_the_actual_field(self):
        target = self.target()
        capture, error = capture_selection(target, expected_pid=target.pid)
        self.assertIsNone(error)
        self.assertEqual(capture['source'], target.content[8:29])
        self.assertEqual(capture['acquisition'], 'ax_selected_text')
        lease, proof = validate_target(target, capture['snapshot'], {
            'strict_replacement': True, 'selection_acquisition': 'ax_selected_text'})
        self.assertIsNotNone(lease, proof)
        from dataclasses import replace
        changed = replace(capture['snapshot'], field_element=object())
        lease, proof = validate_target(target, changed, {
            'strict_replacement': True, 'selection_acquisition': 'ax_selected_text'})
        self.assertIsNone(lease, proof)

    def test_accessibility_warmup_runs_only_after_policy_and_revalidates_focus(self):
        target = self.target()
        calls = []
        target.prepare_text_capture = calls.append
        capture, error = capture_selection(target, denied_apps=[target.bundle])
        self.assertIsNone(capture)
        self.assertEqual(error, 'app_denied')
        self.assertEqual(calls, [])
        def switch(pid):
            calls.append(pid)
            target.frontmost_info['pid'] = pid + 1
        target.prepare_text_capture = switch
        capture, error = capture_selection(target)
        self.assertIsNone(capture)
        self.assertEqual(error, 'destination_unverified')
        self.assertEqual(calls, [target.pid])

    def test_fresh_copy_preserves_clipboard_and_does_not_grant_paste(self):
        target = self.target(); target.direct = False
        target.pb.clear_and_write_text('old clipboard, never the source')
        capture, error = self.service(target).capture_transform_selection(expected_pid=target.pid)
        self.assertIsNone(error)
        self.assertEqual(capture['source'], target.content[8:29])
        self.assertEqual(capture['acquisition'], 'fresh_copy')
        self.assertFalse(capture['can_replace'])
        self.assertEqual(target.pb.current_string(), 'old clipboard, never the source')
        self.assertEqual(target.paste_events, [])

    def test_copy_without_a_new_generation_refuses_stale_text(self):
        target = self.target(); target.direct = False; target.copy_effect = False
        target.pb.clear_and_write_text('FORGE claude-son 200 tx')
        capture, error = self.service(target).capture_transform_selection(expected_pid=target.pid)
        self.assertIsNone(capture)
        self.assertEqual(error, 'no_selection')
        self.assertEqual(target.pb.current_string(), 'FORGE claude-son 200 tx')

    def test_web_selection_uses_one_paste_before_any_ignored_ax_write(self):
        target = FixtureTargetApp(bundle='com.openai.codex')
        target.content = 'prefix draft suffix'; target.selection = (7, 12)
        target.pb.clear_and_write_text('original clipboard')
        capture, reason = capture_selection(target)
        self.assertIsNone(reason)
        def forbidden(*args):
            raise AssertionError('web AX setter must not be attempted before paste')
        target.set_attribute = forbidden
        service = self.service(target); done = threading.Event(); results = []
        service.submit('revised', {'context_snapshot': capture['snapshot'],
            'strict_replacement': True, 'selection_acquisition': capture['acquisition']},
            lambda result: (results.append(result), done.set()))
        self.assertTrue(done.wait(3))
        self.assertEqual(results[0].state, 'confirmed')
        self.assertEqual(target.content, 'prefix revised suffix')
        self.assertEqual(len(target.paste_events), 1)
        self.assertEqual(target.pb.current_string(), 'original clipboard')

    def test_terminal_screen_is_never_copied_or_used_as_composer(self):
        target = self.target(); target.direct = False; target.bundle = 'com.mitchellh.ghostty'
        target.frontmost_info['bundle'] = target.bundle
        capture, error = self.service(target).capture_transform_selection(expected_pid=target.pid)
        self.assertIsNone(capture)
        self.assertEqual(error, 'terminal_buffer_integration_required')
        self.assertEqual(target.pb.ops, [])

    def test_a_notification_exception_cannot_kill_the_insertion_consumer(self):
        service = self.service(self.target())
        def edit(token):
            return PendingEdit(BufferSnapshot('zle', 'synthetic text', 14, 0, 14,
                token, 42, 41, '/dev/ttys999'), token, 30)
        one, two = edit('one'), edit('two')
        done = threading.Event()
        def broken(_):
            raise RuntimeError('synthetic callback failure')
        service.submit_buffer_edit(one, 'first', expected_revision=one.snapshot.revision, on_done=broken)
        service.submit_buffer_edit(two, 'second', expected_revision=two.snapshot.revision, on_done=lambda _: done.set())
        self.assertTrue(done.wait(2))
        self.assertTrue(service._thread.is_alive())
        self.assertEqual(two.result()['text'], 'second')


if __name__ == '__main__':
    unittest.main()
