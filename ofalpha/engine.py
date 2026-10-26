"""Event-driven tick replay with an order-matching simulator (numba-compiled).

Two execution styles are simulated against the recorded Binance tape:

run_taker  crosses the spread when the forecast exceeds a threshold, holds for
           a fixed time, then crosses back. Orders reach the exchange after a
           latency; fills use the best quote at arrival, with one extra tick on
           any size beyond the displayed L1 quantity.

run_maker  joins the best bid/ask on the forecast side and exits with a passive
           order one spread away, with a time stop, a price stop and a
           signal-flip exit (the last three exit with market orders).
           Queue position follows the "risk-averse" model: on arrival we sit
           behind the displayed size; the queue ahead shrinks only through
           trades at our price, or when the displayed size falls below our
           position (cancellations are assumed to come from behind us first).
           A trade through our price, or the opposite quote reaching our
           price, fills us.

Prices are integer ticks; times are epoch milliseconds.
"""
import numpy as np
from numba import njit

# columns of the trade record returned by both engines
ENTRY_T, EXIT_T, SIDE, ENTRY_PX, EXIT_PX, ENTRY_TAKER, EXIT_TAKER, REASON = range(8)
N_COLS = 8
# exit reasons
TARGET, TIMEOUT, STOP, FLIP, EOD, HOLD = 0, 1, 2, 3, 4, 5
REASONS = {TARGET: "target", TIMEOUT: "timeout", STOP: "stop", FLIP: "signal flip",
           EOD: "end of data", HOLD: "holding period"}


@njit(cache=True)
def _asof(times, t):
    return np.searchsorted(times, t, side="right") - 1


@njit(cache=True)
def run_taker(gt, pred, qt, bid, ask, bq, aq, theta, hold_ms, lat_ms, qty):
    R = np.empty((len(gt), N_COLS))
    m = 0
    free_at = gt[0]
    t_last = qt[-1]
    for k in range(len(gt)):
        if gt[k] < free_at or abs(pred[k]) < theta:
            continue
        d = 1 if pred[k] > 0 else -1
        t_in = gt[k] + lat_ms
        t_out = t_in + hold_ms + lat_ms
        if t_out > t_last:
            break
        i, j = _asof(qt, t_in), _asof(qt, t_out)
        if d > 0:
            px_in = ask[i] + max(0.0, qty - aq[i]) / qty
            px_out = bid[j] - max(0.0, qty - bq[j]) / qty
        else:
            px_in = bid[i] - max(0.0, qty - bq[i]) / qty
            px_out = ask[j] + max(0.0, qty - aq[j]) / qty
        R[m, ENTRY_T], R[m, EXIT_T], R[m, SIDE] = t_in, t_out, d
        R[m, ENTRY_PX], R[m, EXIT_PX] = px_in, px_out
        R[m, ENTRY_TAKER], R[m, EXIT_TAKER], R[m, REASON] = 1, 1, HOLD
        m += 1
        free_at = t_out
    return R[:m]


