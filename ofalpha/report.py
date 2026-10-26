"""Figures and results/RESULTS.md from the saved research outputs."""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config as C
from .engine import REASONS, trade_pnl_bp

R = C.RESULTS
INK, MUTED, GRID = "#1f2933", "#6b7785", "#e4e7eb"
PALETTE = ["#2f6db5", "#d9822b", "#2e8b57", "#b8433c", "#7a5ea8", "#8c8c8c", "#c2a33e", "#3aa3a3", "#a3576e"]

plt.rcParams.update({"font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
                     "legend.frameon": False, "figure.dpi": 130})


def md_table(df: pd.DataFrame, floatfmt: str = "{:.3f}") -> str:
    def fmt(v):
        if isinstance(v, (float, np.floating)):
            return "" if np.isnan(v) else floatfmt.format(v)
        return str(v)
    head = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    body = ["| " + " | ".join(fmt(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([head, sep, *body])


def fig_ic(ic: pd.DataFrame, oos: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    tr = ic[ic.split == "train"]
    order = tr[tr.horizon_s == 5].groupby("feature").ic.mean().sort_values(ascending=False).index
    for c, f in zip(PALETTE, order):
        s = tr[tr.feature == f].groupby("horizon_s").ic
        ax.errorbar(s.mean().index, s.mean(), yerr=s.std(), color=c, marker="o", ms=3.5,
                    lw=1.4, capsize=2, label=f)
    m = oos[oos.split == "test"].groupby("horizon_s").ic.mean()
    ax.plot(m.index, m, color=INK, lw=2.6, marker="s", ms=5, label="linear model, test days (OOS)")
    ax.set_xscale("log"); ax.set_xticks(C.HORIZONS_S); ax.set_xticklabels(C.HORIZONS_S)
    ax.set_xlabel("forecast horizon (seconds)"); ax.set_ylabel("Spearman IC")
    ax.set_title("Predictive power by horizon (train days, ±1 sd across days)", loc="left", color=INK)
    ax.legend(fontsize=8, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    fig.tight_layout(); fig.savefig(R / "fig_ic_decay.png"); plt.close(fig)


def fig_deciles(qd: pd.DataFrame, pdec: pd.DataFrame) -> None:
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.8))
    for c, h in zip(PALETTE, (1, 5, 30)):
        a1.plot(qd.decile, qd[f"fwd_{h}"], marker="o", color=c, label=f"{h}s ahead")
        s = pdec[pdec.horizon_s == h]
        a2.plot(s.pred, s.real, marker="o", color=c, label=f"{h}s ahead")
    lim = max(abs(pdec.pred).max(), abs(pdec.real).max()) * 1.1
    a2.plot([-lim, lim], [-lim, lim], color=MUTED, lw=1, ls="--", label="perfect calibration")
    a1.axhline(0, color=MUTED, lw=0.8)
    a1.set_xlabel("queue-imbalance decile (train days)"); a1.set_ylabel("mean mid move (ticks)")
    a1.set_title("Mid-price move by L1 queue imbalance", loc="left", color=INK)
    a2.set_xlabel("forecast (ticks)"); a2.set_ylabel("realised (ticks)")
    a2.set_title("Forecast calibration, test days (deciles)", loc="left", color=INK)
    a1.legend(fontsize=8); a2.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(R / "fig_deciles.png"); plt.close(fig)


def fig_execution(ex: pd.DataFrame) -> None:
    pol = ["immediate", "passive", "signal-aware", "placebo (random-sign signal)"]
    d = ex[ex.policy.isin(pol)].pivot(index="window_s", columns="policy", values="cost_bp")[pol]
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    w = 0.2
    x = np.arange(len(d))
    for n, (c, p) in enumerate(zip([PALETTE[5], PALETTE[0], PALETTE[2], PALETTE[1]], pol)):
        bars = ax.bar(x + (n - 1.5) * w, d[p], w, color=c, label=p)
        ax.bar_label(bars, fmt="%.2f", fontsize=7, color=INK, padding=2)
    ax.set_xticks(x); ax.set_xticklabels([f"{v}s window" for v in d.index])
    ax.set_ylabel("cost vs arrival mid incl. fees (bp)")
    ax.set_title("Execution cost of a USD ~500 child order, test days", loc="left", color=INK)
    ax.set_ylim(0, d.to_numpy().max() * 1.22)
    ax.legend(fontsize=8, ncol=4, loc="upper center")
    fig.tight_layout(); fig.savefig(R / "fig_execution.png"); plt.close(fig)


def fig_strategies(trades: pd.DataFrame) -> pd.DataFrame:
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.8))
    rows = []
    for c, style in zip([PALETTE[3], PALETTE[0]], ["taker", "maker"]):
        t = trades[trades["style"] == style].sort_values("exit_t")
        g, n = trade_pnl_bp(t.to_numpy()[:, :8].astype(float), C.MAKER_FEE_BP, C.TAKER_FEE_BP)
        a1.plot(np.arange(len(n)), np.cumsum(n), color=c, label=f"{style}: net")
        a1.plot(np.arange(len(g)), np.cumsum(g), color=c, ls="--", lw=1, label=f"{style}: gross")
        if style == "maker":
            fees = np.linspace(-1.0, 2.0, 31)
            net = [np.mean(g - np.where(t.entry_taker > 0, C.TAKER_FEE_BP, f)
                           - np.where(t.exit_taker > 0, C.TAKER_FEE_BP, f)) for f in fees]
            a2.plot(fees, net, color=c, marker="o", ms=3)
            a2.axhline(0, color=MUTED, lw=0.8)
            a2.set_xlabel("maker fee (bp, negative = rebate)"); a2.set_ylabel("net PnL per trade (bp)")
            a2.set_title("Passive strategy vs maker fee, test days", loc="left", color=INK)
            for reason, grp in t.groupby("reason"):
                gg, nn = trade_pnl_bp(grp.to_numpy()[:, :8].astype(float), C.MAKER_FEE_BP, C.TAKER_FEE_BP)
                rows.append({"exit reason": REASONS[int(reason)], "trades": len(grp),
                             "share": len(grp) / len(t), "gross_bp": gg.mean(), "net_bp": nn.mean()})
    a1.set_xlabel("trade #"); a1.set_ylabel("cumulative PnL (bp of one clip)")
    a1.set_title("Standalone strategies, test days", loc="left", color=INK)
    a1.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(R / "fig_strategies.png"); plt.close(fig)
    return pd.DataFrame(rows)


# Approximate Binance USD-M fee tiers in early 2024, (maker, taker) in bp.
FEE_TIERS = {"no fees (pure slippage)": (0.0, 0.0), "VIP 0": (2.0, 5.0),
             "VIP 4": (1.0, 3.0), "VIP 9": (0.0, 1.7)}


def fee_sensitivity(orders: pd.DataFrame) -> pd.DataFrame:
    """Re-price the same simulated fills under other fee schedules (no re-selection)."""
    rows = []
    for (W, pol), g in orders.groupby(["window_s", "policy"]):
        for tier, (mk, tk) in FEE_TIERS.items():
            rows.append({"window_s": W, "tier": tier, "policy": pol,
                         "cost_bp": (g.slip_bp + np.where(g.taker > 0, tk, mk)).mean()})
    t = pd.DataFrame(rows).pivot_table(index=["window_s", "tier"], columns="policy", values="cost_bp")
    t["signal minus passive"] = t["signal-aware"] - t["passive"]
    t["signal minus immediate"] = t["signal-aware"] - t["immediate"]
    tier_order = {k: n for n, k in enumerate(FEE_TIERS)}
    t = t.reset_index().sort_values(["window_s", "tier"], key=lambda s: s.map(tier_order) if s.name == "tier" else s)
    return t[["window_s", "tier", "immediate", "passive", "signal-aware",
              "signal minus passive", "signal minus immediate"]]


def main() -> None:
    ic = pd.read_csv(R / "ic_by_day.csv")
    oos = pd.read_csv(R / "model_oos.csv")
    qd = pd.read_csv(R / "qi_deciles.csv")
    pdec = pd.read_csv(R / "pred_deciles.csv")
    test = pd.read_csv(R / "test_results.csv")
    trades = pd.read_parquet(R / "test_trades.parquet")
    sel = json.loads((R / "selection.json").read_text())
    ex = pd.read_csv(R / "execution_test.csv")

    fig_ic(ic, oos)
    fig_deciles(qd, pdec)
    fig_execution(ex)
    reasons = fig_strategies(trades)

    ic_tab = (ic.groupby(["feature", "split"]).ic.mean().unstack()[["train", "valid", "test"]]
              .reset_index())
    ic5 = ic[ic.horizon_s == 5].groupby(["feature", "split"]).ic.mean().unstack()[["train", "valid", "test"]]
    ic5 = ic5.sort_values("train", ascending=False).reset_index()
    oos_tab = (oos.groupby(["horizon_s", "split"])[["r2_oos", "ic"]].mean().unstack("split")
               .reindex(columns=["train", "valid", "test"], level=1))
    oos_tab.columns = [f"{a} {b}" for a, b in oos_tab.columns]
    oos_tab = oos_tab.reset_index()
    strat = (test[test.variant != "latency"].groupby(["style", "variant"])
             .agg(trades=("trades", "sum"), gross_bp=("gross_bp", "mean"), net_bp=("net_bp", "mean"),
                  pnl_usd=("pnl_usd", "sum"), hit=("hit", "mean")).reset_index())
    lat = (test[test.variant == "latency"].groupby("lat_ms")
           .agg(trades=("trades", "sum"), gross_bp=("gross_bp", "mean"), net_bp=("net_bp", "mean"))
           .reset_index())
    ex_cost = ex[ex.cost_bp.notna()][["window_s", "policy", "cost_bp", "slippage_bp",
                                      "passive_fill_rate", "avg_wait_s", "theta", "horizon_s"]]
    ex_diff = ex[ex.diff_bp.notna()][["window_s", "policy", "diff_bp", "se_bp", "t_stat"]]
    fees = fee_sensitivity(pd.read_parquet(R / "execution_orders.parquet"))
    fees.to_csv(R / "execution_fee_tiers.csv", index=False)

    tm = sel["timing"]
    lines = [
        "# Results", "",
        f"Symbol {C.SYMBOL} (Binance USD-M perpetual), {C.DATES[0]} to {C.DATES[-1]}. "
        f"Train {C.TRAIN[0]}..{C.TRAIN[-1]}, validation {C.VALID[0]}..{C.VALID[-1]}, "
        f"test {C.TEST[0]}..{C.TEST[-1]}. Fees: maker {C.MAKER_FEE_BP} bp, taker {C.TAKER_FEE_BP} bp. "
        f"Clip size {C.ORDER_QTY:,.0f} contracts.", "",
        "## 1. Signal: Spearman IC at the 5-second horizon", "", md_table(ic5), "",
        "## 2. Linear forecast fitted on train days only", "",
        "R² is out-of-sample against a zero forecast: 1 - Σ(y - ŷ)² / Σy².", "", md_table(oos_tab, "{:.4f}"), "",
        "## 3. Standalone strategies (configuration chosen on validation, run once on test)", "",
        f"Selected: `{json.dumps(sel['chosen'])}`", "", md_table(strat), "",
        "Maker strategy on test days by exit reason:", "", md_table(reasons), "",
        "Maker strategy latency sensitivity (test days):", "", md_table(lat), "",
        "## 4. Execution-cost study (test days)", "", md_table(ex_cost), "",
        "Paired differences (negative = cheaper), standard errors from 5-minute blocks:", "",
        md_table(ex_diff), "",
        "Same simulated fills re-priced under other fee tiers (policy parameters not re-selected):", "",
        md_table(fees), "",
        "## 5. Compute", "",
        f"Validation sweep: {tm['full_sweep_runs']} backtests in {tm['full_sweep_s']:.1f} s.",
    ]
    if "speedup" in tm:
        lines.append(f"Benchmark on one day's full grid ({tm['runs']} backtests): serial "
                     f"{tm['serial_s']:.1f} s vs {tm['workers']} processes {tm['parallel_s']:.1f} s "
                     f"({tm['speedup']:.1f}x). At this size, process start-up and data loading "
                     f"dominate, so the compiled engine, not parallelism, provides the speed.")
    if "events_per_s" in tm:
        lines.append(f"Maker engine: {tm['events_per_run']:,} events per day replayed in "
                     f"{tm['maker_run_s'] * 1000:.0f} ms on one core "
                     f"({tm['events_per_s'] / 1e6:.0f}M events/s).")
    (R / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print((R / "RESULTS.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
