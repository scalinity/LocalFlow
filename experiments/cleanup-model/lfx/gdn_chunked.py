"""Differentiable chunkwise gated delta rule for training Qwen3.5 in MLX.

mlx-lm 0.31.3 trains GatedDeltaNet layers through ``gated_delta_ops``, a Python
loop over every token (its Metal kernel has no gradient). With ~3.5k-token
LocalFlow prompts that is ~84k sequential steps per example. This module
computes the same recurrence chunk by chunk (WY form, as in the reference
``chunk_gated_delta_rule``): per chunk of 64 tokens the intra-chunk solve is a
64x64 unit-triangular inverse done by recursive block inversion, and only T/64 steps
are sequential.

Recurrence (per value head; S is [Dv, Dk] as in mlx-lm):
    S_t = g_t S_{t-1};  u_t = beta_t (v_t - S_t k_t);  S_t += u_t k_t^T;  y_t = S_t q_t
q and k arrive already RMS-normalized and scaled by the caller
(``qwen3_5.GatedDeltaNet``), so no l2norm or 1/sqrt(d) is applied here.

Only the training path (``use_kernel=False``) is replaced; inference keeps the
stock Metal kernel.
"""

from __future__ import annotations

import mlx.core as mx
import mlx.nn as nn

CHUNK = 64
CALLS = {"chunked": 0}


def log_decay(A_log: mx.array, a: mx.array, dt_bias: mx.array) -> mx.array:
    """log g, computed directly (never log(exp(.)), which underflows)."""
    return -mx.exp(A_log.astype(mx.float32)) * nn.softplus((a + dt_bias).astype(mx.float32))


def unit_lower_inverse(u: mx.array) -> mx.array:
    """Inverse of a batch of unit lower-triangular [..., n, n] matrices, n a
    power of two: inv([[A, 0], [C, D]]) = [[A^-1, 0], [-D^-1 C A^-1, D^-1]],
    with A and D inverted together in one batched recursion."""
    n = u.shape[-1]
    if n == 1:
        return mx.ones_like(u)
    h = n // 2
    a, c, d = u[..., :h, :h], u[..., h:, :h], u[..., h:, h:]
    both = unit_lower_inverse(mx.stack([a, d], axis=0))
    ai, di = both[0], both[1]
    top = mx.concatenate([ai, mx.zeros_like(c).swapaxes(-1, -2)], axis=-1)
    bottom = mx.concatenate([-(di @ c @ ai), di], axis=-1)
    return mx.concatenate([top, bottom], axis=-2)


