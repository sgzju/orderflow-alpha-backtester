"""Extra explanatory figures for the tutorial report (docs/figures/*.png)."""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ofalpha import config as C  # noqa: E402

OUT = ROOT / "docs" / "figures"
INK, MUTED, GRID = "#1f2933", "#6b7785", "#e4e7eb"
BLUE, ORANGE, GREEN, RED, GREY = "#2f6db5", "#d9822b", "#2e8b57", "#b8433c", "#8c8c8c"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
                     "legend.frameon": False, "figure.dpi": 150})


def pipeline() -> None:
    steps = [("1  Download", "data.py", "Binance quotes + trades,\nSHA-256 check, Parquet"),
             ("2  Features", "features.py", "100 ms clock, point-in-time\nQI, OFI, TFI, returns"),
             ("3  Research", "research.py", "IC by horizon, deciles,\nOLS fit on train days"),
             ("4  Matching engine", "engine.py", "event replay, latency,\nqueue position, fees"),
             ("5  Strategy sweep", "sweep.py + execution.py", "validation selection,\ntest run once"),
             ("6  Report", "report.py", "figures, tables,\nRESULTS.md")]
    fig, ax = plt.subplots(figsize=(10, 3.3))
    ax.set_xlim(0, 100); ax.set_ylim(0, 34); ax.axis("off")
    w, h = 28, 13
    pos = [(3, 19), (36, 19), (69, 19), (69, 2), (36, 2), (3, 2)]
    for (name, mod, desc), (x, y) in zip(steps, pos):
        accent = name.startswith("4")
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=1.2",
                                    fc="#eaf1fa" if accent else "white", ec=BLUE if accent else MUTED,
                                    lw=1.8 if accent else 1.0))
        ax.text(x + 1.5, y + h - 3, name, fontsize=10.5, fontweight="bold", color=INK, va="center")
        ax.text(x + 1.5, y + h - 6.2, mod, fontsize=8.5, color=BLUE, family="monospace", va="center")
        ax.text(x + 1.5, y + 3.3, desc, fontsize=8.5, color=MUTED, va="center", linespacing=1.3)
    arrows = [((31, 25.5), (36, 25.5)), ((64, 25.5), (69, 25.5)), ((83, 19), (83, 15)),
              ((69, 8.5), (64, 8.5)), ((36, 8.5), (31, 8.5))]
    for a, b in arrows:
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=12, color=MUTED, lw=1.2))
    fig.tight_layout(); fig.savefig(OUT / "fig_pipeline.png"); plt.close(fig)


def book_snapshot(day: str = "2024-02-08") -> dict:
    q = pd.read_parquet(C.DATA_PQ / "bookTicker" / f"{day}.parquet")
    tr = pd.read_parquet(C.DATA_PQ / "aggTrades" / f"{day}.parquet")
    mid2 = (q.bid + q.ask).to_numpy()
    moves = pd.Series(np.r_[0, np.diff(mid2) != 0], index=q.t // 120_000)
    counts = moves.groupby(level=0).sum()
    counts = counts[(counts.index * 120_000 % 86_400_000 > 6 * 3_600_000)]
    target = counts.quantile(0.9)
    b0 = int((counts - target).abs().idxmin()) * 120_000
    w = q[(q.t >= b0) & (q.t < b0 + 120_000)]
    t = tr[(tr.t >= b0) & (tr.t < b0 + 120_000)]
    s = lambda x: (x - b0) / 1000
    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(10, 6.6), sharex=True,
                                     gridspec_kw={"height_ratios": [2.2, 1.4, 1.1]})
    a1.step(s(w.t), w.ask * C.TICK, where="post", color=RED, lw=1.3, label="best ask")
    a1.step(s(w.t), w.bid * C.TICK, where="post", color=GREEN, lw=1.3, label="best bid")
    for side, col, mk, lab in [(1, GREEN, "^", "aggressive buy"), (-1, RED, "v", "aggressive sell")]:
        z = t[t.side == side]
        a1.scatter(s(z.t), z.px * C.TICK, s=6 + 40 * np.sqrt(z.qty / z.qty.max()) * 4, marker=mk,
                   color=col, alpha=0.45, lw=0, label=lab)
    a1.set_ylabel("price (USD)"); a1.legend(ncol=4, fontsize=8, loc="upper left")
    a1.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.4f}"))
    a2.step(s(w.t), w.bq / 1000, where="post", color=GREEN, lw=1.2, label="bid size")
    a2.step(s(w.t), w.aq / 1000, where="post", color=RED, lw=1.2, label="ask size")
    a2.set_ylabel("L1 size ('000)"); a2.legend(ncol=2, fontsize=8, loc="upper left")
    qi = (w.bq - w.aq) / (w.bq + w.aq)
    a3.step(s(w.t), qi, where="post", color=BLUE, lw=1.2)
    a3.axhline(0, color=MUTED, lw=0.8); a3.set_ylim(-1, 1)
    a3.set_ylabel("queue imbalance"); a3.set_xlabel("seconds into the window")
    start = pd.Timestamp(b0, unit="ms", tz="UTC").strftime("%H:%M")
    a1.set_title(f"Two minutes of the XRPUSDT book, {day} {start} UTC", loc="left", color=INK)
    fig.tight_layout(); fig.savefig(OUT / "fig_book_snapshot.png"); plt.close(fig)
    return {"start": start, "quotes": len(w), "trades": len(t), "mid_moves": int(np.sum(np.diff(w.bid + w.ask) != 0))}


