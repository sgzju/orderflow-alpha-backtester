"""Project-wide settings. Every module reads from here so a run is reproducible."""
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PQ = ROOT / "data" / "parquet"
FEATURES = ROOT / "data" / "features"
RESULTS = ROOT / "results"

SYMBOL = "XRPUSDT"            # Binance USD-M perpetual
TICK = 0.0001                 # price tick for XRPUSDT perpetual (Feb 2024)
START = date(2024, 2, 1)
N_DAYS = 10
DATES = [(START + timedelta(days=i)).isoformat() for i in range(N_DAYS)]

# Chronological split; the test days are used once, after every choice is frozen.
TRAIN = DATES[:5]
VALID = DATES[5:7]
TEST = DATES[7:]

GRID_MS = 100                          # decision / sampling clock
WINDOWS_S = [1, 5, 30]                 # look-back windows for flow features
HORIZONS_S = [1, 2, 5, 10, 30, 60]     # forward mid-price horizons

# Binance USD-M futures, VIP 0 schedule in Feb 2024 (no BNB discount), in basis points.
MAKER_FEE_BP = 2.0
TAKER_FEE_BP = 5.0

ORDER_QTY = 1000.0           # contracts (XRP) per trade, roughly USD 500 notional
