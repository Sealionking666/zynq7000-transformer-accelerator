"""Complete deterministic fixed-point Transformer reference.

Runtime uses integer arrays only. Float operations are confined to offline
parameter/input conversion. Q16 is the PS intermediate representation. GEMMs
accept signed 8-bit operands (or exact radix-128 decomposition of signed 14-bit
operands). The raw32 PL contract is unchanged.
"""
from __future__ import annotations
import math
import numpy as np

Q = 16
ONE = 1 << Q
LINEARS = ("embed", "q", "k", "v", "out", "ff1", "ff2", "classifier")
INPUTS = {"embed": "input", "q": "norm1_output", "k": "norm1_output", "v": "norm1_output",
          "out": "av", "ff1": "norm2_output", "ff2": "ff1_post_relu", "classifier": "pool_output"}


def round_div(x, divisor):
    """Nearest integer, exact halves away from zero; divisor must be positive."""
    x = np.asarray(x, dtype=np.int64)
    return np.where(x >= 0, (x + divisor // 2) // divisor, -((-x + divisor // 2) // divisor))


def rescale(x, binary_shift):
    """Multiply by 2**shift; reductions use floor, including negative values."""
    x = np.asarray(x, dtype=np.int64)
    return x << binary_shift if binary_shift >= 0 else x >> -binary_shift


def quantize_q16(x, scale_exp, bits):
    value = rescale(x, -Q - scale_exp)
    return np.clip(value, -(1 << (bits - 1)), (1 << (bits - 1)) - 1).astype(np.int64)


def isqrt_array(x):
    x = np.asarray(x, dtype=np.int64)
    if np.any(x < 0):
        raise ValueError("negative square-root input")
    return np.fromiter((math.isqrt(int(v)) for v in x.ravel()), dtype=np.int64, count=x.size).reshape(x.shape)


def rmsnorm(x, gamma_q14, epsilon_q32):
    # Same pre-square bound as the portable C runtime (16 terms < 2**60).
    if np.any(x <= -(1 << 28)) or np.any(x >= (1 << 28)):
        raise OverflowError("RMSNorm input exceeds safe integer bound")
    square_sum = np.sum(x * x, axis=-1, keepdims=True, dtype=np.int64)
    denominator = isqrt_array(square_sum // 16 + epsilon_q32)
    denominator = np.maximum(denominator, 1)
    return round_div(x * gamma_q14 * 4, denominator)


def softmax(x, exp_lut):
    # x is Q16; subtract max, clamp to -16, and round distance to Q8.
    delta = np.max(x, axis=-1, keepdims=True) - x
    indices = np.minimum((delta + 128) >> 8, 4096)
    e = exp_lut[indices]
    total = np.sum(e, axis=-1, keepdims=True, dtype=np.int64)
    return (e * ONE + total // 2) // total


def gemm_radix128(a, b, bits, raw8=None):
    """Exact decomposition; returns (wide accumulator, number of PL calls).

    raw8 may be an independent hardware/C++ implementation. Its inputs are
    contiguous row-major int8 arrays and its output must be raw int32.
    """
    if bits == 8:
        return (a @ b if raw8 is None else raw8(a, b)).astype(np.int64), 1
    if bits != 14:
        raise ValueError("Only signed INT8 or signed INT14 limb mode is supported")
    ah, bh = a >> 7, b >> 7
    al, bl = a - ah * 128, b - bh * 128
    mul = (lambda x, y: x @ y) if raw8 is None else raw8
    ll = mul(al, bl).astype(np.int64)
    lh = mul(al, bh).astype(np.int64)
    hl = mul(ah, bl).astype(np.int64)
    hh = mul(ah, bh).astype(np.int64)
    return ll + ((lh + hl) << 7) + (hh << 14), 4


def compile_parameters(state, candidate, bits=8, activation_rounding="floor"):
    if bits not in (8, 14):
        raise ValueError(bits)
    extra = bits - 8
    act_exp = {k: int(round(math.log2(v["scale"]))) - extra
               for k, v in candidate["activation"].items()}
    weight_exp = {k: int(round(math.log2(v["scale"]))) - extra
                  for k, v in candidate["hardware_first_pass"]["weight"].items()}
    array = lambda name: state[name].detach().cpu().numpy().astype(np.float64)
    limit = 1 << (bits - 1)
    if activation_rounding not in ("floor", "nearest"):
        raise ValueError(activation_rounding)
    result = {"bits": bits, "activation_rounding": activation_rounding, "activation_exp": act_exp, "weight_exp": weight_exp,
              "epsilon_q32": int(math.floor(1e-5 * (1 << 32) + 0.5)),
              "position": np.rint(array("position") * ONE).astype(np.int64),
              "exp_lut": np.rint(np.exp(-np.arange(4097, dtype=np.float64) / 256) * (1 << 30)).astype(np.int64)}
    for name in LINEARS:
        result[name + "_weight"] = np.clip(np.rint(array(name + ".weight") / 2.0 ** weight_exp[name]), -limit, limit - 1).astype(np.int64).T.copy()
        result[name + "_bias"] = np.rint(array(name + ".bias") * ONE).astype(np.int64)
    for name in ("norm1", "norm2"):
        result[name + "_gamma"] = np.rint(array(name + ".weight") * (1 << 14)).astype(np.int64)
    return result


def input_to_q16(x):
    x = np.asarray(x)
    if not np.isfinite(x).all() or np.max(np.abs(x)) >= 128:
        raise ValueError("input must be finite and |x| < 128")
    q = np.rint(x.astype(np.float64) * ONE).astype(np.int64)
    if np.any(q <= -8388608) or np.any(q >= 8388608):
        raise ValueError("rounded Q16 input exceeds C runtime domain")
    return q


def forward_q16(x, params, capture=False, raw8=None):
    if x.ndim != 3 or x.shape[1:] != (128, 9) or x.dtype.kind not in "iu":
        raise ValueError("expected integer Q16 [batch,128,9]")
    if not x.size or np.any(x >= 8388608) or (x.dtype.kind == "i" and np.any(x <= -8388608)):
        raise ValueError("Q16 input must satisfy |x| < 8388608")
    x = x.astype(np.int64)
    p = params
    bits = p["bits"]
    trace = {}
    counts = {"logical_gemm_calls_per_sample": 0, "raw8_calls_per_sample": 0, "activation_clipped": {}}

    def quant(name, a):
        exp = p["activation_exp"][name]
        shift = Q + exp
        before = round_div(a, 1 << shift) if p["activation_rounding"] == "nearest" and shift > 0 else rescale(a, -shift)
        lim = 1 << (bits - 1)
        counts["activation_clipped"][name] = {"count": int(np.count_nonzero((before < -lim) | (before >= lim))), "elements": int(before.size)}
        return np.clip(before, -lim, lim - 1), exp

    def matmul(name, a, b, ae, be):
        acc, calls = gemm_radix128(a, b, bits, raw8)
        counts["logical_gemm_calls_per_sample"] += 1
        counts["raw8_calls_per_sample"] += calls
        if capture:
            trace[name + ".a"] = a.copy()
            trace[name + ".b"] = b.copy()
            trace[name + ".acc"] = acc.copy()
        return rescale(acc, Q + ae + be)

    def linear(name, a):
        aq, ae = quant(INPUTS[name], a)
        return matmul(name, aq, p[name + "_weight"], ae, p["weight_exp"][name]) + p[name + "_bias"]

    def record(name, a):
        if np.max(np.abs(a)) >= (1 << 31):
            raise OverflowError(f"{name} exceeds signed INT32 Q16 storage")
        if capture:
            trace[name] = a.copy()
        return a

    h = record("embedding", linear("embed", x.reshape(-1, 32, 36)) + p["position"])
    n1 = record("norm1_output", rmsnorm(h, p["norm1_gamma"], p["epsilon_q32"]))
    q = record("q", linear("q", n1))
    k = record("k", linear("k", n1))
    v = record("v", linear("v", n1))
    qq, qe = quant("q", q)
    kq, ke = quant("k", k)
    scores = record("attention_scores", matmul("qk_scores", qq, kq.swapaxes(-1, -2), qe, ke) >> 2)
    prob = record("softmax_prob", softmax(scores, p["exp_lut"]))
    pq, pe = quant("softmax_prob", prob)
    vq, ve = quant("v", v)
    av = record("av", matmul("av", pq, vq, pe, ve))
    projected = record("output_projection", linear("out", av))
    h = record("norm2_input", h + projected)
    n2 = record("norm2_output", rmsnorm(h, p["norm2_gamma"], p["epsilon_q32"]))
    ff1 = record("ff1_pre_relu", linear("ff1", n2))
    ff1r = record("ff1_post_relu", np.maximum(ff1, 0))
    ff2 = record("ff2", linear("ff2", ff1r))
    h = record("pool_input", h + ff2)
    pooled = record("pool_output", np.sum(h, axis=1, dtype=np.int64) >> 5)
    logits = record("logits", linear("classifier", pooled[:, None, :])[:, 0, :])
    return logits, trace, counts
