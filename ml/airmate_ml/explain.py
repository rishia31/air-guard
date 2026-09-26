"""Shapley-value explanations of the risk score with Captum.

Each explanation group (dust, pollen, recent inhaler use, ...) is swapped for a
"normal day" reference: the person's own baseline for particles and VOCs,
comfortable indoor conditions, a low pollen/AQI forecast, no recent puffs or
symptoms, and midday. Shapley value sampling then splits the gap between the
current score and the normal-day score across groups, so the contributions add
up exactly: score = normal_day_score + sum(contributions).
"""

from __future__ import annotations

import numpy as np
import torch
from captum.attr import ShapleyValueSampling

from .features import CTX_INDEX, SEQ_INDEX
from .model import AirmateRiskNet
from .schema import EXPLAIN_GROUPS, SCORE_HORIZON_INDEX

COMFORT = {"co2_k": 0.6, "humidity": 45.0, "temp_c": 22.0, "pollen": 1.0, "aqi": 30.0, "outdoor_temp_c": 20.0,
           "outdoor_humidity": 50.0}


class RiskExplainer:
    def __init__(self, model: AirmateRiskNet, n_samples: int = 24, seed: int = 0):
        self.model = model.eval()
        self.groups = list(EXPLAIN_GROUPS)
        self.n_samples = n_samples
        self.seed = seed
        n_seq, n_ctx = model.config["n_seq"], model.config["n_ctx"]
        fixed = len(self.groups)
        seq_mask = torch.full((n_seq,), fixed, dtype=torch.long)
        ctx_mask = torch.full((n_ctx,), fixed, dtype=torch.long)
        self._probe: dict[str, tuple[str, int]] = {}
        for gid, (name, spec) in enumerate(EXPLAIN_GROUPS.items()):
            for feat in spec["seq"]:
                seq_mask[SEQ_INDEX[feat]] = gid
            for feat in spec["ctx"]:
                ctx_mask[CTX_INDEX[feat]] = gid
            first = ("ctx", CTX_INDEX[spec["ctx"][0]]) if spec["ctx"] else ("seq", SEQ_INDEX[spec["seq"][0]])
            self._probe[name] = first
        self.seq_mask = seq_mask.view(1, 1, n_seq)
        self.ctx_mask = ctx_mask.view(1, n_ctx)
        self._svs = ShapleyValueSampling(self._score)

    def _score(self, seq: torch.Tensor, ctx: torch.Tensor) -> torch.Tensor:
        return 100.0 * self.model.cumulative_risk(seq, ctx)[:, SCORE_HORIZON_INDEX]

    def reference(self, seq: torch.Tensor, ctx: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        s, c = seq.clone(), ctx.clone()
        for level, rel, mean24, base in (
            ("log_coarse", "rel_coarse", "mean_log_coarse_24h", "base_log_coarse"),
            ("log_pm25", "rel_pm25", "mean_log_pm25_24h", "base_log_pm25"),
            ("log_tvoc", "rel_tvoc", "mean_log_tvoc_24h", "base_log_tvoc"),
        ):
            normal = ctx[:, CTX_INDEX[base]]
            s[:, :, SEQ_INDEX[level]] = normal[:, None]
            s[:, :, SEQ_INDEX[rel]] = 0.0
            c[:, CTX_INDEX[mean24]] = normal
        for feat in ("co2_k", "humidity", "temp_c"):
            s[:, :, SEQ_INDEX[feat]] = COMFORT[feat]
        for feat in ("frac_stuffy_24h", "frac_humid_24h", "frac_cold_24h", "puffs_6h", "puffs_24h", "puffs_7d",
                     "symptoms_24h", "symptoms_7d", "hour_sin"):
            c[:, CTX_INDEX[feat]] = 0.0
        for feat in ("pollen", "aqi", "outdoor_temp_c", "outdoor_humidity"):
            c[:, CTX_INDEX[feat]] = COMFORT[feat]
        c[:, CTX_INDEX["hours_since_puff"]] = 1.0
        c[:, CTX_INDEX["hour_cos"]] = -1.0  # noon
        return s, c

    @torch.no_grad()
    def explain(self, seq: torch.Tensor, ctx: torch.Tensor) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Returns (contributions (B, n_groups) in score points, score (B,), normal-day score (B,))."""
        seq_ref, ctx_ref = self.reference(seq, ctx)
        torch.manual_seed(self.seed)
        attr_seq, attr_ctx = self._svs.attribute(
            (seq, ctx),
            baselines=(seq_ref, ctx_ref),
            feature_mask=(self.seq_mask, self.ctx_mask),
            n_samples=self.n_samples,
            perturbations_per_eval=max(1, min(64, 4096 // max(1, seq.shape[0]))),
        )
        contributions = np.zeros((seq.shape[0], len(self.groups)), np.float32)
        for gid, name in enumerate(self.groups):
            where, col = self._probe[name]
            values = attr_ctx[:, col] if where == "ctx" else attr_seq[:, -1, col]
            contributions[:, gid] = values.numpy()
        return contributions, self._score(seq, ctx).numpy(), self._score(seq_ref, ctx_ref).numpy()
