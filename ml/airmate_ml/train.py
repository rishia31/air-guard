"""Train, calibrate, evaluate, and export the Airmate risk model.

    uv run airmate-train                # full run (a few minutes on a laptop CPU)
    uv run airmate-train --quick        # smoke test
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from . import __version__
from .data import CohortData, build_dataset, split_users
from .evaluate import binary_metrics, reliability_curve, rule_scores, tabular_features
from .explain import RiskExplainer
from .features import CTX_INDEX, DEFAULT_COARSE, SEQ_INDEX
from .model import AirmateRiskNet, hazard_to_cumulative, survival_loss
from .schema import (
    BIN_MINUTES,
    CTX_FEATURES,
    GROUP_TO_TRIGGER,
    HORIZON_HOURS,
    SCORE_HORIZON_INDEX,
    SENSOR_DEFAULTS,
    SEQ_FEATURES,
    TRIGGERS,
    WINDOW_BINS,
)
from .simulate import simulate_cohort

ML_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
REPORTS_DIR = ML_ROOT / "reports"

_LOG_PM25, _LOG_COARSE, _LOG_TVOC = (
    float(np.log1p(SENSOR_DEFAULTS["pm25"])),
    float(np.log1p(DEFAULT_COARSE)),
    float(np.log1p(SENSOR_DEFAULTS["tvoc"])),
)
# What build_timeline produces when a sensor group is absent, so dropout matches serving exactly.
SENSOR_DROPOUT = {
    "pm": (
        {"log_pm25": _LOG_PM25, "log_coarse": _LOG_COARSE, "rel_pm25": 0.0, "rel_coarse": 0.0, "has_pm": 0.0},
        {"mean_log_pm25_24h": _LOG_PM25, "mean_log_coarse_24h": _LOG_COARSE, "pm_coverage_24h": 0.0,
         "base_log_pm25": _LOG_PM25, "base_log_coarse": _LOG_COARSE},
    ),
    "co2": ({"co2_k": SENSOR_DEFAULTS["co2"] / 1000.0, "has_co2": 0.0}, {"frac_stuffy_24h": 0.0}),
    "voc": (
        {"log_tvoc": _LOG_TVOC, "rel_tvoc": 0.0, "has_voc": 0.0},
        {"mean_log_tvoc_24h": _LOG_TVOC, "base_log_tvoc": _LOG_TVOC},
    ),
    "climate": (
        {"temp_c": SENSOR_DEFAULTS["temp_c"], "humidity": SENSOR_DEFAULTS["humidity"], "has_climate": 0.0},
        {"frac_humid_24h": 0.0, "frac_cold_24h": 0.0},
    ),
}
# Forecasts are uncertain in real life; noise here also stops the model from memorizing
# person-days through their exact forecast values.
FORECAST_NOISE = {"aqi": 0.3, "pollen": 0.3, "outdoor_temp_c": 0.3, "outdoor_humidity": 0.3}
SUMMARY_NOISE = ("mean_log_pm25_24h", "mean_log_coarse_24h", "mean_log_tvoc_24h", "base_log_pm25",
                 "base_log_coarse", "base_log_tvoc")


def augment(seq: np.ndarray, ctx: np.ndarray, rng: np.random.Generator, ctx_std: np.ndarray,
            drop_p: float) -> tuple[np.ndarray, np.ndarray]:
    """Sensor-group dropout plus forecast/summary noise, applied in place to a training batch."""
    b = seq.shape[0]
    for seq_vals, ctx_vals in SENSOR_DROPOUT.values():
        drop = rng.random(b) < drop_p
        if not drop.any():
            continue
        for name, value in seq_vals.items():
            seq[drop, :, SEQ_INDEX[name]] = value
        for name, value in ctx_vals.items():
            ctx[drop, CTX_INDEX[name]] = value
    for name, scale in FORECAST_NOISE.items():
        j = CTX_INDEX[name]
        ctx[:, j] += rng.normal(0.0, scale * ctx_std[j], b).astype(np.float32)
    for name in SUMMARY_NOISE:
        j = CTX_INDEX[name]
        ctx[:, j] += rng.normal(0.0, 0.05 * ctx_std[j], b).astype(np.float32)
    return seq, ctx


def _tensors(data: CohortData, idx: np.ndarray) -> tuple[torch.Tensor, torch.Tensor]:
    seq, ctx = data.windows(idx)
    return torch.from_numpy(seq), torch.from_numpy(ctx)


@torch.no_grad()
def predict_logits(model: AirmateRiskNet, data: CohortData, idx: np.ndarray, calibrated: bool) -> torch.Tensor:
    model.eval()
    out = []
    for start in range(0, len(idx), 4096):
        seq, ctx = _tensors(data, idx[start : start + 4096])
        out.append(model(seq, ctx) if calibrated else model.raw_logits(seq, ctx))
    return torch.cat(out)


def fit_platt(model: AirmateRiskNet, logits: torch.Tensor, event: torch.Tensor, at_risk: torch.Tensor) -> None:
    """Per-interval Platt scaling of hazard logits on held-out data."""
    scale = torch.ones(logits.shape[1], requires_grad=True)
    bias = torch.zeros(logits.shape[1], requires_grad=True)
    opt = torch.optim.LBFGS([scale, bias], lr=0.5, max_iter=200)

    def closure():
        opt.zero_grad()
        loss = survival_loss(logits * scale + bias, event, at_risk)
        loss.backward()
        return loss

    opt.step(closure)
    model.calib_scale.copy_(scale.detach())
    model.calib_bias.copy_(bias.detach())


def train(args) -> dict:
    t0 = time.time()
    rng = np.random.default_rng(args.seed)
    torch.manual_seed(args.seed)
    torch.set_num_threads(min(8, os.cpu_count() or 1))

    print(f"Simulating {args.users} people x {args.days} days ...", flush=True)
    cohort = simulate_cohort(args.users, days=args.days, seed=args.seed)
    data = build_dataset(cohort)
    train_users, val_users, test_users = split_users(cohort.n_users, args.seed)
    train_idx = data.indices(train_users, stride=3)
    val_idx = data.indices(val_users, stride=5)
    test_idx = data.indices(test_users, stride=5)
    print(f"  windows: train {len(train_idx):,}  val {len(val_idx):,}  test {len(test_idx):,}  "
          f"({time.time() - t0:.0f}s)", flush=True)

    train_bins = np.flatnonzero(np.isin(data.user, train_users))
    model = AirmateRiskNet(len(SEQ_FEATURES), len(CTX_FEATURES), n_intervals=len(HORIZON_HOURS), hidden=args.hidden,
                           dropout=args.dropout)
    ctx_std = data.ctx[train_bins].std(0)
    model.set_normalization(data.seq[train_bins].mean(0), data.seq[train_bins].std(0), data.ctx[train_bins].mean(0), ctx_std)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"AirmateRiskNet: {n_params:,} parameters", flush=True)

    total_steps = args.epochs * args.steps_per_epoch
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=total_steps, pct_start=0.15)
    val_event = torch.from_numpy(data.event[val_idx])
    val_at_risk = torch.from_numpy(data.at_risk[val_idx])
    best_loss, best_state, history, stale = float("inf"), None, [], 0

    for epoch in range(args.epochs):
        model.train()
        order = rng.choice(train_idx, size=args.steps_per_epoch * args.batch_size, replace=True)
        running = 0.0
        for step in range(args.steps_per_epoch):
            batch = order[step * args.batch_size : (step + 1) * args.batch_size]
            seq, ctx = augment(*data.windows(batch), rng, ctx_std, args.sensor_dropout)
            loss = survival_loss(
                model.raw_logits(torch.from_numpy(seq), torch.from_numpy(ctx)),
                torch.from_numpy(data.event[batch]),
                torch.from_numpy(data.at_risk[batch]),
            )
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            running += loss.item()
        val_loss = survival_loss(predict_logits(model, data, val_idx, calibrated=False), val_event, val_at_risk).item()
        history.append({"epoch": epoch + 1, "train_loss": running / args.steps_per_epoch, "val_loss": val_loss})
        print(f"  epoch {epoch + 1}/{args.epochs}  train {running / args.steps_per_epoch:.4f}  val {val_loss:.4f}  "
              f"({time.time() - t0:.0f}s)", flush=True)
        if val_loss < best_loss:
            best_loss, best_state, stale = val_loss, copy.deepcopy(model.state_dict()), 0
        else:
            stale += 1
            if stale >= args.patience:
                print(f"  early stop: no validation improvement for {args.patience} epochs", flush=True)
                break

    model.load_state_dict(best_state)
    fit_platt(model, predict_logits(model, data, val_idx, calibrated=False), val_event, val_at_risk)
    print(f"Calibrated: scale {model.calib_scale.numpy().round(3)}  bias {model.calib_bias.numpy().round(3)}", flush=True)

    probs = hazard_to_cumulative(predict_logits(model, data, test_idx, calibrated=True)).numpy()
    metrics: dict = {"gru": {}, "rules": {}, "logistic_regression": {}, "gradient_boosting": {}}
    curves: dict = {}
    for j, hours in enumerate(HORIZON_HOURS):
        y, valid = data.binary_labels(test_idx, j)
        metrics["gru"][f"{hours}h"] = binary_metrics(y[valid], probs[valid, j])
        if j == SCORE_HORIZON_INDEX:
            curves["gru"] = (y[valid], probs[valid, j])

    # Baselines on the headline 4 h horizon.
    y_te, valid_te = data.binary_labels(test_idx, SCORE_HORIZON_INDEX)
    te = test_idx[valid_te]
    rules = rule_scores(data, te)
    metrics["rules"]["4h"] = binary_metrics(y_te[valid_te], rules, probabilistic=False)
    curves["rules"] = (y_te[valid_te], rules / 100.0)

    fit_idx = train_idx[rng.choice(len(train_idx), size=min(len(train_idx), args.baseline_samples), replace=False)]
    y_tr, valid_tr = data.binary_labels(fit_idx, SCORE_HORIZON_INDEX)
    x_tr, x_te = tabular_features(data, fit_idx[valid_tr]), tabular_features(data, te)
    for name, clf in (
        ("logistic_regression", make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, C=0.5))),
        ("gradient_boosting", HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, max_leaf_nodes=31,
                                                              random_state=args.seed)),
    ):
        clf.fit(x_tr, y_tr[valid_tr])
        p = clf.predict_proba(x_te)[:, 1]
        metrics[name]["4h"] = binary_metrics(y_te[valid_te], p)
        curves[name] = (y_te[valid_te], p)
    print(f"Baselines fitted ({time.time() - t0:.0f}s)", flush=True)
    metrics["oracle"] = {"4h": binary_metrics(y_te[valid_te], data.log_rate[te], probabilistic=False)}

    metrics["explanations"] = explanation_accuracy(model, data, test_idx, probs[:, SCORE_HORIZON_INDEX], rng, args)
    metrics["training"] = {
        "users": args.users,
        "days": args.days,
        "train_users": int(len(train_users)),
        "val_users": int(len(val_users)),
        "test_users": int(len(test_users)),
        "train_windows": int(len(train_idx)),
        "test_windows": int(len(test_idx)),
        "parameters": int(n_params),
        "epochs": len(history),
        "weight_decay": args.weight_decay,
        "dropout": args.dropout,
        "sensor_dropout": args.sensor_dropout,
        "best_val_loss": round(best_loss, 5),
        "seconds": round(time.time() - t0, 1),
        "history": history,
    }
    print(json.dumps({k: v for k, v in metrics.items() if k != "training"}, indent=2), flush=True)

    args.out.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "format": "airmate-risk-v1",
            "version": __version__,
            "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "config": model.config,
            "state_dict": model.state_dict(),
            "seq_features": list(SEQ_FEATURES),
            "ctx_features": list(CTX_FEATURES),
            "window_bins": WINDOW_BINS,
            "bin_minutes": BIN_MINUTES,
            "horizon_hours": list(HORIZON_HOURS),
            "metrics": json.loads(json.dumps(metrics)),
        },
        args.out / "airmate_risk.pt",
    )
    (args.out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    if not args.quick:
        write_reports(args.reports, metrics, curves)
    print(f"Saved {args.out / 'airmate_risk.pt'} ({time.time() - t0:.0f}s)", flush=True)
    return metrics


def explanation_accuracy(model, data: CohortData, test_idx, p4h, rng, args) -> dict:
    """How often the top Shapley group matches the simulator's hidden dominant trigger."""
    contrib = data.contrib[test_idx].astype(np.float32)
    strong = (p4h >= 0.15) & (contrib.max(axis=1) >= 1.0)
    candidates = np.flatnonzero(strong)
    if len(candidates) == 0:
        return {"n": 0}
    pick = rng.choice(candidates, size=min(len(candidates), args.explain_samples), replace=False)
    explainer = RiskExplainer(model, n_samples=16)
    values = []
    for start in range(0, len(pick), 256):
        seq, ctx = _tensors(data, test_idx[pick[start : start + 256]])
        values.append(explainer.explain(seq, ctx)[0])
    values = np.concatenate(values)
    trigger_groups = [i for i, g in enumerate(explainer.groups) if g in GROUP_TO_TRIGGER]
    top_trigger = np.array(
        [TRIGGERS.index(GROUP_TO_TRIGGER[explainer.groups[trigger_groups[k]]])
         for k in values[:, trigger_groups].argmax(axis=1)]
    )
    truth = contrib[pick].argmax(axis=1)
    majority = np.bincount(truth, minlength=len(TRIGGERS)).max() / len(truth)
    return {
        "n": int(len(pick)),
        "top1_trigger_accuracy": round(float((top_trigger == truth).mean()), 4),
        "majority_class_rate": round(float(majority), 4),
        "per_trigger_recall": {
            t: round(float((top_trigger[truth == i] == i).mean()), 3) for i, t in enumerate(TRIGGERS) if (truth == i).any()
        },
    }


