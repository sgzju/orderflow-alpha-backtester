"""Execution-cost study: does the order-flow forecast lower implementation shortfall?

A parent order of ORDER_QTY arrives every 10 s with a random side and must be
completed within a window W. Three policies are compared on identical orders:

  immediate      market order on arrival
  passive        rest at the near touch, cross at the deadline if unfilled
  signal-aware   as passive, but cross immediately (or early) whenever the
                 forecast says the price is about to move away from us

Cost = side * (fill price - arrival mid) / arrival mid + fee, in basis points.
The signal's (threshold, horizon) is chosen on the validation days for each W;
the test days are evaluated once. Standard errors use 5-minute blocks of
paired differences to account for overlapping windows.
"""
import itertools
import json

import numpy as np
import pandas as pd

from . import config as C
from .engine import IMMEDIATE, PASSIVE, SIGNAL, run_execution
from .sweep import day_arrays

PARENT_EVERY_MS = 10_000
WINDOWS_S = [5, 10, 30, 60]
THETAS = [0.05, 0.1, 0.15, 0.2, 0.3, 0.5]
SIGNAL_H = [1, 2, 5, 10, 30]
LAT_MS = 50
BLOCK_MS = 300_000


def parents(day: str) -> tuple[np.ndarray, np.ndarray]:
    gt = day_arrays(day)["gt"]
    pt = np.arange(gt[0], gt[-1] - 60_000, PARENT_EVERY_MS, dtype=np.int64)
    seed = int(day.replace("-", ""))
    ps = np.random.default_rng(seed).choice(np.array([-1, 1], dtype=np.int64), size=len(pt))
    return pt, ps


def run(day: str, policy: int, window_s: int, theta: float = 0.0, h: int = 5,
        lat_ms: int = LAT_MS, pred=None) -> pd.DataFrame:
    d = day_arrays(day)
    pt, ps = parents(day)
    p = d["pred"][h] if pred is None else pred
    out = run_execution(pt, ps, d["gt"], p, *d["q"], *d["tr"], policy, theta,
                        window_s * 1000, lat_ms, C.ORDER_QTY)
    mid, px, taker, t_fill = out.T
    fee = np.where(taker > 0, C.TAKER_FEE_BP, C.MAKER_FEE_BP)
    return pd.DataFrame({"day": day, "t": pt, "side": ps, "cost_bp": ps * (px - mid) / mid * 1e4 + fee,
                         "slip_bp": ps * (px - mid) / mid * 1e4, "taker": taker,
                         "wait_s": (t_fill - pt) / 1000})


def paired(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    """Mean of the paired cost difference a - b, with a 5-minute-block standard error."""
    diff = a.cost_bp.to_numpy() - b.cost_bp.to_numpy()
    blocks = pd.Series(diff).groupby([a.day.to_numpy(), a.t.to_numpy() // BLOCK_MS]).mean()
    se = blocks.std(ddof=1) / np.sqrt(len(blocks))
    return {"diff_bp": diff.mean(), "se_bp": se, "t_stat": diff.mean() / se}


def main() -> None:
    rows = []
    for W, th, h in itertools.product(WINDOWS_S, THETAS, SIGNAL_H):
        c = pd.concat([run(d, SIGNAL, W, th, h) for d in C.VALID])
        rows.append({"window_s": W, "theta": th, "horizon_s": h, "cost_bp": c.cost_bp.mean(),
                     "taker_share": c.taker.mean()})
    for W in WINDOWS_S:
        c = pd.concat([run(d, PASSIVE, W) for d in C.VALID])
        rows.append({"window_s": W, "policy": "passive", "cost_bp": c.cost_bp.mean()})
    val = pd.DataFrame(rows)
    val.to_csv(C.RESULTS / "execution_valid.csv", index=False)
    sig = val[val.theta.notna()]
    chosen = {int(W): sig[sig.window_s == W].sort_values("cost_bp").iloc[0][["theta", "horizon_s"]]
              .to_dict() for W in WINDOWS_S}
    print("selected on validation:", chosen, flush=True)

    summary, orders = [], []
    rng = np.random.default_rng(11)
    for W in WINDOWS_S:
        th, h = chosen[W]["theta"], int(chosen[W]["horizon_s"])
        imm = pd.concat([run(d, IMMEDIATE, W) for d in C.TEST])
        pas = pd.concat([run(d, PASSIVE, W) for d in C.TEST])
        sgn = pd.concat([run(d, SIGNAL, W, th, h) for d in C.TEST])
        plc = []
        for d in C.TEST:
            p = day_arrays(d)["pred"][h]
            plc.append(run(d, SIGNAL, W, th, h, pred=p * rng.choice([-1.0, 1.0], size=len(p))))
        plc = pd.concat(plc)
        for name, df in [("immediate", imm), ("passive", pas), ("signal-aware", sgn),
                         ("placebo (random-sign signal)", plc)]:
            summary.append({"window_s": W, "policy": name, "orders": len(df),
                            "cost_bp": df.cost_bp.mean(), "slippage_bp": df.slip_bp.mean(),
                            "passive_fill_rate": 1 - df.taker.mean(), "avg_wait_s": df.wait_s.mean(),
                            "theta": th if name.startswith(("signal", "placebo")) else np.nan,
                            "horizon_s": h if name.startswith(("signal", "placebo")) else np.nan})
        for ref_name, ref in [("passive", pas), ("immediate", imm)]:
            summary.append({"window_s": W, "policy": f"signal-aware minus {ref_name}",
                            **paired(sgn, ref)})
        summary.append({"window_s": W, "policy": "placebo minus passive", **paired(plc, pas)})
        orders.append(pd.concat([imm.assign(policy="immediate"), pas.assign(policy="passive"),
                                 sgn.assign(policy="signal-aware")]).assign(window_s=W))

    W = 30
    th, h = chosen[W]["theta"], int(chosen[W]["horizon_s"])
    for lat in (10, 50, 200, 500):
        pas = pd.concat([run(d, PASSIVE, W, lat_ms=lat) for d in C.TEST])
        sgn = pd.concat([run(d, SIGNAL, W, th, h, lat_ms=lat) for d in C.TEST])
        summary.append({"window_s": W, "policy": f"latency {lat} ms: signal-aware minus passive",
                        "lat_ms": lat, **paired(sgn, pas)})

    res = pd.DataFrame(summary)
    res.to_csv(C.RESULTS / "execution_test.csv", index=False)
    pd.concat(orders).to_parquet(C.RESULTS / "execution_orders.parquet", index=False)
    (C.RESULTS / "execution_selection.json").write_text(json.dumps(chosen, indent=1))
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(res.round(3).to_string())


if __name__ == "__main__":
    main()
