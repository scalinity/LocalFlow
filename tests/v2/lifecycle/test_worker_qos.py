"""Native thread scheduling and graceful fallback without loading a model."""
import ctypes
import pathlib
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from localflow.v2 import worker


class InferenceQoSTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "darwin", "macOS scheduling API")
    def test_native_qos_applies_only_to_the_inference_thread(self):
        system = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
        system.qos_class_self.argtypes = []
        system.qos_class_self.restype = ctypes.c_uint
        before = system.qos_class_self()
        result = []

        def run():
            result.append((worker._set_inference_qos(), system.qos_class_self()))

        thread = threading.Thread(target=run)
        thread.start()
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, [(0, 0x19)])
        self.assertEqual(system.qos_class_self(), before)

    def test_denied_qos_does_not_stop_worker_dispatch(self):
        # Exercise the real dispatch loop with a denied scheduling request.
        instance = object.__new__(worker.Worker)
        instance._cond = threading.Condition()
        calls = []
        with patch.object(worker, "_set_inference_qos", return_value=1), \
                patch.object(instance, "_next_task", side_effect=[("clean", {}), None]), \
                patch.object(instance, "_clean", side_effect=lambda _: calls.append("clean")), \
                patch.object(instance, "_sample_memory"), \
                patch.object(worker.sys, "stderr"):
            instance._gpu_loop()
        self.assertEqual(calls, ["clean"])

    def test_missing_native_api_keeps_inherited_scheduling(self):
        with patch.object(worker.sys, "platform", "darwin"), \
                patch("ctypes.CDLL", side_effect=OSError):
            self.assertIsNone(worker._set_inference_qos())


if __name__ == "__main__":
    unittest.main()
