"""Chunked gated delta rule == mlx-lm's reference recurrence (forward and
gradients, exact fp32 on the CPU stream) and close to the inference Metal
kernel on the GPU (forward). The GPU bound is a relative-norm bound because
this machine's fp32 GPU matmul is itself ~8e-4 relative from exact, while the
reference recurrence uses elementwise ops only."""

import sys
import unittest
from pathlib import Path

import mlx.core as mx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lfx.gdn_chunked import chunked_gated_delta, gated_delta_update_chunked, log_decay  # noqa: E402
from mlx_lm.models.gated_delta import compute_g, gated_delta_kernel, gated_delta_ops, gated_delta_update  # noqa: E402


def inputs(B=1, T=150, Hk=2, Hv=4, Dk=32, Dv=32, seed=0, dtype=mx.float32):
    mx.random.seed(seed)
    r = mx.random.normal
    q = r((B, T, Hk, Dk))
    k = r((B, T, Hk, Dk))
    # Same normalization the model applies before the recurrence.
    inv = Dk ** -0.5
    q = (inv ** 2) * mx.fast.rms_norm(q, None, 1e-6)
    k = inv * mx.fast.rms_norm(k, None, 1e-6)
    v = r((B, T, Hv, Dv))
    a = r((B, T, Hv))
    b = r((B, T, Hv))
    A_log = mx.log(mx.random.uniform(1, 16, (Hv,)))
    dt_bias = mx.ones((Hv,))
    state = 0.1 * r((B, Hv, Dv, Dk))
    return [x.astype(dtype) if x.ndim > 1 else x for x in (q, k, v, a, b)] + [A_log, dt_bias, state]


def reference(q, k, v, a, b, A_log, dt_bias, state):
    return gated_delta_ops(q, k, v, compute_g(A_log, a, dt_bias), mx.sigmoid(b), state)


def rel(x, y):
    x, y = x.astype(mx.float32), y.astype(mx.float32)
    return (mx.linalg.norm((x - y).flatten()) / mx.linalg.norm(y.flatten())).item()


