"""
Signal Generator for SilverSnap
================================
Core logic for generating buy/sell signals based on mean reversion
"""

import json
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict
from enum import Enum

import config
from indicators import master_switch_active, get_filter_status
from data_fetcher import DataFetcher, Quote


class SignalType(Enum):
    NO_SIGNAL = "NO_SIGNAL"
    BUY = "BUY"
    SELL_TARGET = "SELL_TARGET"
    SELL_STOP = "SELL_STOP"
    SELL_TIME = "SELL_TIME"
    FILTERS_OFF = "FILTERS_OFF"


@dataclass
class Signal:
    """Trading signal"""
    timestamp: datetime
    signal_type: SignalType
    symbol: str
    reference_symbol: str
    current_price: float
    reference_close: float
    drop_pct: float
    filters_active: bool
    price_filter_green: bool
    rsi_filter_green: bool
    current_rsi: Optional[float]
    message: str
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        d['timestamp'] = self.timestamp.isoformat()
        d['signal_type'] = self.signal_type.value
        return d
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass 
class Position:
    """Current position tracking"""
    symbol: str
    entry_price: float
    entry_time: datetime
    shares: int
    cost_basis: float
    
    def current_pnl(self, current_price: float) -> float:
        return (current_price - self.entry_price) * self.shares
    
    def current_pnl_pct(self, current_price: float) -> float:
        return (current_price - self.entry_price) / self.entry_price
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'entry_price': self.entry_price,
            'entry_time': self.entry_time.isoformat(),
            'shares': self.shares,
            'cost_basis': self.cost_basis
        }


