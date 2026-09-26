"""AirmateRiskNet: a small GRU survival model over the last 3 hours of air readings.

Inputs
  seq: (B, WINDOW_BINS, n_seq) readings at 3-minute resolution
  ctx: (B, n_ctx) forecasts, inhaler/symptom history, 24 h exposure, personal
       baselines, and self-reported triggers

The context is encoded once and used two ways: FiLM (feature-wise scale and
shift) personalizes how the GRU reads the sensor stream, so a dust-sensitive
person's model pays more attention to dust; and it is concatenated before the
head. The head predicts a discrete-time hazard for each horizon interval
(0-1 h, 1-4 h, 4-12 h), which guarantees P(flare by 1 h) <= P(by 4 h) <= P(by 12 h).
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn


class AirmateRiskNet(nn.Module):
    def __init__(self, n_seq: int, n_ctx: int, n_intervals: int = 3, hidden: int = 64, dropout: float = 0.1):
        super().__init__()
        self.config = {"n_seq": n_seq, "n_ctx": n_ctx, "n_intervals": n_intervals, "hidden": hidden, "dropout": dropout}
        self.register_buffer("seq_mean", torch.zeros(n_seq))
        self.register_buffer("seq_std", torch.ones(n_seq))
        self.register_buffer("ctx_mean", torch.zeros(n_ctx))
        self.register_buffer("ctx_std", torch.ones(n_ctx))
        # Per-interval Platt scaling fitted on validation data after training.
        self.register_buffer("calib_scale", torch.ones(n_intervals))
        self.register_buffer("calib_bias", torch.zeros(n_intervals))

        self.ctx_encoder = nn.Sequential(
            nn.Linear(n_ctx, hidden), nn.GELU(), nn.Linear(hidden, hidden), nn.GELU()
        )
        self.seq_in = nn.Sequential(nn.Linear(n_seq, hidden), nn.GELU())
        self.film = nn.Linear(hidden, 2 * hidden)
        self.gru = nn.GRU(hidden, hidden, batch_first=True)
        self.attention = nn.Linear(hidden, 1)
        self.head = nn.Sequential(
            nn.Linear(3 * hidden, hidden), nn.GELU(), nn.Dropout(dropout), nn.Linear(hidden, n_intervals)
        )
        nn.init.zeros_(self.film.weight)
        nn.init.zeros_(self.film.bias)

    def set_normalization(self, seq_mean, seq_std, ctx_mean, ctx_std) -> None:
        for name, value in (("seq_mean", seq_mean), ("seq_std", seq_std), ("ctx_mean", ctx_mean), ("ctx_std", ctx_std)):
            tensor = torch.as_tensor(value, dtype=torch.float32)
            if name.endswith("std"):
                tensor = tensor.clamp_min(1e-3)
            getattr(self, name).copy_(tensor)

    def raw_logits(self, seq: torch.Tensor, ctx: torch.Tensor) -> torch.Tensor:
        """Uncalibrated conditional-hazard logits, shape (B, n_intervals)."""
        x = (seq - self.seq_mean) / self.seq_std
        c = (ctx - self.ctx_mean) / self.ctx_std
        context = self.ctx_encoder(c)
        gamma, beta = self.film(context).chunk(2, dim=-1)
        h = self.seq_in(x) * (1 + gamma.unsqueeze(1)) + beta.unsqueeze(1)
        out, _ = self.gru(h)
        weights = torch.softmax(self.attention(out).squeeze(-1), dim=1)
        pooled = torch.einsum("bt,bth->bh", weights, out)
        return self.head(torch.cat([out[:, -1], pooled, context], dim=-1))

    def forward(self, seq: torch.Tensor, ctx: torch.Tensor) -> torch.Tensor:
        """Calibrated conditional-hazard logits, shape (B, n_intervals)."""
        return self.raw_logits(seq, ctx) * self.calib_scale + self.calib_bias

    def cumulative_risk(self, seq: torch.Tensor, ctx: torch.Tensor) -> torch.Tensor:
        """P(rescue inhaler needed by the end of each horizon), shape (B, n_intervals)."""
        return hazard_to_cumulative(self(seq, ctx))


def hazard_to_cumulative(logits: torch.Tensor) -> torch.Tensor:
    log_survival = torch.cumsum(F.logsigmoid(-logits), dim=-1)
    return 1.0 - torch.exp(log_survival)


def survival_loss(logits: torch.Tensor, event: torch.Tensor, at_risk: torch.Tensor) -> torch.Tensor:
    """Discrete-time survival negative log-likelihood.

    ``at_risk[i, j]`` is 1 when sample i entered interval j event-free and the
    interval was observed (event inside it, or fully observed without one).
    ``event[i, j]`` is 1 when the first event fell inside interval j.
    """
    loss = F.binary_cross_entropy_with_logits(logits, event, weight=at_risk, reduction="sum")
    return loss / at_risk.sum().clamp_min(1.0)
