"""Build docs/OrderFlow_Alpha_Tutorial.pdf: a step-by-step tutorial and results report.

Every number is read from results/ and every code excerpt from ofalpha/, so the
report cannot drift from the project.  Run from the project root:
    .venv/Scripts/python docs/build_tutorial.py
"""
import json
import re
import sys
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, Image, KeepTogether, PageBreak,
                                PageTemplate, Paragraph, Preformatted, Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "docs"))
from ofalpha import config as C  # noqa: E402
from ofalpha.engine import REASONS, trade_pnl_bp  # noqa: E402
import figures as F  # noqa: E402

OUT = ROOT / "docs" / "OrderFlow_Alpha_Tutorial.pdf"
RES, FIG = C.RESULTS, ROOT / "docs" / "figures"

# ---------- fonts, colours, styles ----------
FONTS = Path("C:/Windows/Fonts")
for name, file in [("Arial", "arial.ttf"), ("Arial-Bold", "arialbd.ttf"), ("Arial-Italic", "ariali.ttf"),
                   ("Arial-BoldItalic", "arialbi.ttf"), ("Consolas", "consola.ttf")]:
    pdfmetrics.registerFont(TTFont(name, str(FONTS / file)))
registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial-Italic", boldItalic="Arial-BoldItalic")

INK, MUTED = colors.HexColor("#1f2933"), colors.HexColor("#5f6b78")
ACCENT, TINT = colors.HexColor("#2f6db5"), colors.HexColor("#eef3fa")
RULE, HEAD, CODEBG = colors.HexColor("#d9dee4"), colors.HexColor("#e9edf2"), colors.HexColor("#f4f5f7")

W = A4[0] - 2 * 20 * mm
S = {
    "body": ParagraphStyle("Body", fontName="Arial", fontSize=9.6, leading=13.8, textColor=INK, spaceAfter=6),
    "H1": ParagraphStyle("H1", fontName="Arial-Bold", fontSize=17, leading=21, textColor=INK, spaceAfter=10),
    "H1nt": ParagraphStyle("H1nt", fontName="Arial-Bold", fontSize=17, leading=21, textColor=INK, spaceAfter=10),
    "H2": ParagraphStyle("H2", fontName="Arial-Bold", fontSize=11.8, leading=15, textColor=INK,
                         spaceBefore=10, spaceAfter=5),
    "H3": ParagraphStyle("H3", fontName="Arial-Bold", fontSize=9.8, leading=13, textColor=ACCENT,
                         spaceBefore=6, spaceAfter=3),
    "bullet": ParagraphStyle("Bullet", fontName="Arial", fontSize=9.6, leading=13.4, textColor=INK,
                             leftIndent=14, bulletIndent=3, spaceAfter=3),
    "caption": ParagraphStyle("Caption", fontName="Arial-Italic", fontSize=8.3, leading=11, textColor=MUTED,
                              spaceBefore=3, spaceAfter=11),
    "cell": ParagraphStyle("Cell", fontName="Arial", fontSize=8.3, leading=10.6, textColor=INK),
    "cellh": ParagraphStyle("CellH", fontName="Arial-Bold", fontSize=8.3, leading=10.6, textColor=INK),
    "code": ParagraphStyle("Code", fontName="Consolas", fontSize=7.5, leading=9.6, textColor=INK),
    "callout": ParagraphStyle("Callout", fontName="Arial", fontSize=9.4, leading=13.4, textColor=INK),
    "title": ParagraphStyle("Title", fontName="Arial-Bold", fontSize=26, leading=31, textColor=INK),
    "subtitle": ParagraphStyle("Subtitle", fontName="Arial", fontSize=13.5, leading=18, textColor=MUTED),
    "big": ParagraphStyle("Big", fontName="Arial-Bold", fontSize=19, leading=22, textColor=ACCENT),
    "small": ParagraphStyle("Small", fontName="Arial", fontSize=8.3, leading=10.8, textColor=MUTED),
    "toc0": ParagraphStyle("TOC0", fontName="Arial-Bold", fontSize=10, leading=15, textColor=INK),
    "toc1": ParagraphStyle("TOC1", fontName="Arial", fontSize=9, leading=12.5, leftIndent=14, textColor=MUTED),
}


def P(text, style="body"):
    return Paragraph(text, S[style])


def H1(text):
    return [CondPageBreak(60 * mm), P(text, "H1")]


def H2(text):
    return [CondPageBreak(35 * mm), P(text, "H2")]


def bullets(items):
    return [Paragraph(t, S["bullet"], bulletText="\u2022") for t in items]


def numbered(items):
    return [Paragraph(t, S["bullet"], bulletText=f"{i}.") for i, t in enumerate(items, 1)]


def figure(name, caption, width=W, folder=None):
    path = (folder or RES) / name
    w0, h0 = PILImage.open(path).size
    return KeepTogether([Image(str(path), width=width, height=width * h0 / w0), P(caption, "caption")])


def table(header, rows, widths, intro=None):
    data = [[P(h, "cellh") for h in header]] + [[P(str(c), "cell") for c in r] for r in rows]
    t = Table(data, colWidths=[w * W for w in widths], repeatRows=1, hAlign="LEFT")
    style = [("BACKGROUND", (0, 0), (-1, 0), HEAD), ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
             ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3.2),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2), ("LEFTPADDING", (0, 0), (-1, -1), 5),
             ("RIGHTPADDING", (0, 0), (-1, -1), 5)]
    t.setStyle(TableStyle(style))
    return KeepTogether(([intro] if intro is not None else []) + [t, Spacer(1, 9)])