class SignalGenerator:
    """
    Generates trading signals based on:
    1. PSAR filters (master switch)
    2. Drop from close thresholds (tiered: SLV vs AGQ)
    3. Position management (targets/stops)
    """
    
    def __init__(self, data_fetcher: DataFetcher = None):
        self.fetcher = data_fetcher or DataFetcher()
        self.current_position: Optional[Position] = None
        self.signals_log: List[Signal] = []
        
        # Load config values
        self.trading_symbol = config.TRADING_SYMBOL  # AGQ (2x)
        self.conservative_symbol = config.CONSERVATIVE_SYMBOL  # SLV (1x)
        self.reference_symbol = config.REFERENCE_SYMBOL  # SLV for signals
        
        # Tiered entry thresholds
        self.entry_threshold_min = config.ENTRY_THRESHOLD_MIN  # 2% = SLV
        self.entry_threshold_leveraged = config.ENTRY_THRESHOLD_LEVERAGED  # 4% = AGQ
        
        # Exit thresholds
        self.target_gain = config.TARGET_GAIN  # 5% for both
        self.stop_loss_slv = config.STOP_LOSS_SLV  # 5% stop for SLV
        self.stop_loss_agq = config.STOP_LOSS_AGQ  # 7% stop for AGQ
        
        self.capital = config.CAPITAL
    
    def _get_stop_loss_for_symbol(self, symbol: str) -> float:
        """Get the appropriate stop loss for the symbol"""
        if symbol == self.trading_symbol:  # AGQ
            return self.stop_loss_agq
        else:  # SLV
            return self.stop_loss_slv
    
    def _determine_entry_symbol(self, drop_pct: float) -> Optional[str]:
        """
        Determine which symbol to buy based on drop percentage
        
        Returns:
            Symbol to buy, or None if drop not sufficient
        """
        if drop_pct >= self.entry_threshold_leveraged:
            return self.trading_symbol  # AGQ for 4%+ drops
        elif drop_pct >= self.entry_threshold_min:
            return self.conservative_symbol  # SLV for 2-4% drops
        else:
            return None  # No entry
    
    def check_filters(self) -> Dict:
        """
        Check if PSAR filters allow trading
        
        Returns dict with filter status and details
        """
        # Get reference symbol data for filter calculation
        data = self.fetcher.get_filter_data(
            self.reference_symbol, 
            config.DATA_LOOKBACK_DAYS
        )
        
        is_active, details = master_switch_active(
            data['highs'],
            data['lows'],
            data['closes'],
            rsi_period=config.RSI_PERIOD,
            psar_af_start=config.PSAR_AF_START,
            psar_af_increment=config.PSAR_AF_INCREMENT,
            psar_af_max=config.PSAR_AF_MAX
        )
        
        return {
            'filters_active': is_active,
            **details
        }
    
    def get_current_drop(self) -> Dict:
        """
        Get current price drop from regular session close
        
        Returns dict with drop information for both instruments
        """
        # Get reference symbol quote (SLV for signals)
        ref_quote = self.fetcher.get_quote(self.reference_symbol)
        
        # Get both trading symbol quotes
        agq_quote = self.fetcher.get_quote(self.trading_symbol)
        slv_quote = ref_quote  # SLV is both reference and conservative
        
        # Calculate drop from reference close
        drop = ref_quote.regular_close - ref_quote.last_price
        drop_pct = drop / ref_quote.regular_close if ref_quote.regular_close > 0 else 0
        
        return {
            'reference_symbol': self.reference_symbol,
            'reference_price': ref_quote.last_price,
            'reference_close': ref_quote.regular_close,
            'reference_drop': drop,
            'reference_drop_pct': drop_pct,
            'slv_price': slv_quote.last_price,
            'agq_price': agq_quote.last_price,
            'trading_symbol': self.trading_symbol,
            'conservative_symbol': self.conservative_symbol,
            'is_extended_hours': ref_quote.is_extended_hours,
            'timestamp': ref_quote.timestamp
        }
    
    def generate_signal(self) -> Signal:
        """
        Generate current trading signal
        
        Returns Signal object with recommendation
        """
        # Check filters first
        filter_status = self.check_filters()
        
        # Get current drop
        drop_info = self.get_current_drop()
        
        # If we have a position, check exit conditions first
        if self.current_position:
            return self._check_exit_signal(filter_status, drop_info)
        
        # No position - check entry conditions
        return self._check_entry_signal(filter_status, drop_info)
    
    def _check_entry_signal(self, filter_status: Dict, drop_info: Dict) -> Signal:
        """Check for entry signal - tiered SLV (2-4% drop) vs AGQ (4%+ drop)"""
        
        timestamp = drop_info['timestamp']
        drop_pct = drop_info['reference_drop_pct']
        
        # Determine which symbol to buy based on drop
        entry_symbol = self._determine_entry_symbol(drop_pct)
        
        # Get the appropriate price for the entry symbol
        if entry_symbol == self.trading_symbol:  # AGQ
            entry_price = drop_info['agq_price']
        elif entry_symbol == self.conservative_symbol:  # SLV
            entry_price = drop_info['slv_price']
        else:
            entry_price = drop_info['slv_price']  # Default for display
        
        # Base signal data
        base_data = {
            'timestamp': timestamp,
            'symbol': entry_symbol or self.conservative_symbol,
            'reference_symbol': self.reference_symbol,
            'current_price': entry_price,
            'reference_close': drop_info['reference_close'],
            'drop_pct': drop_pct,
            'filters_active': filter_status['master_switch_active'],
            'price_filter_green': filter_status['price_filter_green'],
            'rsi_filter_green': filter_status['rsi_filter_green'],
            'current_rsi': filter_status.get('current_rsi'),
        }
        
        # Check if filters are off
        if not filter_status['master_switch_active']:
            return Signal(
                **base_data,
                signal_type=SignalType.FILTERS_OFF,
                message=f"Filters OFF - Price PSAR: {'GREEN' if filter_status['price_filter_green'] else 'RED'}, "
                        f"RSI PSAR: {'GREEN' if filter_status['rsi_filter_green'] else 'RED'}. NO TRADING."
            )
        
        # Check if drop meets thresholds
        if entry_symbol == self.trading_symbol:  # AGQ for 4%+ drops
            return Signal(
                **base_data,
                signal_type=SignalType.BUY,
                message=f"🟢 BUY AGQ (2x) - {self.reference_symbol} down {drop_pct:.2%} (≥4%). "
                        f"Buy {self.trading_symbol} @ ${entry_price:.2f}"
            )
        elif entry_symbol == self.conservative_symbol:  # SLV for 2-4% drops
            return Signal(
                **base_data,
                signal_type=SignalType.BUY,
                message=f"🟡 BUY SLV (1x) - {self.reference_symbol} down {drop_pct:.2%} (2-4%). "
                        f"Buy {self.conservative_symbol} @ ${entry_price:.2f}"
            )
        
        # No signal - drop not sufficient
        return Signal(
            **base_data,
            signal_type=SignalType.NO_SIGNAL,
            message=f"No signal - {self.reference_symbol} only down {drop_pct:.2%}. "
                    f"Need {self.entry_threshold_min:.0%}+ for SLV, {self.entry_threshold_leveraged:.0%}+ for AGQ."
        )
    
    def _check_exit_signal(self, filter_status: Dict, drop_info: Dict) -> Signal:
        """Check for exit signal when we have a position"""
        
        timestamp = drop_info['timestamp']
        
        # Get current price for the symbol we're holding
        if self.current_position.symbol == self.trading_symbol:  # AGQ
            current_price = drop_info['agq_price']
        else:  # SLV
            current_price = drop_info['slv_price']
        
        pnl_pct = self.current_position.current_pnl_pct(current_price)
        
        # Get appropriate stop loss for this position
        stop_loss = self._get_stop_loss_for_symbol(self.current_position.symbol)
        
        base_data = {
            'timestamp': timestamp,
            'symbol': self.current_position.symbol,
            'reference_symbol': self.reference_symbol,
            'current_price': current_price,
            'reference_close': drop_info['reference_close'],
            'drop_pct': drop_info['reference_drop_pct'],
            'filters_active': filter_status['master_switch_active'],
            'price_filter_green': filter_status['price_filter_green'],
            'rsi_filter_green': filter_status['rsi_filter_green'],
            'current_rsi': filter_status.get('current_rsi'),
        }
        
        # Check target - 5% for both SLV and AGQ
        if pnl_pct >= self.target_gain:
            return Signal(
                **base_data,
                signal_type=SignalType.SELL_TARGET,
                message=f"🎯 TARGET HIT (+5%) - {self.current_position.symbol} up {pnl_pct:.2%} from entry. "
                        f"SELL @ ${current_price:.2f} - LOCK IT IN!"
            )
        
        # Check stop loss (different for SLV vs AGQ)
        if pnl_pct <= -stop_loss:
            return Signal(
                **base_data,
                signal_type=SignalType.SELL_STOP,
                message=f"🛑 STOP LOSS ({stop_loss:.0%}) - {self.current_position.symbol} down {pnl_pct:.2%} from entry. "
                        f"SELL @ ${current_price:.2f}"
            )
        
        # Check if filters turned off (exit if trend breaks)
        if not filter_status['master_switch_active']:
            return Signal(
                **base_data,
                signal_type=SignalType.FILTERS_OFF,
                message=f"⚠️ FILTERS TURNED OFF - Consider exiting {self.current_position.symbol}. "
                        f"Current P&L: {pnl_pct:.2%}"
            )
        
        # Check time stop (simplified - would need more logic for multi-day)
        hold_duration = timestamp - self.current_position.entry_time
        if hold_duration.days >= config.MAX_HOLD_DAYS:
            return Signal(
                **base_data,
                signal_type=SignalType.SELL_TIME,
                message=f"⏰ TIME STOP - {self.current_position.symbol} held {hold_duration.days} days. "
                        f"Current P&L: {pnl_pct:.2%}. Consider exiting."
            )
        
        # No exit signal - show holding status
        return Signal(
            **base_data,
            signal_type=SignalType.NO_SIGNAL,
            message=f"HOLDING {self.current_position.symbol} - P&L: {pnl_pct:.2%}. "
                    f"Target: +{self.target_gain:.0%}, Stop: -{stop_loss:.0%}"
        )
    
    def record_entry(self, price: float, shares: int):
        """Record a new position"""
        self.current_position = Position(
            symbol=self.trading_symbol,
            entry_price=price,
            entry_time=datetime.now(),
            shares=shares,
            cost_basis=price * shares
        )
    
    def record_exit(self, price: float) -> Dict:
        """
        Record position exit and return trade summary
        """
        if not self.current_position:
            return {'error': 'No position to exit'}
        
        pnl = self.current_position.current_pnl(price)
        pnl_pct = self.current_position.current_pnl_pct(price)
        
        result = {
            'symbol': self.current_position.symbol,
            'entry_price': self.current_position.entry_price,
            'exit_price': price,
            'shares': self.current_position.shares,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'hold_duration': str(datetime.now() - self.current_position.entry_time)
        }
        
        self.current_position = None
        return result
    
    def get_status(self) -> Dict:
        """Get full current status"""
        filter_status = self.check_filters()
        drop_info = self.get_current_drop()
        
        status = {
            'timestamp': datetime.now().isoformat(),
            'asset': config.ASSET_NAME,
            'trading_symbol': self.trading_symbol,
            'conservative_symbol': self.conservative_symbol,
            'reference_symbol': self.reference_symbol,
            'filters': {
                'master_switch': 'ON' if filter_status['master_switch_active'] else 'OFF',
                'price_psar': 'GREEN' if filter_status['price_filter_green'] else 'RED',
                'rsi_psar': 'GREEN' if filter_status['rsi_filter_green'] else 'RED',
                'current_rsi': filter_status.get('current_rsi'),
            },
            'prices': {
                'reference_price': drop_info['reference_price'],
                'reference_close': drop_info['reference_close'],
                'drop_pct': drop_info['reference_drop_pct'],
                'slv_price': drop_info['slv_price'],
                'agq_price': drop_info['agq_price'],
                'is_extended_hours': drop_info['is_extended_hours'],
            },
            'thresholds': {
                'entry_slv': f"{self.entry_threshold_min:.0%}-{self.entry_threshold_leveraged:.0%}",
                'entry_agq': f"{self.entry_threshold_leveraged:.0%}+",
                'target': self.target_gain,
                'stop_slv': self.stop_loss_slv,
                'stop_agq': self.stop_loss_agq,
            },
            'position': self.current_position.to_dict() if self.current_position else None,
        }
        
        # Add signal
        signal = self.generate_signal()
        status['signal'] = signal.to_dict()
        
        return status


