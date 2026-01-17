# SilverSnap 🪙⚡

**Mean Reversion Strategy for High-Volatility Assets**

A systematic trading strategy that exploits overnight/post-market price extremes that tend to revert during the next trading session. Currently configured for Silver (SLV/AGQ), but designed to be easily swapped to any high-volatility asset.

## Strategy Overview

### The Edge
Academic research documents that buying assets with the lowest overnight returns and selling those with the highest yields Sharpe ratios 2-5x larger than traditional reversal strategies across asset classes.

### How It Works

1. **Master Switch (PSAR Filters)** - Only trade when both filters are GREEN:
   - PSAR on Price: Confirms uptrend
   - PSAR on RSI: Confirms momentum

2. **Tiered Entry** - Buy based on drop size:
   | Drop from Close | Action |
   |-----------------|--------|
   | 2-4% | Buy **SLV** (1x, conservative) |
   | 4%+  | Buy **AGQ** (2x, aggressive) |
   | <2%  | No trade |
   
   - Best window: Post-market 6:30-7:30 PM ET ("sweet spot")
   - Alternative: Intraday dips during "Silver Bullet Hour" (10-11 AM ET)

3. **Exit - Lock in 5%+**: 
   - Target: **+5% gain** on either SLV or AGQ → SELL, lock it in!
   - Stop: -5% (SLV) or -7% (AGQ)
   - Time: Midday exit window (11:30 AM - 12:30 PM ET)

## Quick Start

### Option 1: GitHub Actions (Recommended - No Local Setup)

1. **Fork/clone this repo to GitHub**

2. **Add secrets** (Settings → Secrets and variables → Actions):
   ```
   TWELVE_DATA_API_KEY    - For historical data (get free at twelvedata.com)
   SCHWAB_APP_KEY         - Your Schwab API app key
   SCHWAB_APP_SECRET      - Your Schwab API app secret
   SCHWAB_REFRESH_TOKEN   - Your Schwab OAuth refresh token
   SCHWAB_ACCOUNT_HASH    - Your Schwab account hash
   ```

3. **Enable Actions** - The workflow runs automatically at key times:
   - 6:30 PM ET - Post-market sweet spot
   - 7:30 PM ET - Post-market end
   - 9:00 AM ET - Pre-open
   - 10:30 AM ET - Silver bullet hour
   - 12:00 PM ET - Midday exit window

4. **Manual trigger** - Go to Actions → "SilverSnap Signal Check" → Run workflow
   - Check "Execute trades" to enable live trading (default is dry run)

### Option 2: Local/CLI Usage

```bash
# Clone the repo
git clone https://github.com/yourusername/silversnap.git
cd silversnap

# Set environment variables
export TWELVE_DATA_API_KEY='your-twelve-data-key'
export SCHWAB_APP_KEY='your-schwab-app-key'
export SCHWAB_APP_SECRET='your-schwab-secret'
export SCHWAB_REFRESH_TOKEN='your-refresh-token'
export SCHWAB_ACCOUNT_HASH='your-account-hash'

# Check current signal (using Twelve Data)
python main.py status

# Check current signal (using Schwab API - live quotes)
python main.py status --live

# Run strategy - DRY RUN (no actual trades)
python main.py run --live

# Run strategy - LIVE EXECUTION ⚠️
python main.py run --live --execute

# Show current Schwab positions
python main.py positions

# Monitor continuously
python main.py watch --live

# Show filter status
python main.py filters

# Show configuration
python main.py config
```

## Commands

| Command | Description |
|---------|-------------|
| `python main.py status` | Show signal using Twelve Data |
| `python main.py status --live` | Show signal using Schwab API |
| `python main.py run --live` | Run strategy (dry run - no trades) |
| `python main.py run --live --execute` | **Run strategy with LIVE execution** |
| `python main.py positions` | Show Schwab account positions |
| `python main.py watch --live` | Continuous monitoring |
| `python main.py filters` | Show PSAR filter analysis |
| `python main.py config` | Show current configuration |

## Configuration

Edit `config.py` to customize:

### Change the Asset
```python
# Currently: Silver
TRADING_SYMBOL = "AGQ"         # 2x leveraged
CONSERVATIVE_SYMBOL = "SLV"    # 1x conservative  
REFERENCE_SYMBOL = "SLV"       # For signal generation
ASSET_NAME = "Silver"

# To switch to Gold:
TRADING_SYMBOL = "UGL"
CONSERVATIVE_SYMBOL = "GLD"
REFERENCE_SYMBOL = "GLD"
ASSET_NAME = "Gold"

# To switch to Oil:
TRADING_SYMBOL = "UCO"
CONSERVATIVE_SYMBOL = "USO"
REFERENCE_SYMBOL = "USO"
ASSET_NAME = "Oil"
```

### Adjust Thresholds
```python
ENTRY_THRESHOLD_MIN = 0.02        # 2% drop → buy conservative (SLV)
ENTRY_THRESHOLD_LEVERAGED = 0.04  # 4% drop → buy leveraged (AGQ)
TARGET_GAIN = 0.05                # 5% profit target (both)
STOP_LOSS_SLV = 0.05              # 5% stop (1x)
STOP_LOSS_AGQ = 0.07              # 7% stop (2x)
```

## Schwab API Setup

### 1. Create a Schwab Developer App
1. Go to [developer.schwab.com](https://developer.schwab.com)
2. Create an app with "Accounts and Trading" permissions
3. Note your App Key and Secret

### 2. Get OAuth Tokens
```bash
# You'll need to complete OAuth flow once to get refresh token
# The refresh token lasts 7 days and auto-renews when used
```

### 3. Get Account Hash
```bash
# After authentication, call GET /accounts to get your account hash
# It looks like: "encrypted_account_hash_string"
```

### 4. Add to GitHub Secrets
Go to your repo → Settings → Secrets and variables → Actions:
- `SCHWAB_APP_KEY`
- `SCHWAB_APP_SECRET`
- `SCHWAB_REFRESH_TOKEN`
- `SCHWAB_ACCOUNT_HASH`
- `TWELVE_DATA_API_KEY`

## Signal Types

| Signal | Meaning | Action |
|--------|---------|--------|
| `BUY` | Drop threshold met, filters green | Buy SLV or AGQ |
| `SELL_TARGET` | +5% gain reached | SELL - Lock it in! |
| `SELL_STOP` | Stop loss hit | Exit position |
| `SELL_TIME` | Max hold period | Evaluate exit |
| `FILTERS_OFF` | PSAR turned red | No trades / consider exit |
| `NO_SIGNAL` | Waiting | No action |

## Project Structure

```
silversnap/
├── config.py           # Configuration (symbols, thresholds)
├── main.py             # CLI entry point
├── signals.py          # Signal generation logic
├── indicators.py       # PSAR and RSI calculations
├── data_fetcher.py     # Twelve Data API
├── schwab_client.py    # Schwab API integration
├── .github/
│   └── workflows/
│       └── signal-check.yml  # Automated runs
└── README.md
```

## Risk Considerations

⚠️ **This is experimental** - Start with capital you can afford to lose.

- **Post-market spreads** can be wide on leveraged ETFs (use limit orders)
- **Gap risk** - overnight/weekend news can cause large gaps
- **Mean reversion fails in trends** - that's why the PSAR filters are critical
- **Leveraged ETF decay** - AGQ is not for long-term holding

## License

MIT - Use at your own risk.

---

*Built for systematic trading discipline. No FOMO, no emotion - just signals.*
