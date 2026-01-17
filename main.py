#!/usr/bin/env python3
"""
SilverSnap - Mean Reversion Strategy Runner
============================================

Usage:
    python main.py status           # Show current status and signal
    python main.py status --live    # Use Schwab API for live data
    python main.py run --live       # Run strategy with live execution
    python main.py watch            # Continuous monitoring mode
    python main.py positions        # Show current Schwab positions
    
Environment Variables:
    TWELVE_DATA_API_KEY    - For historical data (filters)
    SCHWAB_APP_KEY         - Schwab API app key
    SCHWAB_APP_SECRET      - Schwab API app secret
    SCHWAB_REFRESH_TOKEN   - Schwab OAuth refresh token
    SCHWAB_ACCOUNT_HASH    - Schwab account hash
"""

import sys
import os
import time
import json
from datetime import datetime
import argparse

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from signals import SignalGenerator, SignalType, print_status
from data_fetcher import DataFetcher


def get_schwab_client():
    """Get Schwab client, with helpful error if not configured"""
    try:
        from schwab_client import SchwabClient
        return SchwabClient()
    except ValueError as e:
        print(f"\n❌ Schwab API not configured: {e}")
        print("\n💡 Set these environment variables or GitHub secrets:")
        print("   SCHWAB_APP_KEY")
        print("   SCHWAB_APP_SECRET")
        print("   SCHWAB_REFRESH_TOKEN")
        print("   SCHWAB_ACCOUNT_HASH")
        sys.exit(1)


def cmd_status(live: bool = False):
    """Show current status and signal"""
    print("\n🔄 Fetching data...")
    
    try:
        if live:
            print("   Using Schwab API for live quotes...")
            from schwab_client import SchwabDataFetcher
            fetcher = SchwabDataFetcher()
        else:
            fetcher = DataFetcher()
        
        generator = SignalGenerator(data_fetcher=fetcher)
        status = generator.get_status()
        print_status(status)
        
        # Also save to file
        with open('last_status.json', 'w') as f:
            json.dump(status, f, indent=2, default=str)
        print(f"\n  Status saved to last_status.json")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        if "API key" in str(e) or "TWELVE_DATA" in str(e):
            print("\n💡 Set your API key:")
            print("   export TWELVE_DATA_API_KEY='your-key-here'")
        raise