@njit(cache=True)
def run_maker(gt, pred, qt, bid, ask, bq, aq, tt, tpx, tqty, tside,
              theta, max_hold_ms, stop_ticks, lat_ms, qty):
    NQ, NT, NG = len(qt), len(tt), len(gt)
    INF = np.int64(2 ** 62)
    BIG = 1e18
    R = np.empty((NG, N_COLS))
    m = 0
    b, a, bqq, aqq = 0, 0, 0.0, 0.0                  # current best quotes
    pos, entry_px, entry_t, entry_taker = 0, 0.0, np.int64(0), 0
    # working limit order: state 0 none, 1 in flight, 2 resting
    o_state, o_side, o_px, o_queue = 0, 0, 0, 0.0
    o_act_t, o_cancel_t = INF, INF
    mk_t, mk_reason = INF, 0                          # pending market exit
    n_sent, n_cancel = 0, 0
    i = j = k = 0

    while True:
        # next event; ties resolve market < cancel < activation < trade < quote < decision
        best = INF
        ev = -1
        cand = (mk_t, o_cancel_t if o_state > 0 else INF,
                o_act_t if o_state == 1 else INF,
                tt[j] if j < NT else INF, qt[i] if i < NQ else INF,
                gt[k] if k < NG else INF)
        for e in range(6):
            if cand[e] < best:
                best, ev = cand[e], e
        if ev < 0:
            break
        T = best
        fill, fill_px, fill_taker = False, 0.0, 0

        if ev == 0:                                   # market exit arrives
            mk_t = INF
            if pos != 0:
                if pos > 0:
                    px = b - max(0.0, qty - bqq) / qty
                else:
                    px = a + max(0.0, qty - aqq) / qty
                R[m, ENTRY_T], R[m, EXIT_T], R[m, SIDE] = entry_t, T, pos
                R[m, ENTRY_PX], R[m, EXIT_PX] = entry_px, px
                R[m, ENTRY_TAKER], R[m, EXIT_TAKER], R[m, REASON] = entry_taker, 1, mk_reason
                m += 1
                pos = 0
                o_state, o_cancel_t = 0, INF          # cancel of the exit order lands too

        elif ev == 1:                                 # cancel lands
            o_state, o_cancel_t = 0, INF
            n_cancel += 1

        elif ev == 2:                                 # limit order reaches the book
            o_state = 2
            if o_side > 0:
                if o_px >= a:
                    fill, fill_px, fill_taker = True, float(a), 1
                elif o_px == b:
                    o_queue = bqq
                elif o_px > b:
                    o_queue = 0.0
                else:
                    o_queue = BIG                     # deeper level, size unseen
            else:
                if o_px <= b:
                    fill, fill_px, fill_taker = True, float(b), 1
                elif o_px == a:
                    o_queue = aqq
                elif o_px < a:
                    o_queue = 0.0
                else:
                    o_queue = BIG

        elif ev == 3:                                 # trade print
            px, qv, sd = tpx[j], tqty[j], tside[j]
            j += 1
            if o_state == 2 and sd == -o_side:        # aggressor on the other side
                if (o_side > 0 and px < o_px) or (o_side < 0 and px > o_px):
                    fill, fill_px = True, float(o_px)
                elif px == o_px:
                    o_queue -= qv
                    if o_queue + qty <= 0.0:
                        fill, fill_px = True, float(o_px)

        elif ev == 4:                                 # quote update
            b, a, bqq, aqq = bid[i], ask[i], bq[i], aq[i]
            i += 1
            if o_state == 2:
                if o_side > 0:
                    if a <= o_px:
                        fill, fill_px = True, float(o_px)
                    elif o_px == b:
                        o_queue = min(o_queue, bqq)
                    elif o_px > b:
                        o_queue = min(o_queue, 0.0)
                else:
                    if b >= o_px:
                        fill, fill_px = True, float(o_px)
                    elif o_px == a:
                        o_queue = min(o_queue, aqq)
                    elif o_px < a:
                        o_queue = min(o_queue, 0.0)
            if pos != 0 and mk_t == INF and not fill:
                adverse = entry_px - b if pos > 0 else a - entry_px
                if adverse >= stop_ticks:
                    mk_t, mk_reason = T + lat_ms, STOP
                    if o_state > 0:
                        o_cancel_t = T + lat_ms

        else:                                         # decision on the 100 ms clock
            p = pred[k]
            k += 1
            if b == 0:
                continue
            if pos == 0:
                if o_state == 0:
                    if p > theta or p < -theta:
                        o_side = 1 if p > 0 else -1
                        o_px = b if o_side > 0 else a
                        o_state, o_act_t, o_cancel_t = 1, T + lat_ms, INF
                        n_sent += 1
                elif o_cancel_t == INF:
                    faded = o_side * p < theta / 2
                    left_behind = (o_side > 0 and b > o_px) or (o_side < 0 and a < o_px)
                    if faded or left_behind:
                        o_cancel_t = T + lat_ms
            elif mk_t == INF:
                if T - entry_t >= max_hold_ms or pos * p < -theta:
                    mk_t = T + lat_ms
                    mk_reason = TIMEOUT if T - entry_t >= max_hold_ms else FLIP
                    if o_state > 0:
                        o_cancel_t = T + lat_ms
                elif o_state == 0:                    # passive exit one spread away
                    o_side = -pos
                    o_px = a if pos > 0 else b
                    o_state, o_act_t, o_cancel_t = 1, T + lat_ms, INF
                    n_sent += 1

        if fill:
            o_state, o_cancel_t = 0, INF
            if pos == 0:
                pos, entry_px, entry_t, entry_taker = o_side, fill_px, T, fill_taker
            else:
                R[m, ENTRY_T], R[m, EXIT_T], R[m, SIDE] = entry_t, T, pos
                R[m, ENTRY_PX], R[m, EXIT_PX] = entry_px, fill_px
                R[m, ENTRY_TAKER], R[m, EXIT_TAKER], R[m, REASON] = entry_taker, fill_taker, TARGET
                m += 1
                pos = 0

    if pos != 0:                                      # flatten at the last quote
        px = b if pos > 0 else a
        R[m, ENTRY_T], R[m, EXIT_T], R[m, SIDE] = entry_t, qt[NQ - 1], pos
        R[m, ENTRY_PX], R[m, EXIT_PX] = entry_px, px
        R[m, ENTRY_TAKER], R[m, EXIT_TAKER], R[m, REASON] = entry_taker, 1, EOD
        m += 1
    stats = np.array([n_sent, n_cancel], dtype=np.int64)
    return R[:m], stats


