# Results

Symbol XRPUSDT (Binance USD-M perpetual), 2024-02-01 to 2024-02-10. Train 2024-02-01..2024-02-05, validation 2024-02-06..2024-02-07, test 2024-02-08..2024-02-10. Fees: maker 2.0 bp, taker 5.0 bp. Clip size 1,000 contracts.

## 1. Signal: Spearman IC at the 5-second horizon

| feature | train | valid | test |
|---|---|---|---|
| qi | 0.273 | 0.283 | 0.284 |
| ofi_1 | 0.143 | 0.130 | 0.139 |
| ofi_5 | 0.136 | 0.129 | 0.143 |
| ofi_30 | 0.076 | 0.083 | 0.054 |
| tfi_5 | 0.058 | 0.043 | 0.053 |
| tfi_1 | 0.044 | 0.033 | 0.035 |
| ret_5 | 0.037 | 0.019 | 0.026 |
| tfi_30 | 0.037 | 0.042 | 0.017 |
| ret_30 | 0.035 | 0.035 | 0.005 |

## 2. Linear forecast fitted on train days only

R² is out-of-sample against a zero forecast: 1 - Σ(y - ŷ)² / Σy².

| horizon_s | r2_oos train | r2_oos valid | r2_oos test | ic train | ic valid | ic test |
|---|---|---|---|---|---|---|
| 1 | 0.0322 | 0.0180 | 0.0225 | 0.2155 | 0.2063 | 0.2104 |
| 2 | 0.0410 | 0.0277 | 0.0376 | 0.2543 | 0.2500 | 0.2558 |
| 5 | 0.0436 | 0.0387 | 0.0548 | 0.2769 | 0.2836 | 0.2888 |
| 10 | 0.0363 | 0.0384 | 0.0521 | 0.2587 | 0.2751 | 0.2732 |
| 30 | 0.0198 | 0.0191 | 0.0258 | 0.1902 | 0.1915 | 0.1884 |
| 60 | 0.0108 | 0.0079 | 0.0135 | 0.1350 | 0.1189 | 0.1338 |

## 3. Standalone strategies (configuration chosen on validation, run once on test)

Selected: `{"taker": {"style": "taker", "theta": 0.75, "horizon_s": 30, "lat_ms": 10}, "maker": {"style": "maker", "theta": 0.2, "horizon_s": 2, "lat_ms": 10, "max_hold_s": 120, "stop_ticks": 4.0}}`

| style | variant | trades | gross_bp | net_bp | pnl_usd | hit |
|---|---|---|---|---|---|---|
| maker | random sign | 2155 | -1.952 | -8.257 | -923.129 | 0.000 |
| maker | selected | 326 | -1.554 | -6.914 | -119.471 | 0.002 |
| taker | selected | 815 | -0.559 | -10.559 | -448.637 | 0.020 |

Maker strategy on test days by exit reason:

| exit reason | trades | share | gross_bp | net_bp |
|---|---|---|---|---|
| target | 185 | 0.567 | 0.157 | -4.005 |
| timeout | 3 | 0.009 | -4.491 | -11.491 |
| stop | 31 | 0.095 | -8.701 | -15.895 |
| signal flip | 106 | 0.325 | -2.631 | -9.688 |
| end of data | 1 | 0.003 | -1.944 | -8.944 |

Maker strategy latency sensitivity (test days):

| lat_ms | trades | gross_bp | net_bp |
|---|---|---|---|
| 1 | 321 | -1.618 | -6.893 |
| 10 | 326 | -1.554 | -6.914 |
| 50 | 344 | -1.681 | -7.325 |
| 100 | 356 | -1.739 | -7.556 |
| 200 | 374 | -1.755 | -7.785 |
| 500 | 436 | -1.983 | -8.239 |

## 4. Execution-cost study (test days)

| window_s | policy | cost_bp | slippage_bp | passive_fill_rate | avg_wait_s | theta | horizon_s |
|---|---|---|---|---|---|---|---|
| 5 | immediate | 5.962 | 0.962 | 0.000 | 0.050 |  |  |
| 5 | passive | 5.592 | 1.007 | 0.138 | 4.664 |  |  |
| 5 | signal-aware | 5.465 | 0.837 | 0.124 | 3.342 | 0.200 | 5.000 |
| 5 | placebo (random-sign signal) | 5.828 | 0.979 | 0.051 | 2.481 | 0.200 | 5.000 |
| 10 | immediate | 5.962 | 0.962 | 0.000 | 0.050 |  |  |
| 10 | passive | 5.311 | 1.027 | 0.239 | 8.696 |  |  |
| 10 | signal-aware | 5.158 | 0.759 | 0.201 | 5.647 | 0.200 | 5.000 |
| 10 | placebo (random-sign signal) | 5.763 | 0.987 | 0.075 | 3.895 | 0.200 | 5.000 |
| 30 | immediate | 5.962 | 0.962 | 0.000 | 0.050 |  |  |
| 30 | passive | 4.672 | 1.060 | 0.463 | 21.361 |  |  |
| 30 | signal-aware | 4.542 | 0.724 | 0.394 | 14.749 | 0.500 | 30.000 |
| 30 | placebo (random-sign signal) | 5.270 | 1.022 | 0.251 | 12.565 | 0.500 | 30.000 |
| 60 | immediate | 5.962 | 0.962 | 0.000 | 0.050 |  |  |
| 60 | passive | 4.140 | 0.998 | 0.619 | 34.784 |  |  |
| 60 | signal-aware | 4.147 | 0.684 | 0.512 | 22.172 | 0.200 | 2.000 |
| 60 | placebo (random-sign signal) | 4.882 | 0.998 | 0.372 | 19.698 | 0.200 | 2.000 |