def print_status(status: Dict):
    """Pretty print the status"""
    print("\n" + "="*60)
    print(f"  SilverSnap Status - {status['asset']}")
    print(f"  {status['timestamp']}")
    print("="*60)
    
    # Filters
    f = status['filters']
    master = f['master_switch']
    master_color = '🟢' if master == 'ON' else '🔴'
    print(f"\n  Master Switch: {master_color} {master}")
    print(f"    Price PSAR: {'🟢' if f['price_psar'] == 'GREEN' else '🔴'} {f['price_psar']}")
    print(f"    RSI PSAR:   {'🟢' if f['rsi_psar'] == 'GREEN' else '🔴'} {f['rsi_psar']}")
    if f['current_rsi']:
        print(f"    Current RSI: {f['current_rsi']:.1f}")
    
    # Prices
    p = status['prices']
    print(f"\n  {status['reference_symbol']} (Reference):")
    print(f"    Current: ${p['reference_price']:.2f}")
    print(f"    Close:   ${p['reference_close']:.2f}")
    drop_indicator = '📉' if p['drop_pct'] > 0 else '📈'
    print(f"    Drop:    {drop_indicator} {p['drop_pct']:.2%}")
    print(f"    Extended Hours: {'Yes' if p['is_extended_hours'] else 'No'}")
    
    print(f"\n  Prices:")
    print(f"    SLV: ${p['slv_price']:.2f}")
    print(f"    AGQ: ${p['agq_price']:.2f}")
    
    # Thresholds
    t = status['thresholds']
    print(f"\n  Entry Thresholds:")
    print(f"    📉 2-4% drop → Buy SLV (1x)")
    print(f"    📉 4%+  drop → Buy AGQ (2x)")
    print(f"  Exit:")
    print(f"    🎯 +{t['target']:.0%} target (both)")
    print(f"    🛑 -{t['stop_slv']:.0%} stop (SLV) / -{t['stop_agq']:.0%} stop (AGQ)")
    
    # Position
    if status['position']:
        pos = status['position']
        print(f"\n  Position:")
        print(f"    Symbol: {pos['symbol']}")
        print(f"    Entry: ${pos['entry_price']:.2f}")
        print(f"    Shares: {pos['shares']}")
    
    # Signal
    sig = status['signal']
    print(f"\n  Signal: {sig['signal_type']}")
    print(f"  {sig['message']}")
    
    print("\n" + "="*60)