def chunked_gated_delta(q, k, v, log_g, beta, state=None, chunk: int = CHUNK):
    """q, k: [B,T,Hk,Dk]; v: [B,T,Hv,Dv]; log_g, beta: [B,T,Hv];
    state: [B,Hv,Dv,Dk] fp32 or None. Returns (y [B,T,Hv,Dv] in q.dtype,
    final state [B,Hv,Dv,Dk] fp32)."""
    in_dtype = q.dtype
    B, T, Hk, Dk = q.shape
    Hv, Dv = v.shape[-2:]
    if Hv // Hk > 1:                       # consecutive repeat == kernel's hv // (Hv/Hk)
        q = mx.repeat(q, Hv // Hk, axis=-2)
        k = mx.repeat(k, Hv // Hk, axis=-2)
    f32 = mx.float32
    # [B,H,T,D] in fp32
    q, k, v = (x.astype(f32).transpose(0, 2, 1, 3) for x in (q, k, v))
    log_g = log_g.astype(f32).transpose(0, 2, 1)
    beta = beta.astype(f32).transpose(0, 2, 1)
    pad = (chunk - T % chunk) % chunk
    if pad:
        q = mx.pad(q, [(0, 0), (0, 0), (0, pad), (0, 0)])
        k = mx.pad(k, [(0, 0), (0, 0), (0, pad), (0, 0)])
        v = mx.pad(v, [(0, 0), (0, 0), (0, pad), (0, 0)])
        beta = mx.pad(beta, [(0, 0), (0, 0), (0, pad)])        # beta 0: no write
        log_g = mx.pad(log_g, [(0, 0), (0, 0), (0, pad)])      # log g 0: no decay
    n = (T + pad) // chunk
    H = Hv
    q = q.reshape(B, H, n, chunk, Dk)
    k = k.reshape(B, H, n, chunk, Dk)
    v = v.reshape(B, H, n, chunk, Dv)
    beta = beta.reshape(B, H, n, chunk)
    gc = mx.cumsum(log_g.reshape(B, H, n, chunk), axis=-1)      # within-chunk cumulative log decay

    k_beta = k * beta[..., None]
    v_beta = v * beta[..., None]
    lower = mx.tril(mx.ones((chunk, chunk), dtype=mx.bool_))
    strict = mx.tril(mx.ones((chunk, chunk), dtype=mx.bool_), k=-1)
    diff = gc[..., :, None] - gc[..., None, :]
    decay = mx.where(lower, mx.exp(mx.where(lower, diff, 0.0)), 0.0)   # mask before exp

    # (I + L)^-1 with L = strict_lower(k_beta k^T * decay), by recursive block
    # inversion of the unit lower-triangular matrix (log2(chunk) levels of
    # batched matmuls; no per-row copies kept for autodiff).
    unit = mx.where(strict, (k_beta @ k.swapaxes(-1, -2)) * decay, 0.0) + mx.eye(chunk, dtype=f32)
    attn = unit_lower_inverse(unit)
    u = attn @ v_beta                                           # [B,H,n,C,Dv]
    w = attn @ (k_beta * mx.exp(gc)[..., None])                 # [B,H,n,C,Dk]

    S = mx.zeros((B, H, Dk, Dv), dtype=f32) if state is None \
        else state.astype(f32).swapaxes(-1, -2)                  # M = S^T, [Dk, Dv]
    outs = []
    for c in range(n):
        qc, kc, gcc = q[:, :, c], k[:, :, c], gc[:, :, c]
        intra = mx.where(lower, (qc @ kc.swapaxes(-1, -2)) * decay[:, :, c], 0.0)
        v_new = u[:, :, c] - w[:, :, c] @ S
        outs.append((qc * mx.exp(gcc)[..., None]) @ S + intra @ v_new)
        g_last = gcc[..., -1:]
        S = S * mx.exp(g_last)[..., None] + \
            (kc * mx.exp(g_last - gcc)[..., None]).swapaxes(-1, -2) @ v_new
    y = mx.stack(outs, axis=2).reshape(B, H, n * chunk, Dv)[:, :, :T]
    return y.transpose(0, 2, 1, 3).astype(in_dtype), S.swapaxes(-1, -2)


def gated_delta_update_chunked(q, k, v, a, b, A_log, dt_bias, state=None, mask=None):
    if mask is not None:
        raise ValueError("chunked gated delta: padding masks are not supported in training")
    CALLS["chunked"] += 1
    return chunked_gated_delta(q, k, v, log_decay(A_log, a, dt_bias), mx.sigmoid(b), state)


def patch_qwen3_5() -> None:
    """Replace the training branch of ``mlx_lm.models.qwen3_5.gated_delta_update``
    (the module global called by GatedDeltaNet). Inference is untouched."""
    import mlx_lm.models.qwen3_5 as q35
    if getattr(q35.gated_delta_update, "_lfx_chunked", False):
        return
    original = q35.gated_delta_update

    def patched(q, k, v, a, b, A_log, dt_bias, state=None, mask=None, use_kernel=True):
        if use_kernel:
            return original(q, k, v, a, b, A_log, dt_bias, state, mask, use_kernel=True)
        return gated_delta_update_chunked(q, k, v, a, b, A_log, dt_bias, state, mask)

    patched._lfx_chunked = True
    patched._original = original
    q35.gated_delta_update = patched