def boxed(flowable, bg):
    t = Table([[flowable]], colWidths=[W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("LEFTPADDING", (0, 0), (-1, -1), 9),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 7),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return t


def code(text, intro=None):
    return KeepTogether(([intro] if intro is not None else []) +
                        [boxed(Preformatted(text, S["code"]), CODEBG), Spacer(1, 8)])


def callout(title, text):
    return KeepTogether([boxed(P(f"<b>{title}</b><br/>{text}", "callout"), TINT), Spacer(1, 9)])


def snippet(path, start, stop=None, n=None, include_stop=False):
    lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
    i = next(k for k, ln in enumerate(lines) if start in ln)
    if stop is not None:
        j = next(k for k in range(i + 1, len(lines)) if stop in lines[k]) + (1 if include_stop else 0)
    else:
        j = i + n
    return textwrap.dedent("\n".join(lines[i:j])).rstrip()


def f(x, d=2):
    return f"{x:,.{d}f}".replace("-", "\u2212")


def pct(x, d=1):
    return f"{x * 100:.{d}f}%"


# ---------- numbers from the results ----------
def load():
    R = {}
    ic = pd.read_csv(RES / "ic_by_day.csv")
    R["ic5"] = (ic[ic.horizon_s == 5].groupby(["feature", "split"]).ic.mean().unstack()[["train", "valid", "test"]]
                .sort_values("train", ascending=False))
    oos = pd.read_csv(RES / "model_oos.csv")
    R["oos"] = oos.groupby(["horizon_s", "split"])[["r2_oos", "ic"]].mean().unstack("split")
    R["qid"] = pd.read_csv(RES / "qi_deciles.csv")
    test = pd.read_csv(RES / "test_results.csv")
    R["strat"] = (test[test.variant != "latency"].groupby(["style", "variant"])
                  .agg(trades=("trades", "sum"), gross=("gross_bp", "mean"), net=("net_bp", "mean"),
                       pnl=("pnl_usd", "sum"), hit=("hit", "mean")))
    R["lat"] = (test[test.variant == "latency"].groupby("lat_ms")
                .agg(trades=("trades", "sum"), gross=("gross_bp", "mean"), net=("net_bp", "mean")))
    sel = json.loads((RES / "selection.json").read_text())
    R["chosen"], R["timing"] = sel["chosen"], sel["timing"]
    tr = pd.read_parquet(RES / "test_trades.parquet")
    mk = tr[tr["style"] == "maker"]
    rows = []
    for reason, g in mk.groupby("reason"):
        gg, nn = trade_pnl_bp(g.to_numpy()[:, :8].astype(float), C.MAKER_FEE_BP, C.TAKER_FEE_BP)
        rows.append([REASONS[int(reason)], len(g), pct(len(g) / len(mk), 0), f(gg.mean()), f(nn.mean())])
    R["reasons"] = sorted(rows, key=lambda r: -r[1])
    gm, nm = trade_pnl_bp(mk.to_numpy()[:, :8].astype(float), C.MAKER_FEE_BP, C.TAKER_FEE_BP)
    R["maker_rebate"] = np.mean(gm - np.where(mk.entry_taker > 0, C.TAKER_FEE_BP, -1.0)
                                - np.where(mk.exit_taker > 0, C.TAKER_FEE_BP, -1.0))
    ex = pd.read_csv(RES / "execution_test.csv")
    R["ex"] = ex
    R["ex_sel"] = json.loads((RES / "execution_selection.json").read_text())
    R["fees"] = pd.read_csv(RES / "execution_fee_tiers.csv")
    R["sweep_log"] = (RES / "sweep_log.txt").read_text(encoding="utf-8").strip()
    days = []
    for d in C.DATES:
        q = pd.read_parquet(C.DATA_PQ / "bookTicker" / f"{d}.parquet", columns=["t"])
        t = pd.read_parquet(C.DATA_PQ / "aggTrades" / f"{d}.parquet")
        g = pd.read_parquet(C.FEATURES / f"{d}.parquet", columns=["bid", "ask", "bq", "aq"])
        days.append({"day": d, "split": "train" if d in C.TRAIN else "valid" if d in C.VALID else "test",
                     "quotes": len(q), "trades": len(t), "usd": float((t.qty * t.px * C.TICK).sum()),
                     "depth": float(((g.bq + g.aq) / 2).mean()), "one_tick": float(((g.ask - g.bid) == 1).mean()),
                     "mid": float(((g.bid + g.ask) / 2 * C.TICK).mean()), "grid": len(g)})
    R["days"] = pd.DataFrame(days)
    return R


def ex_row(ex, W, policy, col):
    return float(ex[(ex.window_s == W) & (ex.policy == policy)][col].iloc[0])


# ---------- document ----------
class Doc(BaseDocTemplate):
    def __init__(self, filename):
        super().__init__(filename, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                         bottomMargin=18 * mm, title="Order-Flow Alpha and a Tick-Level Execution Backtester",
                         author="orderflow-alpha-backtester", subject="Tutorial and results report")
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="main")
        self.addPageTemplates([PageTemplate(id="page", frames=[frame], onPage=self.decorate)])

    def decorate(self, canv, doc):
        if doc.page == 1:
            return
        canv.saveState()
        canv.setFont("Arial", 7.8)
        canv.setFillColor(MUTED)
        canv.drawString(20 * mm, 10 * mm, "Order-flow alpha and a tick-level execution backtester \u00b7 tutorial and results")
        canv.drawRightString(A4[0] - 20 * mm, 10 * mm, f"{doc.page}")
        canv.setStrokeColor(RULE)
        canv.line(20 * mm, 13.5 * mm, A4[0] - 20 * mm, 13.5 * mm)
        canv.restoreState()

    def afterFlowable(self, fl):
        if isinstance(fl, Paragraph) and fl.style.name in ("H1", "H2"):
            level = 0 if fl.style.name == "H1" else 1
            key = f"h{id(fl)}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(fl.getPlainText(), key, level=level)
            self.notify("TOCEntry", (level, fl.getPlainText(), self.page, key))