def cmd_run(live: bool = False, dry_run: bool = True):
    """
    Run the strategy - check signal and execute if appropriate
    
    Args:
        live: Use Schwab API for live data and execution
        dry_run: If True, don't actually execute trades
    """
    print("\n🚀 SilverSnap Strategy Run")
    print(f"   Mode: {'LIVE' if live else 'Paper'}")
    print(f"   Execution: {'DRY RUN' if dry_run else '⚠️  LIVE TRADING'}")
    print("="*60)
    
    if live:
        from schwab_client import SchwabClient, SchwabDataFetcher, execute_entry, execute_exit
        client = get_schwab_client()
        fetcher = SchwabDataFetcher(client)
    else:
        fetcher = DataFetcher()
        client = None
    
    generator = SignalGenerator(data_fetcher=fetcher)
    
    # Check for existing position in Schwab
    existing_position = None
    if live and client:
        positions = client.get_positions()
        for symbol in [config.TRADING_SYMBOL, config.CONSERVATIVE_SYMBOL]:
            if symbol in positions and positions[symbol]["quantity"] > 0:
                existing_position = positions[symbol]
                generator.record_entry(
                    price=existing_position["averagePrice"],
                    shares=int(existing_position["quantity"])
                )
                generator.current_position.symbol = symbol
                print(f"\n📊 Found existing position: {symbol}")
                print(f"   Shares: {existing_position['quantity']}")
                print(f"   Avg Price: ${existing_position['averagePrice']:.2f}")
                break
    
    # Get current signal
    status = generator.get_status()
    print_status(status)
    
    signal = status['signal']
    signal_type = signal['signal_type']
    
    # Execute based on signal
    if signal_type == 'BUY':
        symbol = signal['symbol']
        price = status['prices']['agq_price'] if symbol == config.TRADING_SYMBOL else status['prices']['slv_price']
        
        if dry_run:
            shares = int(config.CAPITAL // price)
            print(f"\n🔔 DRY RUN: Would BUY {shares} shares of {symbol} @ ${price:.2f}")
            print(f"   Capital: ${config.CAPITAL:.2f}")
        elif live and client:
            print(f"\n⚡ EXECUTING: BUY {symbol}")
            result = execute_entry(client, symbol, config.CAPITAL, use_limit=True, session="SEAMLESS")
            print(f"   Order ID: {result.get('orderId')}")
            print(f"   Shares: {result.get('shares')}")
            print(f"   Status: {result.get('status')}")
            
            # Save position
            with open('position.json', 'w') as f:
                json.dump({
                    'symbol': symbol,
                    'shares': result.get('shares'),
                    'entry_price': result.get('price'),
                    'entry_time': datetime.now().isoformat(),
                    'order_id': result.get('orderId')
                }, f, indent=2)
    
    elif signal_type in ['SELL_TARGET', 'SELL_STOP', 'SELL_TIME']:
        if existing_position:
            symbol = existing_position['symbol'] if isinstance(existing_position, dict) else generator.current_position.symbol
            shares = int(existing_position['quantity']) if isinstance(existing_position, dict) else generator.current_position.shares
            
            if dry_run:
                print(f"\n🔔 DRY RUN: Would SELL {shares} shares of {symbol}")
            elif live and client:
                print(f"\n⚡ EXECUTING: SELL {symbol}")
                result = execute_exit(client, symbol, shares, use_limit=True, session="SEAMLESS")
                print(f"   Order ID: {result.get('orderId')}")
                print(f"   Shares: {shares}")
                print(f"   Status: {result.get('status')}")
                
                # Clear position file
                if os.path.exists('position.json'):
                    os.remove('position.json')
        else:
            print(f"\n⚠️  {signal_type} signal but no position found")
    
    elif signal_type == 'FILTERS_OFF':
        print(f"\n🔴 Filters are OFF - no trading allowed")
        if existing_position:
            print(f"   ⚠️  Consider manually exiting position in {existing_position.get('symbol', 'unknown')}")
    
    else:
        print(f"\n⏸️  No action needed - {signal_type}")
    
    # Save status
    with open('last_status.json', 'w') as f:
        json.dump(status, f, indent=2, default=str)
    
    return status


def cmd_auth():
    """Authenticate with Schwab - run this first!"""
    print("\n🔐 Schwab Authentication")
    print("="*60)
    
    from schwab_client import SchwabClient
    
    client = SchwabClient()
    if client.authenticate():
        print("\n✅ Authentication successful!")
        print(f"   Tokens saved to: schwab_tokens.json")
        print(f"   Account hash: {client.account_hash}")
        print("\n   For GitHub Actions, create a secret named SCHWAB_TOKEN_FILE")
        print("   with the contents of schwab_tokens.json")
    else:
        print("\n❌ Authentication failed")


def cmd_accounts():
    """Discover Schwab account hashes - run this first if you don't know your account hash"""
    print("\n🔍 Discovering Schwab Accounts...")
    print("="*60)
    
    # Check we have the basic credentials
    import os
    app_key = os.environ.get('SCHWAB_APP_KEY', '')
    app_secret = os.environ.get('SCHWAB_APP_SECRET', '')
    refresh_token = os.environ.get('SCHWAB_REFRESH_TOKEN', '')
    
    if not all([app_key, app_secret, refresh_token]):
        print("\n❌ Missing credentials. Need:")
        print(f"   SCHWAB_APP_KEY: {'✅' if app_key else '❌'}")
        print(f"   SCHWAB_APP_SECRET: {'✅' if app_secret else '❌'}")
        print(f"   SCHWAB_REFRESH_TOKEN: {'✅' if refresh_token else '❌'}")
        print("\n💡 Export these first, then run this command to get your account hash.")
        return
    
    import base64
    import requests
    
    # Get access token
    auth_string = f"{app_key}:{app_secret}"
    auth_bytes = base64.b64encode(auth_string.encode()).decode()
    
    print("\n   Getting access token...")
    token_response = requests.post(
        "https://api.schwabapi.com/v1/oauth/token",
        headers={
            "Authorization": f"Basic {auth_bytes}",
            "Content-Type": "application/x-www-form-urlencoded"
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }
    )
    
    if token_response.status_code != 200:
        print(f"\n❌ Token error: {token_response.status_code}")
        print(f"   {token_response.text}")
        return
    
    access_token = token_response.json()["access_token"]
    print("   ✅ Got access token")
    
    # Get accounts
    print("   Fetching accounts...")
    accounts_response = requests.get(
        "https://api.schwabapi.com/trader/v1/accounts",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    
    if accounts_response.status_code != 200:
        print(f"\n❌ Accounts error: {accounts_response.status_code}")
        print(f"   {accounts_response.text}")
        return
    
    accounts = accounts_response.json()
    
    print(f"\n   Found {len(accounts)} account(s):\n")
    
    for i, account in enumerate(accounts):
        sec_account = account.get("securitiesAccount", {})
        account_hash = account.get("hashValue", "N/A")
        account_num = sec_account.get("accountNumber", "N/A")
        account_type = sec_account.get("type", "N/A")
        
        balances = sec_account.get("currentBalances", {})
        cash = balances.get("cashBalance", 0)
        
        print(f"   Account {i+1}:")
        print(f"      Number: {account_num}")
        print(f"      Type: {account_type}")
        print(f"      Cash: ${cash:,.2f}")
        print(f"      Hash: {account_hash}")
        print()
    
    if accounts:
        first_hash = accounts[0].get("hashValue", "")
        print(f"   💡 To use the first account, run:")
        print(f"      export SCHWAB_ACCOUNT_HASH='{first_hash}'")
    
    print("="*60)


def cmd_positions():
    """Show current Schwab positions"""
    print("\n📊 Schwab Positions")
    print("="*60)
    
    client = get_schwab_client()
    
    # Get account info
    buying_power = client.get_buying_power()
    print(f"\n  Buying Power: ${buying_power:,.2f}")
    
    # Get positions
    positions = client.get_positions()
    
    if not positions:
        print("\n  No positions")
    else:
        print(f"\n  Positions ({len(positions)}):")
        for symbol, pos in positions.items():
            pnl = pos['currentDayProfitLoss']
            pnl_pct = pos['currentDayProfitLossPercentage']
            pnl_color = '🟢' if pnl >= 0 else '🔴'
            print(f"\n    {symbol}:")
            print(f"      Qty: {pos['quantity']}")
            print(f"      Avg Price: ${pos['averagePrice']:.2f}")
            print(f"      Market Value: ${pos['marketValue']:,.2f}")
            print(f"      Today P&L: {pnl_color} ${pnl:,.2f} ({pnl_pct:.2f}%)")
    
    # Check for SLV/AGQ specifically
    slv_agq = [s for s in [config.TRADING_SYMBOL, config.CONSERVATIVE_SYMBOL] if s in positions]
    if slv_agq:
        print(f"\n  🎯 Strategy positions: {', '.join(slv_agq)}")
    else:
        print(f"\n  ℹ️  No {config.TRADING_SYMBOL}/{config.CONSERVATIVE_SYMBOL} positions")
    
    print("="*60)


def cmd_watch(interval: int = 60, live: bool = False):
    """
    Continuous monitoring mode
    
    Args:
        interval: Seconds between checks
        live: Use Schwab API
    """
    print(f"\n👁️  SilverSnap Watch Mode - Checking every {interval}s")
    print(f"   Data source: {'Schwab API' if live else 'Twelve Data'}")
    print("   Press Ctrl+C to stop\n")
    
    if live:
        from schwab_client import SchwabDataFetcher
        fetcher = SchwabDataFetcher()
    else:
        fetcher = DataFetcher()
    
    generator = SignalGenerator(data_fetcher=fetcher)
    last_signal_type = None
    
    while True:
        try:
            status = generator.get_status()
            
            # Clear screen and print status
            os.system('clear' if os.name == 'posix' else 'cls')
            print_status(status)
            
            # Alert on signal change
            current_signal = status['signal']['signal_type']
            if current_signal != last_signal_type:
                if current_signal in ['BUY', 'SELL_TARGET', 'SELL_STOP']:
                    print("\n🔔 SIGNAL CHANGE! 🔔")
                    print(f"   {status['signal']['message']}")
                last_signal_type = current_signal
            
            # Save status
            with open('last_status.json', 'w') as f:
                json.dump(status, f, indent=2, default=str)
            
            print(f"\n   Next check in {interval}s...")
            time.sleep(interval)
            
        except KeyboardInterrupt:
            print("\n\n👋 Stopping watch mode")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print(f"   Retrying in {interval}s...")
            time.sleep(interval)


def cmd_filters():
    """Show detailed filter status"""
    print("\n🔍 Filter Analysis")
    print("="*60)
    
    generator = SignalGenerator()
    filter_status = generator.check_filters()
    
    print(f"\n  Reference Symbol: {config.REFERENCE_SYMBOL}")
    print(f"\n  PSAR on Price:")
    print(f"    Status: {'🟢 GREEN (Bullish)' if filter_status['price_filter_green'] else '🔴 RED (Bearish)'}")
    if filter_status['price_psar_value']:
        print(f"    PSAR Value: ${filter_status['price_psar_value']:.2f}")
    print(f"    Trend: {filter_status['price_psar_trend']}")
    
    print(f"\n  PSAR on RSI:")
    print(f"    Status: {'🟢 GREEN (Bullish)' if filter_status['rsi_filter_green'] else '🔴 RED (Bearish)'}")
    if filter_status['rsi_psar_value']:
        print(f"    RSI PSAR Value: {filter_status['rsi_psar_value']:.2f}")
    print(f"    RSI Trend: {filter_status['rsi_psar_trend']}")
    if filter_status['current_rsi']:
        print(f"    Current RSI: {filter_status['current_rsi']:.2f}")
    
    print(f"\n  Master Switch: {'🟢 ON - TRADING ALLOWED' if filter_status['master_switch_active'] else '🔴 OFF - NO TRADING'}")
    print("="*60)


def cmd_config():
    """Show current configuration"""
    print("\n⚙️  SilverSnap Configuration")
    print("="*60)
    
    print(f"\n  Asset: {config.ASSET_NAME}")
    print(f"  Trading Symbol (2x): {config.TRADING_SYMBOL}")
    print(f"  Conservative Symbol (1x): {config.CONSERVATIVE_SYMBOL}")
    print(f"  Reference Symbol: {config.REFERENCE_SYMBOL}")
    
    print(f"\n  Entry Thresholds (Tiered):")
    print(f"    2-4% drop → Buy {config.CONSERVATIVE_SYMBOL} (1x)")
    print(f"    4%+  drop → Buy {config.TRADING_SYMBOL} (2x)")
    
    print(f"\n  Exit Thresholds:")
    print(f"    Target Gain: {config.TARGET_GAIN:.0%} (both)")
    print(f"    Stop Loss: {config.STOP_LOSS_SLV:.0%} ({config.CONSERVATIVE_SYMBOL}) / {config.STOP_LOSS_AGQ:.0%} ({config.TRADING_SYMBOL})")
    print(f"    Max Hold Days: {config.MAX_HOLD_DAYS}")
    
    print(f"\n  Capital: ${config.CAPITAL:,.2f}")
    
    print(f"\n  Trading Windows (ET):")
    print(f"    Post-Market: {config.POSTMARKET_START} - {config.POSTMARKET_END}")
    print(f"    Sweet Spot: {config.POSTMARKET_SWEET_SPOT_START} - {config.POSTMARKET_SWEET_SPOT_END}")
    print(f"    Exit Window: {config.EXIT_WINDOW_START} - {config.EXIT_WINDOW_END}")
    
    # Check API keys
    td_key = config.TWELVE_DATA_API_KEY or os.environ.get('TWELVE_DATA_API_KEY', '')
    schwab_key = os.environ.get('SCHWAB_APP_KEY', '')
    
    print(f"\n  API Status:")
    print(f"    Twelve Data: {'✅ Set' if td_key else '❌ Not Set'}")
    print(f"    Schwab: {'✅ Set' if schwab_key else '❌ Not Set'}")
    
    print("="*60)


def main():
    parser = argparse.ArgumentParser(
        description='SilverSnap - Mean Reversion Strategy',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py status              # Check current signal (Twelve Data)
    python main.py status --live       # Check signal using Schwab API
    python main.py run --live          # Run strategy, dry run mode
    python main.py run --live --execute  # Run strategy with LIVE execution
    python main.py positions           # Show Schwab positions
    python main.py watch --live        # Monitor using Schwab API
    python main.py filters             # Show PSAR filter status
    python main.py config              # Show configuration
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show current status and signal')
    status_parser.add_argument('--live', action='store_true', help='Use Schwab API for live quotes')
    
    # Run command (main strategy execution)
    run_parser = subparsers.add_parser('run', help='Run strategy and execute trades')
    run_parser.add_argument('--live', action='store_true', help='Use Schwab API for live data')
    run_parser.add_argument('--execute', action='store_true', help='Actually execute trades (default is dry run)')
    
    # Auth command
    auth_parser = subparsers.add_parser('auth', help='Authenticate with Schwab (run this first!)')
    
    # Accounts discovery command
    accounts_parser = subparsers.add_parser('accounts', help='Discover Schwab account hashes')
    
    # Positions command
    positions_parser = subparsers.add_parser('positions', help='Show Schwab positions')
    
    # Watch command
    watch_parser = subparsers.add_parser('watch', help='Continuous monitoring mode')
    watch_parser.add_argument('--interval', '-i', type=int, default=60,
                              help='Seconds between checks (default: 60)')
    watch_parser.add_argument('--live', action='store_true', help='Use Schwab API')
    
    # Filters command
    filters_parser = subparsers.add_parser('filters', help='Show detailed filter status')
    
    # Config command
    config_parser = subparsers.add_parser('config', help='Show configuration')
    
    args = parser.parse_args()
    
    if args.command == 'status':
        cmd_status(live=args.live)
    elif args.command == 'run':
        cmd_run(live=args.live, dry_run=not args.execute)
    elif args.command == 'auth':
        cmd_auth()
    elif args.command == 'accounts':
        cmd_accounts()
    elif args.command == 'positions':
        cmd_positions()
    elif args.command == 'watch':
        cmd_watch(interval=args.interval, live=args.live)
    elif args.command == 'filters':
        cmd_filters()
    elif args.command == 'config':
        cmd_config()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
