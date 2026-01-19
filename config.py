"""
SilverSnap Configuration V2 - Bi-Directional
==============================================
Now supports both LONG (bullish) and SHORT (bearish) regimes

LONG (Bullish Regime):
- PSAR bullish + RSI PSAR bullish → Buy dips in SLV/AGQ

SHORT (Bearish Regime):
- Price below 200MA + PSAR bearish + RSI slope negative → Buy bounces in ZSL
"""

# =============================================================================
# SYMBOL CONFIGURATION
# =============================================================================

# The instrument we actually trade (leveraged long)
TRADING_SYMBOL = "AGQ"  # ProShares Ultra Silver (2x long)

# Conservative long instrument (1x)
CONSERVATIVE_SYMBOL = "SLV"  # iShares Silver Trust

# Reference symbol for signals (1x, cleaner price action)
REFERENCE_SYMBOL = "SLV"  # iShares Silver Trust

# SHORT SIDE - Inverse instrument
INVERSE_SYMBOL = "ZSL"  # ProShares UltraShort Silver (-2x)

# Description for logging
ASSET_NAME = "Silver"


# =============================================================================
# REGIME DETECTION SETTINGS
# =============================================================================

# Moving Average period for trend regime
MA_PERIOD = 200  # 200-day MA for regime detection

# RSI slope lookback period
RSI_SLOPE_PERIOD = 5  # Compare current RSI to RSI N periods ago

# RSI slope threshold (negative means deteriorating momentum)
RSI_SLOPE_THRESHOLD = 0.0  # Any negative slope = bearish momentum


# =============================================================================
# LONG SIDE - ENTRY THRESHOLDS (Tiered: SLV for smaller drops, AGQ for bigger)
# =============================================================================

# Master switch must be ON (both PSAR filters green)

# Minimum drop to consider long entry
ENTRY_THRESHOLD_MIN = 0.02  # 2% drop minimum → buy SLV

# Threshold where we switch from SLV to AGQ
ENTRY_THRESHOLD_LEVERAGED = 0.04  # 4%+ drop → buy AGQ


# =============================================================================
# SHORT SIDE - ENTRY THRESHOLDS (Buy ZSL on bounces in bearish regime)
# =============================================================================

# MASTER SWITCH - Disable short side entirely (recommended during bull markets)
SHORT_SIDE_DISABLED = True  # Long-only mode - ZSL trading disabled

# Stricter filters to avoid counter-trend traps (only if SHORT_SIDE_DISABLED = False)
SHORT_CONSECUTIVE_BEARISH_DAYS = 2   # Require 2 consecutive bearish regime days
SHORT_REQUIRE_WEEKLY_MA_DECLINING = True  # Only short if 50-week MA is falling
SHORT_WEEKLY_MA_PERIOD = 50          # 50-week MA (250 trading days)

# Bearish regime requirements (ALL must be true):
# 1. Price below 200MA
# 2. PSAR bearish (dots above price)
# 3. RSI slope negative
# 4. 2 consecutive bearish days (if enabled)
# 5. 50-week MA declining (if enabled)

# Minimum bounce to consider short entry (buy ZSL)
SHORT_ENTRY_THRESHOLD_MIN = 0.02  # 2% bounce from recent low → buy ZSL

# Larger bounce threshold for bigger position
SHORT_ENTRY_THRESHOLD_AGGRESSIVE = 0.04  # 4%+ bounce → larger ZSL position


# =============================================================================
# EXIT THRESHOLDS - LONG SIDE
# =============================================================================

# Target gain - SAME for both SLV and AGQ
TARGET_GAIN = 0.05  # 5% gain target

# Stop loss from entry price
STOP_LOSS_SLV = 0.05  # 5% stop on SLV (1x)
STOP_LOSS_AGQ = 0.07  # 7% stop on AGQ (2x, wider for volatility)


# =============================================================================
# EXIT THRESHOLDS - SHORT SIDE (ZSL)
# =============================================================================

# Target gain for ZSL
TARGET_GAIN_ZSL = 0.05  # 5% gain target

# Stop loss for ZSL
STOP_LOSS_ZSL = 0.07  # 7% stop (inverse is volatile)


# =============================================================================
# TIME-BASED SETTINGS
# =============================================================================

# Max hold days before forced evaluation
MAX_HOLD_DAYS = 8


# =============================================================================
# PSAR FILTER SETTINGS
# =============================================================================

PSAR_AF_START = 0.02
PSAR_AF_INCREMENT = 0.02
PSAR_AF_MAX = 0.20

# RSI period for PSAR-on-RSI filter
RSI_PERIOD = 14

# Lookback for daily data
DATA_LOOKBACK_DAYS = 300  # Need 250+ for 50-week MA calculation


# =============================================================================
# TRADING WINDOWS (Eastern Time)
# =============================================================================

POSTMARKET_START = "16:00"
POSTMARKET_END = "20:00"
POSTMARKET_SWEET_SPOT_START = "18:30"
POSTMARKET_SWEET_SPOT_END = "19:30"
EXIT_WINDOW_START = "11:30"
EXIT_WINDOW_END = "12:30"
SILVER_BULLET_START = "10:00"
SILVER_BULLET_END = "11:00"


# =============================================================================
# API KEYS (set via environment variables)
# =============================================================================

TWELVE_DATA_API_KEY = ""
SCHWAB_APP_KEY = ""
SCHWAB_APP_SECRET = ""
SCHWAB_ACCOUNT_HASH = ""


# =============================================================================
# NOTIFICATION & LOGGING
# =============================================================================

ENABLE_CONSOLE_ALERTS = True
ENABLE_FILE_LOGGING = True
LOG_FILE = "silversnap.log"
SIGNAL_LOG_FILE = "signals.json"


# =============================================================================
# ACCOUNT SETTINGS
# =============================================================================

CAPITAL = 1000.00
POSITION_SIZE_PCT = 1.0
