"""
SilverSnap Configuration
========================
Swap these symbols when the momentum play shifts to another asset.
Currently configured for: SILVER (via AGQ 2x leveraged ETF)

To change the play:
1. Update TRADING_SYMBOL to the new leveraged ETF
2. Update REFERENCE_SYMBOL to the underlying 1x ETF (for cleaner signals)
3. Adjust thresholds if the new asset has different volatility characteristics
"""

# =============================================================================
# SYMBOL CONFIGURATION
# =============================================================================

# The instrument we actually trade (leveraged)
TRADING_SYMBOL = "AGQ"  # ProShares Ultra Silver (2x)

# Reference symbol for signals (1x, cleaner price action)
REFERENCE_SYMBOL = "SLV"  # iShares Silver Trust

# Description for logging
ASSET_NAME = "Silver"

# Alternative configurations (uncomment to switch):
# -----------------------------------------------------------------------------
# GOLD:
# TRADING_SYMBOL = "UGL"   # ProShares Ultra Gold (2x)
# REFERENCE_SYMBOL = "GLD" # SPDR Gold Trust
# ASSET_NAME = "Gold"

# NATURAL GAS:
# TRADING_SYMBOL = "BOIL"  # ProShares Ultra Bloomberg Natural Gas (2x)
# REFERENCE_SYMBOL = "UNG" # United States Natural Gas Fund
# ASSET_NAME = "Natural Gas"

# OIL:
# TRADING_SYMBOL = "UCO"   # ProShares Ultra Bloomberg Crude Oil (2x)
# REFERENCE_SYMBOL = "USO" # United States Oil Fund
# ASSET_NAME = "Oil"

# NASDAQ (if you want to apply this to tech):
# TRADING_SYMBOL = "TQQQ"  # ProShares UltraPro QQQ (3x)
# REFERENCE_SYMBOL = "QQQ" # Invesco QQQ Trust
# ASSET_NAME = "Nasdaq"

# BITCOIN:
# TRADING_SYMBOL = "BITU"  # ProShares Ultra Bitcoin ETF (2x)
# REFERENCE_SYMBOL = "IBIT" # iShares Bitcoin Trust
# ASSET_NAME = "Bitcoin"


# =============================================================================
# ENTRY THRESHOLDS (Tiered: SLV for smaller drops, AGQ for bigger drops)
# =============================================================================

# Drop thresholds determine WHICH instrument to buy:
#   - Drop 2-4%   → Buy SLV (1x, conservative)
#   - Drop 4%+    → Buy AGQ (2x, aggressive)

# Minimum drop to consider any entry
ENTRY_THRESHOLD_MIN = 0.02  # 2% drop minimum to consider entry

# Threshold where we switch from SLV to AGQ
ENTRY_THRESHOLD_LEVERAGED = 0.04  # 4%+ drop = buy AGQ instead of SLV

# Conservative instrument (1x)
CONSERVATIVE_SYMBOL = "SLV"  # iShares Silver Trust (1x)

# Aggressive instrument (2x) - same as TRADING_SYMBOL
# TRADING_SYMBOL = "AGQ" defined above


# =============================================================================
# EXIT THRESHOLDS
# =============================================================================

# Target gain - SAME for both SLV and AGQ (5% gain = lock it in)
TARGET_GAIN = 0.05  # 5% gain target - lock it in!

# Stop loss from entry price (as decimal)  
STOP_LOSS_SLV = 0.05  # 5% stop on SLV (1x)
STOP_LOSS_AGQ = 0.07  # 7% stop on AGQ (2x, wider for volatility)

# Time-based exit: if position open past this many trading days, evaluate exit
MAX_HOLD_DAYS = 2


# =============================================================================
# PSAR FILTER SETTINGS
# =============================================================================

# PSAR parameters for trend filter
PSAR_AF_START = 0.02  # Acceleration factor start
PSAR_AF_INCREMENT = 0.02  # AF increment
PSAR_AF_MAX = 0.20  # Maximum AF

# RSI period for PSAR-on-RSI filter
RSI_PERIOD = 14

# Lookback for daily data (need enough for PSAR calculation)
DATA_LOOKBACK_DAYS = 60


# =============================================================================
# TRADING WINDOWS (Eastern Time)
# =============================================================================

# Post-market monitoring window
POSTMARKET_START = "16:00"  # 4:00 PM ET
POSTMARKET_END = "20:00"    # 8:00 PM ET

# Sweet spot for post-market entries
POSTMARKET_SWEET_SPOT_START = "18:30"  # 6:30 PM ET
POSTMARKET_SWEET_SPOT_END = "19:30"    # 7:30 PM ET

# Primary exit window (midday)
EXIT_WINDOW_START = "11:30"  # 11:30 AM ET
EXIT_WINDOW_END = "12:30"    # 12:30 PM ET

# Silver bullet hour (high liquidity)
SILVER_BULLET_START = "10:00"  # 10:00 AM ET
SILVER_BULLET_END = "11:00"    # 11:00 AM ET


# =============================================================================
# DATA SOURCES
# =============================================================================

# Twelve Data API (you already have this)
TWELVE_DATA_API_KEY = ""  # Set via environment variable TWELVE_DATA_API_KEY

# Schwab API credentials (for execution)
SCHWAB_APP_KEY = ""  # Set via environment variable
SCHWAB_APP_SECRET = ""
SCHWAB_ACCOUNT_HASH = ""


# =============================================================================
# NOTIFICATION SETTINGS
# =============================================================================

# How to receive alerts
ENABLE_CONSOLE_ALERTS = True
ENABLE_FILE_LOGGING = True

# Log file location
LOG_FILE = "silversnap.log"
SIGNAL_LOG_FILE = "signals.json"


# =============================================================================
# ACCOUNT SETTINGS
# =============================================================================

# Capital allocated to this strategy
CAPITAL = 1000.00

# Use all capital per trade (no position sizing)
POSITION_SIZE_PCT = 1.0  # 100% of capital per trade
