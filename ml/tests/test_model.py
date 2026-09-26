import numpy as np
import torch

from airmate_ml.data import INTERVAL_BOUNDS, NO_EVENT, survival_labels
from airmate_ml.model import AirmateRiskNet, hazard_to_cumulative, survival_loss
from airmate_ml.schema import CTX_FEATURES, SEQ_FEATURES, WINDOW_BINS


def _model(**kw) -> AirmateRiskNet:
    torch.manual_seed(0)
    return AirmateRiskNet(len(SEQ_FEATURES), len(CTX_FEATURES), **kw).eval()


def test_cumulative_risk_is_a_monotone_probability():
    model = _model()
    seq = torch.randn(32, WINDOW_BINS, len(SEQ_FEATURES)) * 3
    ctx = torch.randn(32, len(CTX_FEATURES)) * 3
    with torch.no_grad():
        risk = model.cumulative_risk(seq, ctx)
    assert risk.shape == (32, 3)
    assert ((risk >= 0) & (risk <= 1)).all()
    assert (risk[:, 1:] >= risk[:, :-1] - 1e-7).all()


def test_hazard_to_cumulative_matches_closed_form():
    logits = torch.tensor([[0.0, 0.0, 0.0]])
    assert torch.allclose(hazard_to_cumulative(logits), torch.tensor([[0.5, 0.75, 0.875]]))


def test_survival_loss_ignores_samples_not_at_risk():
    logits = torch.tensor([[2.0, -1.0, 5.0]])
    event = torch.tensor([[0.0, 1.0, 0.0]])
    at_risk = torch.tensor([[1.0, 1.0, 0.0]])
    expected = (torch.nn.functional.softplus(torch.tensor(2.0)) + torch.nn.functional.softplus(torch.tensor(1.0))) / 2
    assert torch.isclose(survival_loss(logits, event, at_risk), expected)


def test_calibration_buffers_change_forward_only():
    model = _model()
    seq, ctx = torch.randn(4, WINDOW_BINS, len(SEQ_FEATURES)), torch.randn(4, len(CTX_FEATURES))
    raw = model.raw_logits(seq, ctx)
    model.calib_scale.fill_(2.0)
    model.calib_bias.fill_(-1.0)
    assert torch.allclose(model(seq, ctx), raw * 2 - 1)
    assert torch.allclose(model.raw_logits(seq, ctx), raw)


def test_model_learns_a_simple_signal():
    """A few hundred steps should separate windows with a dust spike from windows without."""
    torch.manual_seed(1)
    model = AirmateRiskNet(len(SEQ_FEATURES), len(CTX_FEATURES), hidden=16)
    opt = torch.optim.Adam(model.parameters(), lr=1e-2)
    n = 256
    seq = torch.randn(n, WINDOW_BINS, len(SEQ_FEATURES)) * 0.1
    spike = torch.rand(n) < 0.5
    seq[spike, -10:, SEQ_FEATURES.index("rel_coarse")] += 2.0
    ctx = torch.zeros(n, len(CTX_FEATURES))
    event = torch.zeros(n, 3)
    event[spike, 0] = 1.0
    at_risk = torch.ones(n, 3)
    at_risk[spike, 1:] = 0.0
    for _ in range(150):
        opt.zero_grad()
        loss = survival_loss(model.raw_logits(seq, ctx), event, at_risk)
        loss.backward()
        opt.step()
    model.eval()
    with torch.no_grad():
        risk = model.cumulative_risk(seq, ctx)[:, 0]
    assert risk[spike].mean() > 0.8 and risk[~spike].mean() < 0.2


def test_survival_labels_intervals_and_censoring():
    n = 400
    puffs = np.zeros(n, np.int16)
    puffs[100] = 2
    event, at_risk, tte, observed = survival_labels(puffs)
    one_h, four_h, twelve_h = INTERVAL_BOUNDS[1:]
    # 10 bins before the puff: event in the first interval.
    assert tte[90] == 10 and event[90].tolist() == [1, 0, 0] and at_risk[90].tolist() == [1, 0, 0]
    # 50 bins before: survives the first hour, event in 1-4 h.
    assert event[50].tolist() == [0, 1, 0] and at_risk[50].tolist() == [1, 1, 0]
    # The bin with the puff looks strictly forward, so no future event is known.
    assert tte[100] == NO_EVENT
    # Near the end of the timeline the future is censored.
    t = n - 1 - (one_h + 5)
    assert at_risk[t].tolist() == [1, 0, 0] and observed[t] == one_h + 5
    assert at_risk[n - 1].sum() == 0
    assert twelve_h > four_h > one_h