IMMEDIATE, PASSIVE, SIGNAL = 0, 1, 2
POLICIES = {IMMEDIATE: "immediate (market)", PASSIVE: "passive, cross at deadline",
            SIGNAL: "signal-aware"}


@njit(cache=True)
def run_execution(pt, ps, gt, pred, qt, bid, ask, bq, aq, tt, tpx, tqty, tside,
                  policy, theta, window_ms, lat_ms, qty):
    """Execute one child order per parent (time pt[n], side ps[n] = +1 buy / -1 sell).

    IMMEDIATE  market order on arrival.
    PASSIVE    join the near touch; if unfilled at the deadline, cancel and cross.
    SIGNAL     cross at once when the forecast says the price is about to move
               against us (side * pred > theta); otherwise rest passively and
               cross early if that condition appears while waiting.

    Returns per parent: [arrival_mid, fill_px, taker, fill_t] (prices in ticks).
    """
    NQ, NT, NG = len(qt), len(tt), len(gt)
    INF = np.int64(2 ** 62)
    BIG = 1e18
    out = np.empty((len(pt), 4))
    for n in range(len(pt)):
        t0, s = pt[n], ps[n]
        i0 = _asof(qt, t0)
        mid0 = (bid[i0] + ask[i0]) / 2.0
        g0 = _asof(gt, t0)
        cross_t = np.int64(-1)                        # time a market order arrives
        if policy == IMMEDIATE or (policy == SIGNAL and s * pred[g0] > theta):
            cross_t = t0 + lat_ms
        filled, fill_px, fill_t = False, 0.0, np.int64(0)
        if cross_t < 0:
            o_px = bid[i0] if s > 0 else ask[i0]
            t_act = t0 + lat_ms
            deadline = t0 + window_ms
            cancel_t = deadline + lat_ms
            ia = _asof(qt, t_act - 1)
            b, a, bqq, aqq = bid[ia], ask[ia], bq[ia], aq[ia]
            if (s > 0 and o_px >= a) or (s < 0 and o_px <= b):
                cross_t = t_act                       # book moved through us
            else:
                if s > 0:
                    queue = bqq if o_px == b else (0.0 if o_px > b else BIG)
                else:
                    queue = aqq if o_px == a else (0.0 if o_px < a else BIG)
                i = ia + 1
                j = np.searchsorted(tt, t_act, side="left")
                k = np.searchsorted(gt, t0, side="right")
                while True:
                    tq_ = qt[i] if i < NQ else INF
                    ttr = tt[j] if j < NT else INF
                    tg = gt[k] if (policy == SIGNAL and k < NG) else INF
                    T = min(tq_, ttr, tg)
                    if T >= cancel_t or T == INF:
                        cross_t = cancel_t
                        break
                    if ttr == T:                      # trades first on ties
                        px, qv, sd = tpx[j], tqty[j], tside[j]
                        j += 1
                        if sd == -s:
                            if (s > 0 and px < o_px) or (s < 0 and px > o_px):
                                filled = True
                            elif px == o_px:
                                queue -= qv
                                filled = queue + qty <= 0.0
                    elif tq_ == T:
                        b, a, bqq, aqq = bid[i], ask[i], bq[i], aq[i]
                        i += 1
                        if s > 0:
                            if a <= o_px:
                                filled = True
                            elif o_px == b:
                                queue = min(queue, bqq)
                            elif o_px > b:
                                queue = min(queue, 0.0)
                        else:
                            if b >= o_px:
                                filled = True
                            elif o_px == a:
                                queue = min(queue, aqq)
                            elif o_px < a:
                                queue = min(queue, 0.0)
                    else:
                        k += 1
                        if T > t0 and s * pred[k - 1] > theta and T + lat_ms < cancel_t:
                            cancel_t = T + lat_ms     # pull the order and cross early
                    if filled:
                        fill_px, fill_t = float(o_px), T
                        break
        if not filled:
            ic = _asof(qt, cross_t)
            if s > 0:
                fill_px = ask[ic] + max(0.0, qty - aq[ic]) / qty
            else:
                fill_px = bid[ic] - max(0.0, qty - bq[ic]) / qty
            fill_t = cross_t
        out[n, 0], out[n, 1], out[n, 2], out[n, 3] = mid0, fill_px, 0.0 if filled else 1.0, fill_t
    return out


def trade_pnl_bp(R: np.ndarray, maker_bp: float, taker_bp: float) -> tuple[np.ndarray, np.ndarray]:
    """Gross and net PnL per round trip, in basis points of entry price."""
    gross = R[:, SIDE] * (R[:, EXIT_PX] - R[:, ENTRY_PX]) / R[:, ENTRY_PX] * 1e4
    fees = np.where(R[:, ENTRY_TAKER] > 0, taker_bp, maker_bp) + \
        np.where(R[:, EXIT_TAKER] > 0, taker_bp, maker_bp)
    return gross, gross - fees