def write_reports(reports: Path, metrics: dict, curves: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import precision_recall_curve, roc_curve

    reports.mkdir(parents=True, exist_ok=True)
    names = {"gru": "GRU survival (ours)", "gradient_boosting": "Gradient boosting", "logistic_regression":
             "Logistic regression", "rules": "Rule-based score"}
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4))
    for key, (y, p) in curves.items():
        fpr, tpr, _ = roc_curve(y, p)
        prec, rec, _ = precision_recall_curve(y, p)
        m = metrics[key]["4h"]
        axes[0].plot(fpr, tpr, label=f"{names[key]} (AUROC {m['auroc']:.3f})")
        axes[1].plot(rec, prec, label=f"{names[key]} (AUPRC {m['auprc']:.3f})")
    axes[0].plot([0, 1], [0, 1], "k:", lw=1)
    axes[0].set(title="ROC: rescue inhaler within 4 h", xlabel="False positive rate", ylabel="True positive rate")
    axes[1].set(title="Precision-recall", xlabel="Recall", ylabel="Precision")
    y, p = curves["gru"]
    pred, obs = reliability_curve(y, p, bins=12)
    axes[2].plot([0, pred.max()], [0, pred.max()], "k:", lw=1)
    axes[2].plot(pred, obs, "o-", label="GRU (calibrated)")
    axes[2].set(title="Calibration (held-out users)", xlabel="Predicted probability", ylabel="Observed frequency")
    for ax in axes:
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
    fig.suptitle("Airmate risk model on simulated held-out users (not real patient data)")
    fig.tight_layout()
    fig.savefig(reports / "evaluation.png", dpi=130)
    plt.close(fig)

    hist = metrics["training"]["history"]
    fig, ax = plt.subplots(figsize=(5, 3.2))
    ax.plot([h["epoch"] for h in hist], [h["train_loss"] for h in hist], "o-", label="train")
    ax.plot([h["epoch"] for h in hist], [h["val_loss"] for h in hist], "o-", label="validation")
    ax.set(title="Survival loss", xlabel="Epoch", ylabel="NLL per at-risk interval")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(reports / "training_curve.png", dpi=130)
    plt.close(fig)
    write_model_card(ML_ROOT / "MODEL_CARD.md", metrics)


