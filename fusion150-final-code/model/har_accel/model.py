"""One-layer, one-head, pre-RMSNorm HAR Transformer (float reference)."""
from __future__ import annotations
import math
import torch
from torch import nn


class RMSNorm(nn.Module):
    def __init__(self, width: int, eps: float = 1e-5):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(width))
        self.eps = eps

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x * torch.rsqrt(x.square().mean(dim=-1, keepdim=True) + self.eps) * self.weight


class HARTransformer(nn.Module):
    def __init__(self, eps: float = 1e-5):
        super().__init__()
        self.embed = nn.Linear(36, 16)
        self.norm1 = RMSNorm(16, eps)
        self.q = nn.Linear(16, 16)
        self.k = nn.Linear(16, 16)
        self.v = nn.Linear(16, 16)
        self.out = nn.Linear(16, 16)
        self.norm2 = RMSNorm(16, eps)
        self.ff1 = nn.Linear(16, 32)
        self.ff2 = nn.Linear(32, 16)
        self.classifier = nn.Linear(16, 6)
        position = torch.arange(32, dtype=torch.float32).unsqueeze(1)
        inv = torch.exp(torch.arange(0, 16, 2, dtype=torch.float32) * (-math.log(10000.0) / 16))
        pe = torch.zeros(32, 16)
        pe[:, 0::2] = torch.sin(position * inv)
        pe[:, 1::2] = torch.cos(position * inv)
        self.register_buffer("position", pe, persistent=True)

    def forward(self, x: torch.Tensor, capture: bool = False):
        if x.ndim != 3 or x.shape[1:] != (128, 9):
            raise ValueError(f"Expected [batch,128,9], got {tuple(x.shape)}")
        t = {}
        def record(name, value):
            if capture:
                t[name] = value.detach()
            return value
        patch = x.reshape(x.shape[0], 32, 36)
        h = record("embedding", self.embed(patch) + self.position)
        record("norm1_input", h)
        n1 = record("norm1_output", self.norm1(h))
        q = record("q", self.q(n1))
        k = record("k", self.k(n1))
        v = record("v", self.v(n1))
        scores = record("attention_scores", torch.matmul(q, k.transpose(-2, -1)) / math.sqrt(16))
        prob = record("softmax_prob", torch.softmax(scores, dim=-1))
        av = record("av", torch.matmul(prob, v))
        projected = record("output_projection", self.out(av))
        h = record("norm2_input", h + projected)
        n2 = record("norm2_output", self.norm2(h))
        before_relu = record("ff1_pre_relu", self.ff1(n2))
        after_relu = record("ff1_post_relu", torch.relu(before_relu))
        ff2 = record("ff2", self.ff2(after_relu))
        h = record("pool_input", h + ff2)
        pooled = record("pool_output", h.mean(dim=1))
        logits = record("logits", self.classifier(pooled))
        return (logits, t) if capture else logits
