"""Parallel parameter sweep for both execution styles, with a clean
validation -> test protocol.

1. Every configuration is run on the validation days (multiprocessing pool).
2. One configuration per style is selected on validation PnL.
3. Only the selected configurations are run on the test days, plus a latency
   sweep and a random-direction baseline for the maker strategy.
"""
import argparse
import itertools
import json
import os
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

from . import config as C
from .engine import ENTRY_PX, ENTRY_T, EXIT_T, EXIT_TAKER, run_maker, run_taker, trade_pnl_bp
from .research import load as load_features, predict

TAKER_GRID = [dict(style="taker", theta=th, horizon_s=h, lat_ms=lat)
              for th, h, lat in itertools.product([0.25, 0.5, 0.75, 1.0, 1.5, 2.0],
                                                  C.HORIZONS_S, [10, 50, 200])]
MAKER_GRID = [dict(style="maker", theta=th, horizon_s=h, max_hold_s=mh, stop_ticks=st, lat_ms=lat)
              for th, h, mh, st, lat in itertools.product([0.1, 0.2, 0.3, 0.5, 0.75], [2, 5, 10, 30],
                                                          [5, 30, 120], [2, 4], [10, 50, 200])]

_cache: dict = {}


def day_arrays(day: str) -> dict:
    if day not in _cache:
        _cache.clear()
        q = pd.read_parquet(C.DATA_PQ / "bookTicker" / f"{day}.parquet")
        tr = pd.read_parquet(C.DATA_PQ / "aggTrades" / f"{day}.parquet")
        f = load_features(day)
        model = json.loads((C.RESULTS / "model.json").read_text())
        _cache[day] = {
            "gt": f.t.to_numpy(np.int64),
            "pred": {h: predict(f, model, h) for h in C.HORIZONS_S},
            "q": (q.t.to_numpy(np.int64), q.bid.to_numpy(np.int64), q.ask.to_numpy(np.int64),
                  q.bq.to_numpy(np.float64), q.aq.to_numpy(np.float64)),
            "tr": (tr.t.to_numpy(np.int64), tr.px.to_numpy(np.int64),
                   tr.qty.to_numpy(np.float64), tr.side.to_numpy(np.int64)),
        }
    return _cache[day]


def run_one(day: str, cfg: dict, pred=None):
    d = day_arrays(day)
    p = d["pred"][cfg["horizon_s"]] if pred is None else pred
    if cfg["style"] == "taker":
        R = run_taker(d["gt"], p, *d["q"], cfg["theta"], cfg["horizon_s"] * 1000,
                      cfg["lat_ms"], C.ORDER_QTY)
        stats = np.array([len(R), 0])
    else:
        R, stats = run_maker(d["gt"], p, *d["q"], *d["tr"], cfg["theta"],
                             cfg["max_hold_s"] * 1000, cfg["stop_ticks"], cfg["lat_ms"], C.ORDER_QTY)
    return R, stats


def summarise(day: str, cfg: dict, R: np.ndarray, stats) -> dict:
    gross, net = trade_pnl_bp(R, C.MAKER_FEE_BP, C.TAKER_FEE_BP)
    notional = R[:, ENTRY_PX] * C.TICK * C.ORDER_QTY
    return {**cfg, "day": day, "trades": len(R),
            "gross_bp": gross.mean() if len(R) else np.nan,
            "net_bp": net.mean() if len(R) else np.nan,
            "pnl_usd": float(np.sum(net / 1e4 * notional)),
            "hit": float(np.mean(net > 0)) if len(R) else np.nan,
            "taker_exit_share": float(np.mean(R[:, EXIT_TAKER] > 0)) if len(R) else np.nan,
            "hold_s": float(np.mean(R[:, EXIT_T] - R[:, ENTRY_T]) / 1000) if len(R) else np.nan,
            "orders_sent": int(stats[0]), "cancels": int(stats[1])}


def _task(args):
    day, cfgs = args
    return [summarise(day, c, *run_one(day, c)) for c in cfgs]


def sweep(days, cfgs, workers: int) -> pd.DataFrame:
    chunks = max(1, workers)
    tasks = [(d, cfgs[i::chunks]) for d in days for i in range(chunks)]
    if workers <= 1:
        rows = [r for t in tasks for r in _task(t)]
    else:
        with Pool(workers) as pool:
            rows = [r for part in pool.imap_unordered(_task, tasks) for r in part]
    return pd.DataFrame(rows)


