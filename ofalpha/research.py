"""Signal research: information coefficients, conditional moves, and an
out-of-sample linear forecast of the forward mid-price change.

Outputs (results/):
  ic_by_day.csv        Spearman IC of each feature vs each horizon, per day
  qi_deciles.csv       mean forward move by queue-imbalance decile (train days)
  model.json           standardisation + OLS coefficients per horizon (train days only)
  model_oos.csv        R^2 and IC of the forecast on train / valid / test days
  pred_deciles.csv     realised move by forecast decile on the test days
"""
import json

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from . import config as C
from .features import FEATURES, TARGETS


def load(day: str) -> pd.DataFrame:
    df = pd.read_parquet(C.FEATURES / f"{day}.parquet")
    ok = (df.ask > df.bid) & np.isfinite(df[FEATURES + TARGETS]).all(axis=1)
    return df[ok].reset_index(drop=True)


def split_of(day: str) -> str:
    return "train" if day in C.TRAIN else "valid" if day in C.VALID else "test"


def rank_ic(x: np.ndarray, y: np.ndarray) -> float:
    return float(np.corrcoef(rankdata(x), rankdata(y))[0, 1])


def ic_by_day(days) -> pd.DataFrame:
    rows = []
    for day in days:
        df = load(day)
        ranks = {c: rankdata(df[c]) for c in FEATURES + TARGETS}
        for f in FEATURES:
            for tgt in TARGETS:
                rows.append({"day": day, "split": split_of(day), "feature": f,
                             "horizon_s": int(tgt.split("_")[1]),
                             "ic": float(np.corrcoef(ranks[f], ranks[tgt])[0, 1])})
    return pd.DataFrame(rows)


def qi_deciles(days) -> pd.DataFrame:
    df = pd.concat([load(d) for d in days])
    df["decile"] = pd.qcut(df.qi.rank(method="first"), 10, labels=range(1, 11))
    cols = ["fwd_1", "fwd_5", "fwd_30"]
    out = df.groupby("decile", observed=True)[["qi"] + cols].mean()
    out["n"] = df.groupby("decile", observed=True).size()
    return out.reset_index()


def fit(days) -> dict:
    df = pd.concat([load(d) for d in days])
    X = df[FEATURES].to_numpy(np.float64)
    mu, sd = X.mean(0), X.std(0)
    Z = np.column_stack([np.ones(len(X)), (X - mu) / sd])
    model = {"features": FEATURES, "mean": mu.tolist(), "std": sd.tolist(), "beta": {}}
    for tgt in TARGETS:
        beta, *_ = np.linalg.lstsq(Z, df[tgt].to_numpy(np.float64), rcond=None)
        model["beta"][tgt] = beta.tolist()
    return model


def predict(df: pd.DataFrame, model: dict, horizon_s: int) -> np.ndarray:
    X = df[model["features"]].to_numpy(np.float64)
    Z = (X - np.array(model["mean"])) / np.array(model["std"])
    b = np.array(model["beta"][f"fwd_{horizon_s}"])
    return b[0] + Z @ b[1:]


def evaluate(model: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, dec = [], []
    for day in C.DATES:
        df = load(day)
        for h in C.HORIZONS_S:
            y, p = df[f"fwd_{h}"].to_numpy(np.float64), predict(df, model, h)
            rows.append({"day": day, "split": split_of(day), "horizon_s": h,
                         "r2_oos": 1 - np.sum((y - p) ** 2) / np.sum(y ** 2),
                         "ic": rank_ic(p, y), "pred_sd": p.std(), "n": len(y)})
            if split_of(day) == "test" and h in (1, 5, 30):
                d = pd.DataFrame({"pred": p, "real": y, "horizon_s": h})
                d["decile"] = pd.qcut(d.pred.rank(method="first"), 10, labels=range(1, 11))
                dec.append(d)
    pred_dec = (pd.concat(dec).groupby(["horizon_s", "decile"], observed=True)[["pred", "real"]]
                .mean().reset_index())
    return pd.DataFrame(rows), pred_dec


def main() -> None:
    C.RESULTS.mkdir(exist_ok=True)
    ic = ic_by_day(C.DATES)
    ic.to_csv(C.RESULTS / "ic_by_day.csv", index=False)
    summary = (ic.groupby(["feature", "horizon_s", "split"]).ic.mean()
               .unstack("split")[["train", "valid", "test"]])
    print("Mean Spearman IC by split\n", summary.round(3).to_string(), "\n")

    qi_deciles(C.TRAIN).to_csv(C.RESULTS / "qi_deciles.csv", index=False)

    model = fit(C.TRAIN)
    (C.RESULTS / "model.json").write_text(json.dumps(model, indent=1))
    oos, pred_dec = evaluate(model)
    oos.to_csv(C.RESULTS / "model_oos.csv", index=False)
    pred_dec.to_csv(C.RESULTS / "pred_deciles.csv", index=False)
    print("Linear forecast, mean by split\n",
          oos.groupby(["horizon_s", "split"])[["r2_oos", "ic"]].mean()
          .unstack("split").round(4).to_string())


if __name__ == "__main__":
    main()