class ChunkedGatedDeltaTests(unittest.TestCase):
    def setUp(self):
        self.cpu = mx.stream(mx.cpu)

    def assertRel(self, x, y, bound, msg=""):
        r = rel(x, y)
        self.assertLessEqual(r, bound, f"{msg} relative error {r:.3g}")

    def assertClose(self, x, y, atol=1e-4, rtol=1e-4, msg=""):
        diff = mx.abs(x.astype(mx.float32) - y.astype(mx.float32))
        tol = atol + rtol * mx.abs(y.astype(mx.float32))
        worst = mx.max(diff - tol).item()
        self.assertLessEqual(worst, 0.0, f"{msg} max excess {worst:.3g}, max abs diff {mx.max(diff).item():.3g}")

    def test_forward_matches_reference_ops_exactly_on_cpu(self):
        with self.cpu:
            for T in (1, 63, 64, 65, 150, 200):
                args = inputs(T=T, seed=T)
                y_ref, s_ref = reference(*args)
                y, s = gated_delta_update_chunked(*args)
                self.assertClose(y, y_ref, atol=1e-5, rtol=1e-4, msg=f"y T={T}")
                self.assertClose(s, s_ref, atol=1e-5, rtol=1e-4, msg=f"state T={T}")

    def test_no_initial_state(self):
        with self.cpu:
            q, k, v, a, b, A_log, dt_bias, _ = inputs(T=90)
            y_ref, s_ref = gated_delta_ops(q, k, v, compute_g(A_log, a, dt_bias), mx.sigmoid(b))
            y, s = gated_delta_update_chunked(q, k, v, a, b, A_log, dt_bias, None)
            self.assertClose(y, y_ref, atol=1e-5)
            self.assertClose(s, s_ref, atol=1e-5)

    def test_gpu_forward_relative_error(self):
        args = inputs(T=200, seed=9)
        y_ref, s_ref = reference(*args)
        y, s = gated_delta_update_chunked(*args)
        self.assertRel(y, y_ref, 5e-3, "gpu y")
        self.assertRel(s, s_ref, 5e-3, "gpu state")

    def test_gradients_match_reference_ops(self):
        args = inputs(T=100, seed=7)
        mx.random.seed(11)
        wy = mx.random.normal(args[2].shape)
        ws = mx.random.normal(args[7].shape)

        def loss(fn):
            def f(q, k, v, a, b, A_log, dt_bias, state):
                y, s = fn(q, k, v, a, b, A_log, dt_bias, state)
                return (y * wy).sum() + (s * ws).sum()
            return f

        argnums = tuple(range(8))
        names = ["q", "k", "v", "a", "b", "A_log", "dt_bias", "state"]
        with self.cpu:
            g_ref = mx.grad(loss(reference), argnums=argnums)(*args)
            g_new = mx.grad(loss(gated_delta_update_chunked), argnums=argnums)(*args)
            for name, x, y in zip(names, g_new, g_ref):
                self.assertTrue(mx.all(mx.isfinite(x)).item(), name)
                self.assertRel(x, y, 1e-4, f"cpu grad {name}")
        g_gpu = mx.grad(loss(gated_delta_update_chunked), argnums=argnums)(*args)
        for name, x, y in zip(names, g_gpu, g_ref):
            self.assertTrue(mx.all(mx.isfinite(x)).item(), name)
            self.assertRel(x, y, 1e-2, f"gpu grad {name}")

    def test_forward_matches_metal_kernel_model_shapes(self):
        # Qwen3.5-4B linear-attention shapes: Hk=16, Hv=32, Dk=Dv=128.
        args = inputs(T=300, Hk=16, Hv=32, Dk=128, Dv=128, seed=3)
        q, k, v, a, b, A_log, dt_bias, state = args
        y_kernel, s_kernel = gated_delta_update(q, k, v, a, b, A_log, dt_bias, state, None, use_kernel=True)
        y, s = gated_delta_update_chunked(q, k, v, a, b, A_log, dt_bias, state)
        self.assertRel(y, y_kernel, 5e-3, "y vs kernel")
        self.assertRel(s, s_kernel, 5e-3, "state vs kernel")

    def test_long_sequence_against_kernel(self):
        # A full LocalFlow main-pass prompt is ~3.5k tokens.
        args = inputs(T=3500, Hk=16, Hv=32, Dk=128, Dv=128, seed=21)
        q, k, v, a, b, A_log, dt_bias, state = args
        y_kernel, s_kernel = gated_delta_update(q, k, v, a, b, A_log, dt_bias, state, None, use_kernel=True)
        y, s = gated_delta_update_chunked(q, k, v, a, b, A_log, dt_bias, state)
        self.assertRel(y, y_kernel, 1e-2, "long y vs kernel")
        self.assertRel(s, s_kernel, 1e-2, "long state vs kernel")

    def test_bfloat16_inputs_close_to_fp32(self):
        args32 = inputs(T=128, Hk=16, Hv=32, Dk=128, Dv=128, seed=5)
        args16 = [x.astype(mx.bfloat16) if i < 5 else x for i, x in enumerate(args32)]
        y32, _ = gated_delta_update_chunked(*args32)
        y16, _ = gated_delta_update_chunked(*args16)
        self.assertEqual(y16.dtype, mx.bfloat16)
        self.assertRel(y16, y32, 3e-2, "bf16")

    def test_mask_rejected(self):
        args = inputs(T=10)
        with self.assertRaises(ValueError):
            gated_delta_update_chunked(*args[:7], args[7], mx.ones((1, 10), dtype=mx.bool_))

    def test_unit_lower_inverse_fold_is_bit_identical(self):
        # The batch-dim fold (for MLX's 10-dim CUDA limit) against the unfolded recursion.
        from lfx import gdn_chunked as g
        u = mx.tril(0.05 * mx.random.normal((1, 8, 5, 64, 64), key=mx.random.key(3)), k=-1) + mx.eye(64)
        fold = g.unit_lower_inverse
        for device in (mx.cpu, mx.gpu):
            with mx.stream(device):
                folded = fold(u)
                g.unit_lower_inverse = g._unit_lower_inverse  # the recursion calls the module name
                try:
                    unfolded = g._unit_lower_inverse(u)
                finally:
                    g.unit_lower_inverse = fold
                self.assertEqual(folded.shape, u.shape)
                self.assertTrue(mx.array_equal(folded, unfolded).item(), f"{device}")

    def test_log_decay_matches_compute_g(self):
        _, _, _, a, _, A_log, dt_bias, _ = inputs(T=20)
        self.assertClose(mx.exp(log_decay(A_log, a, dt_bias)), compute_g(A_log, a, dt_bias), atol=1e-6)


if __name__ == "__main__":
    unittest.main()