def queue_model() -> None:
    fig, ax = plt.subplots(figsize=(10, 3.1))
    ax.set_xlim(-60, 860); ax.set_ylim(0, 66); ax.axis("off")
    segs = [(0, 500, "#d5d9de", "queue ahead of us: 500"), (500, 100, BLUE, "our order: 100"),
            (600, 180, "#eceef1", "joined after us")]
    for x, wd, col, lab in segs:
        ax.add_patch(FancyBboxPatch((x, 32), wd, 14, boxstyle="square,pad=0", fc=col, ec="white", lw=1.5))
        ax.text(x + wd / 2, 39, lab, ha="center", va="center", fontsize=9,
                color="white" if col == BLUE else INK, fontweight="bold" if col == BLUE else None)
    ax.text(-55, 39, "bid\n@ p", ha="left", va="center", fontsize=9, color=MUTED)
    ax.add_patch(FancyArrowPatch((140, 58), (10, 49), arrowstyle="-|>", mutation_scale=12, color=RED, lw=1.3))
    ax.text(150, 59, "1  aggressive sells at p remove volume from the front of the queue",
            fontsize=9, color=INK, va="center")
    ax.add_patch(FancyArrowPatch((660, 20), (770, 29), arrowstyle="-|>", mutation_scale=12, color=GREY, lw=1.3))
    ax.text(0, 20, "2  displayed size falls below our position: cancellations are assumed to come from\n"
                   "    behind us, so queue ahead = min(queue ahead, displayed size)",
            fontsize=9, color=INK, va="center")
    ax.text(0, 5, "3  we are filled when traded volume at p clears queue ahead + our size, or on any trade below p",
            fontsize=9, color=MUTED, va="center")
    fig.tight_layout(); fig.savefig(OUT / "fig_queue_model.png"); plt.close(fig)


def cost_decomposition() -> None:
    ex = pd.read_csv(C.RESULTS / "execution_test.csv")
    pols = ["immediate", "passive", "signal-aware"]
    d = ex[ex.policy.isin(pols)].copy()
    d["fees_bp"] = d.cost_bp - d.slippage_bp
    fig, ax = plt.subplots(figsize=(10, 3.6))
    wins = sorted(d.window_s.unique())
    cols = {"immediate": GREY, "passive": "#8fb1dc", "signal-aware": BLUE}
    for i, W in enumerate(wins):
        for j, p in enumerate(pols):
            r = d[(d.window_s == W) & (d.policy == p)].iloc[0]
            x = i * 4 + j
            ax.bar(x, r.slippage_bp, 0.8, color=cols[p])
            ax.bar(x, r.fees_bp, 0.8, bottom=r.slippage_bp, color=cols[p], alpha=0.35, hatch="///",
                   edgecolor="white")
            ax.text(x, r.slippage_bp / 2, f"{r.slippage_bp:.2f}", ha="center", va="center", fontsize=7.5,
                    color=INK if p == "passive" else "white")
            ax.text(x, r.cost_bp + 0.08, f"{r.cost_bp:.2f}", ha="center", fontsize=7.5, color=INK)
    ax.set_xticks([i * 4 + 1 for i in range(len(wins))])
    ax.set_xticklabels([f"{W}s window" for W in wins])
    ax.set_ylabel("bp vs arrival mid")
    handles = [plt.Rectangle((0, 0), 1, 1, color=cols[p]) for p in pols] + \
              [plt.Rectangle((0, 0), 1, 1, fc="white", ec=MUTED, hatch="///")]
    ax.legend(handles, pols + ["fees (hatched)"], ncol=4, fontsize=8, loc="upper right")
    ax.set_ylim(0, d.cost_bp.max() * 1.25)
    ax.set_title("Solid = slippage (number inside), hatched = fees; total on top", loc="left",
                 color=INK, fontsize=10)
    fig.tight_layout(); fig.savefig(OUT / "fig_cost_decomposition.png"); plt.close(fig)


def main() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    pipeline()
    info = book_snapshot()
    queue_model()
    cost_decomposition()
    return info


if __name__ == "__main__":
    print(main())