Paired differences (negative = cheaper), standard errors from 5-minute blocks:

| window_s | policy | diff_bp | se_bp | t_stat |
|---|---|---|---|---|
| 5 | signal-aware minus passive | -0.126 | 0.007 | -18.431 |
| 5 | signal-aware minus immediate | -0.497 | 0.014 | -35.009 |
| 5 | placebo minus passive | 0.236 | 0.012 | 19.511 |
| 10 | signal-aware minus passive | -0.153 | 0.010 | -15.328 |
| 10 | signal-aware minus immediate | -0.805 | 0.018 | -45.572 |
| 10 | placebo minus passive | 0.452 | 0.017 | 26.230 |
| 30 | signal-aware minus passive | -0.130 | 0.016 | -7.997 |
| 30 | signal-aware minus immediate | -1.420 | 0.025 | -57.775 |
| 30 | placebo minus passive | 0.598 | 0.022 | 27.091 |
| 60 | signal-aware minus passive | 0.007 | 0.026 | 0.273 |
| 60 | signal-aware minus immediate | -1.815 | 0.029 | -62.691 |
| 60 | placebo minus passive | 0.742 | 0.030 | 24.668 |
| 30 | latency 10 ms: signal-aware minus passive | -0.152 | 0.016 | -9.324 |
| 30 | latency 50 ms: signal-aware minus passive | -0.130 | 0.016 | -7.997 |
| 30 | latency 200 ms: signal-aware minus passive | -0.086 | 0.016 | -5.248 |
| 30 | latency 500 ms: signal-aware minus passive | -0.050 | 0.016 | -3.047 |

Same simulated fills re-priced under other fee tiers (policy parameters not re-selected):

| window_s | tier | immediate | passive | signal-aware | signal minus passive | signal minus immediate |
|---|---|---|---|---|---|---|
| 5 | no fees (pure slippage) | 0.962 | 1.007 | 0.837 | -0.170 | -0.125 |
| 5 | VIP 0 | 5.962 | 5.592 | 5.465 | -0.126 | -0.497 |
| 5 | VIP 4 | 3.962 | 3.730 | 3.589 | -0.141 | -0.373 |
| 5 | VIP 9 | 2.662 | 2.471 | 2.326 | -0.145 | -0.336 |
| 10 | no fees (pure slippage) | 0.962 | 1.027 | 0.759 | -0.267 | -0.203 |
| 10 | VIP 0 | 5.962 | 5.311 | 5.158 | -0.153 | -0.805 |
| 10 | VIP 4 | 3.962 | 3.550 | 3.358 | -0.191 | -0.604 |
| 10 | VIP 9 | 2.662 | 2.321 | 2.118 | -0.203 | -0.544 |
| 30 | no fees (pure slippage) | 0.962 | 1.060 | 0.724 | -0.336 | -0.238 |
| 30 | VIP 0 | 5.962 | 4.672 | 4.542 | -0.130 | -1.420 |
| 30 | VIP 4 | 3.962 | 3.135 | 2.936 | -0.199 | -1.026 |
| 30 | VIP 9 | 2.662 | 1.974 | 1.754 | -0.219 | -0.908 |
| 60 | no fees (pure slippage) | 0.962 | 0.998 | 0.684 | -0.314 | -0.278 |
| 60 | VIP 0 | 5.962 | 4.140 | 4.147 | 0.007 | -1.815 |
| 60 | VIP 4 | 3.962 | 2.759 | 2.659 | -0.100 | -1.303 |
| 60 | VIP 9 | 2.662 | 1.645 | 1.513 | -0.132 | -1.149 |

## 5. Compute

Validation sweep: 936 backtests in 17.3 s.
Benchmark on one day's full grid (468 backtests): serial 10.3 s vs 18 processes 9.5 s (1.1x). At this size, process start-up and data loading dominate, so the compiled engine, not parallelism, provides the speed.
Maker engine: 4,025,047 events per day replayed in 27 ms on one core (148M events/s).
