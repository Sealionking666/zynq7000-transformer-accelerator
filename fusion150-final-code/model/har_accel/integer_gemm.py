"""Independent scalar INT8 GEMM oracle, with explicit INT32 accumulator semantics.

This is a matrix-engine reference, not yet an integer implementation of the
whole Transformer. It deliberately has no dependency on an HLS implementation.
"""
from __future__ import annotations

INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1


def bits_needed_signed(magnitude: int) -> int:
    """Signed width needed for a magnitude, including sign bit."""
    if magnitude < 0:
        raise ValueError(magnitude)
    return magnitude.bit_length() + 1 if magnitude else 1


def floor_shift(value: int, shift: int) -> int:
    if shift < 0:
        raise ValueError(shift)
    return value // (1 << shift)


def saturate_int8(value: int) -> int:
    return max(-128, min(127, value))


def gemm_int8(a: list[list[int]], b: list[list[int]], shift: int) -> list[list[int]]:
    """A[M,K] times B[K,N]; floor shift and signed saturation."""
    if not a or not b or not a[0] or not b[0] or len(a[0]) != len(b):
        raise ValueError("Invalid matrix dimensions")
    m, k, n = len(a), len(b), len(b[0])
    if any(len(row) != k for row in a) or any(len(row) != n for row in b):
        raise ValueError("Ragged matrix")
    if not 0 <= shift <= 31:
        raise ValueError(shift)
    for row in a + b:
        if any(not -128 <= v <= 127 or not isinstance(v, int) for v in row):
            raise ValueError("Operands must be INT8")
    out = []
    for i in range(m):
        result_row = []
        for j in range(n):
            acc = 0
            for p in range(k):
                acc += a[i][p] * b[p][j]
                if not INT32_MIN <= acc <= INT32_MAX:
                    raise OverflowError("INT32 accumulator overflow")
            result_row.append(saturate_int8(floor_shift(acc, shift)))
        out.append(result_row)
    return out


def gemm_raw32(a: list[list[int]], b: list[list[int]]) -> list[list[int]]:
    """Independent scalar raw INT32 output for the first hardware bring-up."""
    if not a or not b or not a[0] or not b[0] or len(a[0]) != len(b):
        raise ValueError("Invalid matrix dimensions")
    m, k, n = len(a), len(b), len(b[0])
    if any(len(row) != k for row in a) or any(len(row) != n for row in b):
        raise ValueError("Ragged matrix")
    if any(not isinstance(v, int) or not -128 <= v <= 127 for row in a + b for v in row):
        raise ValueError("Operands must be INT8")
    result = []
    for i in range(m):
        row = []
        for j in range(n):
            acc = 0
            for p in range(k):
                acc += a[i][p] * b[p][j]
                if not INT32_MIN <= acc <= INT32_MAX:
                    raise OverflowError("INT32 accumulator overflow")
            row.append(acc)
        result.append(row)
    return result