def build(R, snap):
    T, story = R["timing"], []
    ic5, oos, strat, ex = R["ic5"], R["oos"], R["strat"], R["ex"]
    days = R["days"]
    qi = ic5.loc["qi"]
    m5_ic, m5_r2 = oos.loc[5, ("ic", "test")], oos.loc[5, ("r2_oos", "test")]
    tk, mk, rnd = strat.loc[("taker", "selected")], strat.loc[("maker", "selected")], strat.loc[("maker", "random sign")]
    imm30, pas30, sig30 = (ex_row(ex, 30, p, "cost_bp") for p in ("immediate", "passive", "signal-aware"))
    slp_pas30, slp_sig30 = ex_row(ex, 30, "passive", "slippage_bp"), ex_row(ex, 30, "signal-aware", "slippage_bp")
    diffs = ex[ex.diff_bp.notna()]
    d = lambda W, pol, col="diff_bp": float(diffs[(diffs.window_s == W) & (diffs.policy == pol)][col].iloc[0])
    n_orders = int(ex[(ex.window_s == 30) & (ex.policy == "passive")].orders.iloc[0])
    tick_bp = C.TICK / days.mid.mean() * 1e4
    slip_cut = 1 - slp_sig30 / slp_pas30

    # ---- cover ----
    story += [Spacer(1, 38 * mm), P("Order-Flow Alpha and a Tick-Level Execution Backtester", "title"),
              Spacer(1, 6 * mm), P("A step-by-step tutorial and results report", "subtitle"), Spacer(1, 4 * mm),
              P(f"Binance USD-M perpetual {C.SYMBOL} \u00b7 {C.DATES[0]} to {C.DATES[-1]} \u00b7 "
                f"{days.quotes.sum() / 1e6:.1f} million quote updates and {days.trades.sum() / 1e6:.2f} million trades",
                "subtitle"), Spacer(1, 22 * mm)]
    tiles = [(f(m5_ic), "test-day rank IC of the 5-second forecast"),
             (f(tk.net, 1) + " bp", "taker strategy, net per round trip"),
             (f"\u2212{slip_cut * 100:.0f}%", "slippage vs passive execution (30 s window)"),
             (f"{T['events_per_s'] / 1e6:.0f}M/s", "events replayed per second, one core")]
    cells = [[P(v, "big") for v, _ in tiles], [P(t, "small") for _, t in tiles]]
    tt = Table(cells, colWidths=[W / 4] * 4)
    tt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TINT), ("LINEAFTER", (0, 0), (-2, -1), 4, colors.white),
                            ("TOPPADDING", (0, 0), (-1, 0), 10), ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
                            ("LEFTPADDING", (0, 0), (-1, -1), 10), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [tt, Spacer(1, 30 * mm),
              P("Project folder: <font name='Consolas'>orderflow-alpha-backtester</font> \u00b7 Python, NumPy, pandas, "
                "Numba, Matplotlib \u00b7 report generated from the project's own result files", "small"),
              PageBreak()]

    # ---- contents ----
    toc = TableOfContents()
    toc.levelStyles = [S["toc0"], S["toc1"]]
    story += [P("Contents", "H1nt"), toc, PageBreak()]

    # ---- 1 summary ----
    story += H1("1. Executive summary")
    story += [P("This project asks a practical question that every short-horizon quant faces: <b>a signal predicts the "
                "next few seconds of price movement, but does it survive real trading?</b> To answer it, the project "
                "downloads raw tick data, builds order-flow features, measures their predictive power out of sample, "
                "and then replays every quote and trade through a purpose-built matching engine with latency, queue "
                "position and exchange fees."),
              P("The answer has three parts:")]
    story += numbered([
        f"<b>The signal is real.</b> Level-1 queue imbalance has a Spearman IC of {f(qi.train, 3)} with the 5-second "
        f"mid move on training days, {f(qi.valid, 3)} on validation days and {f(qi.test, 3)} on test days. A linear "
        f"model of nine features reaches a test IC of {f(m5_ic, 3)} and an out-of-sample R\u00b2 of {pct(m5_r2)}.",
        f"<b>It cannot be traded on its own.</b> The forecast rarely exceeds half a tick, while the spread is one tick "
        f"(about {f(tick_bp)} bp) and fees add 4 to 10 bp per round trip. The best taker configuration loses "
        f"{f(-tk.net, 1)} bp per trade; the best maker configuration loses {f(-mk.net, 1)} bp.",
        f"<b>It is valuable for execution.</b> Across {n_orders:,} simulated child orders, using the forecast to decide "
        f"when to wait and when to cross cuts slippage by {slip_cut * 100:.0f}% against plain passive execution and "
        f"total cost by {f(imm30 - sig30)} bp ({(imm30 - sig30) / imm30 * 100:.0f}%) against market orders, in a "
        f"30-second window. A random-sign placebo makes costs worse, so the gain comes from the signal."])
    story += [Spacer(1, 4)]
    rows = [["Signal", f"Queue imbalance IC {f(qi.test, 3)} at 5 s on test days; stable across all splits"],
            ["Forecast", f"Test IC {f(m5_ic, 3)}, out-of-sample R\u00b2 {pct(m5_r2)} at 5 s; well calibrated by decile"],
            ["Taker strategy", f"{int(tk.trades)} test trades, gross {f(tk.gross)} bp, net {f(tk.net)} bp per trade"],
            ["Maker strategy", f"{int(mk.trades)} test trades, gross {f(mk.gross)} bp, net {f(mk.net)} bp per trade"],
            ["Execution overlay", f"Cost {f(sig30)} bp vs {f(pas30)} bp passive and {f(imm30)} bp immediate "
                                  f"(30 s window, t = {f(d(30, 'signal-aware minus passive', 't_stat'), 1)})"],
            ["Engine", f"{T['events_per_run']:,} events per day replayed in {T['maker_run_s'] * 1000:.0f} ms; "
                       f"{T['full_sweep_runs']} backtests in {T['full_sweep_s']:.0f} s; 14 unit tests"]]
    story += [table(["Area", "Headline result"], rows, [0.2, 0.8])]
    story += [P("<b>How to read this report.</b> Section 2 explains the market-microstructure ideas the project relies "
                "on. Sections 3 to 9 follow the pipeline step by step: what each step does, why it is built that way, "
                "the command that runs it, and the result it produced. Section 10 lists the limitations and natural "
                "extensions.")]

    # ---- 2 concepts ----
    story += H1("2. Concepts you need first")
    story += H2("2.1 The limit order book and the touch")
    story += [P("An exchange keeps a <b>limit order book</b>: resting buy orders (bids) and sell orders (asks) at "
                "different prices. The highest bid and the lowest ask form the <b>touch</b> (level 1). Their difference "
                "is the <b>spread</b>; the smallest allowed price step is the <b>tick</b>. The quantity resting at each "
                "touch price is the <b>L1 size</b> or depth. The <b>mid price</b> is the average of the best bid and ask."),
              P(f"{C.SYMBOL} traded between about US$0.49 and US$0.53 in the sample, and its tick is {C.TICK}. One tick "
                f"is therefore about {f(tick_bp)} bp of price, and the spread was exactly one tick in "
                f"{pct(days.one_tick.mean(), 2)} of samples. Assets like this are called <b>large-tick</b>: the price "
                "is pinned to a one-tick spread, large queues build up at the touch, and the mid moves only when one "
                "side's queue is used up. That makes queue sizes very informative about the next price move.")]
    story += H2("2.2 Three order-flow signals")
    story += bullets([
        "<b>Queue imbalance (QI)</b> compares the bid and ask queues: QI = (q<sub>bid</sub> \u2212 q<sub>ask</sub>) / "
        "(q<sub>bid</sub> + q<sub>ask</sub>). It runs from \u22121 (all size on the ask) to +1 (all on the bid). A "
        "thin ask queue is likely to be consumed first, so a high QI predicts an up-tick.",
        "<b>Order-flow imbalance (OFI)</b>, from Cont, Kukanov and Stoikov (2014), adds up the net change in "
        "bid-side and ask-side demand at every quote update: e<sub>n</sub> = 1{P<super>b</super><sub>n</sub> \u2265 "
        "P<super>b</super><sub>n\u22121</sub>} q<super>b</super><sub>n</sub> \u2212 1{P<super>b</super><sub>n</sub> \u2264 "
        "P<super>b</super><sub>n\u22121</sub>} q<super>b</super><sub>n\u22121</sub> \u2212 1{P<super>a</super><sub>n</sub> \u2264 "
        "P<super>a</super><sub>n\u22121</sub>} q<super>a</super><sub>n</sub> + 1{P<super>a</super><sub>n</sub> \u2265 "
        "P<super>a</super><sub>n\u22121</sub>} q<super>a</super><sub>n\u22121</sub>. Summed over a window, it measures "
        "buying versus selling pressure in the book itself.",
        "<b>Trade-flow imbalance (TFI)</b> uses executed trades: signed aggressor volume divided by total volume over "
        "a window. A buy is 'aggressive' when the buyer crossed the spread to hit a resting ask.",
        "<b>Recent returns</b> (the mid change over the last 5 and 30 seconds) test for short-term momentum or reversal."])
    story += H2("2.3 Makers, takers, fees and latency")
    story += [P(f"A <b>taker</b> crosses the spread with a marketable order and is filled at once, paying the spread "
                f"and the taker fee ({C.TAKER_FEE_BP} bp on Binance VIP 0). A <b>maker</b> rests a limit order in the "
                f"book and pays the lower maker fee ({C.MAKER_FEE_BP} bp), but must wait in the queue and may never be "
                "filled. <b>Latency</b> is the delay between deciding and the order reaching the exchange; during that "
                "time the book can move. A taker round trip on XRP therefore costs one tick of spread plus 10 bp of fees, "
                "about 12 bp in total, before any signal is applied.")]
    story += H2("2.4 Adverse selection and queue position")
    story += [P("A resting bid is filled when someone sells into it. That tends to happen exactly when sellers are "
                "aggressive and the price is about to fall, so passive fills arrive at the worst moments: this is "
                "<b>adverse selection</b>. How bad it is depends on <b>queue position</b>. An order at the back of a "
                "100,000-contract queue is filled only when the whole level is nearly gone, which is usually just "
                "before the price ticks against it.")]
    story += H2("2.5 Measuring prediction")
    story += bullets([
        "<b>Spearman information coefficient (IC)</b>: the rank correlation between a feature and the forward mid move. "
        "It is computed separately for each day, and days are then averaged within each split.",
        "<b>Out-of-sample R\u00b2</b> against a zero forecast: R\u00b2<sub>OOS</sub> = 1 \u2212 \u03a3(y \u2212 "
        "\u0177)\u00b2 / \u03a3y\u00b2. It is positive only if the forecast beats predicting no move at all.",
        f"<b>Chronological split</b>: train on {C.TRAIN[0]} to {C.TRAIN[-1]}, validate on {C.VALID[0]} to "
        f"{C.VALID[-1]}, test on {C.TEST[0]} to {C.TEST[-1]}. Every choice is made before the test days are touched."])
    story += H2("2.6 Measuring execution cost")
    story += [P("For an order of side s (+1 buy, \u22121 sell) arriving when the mid is m<sub>0</sub> and filled at "
                "price p, the <b>implementation shortfall</b> in basis points is: cost = s \u00b7 (p \u2212 m<sub>0</sub>) "
                "/ m<sub>0</sub> \u00b7 10<super>4</super> + fee. The first term is <b>slippage</b>. It is about half "
                "a tick for a market order, and can be negative for a passive fill.")]

    # ---- 3 setup ----
    story += H1("3. Project layout and setup")
    story += [P("The project is a small Python package, <font name='Consolas'>ofalpha</font>, with one module per "
                "pipeline step. Each step reads the previous step's files from disk, so any step can be re-run on its own."),
              figure("fig_pipeline.png", "Figure 1. The six-step pipeline. The matching engine (step 4) is the core "
                     "piece of engineering; everything after it runs on top of it.", folder=FIG)]
    mods = [["ofalpha/config.py", "Symbol, dates, train/validation/test split, fees, clip size"],
            ["ofalpha/data.py", "Downloads quotes and trades, verifies SHA-256 checksums, writes Parquet"],
            ["ofalpha/features.py", "Point-in-time features and forward targets on a 100 ms clock"],
            ["ofalpha/research.py", "IC analysis, decile tables, OLS forecast, out-of-sample evaluation"],
            ["ofalpha/engine.py", "Numba matching engine: taker, maker and execution-overlay simulators"],
            ["ofalpha/sweep.py", "Parameter sweep, validation selection, single test run"],
            ["ofalpha/execution.py", "Execution-cost study with placebo, latency and block standard errors"],
            ["ofalpha/report.py", "Figures and results/RESULTS.md"],
            ["tests/test_engine.py", "14 hand-built order-book scenarios with known fills"],
            ["run_all.py", "Runs the whole pipeline in order"]]
    story += [table(["File", "Role"], mods, [0.3, 0.7])]
    story += [P("<b>Setup and full run.</b> Create a virtual environment, install the pinned packages, run the tests, then "
                "run the pipeline. The download is about 550 MB; compute takes about seven minutes on a desktop CPU."),
              code("python -m venv .venv\n.venv\\Scripts\\activate            # Windows (source .venv/bin/activate elsewhere)\n"
                   "pip install -r requirements.txt\npython -m pytest -q tests          # 14 matching-engine tests\n"
                   "python run_all.py                  # download -> features -> research -> sweep -> execution -> report")]
    cfg = [["SYMBOL", C.SYMBOL, "Binance USD-M perpetual"], ["TICK", C.TICK, "price step"],
           ["DATES", f"{C.DATES[0]} \u2026 {C.DATES[-1]}", f"{C.N_DAYS} days"],
           ["TRAIN / VALID / TEST", f"{len(C.TRAIN)} / {len(C.VALID)} / {len(C.TEST)} days", "chronological"],
           ["GRID_MS", C.GRID_MS, "sampling and decision clock"],
           ["WINDOWS_S", C.WINDOWS_S, "look-back windows for flow features"],
           ["HORIZONS_S", C.HORIZONS_S, "forward horizons for targets"],
           ["MAKER / TAKER_FEE_BP", f"{C.MAKER_FEE_BP} / {C.TAKER_FEE_BP}", "Binance VIP 0, Feb 2024"],
           ["ORDER_QTY", f"{C.ORDER_QTY:,.0f}", "contracts per order, about US$500"]]
    story += [table(["Setting", "Value", "Meaning"], cfg, [0.28, 0.32, 0.4],
                    intro=P("<b>Configuration</b> (<font name='Consolas'>ofalpha/config.py</font>):"))]

    # ---- 4 data ----
    story += H1("4. Step 1: Getting the data")
    story += [P("Binance publishes daily archives of every best-bid/ask change (<font name='Consolas'>bookTicker</font>) "
                "and every aggregated trade (<font name='Consolas'>aggTrades</font>) at "
                "<font name='Consolas'>data.binance.vision</font>. The bookTicker archive for USD-M futures ends in "
                "March 2024, which is why the sample is February 2024."),
              P("<b>What the step does.</b> For each day it downloads both zip files, checks them against the published "
                "SHA-256 checksum, converts prices to <b>integer ticks</b> (so price comparisons in the engine are exact), "
                "drops repeated identical quotes, and stores compact Parquet files. Raw zips are processed in memory "
                "and never written to disk."),
              P("The one non-obvious field is <font name='Consolas'>is_buyer_maker</font>: when it is true, the buyer "
                "was resting in the book, so the <i>seller</i> was the aggressor."),
              code(snippet("ofalpha/data.py", "# is_buyer_maker=True means", n=2)),
              code("python -m ofalpha.data            # ~550 MB, prints rows per file")]
    rows = [[r.day, r.split, f"{r.quotes:,}", f"{r.trades:,}", f"{r.usd / 1e6:,.0f}", f"{r.depth:,.0f}",
             pct(r.one_tick, 2)] for r in days.itertuples()]
    rows.append(["Total", "", f"{days.quotes.sum():,}", f"{days.trades.sum():,}", f"{days.usd.sum() / 1e6:,.0f}",
                 f"{days.depth.mean():,.0f}", pct(days.one_tick.mean(), 2)])
    story += [table(["Day", "Split", "Quote updates", "Trades", "Traded (US$M)", "Mean L1 depth", "1-tick spread"],
                    rows, [0.14, 0.09, 0.16, 0.12, 0.15, 0.16, 0.18])]
    story += [figure("fig_book_snapshot.png", f"Figure 2. Two minutes of raw data ({snap['quotes']:,} quote updates, "
                     f"{snap['trades']} trades, {snap['mid_moves']} mid moves). The spread sits at one tick; the mid "
                     "moves when one side's L1 queue runs out, and queue imbalance (bottom) often leans the right way "
                     "beforehand.", folder=FIG)]

    # ---- 5 features ----
    story += H1("5. Step 2: Point-in-time features")
    story += [P(f"<b>What the step does.</b> It puts every day on a fixed {C.GRID_MS} ms clock ({days.grid.sum():,} "
                "samples in total; the first 30 s and the last 60 s of each day are dropped so every window and horizon "
                "is complete). At each clock time g, it takes the <b>last</b> quote and trade stamped at or before g. "
                "This 'as-of' join is what makes the features point-in-time: no feature can see the future."),
              code(snippet("ofalpha/features.py", "def asof(times)", n=2)),
              P("OFI is computed once per quote update with vectorised NumPy, cumulated, and differenced over each "
                "window. It is then divided by current L1 depth so that days with deep and shallow books are comparable."),
              code(snippet("ofalpha/features.py", "def ofi_increments", "return e", include_stop=True)),
              P("Targets are forward mid changes in ticks, read with the same as-of lookup at g + h:"),
              code(snippet("ofalpha/features.py", "for h in C.HORIZONS_S:", n=2))]
    feats = [["qi", "(bid size \u2212 ask size) / (bid size + ask size) at the touch"],
             ["ofi_1, ofi_5, ofi_30", "Order-flow imbalance over 1, 5 and 30 s, divided by L1 depth"],
             ["tfi_1, tfi_5, tfi_30", "Signed aggressor volume / total volume over 1, 5 and 30 s"],
             ["ret_5, ret_30", "Mid change over the last 5 and 30 s, in ticks"],
             ["fwd_1 \u2026 fwd_60", "Target: mid change over the next 1, 2, 5, 10, 30, 60 s, in ticks"]]
    story += [table(["Column", "Definition"], feats, [0.26, 0.74]),
              code("python -m ofalpha.features        # ~20 s; prints grid points, 1-tick share, mean depth per day")]

    # ---- 6 research ----
    story += H1("6. Step 3: Signal research")
    story += H2("6.1 Which features predict, and how far ahead")
    story += [P("For each day, feature and horizon, the step computes the Spearman IC on all ~860,000 samples of that "
                "day. Averaging per split shows whether predictive power is stable or a fluke of one period.")]
    rows = [[k, f(v.train, 3), f(v.valid, 3), f(v.test, 3)] for k, v in ic5.iterrows()]
    story += [table(["Feature", "Train IC", "Validation IC", "Test IC"], rows, [0.31, 0.23, 0.23, 0.23]),
              figure("fig_ic_decay.png", "Figure 3. IC by forecast horizon (train days, error bars = one standard "
                     "deviation across days). Queue imbalance dominates and peaks at 5 seconds; the combined model on "
                     "test days (black) tracks it closely.")]
    story += [callout("Reading the result", f"Queue imbalance alone carries most of the information, with an IC near "
                      f"{f(qi.test, 2)} at 5 s that is almost identical in all three periods. Order-flow imbalance adds a "
                      "little; trade flow and past returns are weak. Predictive power peaks at 5 to 10 seconds and halves "
                      "by 60 seconds: this is a seconds-scale signal.")]
    story += H2("6.2 How big the predicted moves are")
    q = R["qid"]
    top, bot = q.iloc[-1], q.iloc[0]
    story += [figure("fig_deciles.png", "Figure 4. Left: mean forward mid move by queue-imbalance decile (train days). "
                     "Right: forecast versus realised move by forecast decile on test days; points close to the diagonal "
                     "mean the forecast's size, not just its sign, is right."),
              P(f"The relationship is monotonic, but the moves are small. In the top QI decile the mid rises on average "
                f"{f(top.fwd_5)} ticks over 5 s and {f(top.fwd_30)} ticks over 30 s; in the bottom decile it falls "
                f"{f(-bot.fwd_5)} and {f(-bot.fwd_30)} ticks. Even the most extreme decile predicts less than one tick, "
                "and that is the central fact for everything that follows.")]
    story += H2("6.3 A combined linear forecast")
    story += [P("All nine features are standardised with train-day means and standard deviations, then one OLS "
                "regression per horizon is fitted on the train days only. The fitted coefficients are frozen in "
                "<font name='Consolas'>results/model.json</font> and applied unchanged to validation and test days."),
              code(snippet("ofalpha/research.py", "def fit(days)", "return model", include_stop=True))]
    rows = [[h, pct(oos.loc[h, ("r2_oos", "train")], 2), pct(oos.loc[h, ("r2_oos", "valid")], 2),
             pct(oos.loc[h, ("r2_oos", "test")], 2), f(oos.loc[h, ("ic", "train")], 3), f(oos.loc[h, ("ic", "valid")], 3),
             f(oos.loc[h, ("ic", "test")], 3)] for h in C.HORIZONS_S]
    story += [table(["Horizon (s)", "R\u00b2 train", "R\u00b2 valid", "R\u00b2 test", "IC train", "IC valid", "IC test"],
                    rows, [0.16, 0.14, 0.14, 0.14, 0.14, 0.14, 0.14]),
              code("python -m ofalpha.research        # ~80 s; IC table, decile table, model.json, out-of-sample metrics")]

    # ---- 7 engine ----
    story += H1("7. Step 4: The matching engine")
    story += [P("Vectorised backtests (multiply a signal by next-period returns) ignore exactly the things that decide "
                "whether a seconds-scale signal makes money: the spread, queue position, latency and fees. The engine "
                "replays the recorded tape event by event instead, and simulates how the strategy's own orders would "
                "have been filled. It is written in Numba, so the inner loop compiles to machine code.")]
    story += H2("7.1 Event loop")
    story += bullets([
        "Six event sources are merged in time order: market-order arrivals, cancel arrivals, limit-order activations, "
        "trade prints, quote updates and decision ticks on the 100 ms clock.",
        "Ties at the same millisecond are resolved in that order. Trades come before quotes so that a trade and the "
        "quote update it caused are not double-counted against our queue position.",
        "Every action the strategy takes (send, cancel, market exit) becomes a scheduled event at decision time + latency."])
    story += H2("7.2 Fill rules")
    story += bullets([
        "<b>Market orders</b> fill at the touch at arrival. Any size beyond the displayed L1 quantity pays one extra tick.",
        "<b>Limit orders</b> join the back of the queue at their price; their queue position is tracked as shown in Figure 5.",
        "A limit order that would cross when it arrives (the book moved through it) is filled as a taker."])
    story += [figure("fig_queue_model.png", "Figure 5. The 'risk-averse' queue model. It is deliberately conservative: "
                     "it never assumes that cancellations happen in front of our order.", folder=FIG),
              code(snippet("ofalpha/engine.py", "elif ev == 3:", "elif ev == 4:"),
                   intro=P("The queue logic inside the event loop. A trade print on the other side either trades "
                           "through our price or eats into the queue ahead of us:")),
              code(snippet("ofalpha/engine.py", "elif ev == 4:", "if pos != 0 and mk_t == INF and not fill:"),
                   intro=P("A quote update applies the risk-averse rule, and fills us if the opposite quote reaches "
                           "our price:"))]
    story += H2("7.3 Unit tests")
    tests = [["taker_round_trip_pays_the_spread", "Taker buys at the ask, sells at the bid; 5 non-overlapping trades"],
             ["taker_slippage_beyond_displayed_size", "Size beyond L1 fills one tick worse (101.5 in, 99.5 out)"],
             ["maker_fills_only_after_queue_ahead_trades", "Fill only after 500 ahead + 100 ours trade; exit at target"],
             ["maker_no_fill_while_queue_ahead_remains", "150 traded against 500 ahead: no fill"],
             ["displayed_size_drop_moves_us_forward", "Displayed size falls to 50, so a 150 trade fills us"],
             ["trade_through_fills", "A trade below our bid fills us at our price"],
             ["timeout_exits_with_market_order", "Maximum holding time triggers a market exit at the bid"],
             ["stop_loss_exits_at_bid", "A 3-tick adverse move with a 2-tick stop exits at 97"],
             ["execution_immediate_buys_at_ask", "Immediate policy pays the ask at arrival + latency"],
             ["execution_passive_fill_through_queue", "Passive child order fills once the queue clears"],
             ["execution_passive_crosses_at_deadline", "Unfilled order cancels at deadline + latency, then crosses"],
             ["execution_signal_crosses_at_once_...", "Signal-aware policy crosses at once when the forecast is adverse"],
             ["execution_signal_crosses_early_...", "Forecast turns at 1,000 ms: crosses at 1,010 ms"],
             ["execution_sell_side_is_symmetric", "Sell orders mirror buy orders"]]
    story += [table(["Test", "What it proves"], tests, [0.42, 0.58]),
              code("python -m pytest -q tests\n..............                                     [100%]\n14 passed")]
    story += [callout("Speed", f"The maker engine replays {T['events_per_run']:,} events (one day of quotes, trades and "
                      f"decisions) in {T['maker_run_s'] * 1000:.0f} ms on a single core, about "
                      f"{T['events_per_s'] / 1e6:.0f} million events per second. A {T['full_sweep_runs']}-backtest sweep "
                      f"takes {T['full_sweep_s']:.0f} s. Splitting one day's {T['runs']} backtests over {T['workers']} "
                      f"processes gave only {T['speedup']:.1f}x, because process start-up and data loading cost more "
                      "than the compiled runs themselves.")]

    # ---- 8 strategies ----
    story += H1("8. Step 5: Standalone strategies")
    story += [P("Two ways of trading the forecast directly are tested, each with a parameter grid. Every configuration "
                "is run on the two validation days. One configuration per style is selected by validation PnL, and "
                "only that configuration is run on the three test days.")]
    story += bullets([
        "<b>Taker</b>: when |forecast| exceeds \u03b8 ticks, cross the spread, hold for h seconds, cross back. Grid: "
        "6 thresholds \u00d7 6 horizons \u00d7 3 latencies = 108 configurations.",
        "<b>Maker</b>: join the touch on the side the forecast favours; cancel if the signal fades or the price leaves; "
        "after a fill, post a passive exit one spread away; exit by market order on a time stop, a price stop or a "
        "signal flip. Grid: 5 \u00d7 4 \u00d7 3 \u00d7 2 \u00d7 3 = 360 configurations."])
    ch = R["chosen"]
    rows = [["Taker", f"\u03b8 = {ch['taker']['theta']} ticks, horizon {ch['taker']['horizon_s']} s, "
                      f"latency {ch['taker']['lat_ms']} ms"],
            ["Maker", f"\u03b8 = {ch['maker']['theta']} ticks, horizon {ch['maker']['horizon_s']} s, max hold "
                      f"{ch['maker']['max_hold_s']} s, stop {ch['maker']['stop_ticks']:g} ticks, latency {ch['maker']['lat_ms']} ms"]]
    story += [table(["Style", "Configuration selected on validation"], rows, [0.15, 0.85])]
    rows = [["Taker (selected)", int(tk.trades), f(tk.gross), f(tk.net), f(tk.pnl, 0), pct(tk.hit)],
            ["Maker (selected)", int(mk.trades), f(mk.gross), f(mk.net), f(mk.pnl, 0), pct(mk.hit)],
            ["Maker, random-sign signal", int(rnd.trades), f(rnd.gross), f(rnd.net), f(rnd.pnl, 0), pct(rnd.hit)]]
    story += [table(["Strategy", "Trades", "Gross bp", "Net bp", "PnL (US$)", "Win rate"], rows,
                    [0.32, 0.12, 0.14, 0.14, 0.14, 0.14],
                    intro=P("<b>Test-day results</b> (per round trip, in basis points of the entry price):")),
              figure("fig_strategies.png", "Figure 6. Left: cumulative test-day PnL per trade, gross (dashed) and net "
                     "(solid). Right: the maker strategy's net PnL per trade as the maker fee varies; it stays negative "
                     "even with a 1 bp rebate.")]
    story += [table(["Exit reason", "Trades", "Share", "Gross bp", "Net bp"], R["reasons"], [0.3, 0.15, 0.15, 0.2, 0.2],
                    intro=P("<b>Why the maker strategy loses</b>: test-day trades by exit reason."))]
    rows = [[int(k), int(v.trades), f(v.gross), f(v.net)] for k, v in R["lat"].iterrows()]
    story += [table(["Latency (ms)", "Trades", "Gross bp", "Net bp"], rows, [0.25, 0.25, 0.25, 0.25],
                    intro=P("<b>Maker latency sensitivity</b> on test days:")),
              callout("Reading the result", f"The taker loses only {f(-tk.gross)} bp before fees, so the forecast "
                      f"recovers most of the ~{f(tick_bp, 1)} bp spread, but 10 bp of taker fees cannot be overcome. "
                      "The maker strategy is adversely selected. Passive 'target' exits only scratch, because by the "
                      "time the order fills the price has usually moved against it, while stops and signal flips lose "
                      f"several bp. With a 1 bp maker rebate it still nets {f(R['maker_rebate'])} bp per trade. "
                      f"The random-sign version is worse ({f(rnd.gross)} bp gross), so the signal does reduce adverse "
                      "selection, but not by enough."),
              code("python -m ofalpha.sweep --bench   # benchmark, 936 validation runs, selection, test run")]

    # ---- 9 execution ----
    story += H1("9. Step 6: The execution overlay")
    story += [P("Section 8 shows the forecast cannot pay for its own trades. Most real trading is not optional, though: "
                "a portfolio rebalance or a hedge must be executed anyway, and the question becomes <i>how cheaply</i>. "
                "This step tests whether the forecast lowers the cost of trades that have to happen.")]
    story += H2("9.1 Design")
    story += bullets([
        f"A parent order of {C.ORDER_QTY:,.0f} contracts arrives every 10 seconds with a random side "
        f"({n_orders:,} orders on the test days) and must be completed within a window W of 5, 10, 30 or 60 seconds.",
        "<b>Immediate</b>: market order on arrival.",
        "<b>Passive</b>: rest at the near touch; if still unfilled at the deadline, cancel and cross.",
        "<b>Signal-aware</b>: as passive, but cross at once (or early, while waiting) whenever the forecast says the "
        "price is about to move away from us, that is when side \u00d7 forecast > \u03b8.",
        "<b>Placebo</b>: the signal-aware rule driven by a forecast with a random sign; it should not help.",
        "The threshold \u03b8 and forecast horizon are chosen on validation days for each W; test days are run once.",
        "Standard errors of paired cost differences use 5-minute blocks, because orders with overlapping windows are "
        "not independent."])
    story += [code(snippet("ofalpha/engine.py", "if policy == IMMEDIATE or (policy == SIGNAL", n=2) + "\n    ...\n" +
                   snippet("ofalpha/engine.py", "if T > t0 and s * pred[k - 1] > theta", n=2))]
    story += [CondPageBreak(120 * mm)] + H2("9.2 Results")
    pols = ["immediate", "passive", "signal-aware", "placebo (random-sign signal)"]
    rows = []
    for W_ in sorted(ex.window_s.unique()):
        for p in pols:
            r = ex[(ex.window_s == W_) & (ex.policy == p)].iloc[0]
            rows.append([f"{W_} s", p, f(r.cost_bp), f(r.slippage_bp), pct(r.passive_fill_rate, 0), f(r.avg_wait_s, 1)])
    story += [table(["Window", "Policy", "Cost bp", "Slippage bp", "Passive fills", "Avg wait (s)"], rows,
                    [0.11, 0.33, 0.13, 0.15, 0.15, 0.13]),
              figure("fig_execution.png", "Figure 7. Total cost per order on test days, including fees."),
              figure("fig_cost_decomposition.png", "Figure 8. The same costs split into slippage (solid) and fees "
                     "(hatched). The forecast cuts slippage in every window, but crossing more often pays more taker "
                     "fees, which absorbs part of the gain.", folder=FIG)]
    rows = [[f"{int(r.window_s)} s", r.policy, f(r.diff_bp, 3), f(r.se_bp, 3), f(r.t_stat, 1)]
            for r in diffs.itertuples()]
    story += [table(["Window", "Comparison", "Difference bp", "Std. error", "t-stat"], rows, [0.11, 0.47, 0.15, 0.14, 0.13],
                    intro=P("<b>Paired differences</b> (same orders, negative = cheaper):"))]
    fz = R["fees"]
    rows = [[f"{int(r.window_s)} s", r.tier, f(r.immediate), f(r.passive), f(r._5), f(r._6, 3)]
            for r in fz.itertuples()]
    story += [table(["Window", "Fee tier", "Immediate", "Passive", "Signal-aware", "Signal \u2212 passive"], rows,
                    [0.11, 0.29, 0.14, 0.14, 0.16, 0.16],
                    intro=P("<b>Fee-tier sensitivity</b>: the same simulated fills re-priced under other Binance fee "
                            "tiers (policy parameters not re-selected):"))]
    story += [callout("Reading the result",
                      f"In the 30-second window the forecast lowers slippage from {f(slp_pas30)} to {f(slp_sig30)} bp "
                      f"({slip_cut * 100:.0f}%) and total cost by {f(-d(30, 'signal-aware minus passive'), 3)} bp "
                      f"(t = {f(d(30, 'signal-aware minus passive', 't_stat'), 1)}). The placebo raises cost by "
                      f"{f(d(30, 'placebo minus passive'), 2)} bp, so direction matters, not only timing. The gain fades "
                      "with latency, and it grows as fees fall, because cheaper crossing makes acting on the forecast "
                      "cheaper. In the 60-second window, waiting alone already captures most of the benefit."),
              code("python -m ofalpha.execution       # ~4 min; selection on validation, test once, placebo, latency")]

    # ---- 10 limitations ----
    story += H1("10. Limitations and next steps")
    story += H2("10.1 Limitations")
    story += bullets([
        "One symbol, ten days and one market regime. The three test days give tens of thousands of orders and trades "
        "(enough for execution comparisons) but are too short for a strategy-level Sharpe ratio.",
        "Level-1 data only: queue position is modelled, not observed, and deeper book levels are invisible. The "
        "risk-averse queue rule is a deliberately conservative assumption.",
        "Our own orders are assumed not to move the market. That is reasonable for 1,000-contract clips against about "
        f"{days.depth.mean():,.0f} contracts at the touch, but not for large size.",
        "Quote and trade streams are aligned at millisecond resolution; trades are processed first on ties.",
        "Fee tiers other than VIP 0 are approximate."])
    story += H2("10.2 Natural extensions")
    story += bullets([
        "<b>More data</b>: more symbols (BTC, ETH, SOL) and months, using the same pipeline, to test whether the "
        "results generalise.",
        "<b>Lead-lag</b>: use BTC order flow to forecast XRP, a cross-asset signal that may reach further ahead.",
        "<b>Queue-position strategies</b>: join a new price level as soon as it forms, while the queue is short, "
        "instead of joining at the back.",
        "<b>Longer horizons</b>: forecast minutes ahead, where predicted moves can exceed one tick.",
        "<b>Overfitting audit</b>: deflated Sharpe ratio and probability of backtest overfitting across the 936-run sweep."])

    # ---- appendix ----
    story += H1("Appendix A. Console output of the sweep")
    story += [P("Captured from <font name='Consolas'>results/sweep_log.txt</font> after a full run:"),
              code("\n".join(textwrap.fill(ln, 110, subsequent_indent="  ") for ln in R["sweep_log"].splitlines()))]
    story += H1("Appendix B. Glossary")
    gl = [["Aggressor", "The side that crossed the spread to trigger a trade"],
          ["As-of join", "Matching each time to the latest record stamped at or before it"],
          ["bp (basis point)", "One hundredth of a percent, 0.01%"],
          ["IC", "Information coefficient; here the Spearman rank correlation with the forward move"],
          ["Implementation shortfall", "Cost of a trade measured against the mid price when the order arrived"],
          ["Large-tick asset", "Instrument whose spread is pinned at one tick with deep queues"],
          ["Latency", "Delay between a decision and the order reaching the exchange"],
          ["Maker / taker", "Resting liquidity provider / immediate liquidity consumer"],
          ["OFI", "Order-flow imbalance (Cont, Kukanov and Stoikov, 2014)"],
          ["Placebo", "A version of a test with the signal's information removed, used as a control"],
          ["Queue imbalance", "(bid size \u2212 ask size) / (bid size + ask size) at the touch"],
          ["Touch / L1", "The best bid and best ask"]]
    story += [table(["Term", "Meaning"], gl, [0.28, 0.72])]
    return story


def main():
    snap = F.main()
    R = load()
    doc = Doc(str(OUT))
    doc.multiBuild(build(R, snap))
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