def select(res: pd.DataFrame, style: str, min_trades: int = 200) -> dict:
    keys = [c for c in res.columns if c in ("theta", "horizon_s", "max_hold_s", "stop_ticks", "lat_ms")]
    s = res[res["style"] == style]
    agg = s.groupby(keys, dropna=False).agg(trades=("trades", "sum"), pnl_usd=("pnl_usd", "sum"))
    agg = agg[agg.trades >= min_trades].sort_values("pnl_usd", ascending=False)
    best = agg.index[0]
    cfg = {"style": style}
    for k, v in zip(keys, best if isinstance(best, tuple) else (best,)):
        v = float(v)
        if not np.isnan(v):
            cfg[k] = int(v) if k in ("horizon_s", "lat_ms", "max_hold_s") else v
    return cfg


def warm_up() -> None:
    """Compile the numba kernels once in the parent so workers load from cache."""
    t = np.arange(0, 1000, 100, dtype=np.int64)
    q = (t, np.full(10, 100, np.int64), np.full(10, 101, np.int64), np.ones(10), np.ones(10))
    tr = (t, np.full(10, 100, np.int64), np.ones(10), -np.ones(10, np.int64))
    run_taker(t, np.zeros(10), *q, 1.0, 100, 10, 1.0)
    run_maker(t, np.zeros(10), *q, *tr, 1.0, 100, 2.0, 10, 1.0)


def main(workers: int, bench: bool) -> None:
    warm_up()
    grid = TAKER_GRID + MAKER_GRID
    timing = {}
    if bench:                                   # same work (one day, full grid), serial vs parallel
        sub = grid
        t0 = time.perf_counter(); sweep(C.VALID[:1], sub, 1); timing["serial_s"] = time.perf_counter() - t0
        t0 = time.perf_counter(); sweep(C.VALID[:1], sub, workers); timing["parallel_s"] = time.perf_counter() - t0
        timing.update(runs=len(sub), workers=workers, speedup=timing["serial_s"] / timing["parallel_s"])
        print(f"benchmark: {len(sub)} runs, serial {timing['serial_s']:.1f}s, "
              f"{workers} workers {timing['parallel_s']:.1f}s, speedup {timing['speedup']:.1f}x", flush=True)
        # single-core replay speed of the maker engine (quotes + trades + decisions)
        d, cfgs = day_arrays(C.VALID[0]), MAKER_GRID[:20]
        events = len(d["q"][0]) + len(d["tr"][0]) + len(d["gt"])
        t0 = time.perf_counter()
        for c in cfgs:
            run_one(C.VALID[0], c)
        per_run = (time.perf_counter() - t0) / len(cfgs)
        timing.update(events_per_run=events, maker_run_s=per_run, events_per_s=events / per_run)
        print(f"maker replay: {events:,} events in {per_run * 1000:.0f} ms "
              f"({events / per_run / 1e6:.0f}M events/s, one core)", flush=True)

    t0 = time.perf_counter()
    val = sweep(C.VALID, grid, workers)
    timing.update(full_sweep_runs=len(val), full_sweep_s=time.perf_counter() - t0)
    val.to_csv(C.RESULTS / "sweep_valid.csv", index=False)
    print(f"validation sweep: {len(val)} runs in {timing['full_sweep_s']:.1f}s", flush=True)

    chosen = {s: select(val, s) for s in ("taker", "maker")}
    print("selected on validation:", chosen, flush=True)

    test_rows, trades = [], []
    for style, cfg in chosen.items():
        for day in C.TEST:
            R, st = run_one(day, cfg)
            test_rows.append({**summarise(day, cfg, R, st), "variant": "selected"})
            t = pd.DataFrame(R, columns=["entry_t", "exit_t", "side", "entry_px", "exit_px",
                                         "entry_taker", "exit_taker", "reason"])
            trades.append(t.assign(style=style, day=day))
    mk = chosen["maker"]
    rng = np.random.default_rng(7)
    for day in C.TEST:
        for lat in (1, 10, 50, 100, 200, 500):
            cfg = {**mk, "lat_ms": lat}
            test_rows.append({**summarise(day, cfg, *run_one(day, cfg)), "variant": "latency"})
        p = day_arrays(day)["pred"][mk["horizon_s"]]
        rand = np.abs(p) * rng.choice([-1.0, 1.0], size=len(p))
        test_rows.append({**summarise(day, mk, *run_one(day, mk, pred=rand)), "variant": "random sign"})
    pd.DataFrame(test_rows).to_csv(C.RESULTS / "test_results.csv", index=False)
    pd.concat(trades).to_parquet(C.RESULTS / "test_trades.parquet", index=False)
    (C.RESULTS / "selection.json").write_text(json.dumps({"chosen": chosen, "timing": timing}, indent=1))
    print(pd.DataFrame(test_rows).groupby(["style", "variant", "lat_ms"])
          [["trades", "gross_bp", "net_bp", "pnl_usd"]].agg({"trades": "sum", "gross_bp": "mean",
                                                             "net_bp": "mean", "pnl_usd": "sum"})
          .round(3).to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--bench", action="store_true")
    a = ap.parse_args()
    main(a.workers, a.bench)
