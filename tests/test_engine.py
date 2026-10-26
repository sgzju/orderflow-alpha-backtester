"""Hand-built scenarios with known answers for the matching engine."""
import numpy as np
import pytest

from ofalpha.engine import (ENTRY_PX, ENTRY_T, EXIT_PX, EXIT_TAKER, IMMEDIATE, PASSIVE,
                            REASON, SIGNAL, STOP, TARGET, TIMEOUT, run_execution,
                            run_maker, run_taker)

I64 = np.int64


def quotes(rows):
    """rows of (t, bid, bq, ask, aq) -> engine arrays."""
    r = np.array(rows, dtype=float)
    return (r[:, 0].astype(I64), r[:, 1].astype(I64), r[:, 3].astype(I64),
            r[:, 2].copy(), r[:, 4].copy())


def trades(rows):
    """rows of (t, px, qty, side) with side +1 aggressive buy, -1 aggressive sell."""
    if not rows:
        return (np.zeros(0, I64), np.zeros(0, I64), np.zeros(0), np.zeros(0, I64))
    r = np.array(rows, dtype=float)
    return r[:, 0].astype(I64), r[:, 1].astype(I64), r[:, 2].copy(), r[:, 3].astype(I64)


def maker(q, tr, pred=1.0, end=5_000, theta=0.5, hold=10**9, stop=100.0, lat=10, qty=100.0):
    gt = np.arange(0, end, 100, dtype=I64)
    p = np.full(len(gt), pred) if np.isscalar(pred) else pred
    qt, bid, ask, bq, aq = q
    R, _ = run_maker(gt, p, qt, bid, ask, bq, aq, *tr, theta, hold, stop, lat, qty)
    return R


def test_taker_round_trip_pays_the_spread():
    q = quotes([(0, 100, 1e6, 101, 1e6), (10_000, 100, 1e6, 101, 1e6)])
    gt = np.arange(0, 5_000, 100, dtype=I64)
    R = run_taker(gt, np.ones(len(gt)), *q, 0.5, 1_000, 10, 100.0)
    assert len(R) == 5                       # decisions at 0, 1100, 2200, 3300, 4400
    assert np.all(R[:, ENTRY_PX] == 101) and np.all(R[:, EXIT_PX] == 100)


def test_taker_slippage_beyond_displayed_size():
    q = quotes([(0, 100, 50.0, 101, 50.0), (10_000, 100, 50.0, 101, 50.0)])
    gt = np.array([0], dtype=I64)
    R = run_taker(gt, np.ones(1), *q, 0.5, 1_000, 10, 100.0)
    assert R[0, ENTRY_PX] == pytest.approx(101.5)   # half the size one tick worse
    assert R[0, EXIT_PX] == pytest.approx(99.5)


def test_maker_fills_only_after_queue_ahead_trades():
    q = quotes([(0, 100, 500.0, 101, 500.0)])
    tr = trades([(20, 100, 300, -1), (30, 100, 300, -1), (200, 101, 600, 1)])
    R = maker(q, tr)
    assert len(R) == 1
    assert R[0, ENTRY_T] == 30                # 500 ahead + our 100 cleared at t=30
    assert R[0, ENTRY_PX] == 100 and R[0, EXIT_PX] == 101
    assert R[0, REASON] == TARGET and R[0, EXIT_TAKER] == 0


def test_maker_no_fill_while_queue_ahead_remains():
    q = quotes([(0, 100, 500.0, 101, 500.0)])
    R = maker(q, trades([(30, 100, 150, -1)]))
    assert len(R) == 0


def test_displayed_size_drop_moves_us_forward():
    q = quotes([(0, 100, 500.0, 101, 500.0), (20, 100, 50.0, 101, 500.0)])
    R = maker(q, trades([(30, 100, 150, -1)]), hold=1_000)
    assert len(R) == 1 and R[0, ENTRY_T] == 30


def test_trade_through_fills():
    q = quotes([(0, 100, 500.0, 101, 500.0)])
    R = maker(q, trades([(30, 99, 1, -1)]), hold=1_000)
    assert len(R) == 1 and R[0, ENTRY_PX] == 100


def test_timeout_exits_with_market_order():
    q = quotes([(0, 100, 500.0, 101, 500.0)])
    R = maker(q, trades([(30, 99, 1, -1)]), hold=1_000)
    assert R[0, REASON] == TIMEOUT and R[0, EXIT_TAKER] == 1
    assert R[0, EXIT_PX] == 100               # sold at the bid


def test_stop_loss_exits_at_bid():
    q = quotes([(0, 100, 500.0, 101, 500.0), (500, 97, 500.0, 98, 500.0)])
    R = maker(q, trades([(30, 99, 1, -1)]), stop=2.0)
    assert R[0, REASON] == STOP and R[0, EXIT_PX] == 97


def execute(q, tr, policy, pred=0.0, side=1, window=2_000, theta=0.5, lat=10, qty=100.0):
    gt = np.arange(0, 10_000, 100, dtype=I64)
    p = np.full(len(gt), pred) if np.isscalar(pred) else pred
    pt, ps = np.array([0], dtype=I64), np.array([side], dtype=I64)
    return run_execution(pt, ps, gt, p, *q, *tr, policy, theta, window, lat, qty)[0]


BOOK = [(0, 100, 500.0, 101, 500.0), (3_000, 101, 500.0, 102, 500.0)]


def test_execution_immediate_buys_at_ask():
    mid, px, taker, t = execute(quotes(BOOK), trades([]), IMMEDIATE)
    assert (mid, px, taker, t) == (100.5, 101, 1, 10)


def test_execution_passive_fill_through_queue():
    mid, px, taker, t = execute(quotes(BOOK), trades([(500, 100, 600, -1)]), PASSIVE)
    assert (px, taker, t) == (100, 0, 500)


def test_execution_passive_crosses_at_deadline():
    q = quotes([(0, 100, 500.0, 101, 500.0), (1_500, 101, 500.0, 102, 500.0)])
    mid, px, taker, t = execute(q, trades([]), PASSIVE)
    assert (px, taker, t) == (102, 1, 2_010)   # cancel lands at deadline + latency


def test_execution_signal_crosses_at_once_when_price_will_run():
    mid, px, taker, t = execute(quotes(BOOK), trades([]), SIGNAL, pred=1.0)
    assert (px, taker, t) == (101, 1, 10)


def test_execution_signal_crosses_early_while_waiting():
    p = np.zeros(100)
    p[10:] = 1.0                               # forecast turns at t = 1000
    mid, px, taker, t = execute(quotes(BOOK), trades([]), SIGNAL, pred=p)
    assert (px, taker, t) == (101, 1, 1_010)


def test_execution_sell_side_is_symmetric():
    mid, px, taker, t = execute(quotes(BOOK), trades([(500, 101, 600, 1)]), PASSIVE, side=-1)
    assert (px, taker, t) == (101, 0, 500)
