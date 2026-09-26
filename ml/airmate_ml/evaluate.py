"""Metrics and baselines for the risk model."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from .data import CohortData
from .features import CTX_INDEX
from .rules import rule_components, score_from_points
from .schema import TRIGGERS


def expected_calibration_error(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    which = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    err = 0.0
    for b in range(bins):
        sel = which == b
        if sel.any():
            err += sel.mean() * abs(y[sel].mean() - p[sel].mean())
    return float(err)


def binary_metrics(y: np.ndarray, p: np.ndarray, probabilistic: bool = True) -> dict:
    out = {
        "n": int(len(y)),
        "base_rate": round(float(y.mean()), 4),
        "auroc": round(float(roc_auc_score(y, p)), 4),
        "auprc": round(float(average_precision_score(y, p)), 4),
    }
    if probabilistic:
        out["brier"] = round(float(brier_score_loss(y, p)), 4)
        out["ece"] = round(expected_calibration_error(y, p), 4)
        out["mean_pred"] = round(float(p.mean()), 4)
    return out


def reliability_curve(y: np.ndarray, p: np.ndarray, bins: int = 10) -> tuple[np.ndarray, np.ndarray]:
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    which = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    pred = np.array([p[which == b].mean() for b in range(bins) if (which == b).any()])
    obs = np.array([y[which == b].mean() for b in range(bins) if (which == b).any()])
    return pred, obs


def tabular_features(data: CohortData, idx: np.ndarray) -> np.ndarray:
    """Hand-built window summaries for the scikit-learn baselines."""
    seq, ctx = data.windows(idx)
    sensors = seq[:, :, :6]
    return np.concatenate(
        [seq[:, -1, :], sensors.mean(axis=1), sensors.max(axis=1), sensors[:, -10:, :].mean(axis=1), ctx], axis=1
    )


def rule_scores(data: CohortData, idx: np.ndarray) -> np.ndarray:
    raw, ctx = data.raw[idx], data.ctx[idx]
    points = rule_components(
        raw[:, 0],
        raw[:, 1],
        raw[:, 2],
        raw[:, 3],
        raw[:, 4],
        raw[:, 5],
        ctx[:, CTX_INDEX["pollen"]],
        ctx[:, CTX_INDEX["aqi"]],
        np.expm1(ctx[:, CTX_INDEX["puffs_24h"]]),
        np.expm1(ctx[:, CTX_INDEX["symptoms_24h"]]),
        {t: ctx[:, CTX_INDEX[f"trig_{t}"]] for t in TRIGGERS},
    )
    return score_from_points(points)
