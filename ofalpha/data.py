"""Download Binance public tick data, verify checksums, and store compact Parquet.

Quotes  (bookTicker): every best-bid / best-ask change.
Trades  (aggTrades) : every aggressive order, with the aggressor side.

Prices are stored as integer ticks so that equality tests in the matching
engine are exact.
"""
import argparse
import hashlib
import io
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from . import config as C

BASE = "https://data.binance.vision/data/futures/um/daily"

QUOTE_COLS = ["update_id", "best_bid_price", "best_bid_qty", "best_ask_price",
              "best_ask_qty", "transaction_time", "event_time"]
TRADE_COLS = ["agg_trade_id", "price", "quantity", "first_trade_id",
              "last_trade_id", "transact_time", "is_buyer_maker"]


def _url(kind: str, day: str) -> str:
    return f"{BASE}/{kind}/{C.SYMBOL}/{C.SYMBOL}-{kind}-{day}.zip"


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ofalpha-research"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def _read_csv(blob: bytes, cols: list[str]) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        raw = z.read(z.namelist()[0])
    has_header = not raw[:1].isdigit()
    return pd.read_csv(io.BytesIO(raw), header=0 if has_header else None,
                       names=cols, engine="pyarrow")


def _to_ticks(px: pd.Series) -> np.ndarray:
    return np.rint(px.to_numpy(np.float64) / C.TICK).astype(np.int32)


def fetch_day(kind: str, day: str) -> str:
    out = C.DATA_PQ / kind / f"{day}.parquet"
    if out.exists():
        return f"{kind} {day}: cached"
    url = _url(kind, day)
    blob = _fetch(url)
    expected = _fetch(url + ".CHECKSUM").decode().split()[0]
    if hashlib.sha256(blob).hexdigest() != expected:
        raise IOError(f"checksum mismatch for {url}")

    if kind == "bookTicker":
        df = _read_csv(blob, QUOTE_COLS).sort_values(["transaction_time", "update_id"])
        df = pd.DataFrame({
            "t": df.transaction_time.to_numpy(np.int64),
            "bid": _to_ticks(df.best_bid_price), "bq": df.best_bid_qty.to_numpy(np.float64),
            "ask": _to_ticks(df.best_ask_price), "aq": df.best_ask_qty.to_numpy(np.float64),
        })
        # drop consecutive duplicates (same book state re-published)
        same = (df[["bid", "bq", "ask", "aq"]].diff().abs().sum(axis=1) == 0)
        df = df[~same].reset_index(drop=True)
    else:
        df = _read_csv(blob, TRADE_COLS).sort_values("agg_trade_id")
        # is_buyer_maker=True means the seller was the aggressor (hit the bid)
        side = np.where(df.is_buyer_maker.astype(bool).to_numpy(), -1, 1).astype(np.int8)
        df = pd.DataFrame({
            "t": df.transact_time.to_numpy(np.int64), "px": _to_ticks(df.price),
            "qty": df.quantity.to_numpy(np.float64), "side": side,
        })

    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return f"{kind} {day}: {len(df):,} rows, {len(blob) / 1e6:.0f} MB zipped"


def main(days: list[str], workers: int = 4) -> None:
    jobs = [(k, d) for d in days for k in ("bookTicker", "aggTrades")]
    with ThreadPoolExecutor(workers) as pool:
        for msg in pool.map(lambda j: fetch_day(*j), jobs):
            print(msg, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workers", type=int, default=4)
    main(C.DATES, ap.parse_args().workers)