def write_model_card(path: Path, m: dict) -> None:
    rows = []
    for key, label in (("gru", "GRU survival model (ours)"), ("gradient_boosting", "Gradient boosting (scikit-learn)"),
                       ("logistic_regression", "Logistic regression (scikit-learn)"), ("rules", "Rule-based score"),
                       ("oracle", "Oracle: the simulator's hidden current flare rate (reference)")):
        if key not in m:
            continue
        r = m[key]["4h"]
        brier = f"{r['brier']:.4f}" if "brier" in r else "n/a"
        ece = f"{r['ece']:.4f}" if "ece" in r else "n/a"
        rows.append(f"| {label} | {r['auroc']:.3f} | {r['auprc']:.3f} | {brier} | {ece} |")
    horizons = "\n".join(
        f"| {h} | {m['gru'][h]['auroc']:.3f} | {m['gru'][h]['auprc']:.3f} | {m['gru'][h]['brier']:.4f} | "
        f"{m['gru'][h]['base_rate']:.3f} | {m['gru'][h]['mean_pred']:.3f} |"
        for h in m["gru"]
    )
    e = m["explanations"]
    t = m["training"]
    recall = ", ".join(f"{k.replace('_', ' ')} {v:.0%}" for k, v in e.get("per_trigger_recall", {}).items())
    path.write_text(f"""# Model card: Airmate risk model

> Trained and evaluated **only on simulated data**. There is no public dataset that pairs home
> air-quality streams with inhaler use, so these numbers show the pipeline works end to end.
> They are not evidence of clinical accuracy. Airmate is an early-warning and support tool, not a medical device.

## What it predicts

The probability that the person will need their rescue inhaler within the next 1, 4, and 12 hours.
The 0-100 risk score in the app is the calibrated 4-hour probability × 100.

## Inputs

* **Sensor stream** (last 3 h at 3-minute resolution): PM2.5, coarse dust (PM10 − PM2.5), CO₂, TVOC,
  temperature, humidity, each particle/VOC channel relative to the person's own 24 h baseline, plus
  availability masks, so the model works with whichever sensors are attached.
* **Context:** time of day, outdoor AQI and pollen forecast, outdoor weather, rescue puffs in the last
  6 h / 24 h / 7 days, hours since last puff, logged symptoms, 24 h exposure summaries, personal
  baselines, and self-reported triggers.

## Architecture

`AirmateRiskNet` (PyTorch, {t['parameters']:,} parameters): context MLP → FiLM modulation of the sensor
sequence → GRU → attention pooling → discrete-time survival head with one conditional hazard per
interval (0-1 h, 1-4 h, 4-12 h). Cumulative risk is monotone across horizons by construction.
Trained with the survival negative log-likelihood (censoring handled), AdamW with a one-cycle
learning-rate schedule, early stopping on validation loss, then per-interval Platt calibration.

## Data

`airmate_ml.simulate` generates {t['users']} people × {t['days']} days. Each person has hidden trigger
sensitivities, a home with its own ventilation, cooking, cleaning, candles, sprays, pets, humidity,
and heating, a daily schedule, and seasonal outdoor pollen, smoke episodes, and weather.
Flares follow a hazard process with fast-attack/slow-release acute effects, an allergen late-phase
response, day-scale inflammation, a night-time peak, and rescue-inhaler protection. Readings get
sensor noise, missing sensors, and offline gaps. People are split by person (train {t['train_users']},
validation {t['val_users']}, test {t['test_users']}), so the test set is people the model never saw.

## Results on held-out simulated people (4-hour horizon)

| Model | AUROC | AUPRC | Brier | ECE |
|---|---|---|---|---|
{chr(10).join(rows)}

The oracle ranks each moment by the simulator's hidden *current* flare rate, which no real model can see.
It is a reference point, not a ceiling: the model can beat it because it also anticipates what usually
happens next (dinner-time cooking, night-time peaks) and learns the logging habits behind the labels.

GRU by horizon:

| Horizon | AUROC | AUPRC | Brier | Base rate | Mean predicted |
|---|---|---|---|---|---|
{horizons}

## Explanations

Captum Shapley value sampling splits each score into contributions from dust, fine particles,
VOCs, CO₂, humidity, cold air, pollen, outdoor AQI, weather, inhaler use, symptoms, and time of day,
relative to a "normal day" reference built from the person's own baselines. On {e.get('n', 0)} high-risk
test moments, the top trigger group matched the simulator's hidden dominant trigger
**{e.get('top1_trigger_accuracy', 0):.0%}** of the time (always guessing the most common trigger: {e.get('majority_class_rate', 0):.0%}).
Recall by trigger: {recall}.

![Evaluation](reports/evaluation.png)

## Limitations

* Simulated data encodes our assumptions about asthma; real people will differ.
* The label is "rescue inhaler used", which in real life is affected by adherence and logging.
* Exposure away from home is invisible to a home sensor.
* A real deployment would need prospective validation with clinicians, consent, and HIPAA-compliant handling.
""")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Train the Airmate risk model on a simulated cohort.")
    parser.add_argument("--users", type=int, default=1200)
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--steps-per-epoch", type=int, default=500)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--lr", type=float, default=2e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-2)
    parser.add_argument("--dropout", type=float, default=0.2)
    parser.add_argument("--sensor-dropout", type=float, default=0.1, help="per-group chance of hiding a sensor")
    parser.add_argument("--patience", type=int, default=3)
    parser.add_argument("--hidden", type=int, default=64)
    parser.add_argument("--baseline-samples", type=int, default=200_000)
    parser.add_argument("--explain-samples", type=int, default=1500)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--out", type=Path, default=ARTIFACT_DIR)
    parser.add_argument("--reports", type=Path, default=REPORTS_DIR)
    parser.add_argument("--quick", action="store_true", help="tiny run for smoke tests")
    args = parser.parse_args(argv)
    if args.quick:
        args.users, args.days, args.epochs, args.steps_per_epoch = 40, 8, 1, 20
        args.baseline_samples, args.explain_samples = 5000, 64
    train(args)


if __name__ == "__main__":
    main()
