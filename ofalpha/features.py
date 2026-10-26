"""Point-in-time features and forward targets on a fixed 100 ms clock.

Every feature at grid time g uses only quotes/trades with timestamp <= g.
Targets are forward mid-price changes in ticks, mid(g + h) - mid(g).

Features
  qi        L1 queue imbalance (bq - aq) / (bq + aq)
  ofi_w     order-flow imbalance (Cont, Kukanov & Stoikov 2014) summed over the
            last w seconds, scaled by current L1 depth
  tfi_w     trade-flow imbalance: signed aggressor volume / total volume, last w s
  ret_w     mid-price change over the last w seconds, in ticks
"""
import numpy as np
import pandas as pd

from . import config as C

FEATURES = ["qi"] + [f"ofi_{w}" for w in C.WINDOWS_S] + \
           [f"tfi_{w}" for w in C.WINDOWS_S] + ["ret_5", "ret_30"]
TARGETS = [f"fwd_{h}" for h in C.HORIZONS_S]


def load_day(day: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    q = pd.read_parquet(C.DATA_PQ / "bookTicker" / f"{day}.parquet")
    tr = pd.read_parquet(C.DATA_PQ / "aggTrades" / f"{day}.parquet")
    return q, tr


def ofi_increments(bid, bq, ask, aq) -> np.ndarray:
    """Per-update order-flow imbalance e_n at the best quotes."""
    e = np.zeros(len(bid))
    b0, b1, a0, a1 = bid[:-1], bid[1:], ask[:-1], ask[1:]
    e[1:] = ((b1 >= b0) * bq[1:] - (b1 <= b0) * bq[:-1]
             - (a1 <= a0) * aq[1:] + (a1 >= a0) * aq[:-1])
    return e


def build_day(day: str) -> pd.DataFrame:
    q, tr = load_day(day)
    t0 = int(pd.Timestamp(day, tz="UTC").timestamp() * 1000)
    warm, tail = max(C.WINDOWS_S + [30]) * 1000, max(C.HORIZONS_S) * 1000
    g = np.arange(t0 + warm, t0 + 86_400_000 - tail, C.GRID_MS, dtype=np.int64)

    qt = q.t.to_numpy()
    bid, ask = q.bid.to_numpy(np.int64), q.ask.to_numpy(np.int64)
    bq, aq = q.bq.to_numpy(), q.aq.to_numpy()
    mid2 = bid + ask                                    # twice the mid, in ticks

    def asof(times):                                    # last quote with t <= time
        return np.searchsorted(qt, times, side="right") - 1

    iq = asof(g)
    out = {"t": g, "bid": bid[iq].astype(np.int32), "ask": ask[iq].astype(np.int32),
           "bq": bq[iq].astype(np.float32), "aq": aq[iq].astype(np.float32)}
    depth = (bq[iq] + aq[iq]) / 2
    out["qi"] = (bq[iq] - aq[iq]) / (bq[iq] + aq[iq])

    cum_e = np.cumsum(ofi_increments(bid, bq, ask, aq))
    tt = tr.t.to_numpy()
    cum_s = np.cumsum(tr.qty.to_numpy() * tr.side.to_numpy())
    cum_v = np.cumsum(tr.qty.to_numpy())
    it = np.searchsorted(tt, g, side="right") - 1
    for w in C.WINDOWS_S:
        ofi = cum_e[iq] - cum_e[asof(g - w * 1000)]
        out[f"ofi_{w}"] = ofi / depth
        jw = np.searchsorted(tt, g - w * 1000, side="right") - 1
        sv, vv = cum_s[it] - cum_s[jw], cum_v[it] - cum_v[jw]
        out[f"tfi_{w}"] = np.divide(sv, vv, out=np.zeros_like(sv), where=vv > 0)
    for w in (5, 30):
        out[f"ret_{w}"] = (mid2[iq] - mid2[asof(g - w * 1000)]) / 2
    for h in C.HORIZONS_S:
        out[f"fwd_{h}"] = (mid2[asof(g + h * 1000)] - mid2[iq]) / 2

    df = pd.DataFrame(out)
    for c in FEATURES + TARGETS:
        df[c] = df[c].astype(np.float32)
    return df


def main() -> None:
    C.FEATURES.mkdir(parents=True, exist_ok=True)
    for day in C.DATES:
        df = build_day(day)
        df.to_parquet(C.FEATURES / f"{day}.parquet", index=False)
        spread = (df.ask - df.bid)
        print(f"{day}: {len(df):,} grid points, spread=1 tick {np.mean(spread == 1):.1%}, "
              f"mean L1 depth {((df.bq + df.aq) / 2).mean():,.0f}", flush=True)


if __name__ == "__main__":
    main()
