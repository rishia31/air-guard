"""Assemble model windows and survival labels from a simulated cohort."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .features import build_timeline
from .schema import BINS_PER_HOUR, HORIZON_HOURS, TRIGGERS, WINDOW_BINS
from .simulate import Cohort

NO_EVENT = np.iinfo(np.int32).max // 2
INTERVAL_BOUNDS = (0, *(h * BINS_PER_HOUR for h in HORIZON_HOURS))
_WINDOW_OFFSETS = np.arange(-WINDOW_BINS + 1, 1)


def survival_labels(puffs: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Per-bin labels for "rescue inhaler used within each horizon interval".

    Returns (event, at_risk, time_to_event, observed_future), where times are in bins.
    """
    n = len(puffs)
    idx = np.arange(n)
    positions = np.where(puffs > 0, idx, NO_EVENT)
    at_or_after = np.minimum.accumulate(positions[::-1])[::-1]
    after = np.append(at_or_after[1:], NO_EVENT)
    tte = np.where(after < NO_EVENT, after - idx, NO_EVENT)
    observed = n - 1 - idx
    event = np.zeros((n, len(HORIZON_HOURS)), np.float32)
    at_risk = np.zeros_like(event)
    for j in range(len(HORIZON_HOURS)):
        lo, hi = INTERVAL_BOUNDS[j], INTERVAL_BOUNDS[j + 1]
        entered = (tte > lo) & (observed > lo)
        hit = entered & (tte <= hi)
        event[:, j] = hit
        at_risk[:, j] = entered & (hit | (observed >= hi))
    return event, at_risk, tte.astype(np.int32), observed.astype(np.int32)


@dataclass
class CohortData:
    seq: np.ndarray  # (N, n_seq) concatenated per-bin sequence features
    ctx: np.ndarray  # (N, n_ctx)
    raw: np.ndarray  # (N, 6) imputed readings in natural units
    normal: np.ndarray  # (N, 3) personal normal: pm25, coarse, tvoc
    event: np.ndarray  # (N, n_intervals)
    at_risk: np.ndarray  # (N, n_intervals)
    tte: np.ndarray  # (N,) bins until next rescue puff
    observed: np.ndarray  # (N,) bins of observed future
    contrib: np.ndarray  # (N, 6) hidden per-trigger hazard contribution
    log_rate: np.ndarray  # (N,) hidden true log flare rate, only used to report the oracle ceiling
    user: np.ndarray  # (N,) user index
    local_t: np.ndarray  # (N,) bin index within the user's timeline

    def windows(self, idx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(B, WINDOW_BINS, n_seq) sequences and (B, n_ctx) contexts ending at ``idx``."""
        return self.seq[idx[:, None] + _WINDOW_OFFSETS[None, :]], self.ctx[idx]

    def indices(self, users: np.ndarray, stride: int) -> np.ndarray:
        """Window end positions for the given users, every ``stride`` bins."""
        keep = np.isin(self.user, users) & (self.local_t >= WINDOW_BINS - 1) & (self.local_t % stride == 0)
        return np.flatnonzero(keep)

    def binary_labels(self, idx: np.ndarray, horizon_index: int) -> tuple[np.ndarray, np.ndarray]:
        """(y, valid) for "rescue puff within horizon", excluding censored windows."""
        hi = INTERVAL_BOUNDS[horizon_index + 1]
        y = self.tte[idx] <= hi
        valid = y | (self.observed[idx] >= hi)
        return y.astype(np.float32), valid


def build_dataset(cohort: Cohort) -> CohortData:
    cols: dict[str, list[np.ndarray]] = {k: [] for k in CohortData.__dataclass_fields__}
    for u in range(cohort.n_users):
        tl = build_timeline(
            cohort.sensors[u], cohort.hour, cohort.puffs[u], cohort.symptoms[u], cohort.outdoor[u], cohort.reported[u]
        )
        event, at_risk, tte, observed = survival_labels(cohort.puffs[u])
        n = cohort.n_bins
        cols["seq"].append(tl.seq)
        cols["ctx"].append(tl.ctx)
        cols["raw"].append(tl.raw)
        cols["normal"].append(np.stack([tl.normal["pm25"], tl.normal["coarse"], tl.normal["tvoc"]], axis=1))
        cols["event"].append(event)
        cols["at_risk"].append(at_risk)
        cols["tte"].append(tte)
        cols["observed"].append(observed)
        cols["contrib"].append(cohort.contrib[u].reshape(n, len(TRIGGERS)))
        cols["log_rate"].append(cohort.log_rate[u])
        cols["user"].append(np.full(n, u, np.int32))
        cols["local_t"].append(np.arange(n, dtype=np.int32))
    return CohortData(**{k: np.concatenate(v, axis=0) for k, v in cols.items()})


def split_users(n_users: int, seed: int, val: float = 0.15, test: float = 0.15):
    perm = np.random.default_rng(seed).permutation(n_users)
    n_val, n_test = int(round(n_users * val)), int(round(n_users * test))
    return perm[n_val + n_test :], perm[:n_val], perm[n_val : n_val + n_test]
