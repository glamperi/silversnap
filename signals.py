"""
Signal Generator for SilverSnap - Long-Only Dip Buyer
======================================================
Buy dips in SLV (2-4% drop) or AGQ (4%+ drop) when master switch is ON
Exit at +5% target, stop loss, or time limit
"""

import json
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict
from enum import Enum

import config
from indicators import get_filter_status, FilterStatus
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
    master_switch_on: bool
    details: Dict
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
    Generates trading signals for long-only dip buying
    
    Master Switch ON → Buy dips in SLV/AGQ
    Master Switch OFF → No trades (wait for green light)
    """
    
    def __init__(self, data_fetcher: DataFetcher = None):
        self.fetcher = data_fetcher or DataFetcher()
        self.current_position: Optional[Position] = None
        self.signals_log: List[Signal] = []
        
        # Symbols
        self.trading_symbol = config.TRADING_SYMBOL  # AGQ (2x)
        self.conservative_symbol = config.CONSERVATIVE_SYMBOL  # SLV (1x)
        self.reference_symbol = config.REFERENCE_SYMBOL
        
        # Entry thresholds
        self.entry_threshold_min = config.ENTRY_THRESHOLD_MIN
        self.entry_threshold_leveraged = config.ENTRY_THRESHOLD_LEVERAGED
        
        # Exit thresholds
        self.target_gain = config.TARGET_GAIN
        self.stop_loss_slv = config.STOP_LOSS_SLV
        self.stop_loss_agq = config.STOP_LOSS_AGQ
        
        self.capital = config.CAPITAL
    
    def _get_stop_loss_for_symbol(self, symbol: str) -> float:
        """Get the appropriate stop loss for the symbol"""
        if symbol == self.trading_symbol:  # AGQ
            return self.stop_loss_agq
        return self.stop_loss_slv  # SLV
    
    def _determine_entry_symbol(self, drop_pct: float) -> Optional[str]:
        """Determine which symbol to buy based on drop percentage"""
        if drop_pct >= self.entry_threshold_leveraged:
            return self.trading_symbol  # AGQ for 4%+ drops
        elif drop_pct >= self.entry_threshold_min:
            return self.conservative_symbol  # SLV for 2-4% drops
        return None
    
    def get_filter_status(self) -> FilterStatus:
        """Get current filter status"""
        data = self.fetcher.get_filter_data(
            self.reference_symbol, 
            config.DATA_LOOKBACK_DAYS
        )
        
        return get_filter_status(
            data['highs'],
            data['lows'],
            data['closes'],
            rsi_period=config.RSI_PERIOD,
            psar_af_start=config.PSAR_AF_START,
            psar_af_increment=config.PSAR_AF_INCREMENT,
            psar_af_max=config.PSAR_AF_MAX
        )
    
    def get_current_prices(self) -> Dict:
        """Get current prices for relevant symbols"""
        ref_quote = self.fetcher.get_quote(self.reference_symbol)
        agq_quote = self.fetcher.get_quote(self.trading_symbol)
        
        # Calculate drop from close
        drop = ref_quote.regular_close - ref_quote.last_price
        drop_pct = drop / ref_quote.regular_close if ref_quote.regular_close > 0 else 0
        
        return {
            'reference_symbol': self.reference_symbol,
            'reference_price': ref_quote.last_price,
            'reference_close': ref_quote.regular_close,
            'drop_pct': drop_pct,
            'slv_price': ref_quote.last_price,
            'agq_price': agq_quote.last_price,
            'is_extended_hours': ref_quote.is_extended_hours,
            'timestamp': ref_quote.timestamp
        }
    
    def generate_signal(self) -> Signal:
        """Generate current trading signal"""
        filter_status = self.get_filter_status()
        prices = self.get_current_prices()
        
        # If we have a position, check for exit
        if self.current_position:
            return self._check_exit(filter_status, prices)
        
        # No position - check for entry
        return self._check_entry(filter_status, prices)
    
    def _check_entry(self, filters: FilterStatus, prices: Dict) -> Signal:
        """Check for entry signal"""
        
        # Master switch must be ON
        if not filters.master_switch_on:
            which_off = []
            if not filters.price_psar_green:
                which_off.append("Price PSAR")
            if not filters.rsi_psar_green:
                which_off.append("RSI PSAR")
            
            return Signal(
                timestamp=datetime.now(),
                signal_type=SignalType.FILTERS_OFF,
                symbol="",
                reference_symbol=self.reference_symbol,
                current_price=prices['reference_price'],
                reference_close=prices['reference_close'],
                drop_pct=prices['drop_pct'],
                master_switch_on=False,
                details=self._filter_to_dict(filters),
                message=f"🔴 Master switch OFF ({', '.join(which_off)} red) - No trades"
            )
        
        # Check drop threshold
        drop_pct = prices['drop_pct']
        entry_symbol = self._determine_entry_symbol(drop_pct)
        
        if entry_symbol:
            leverage = "2x" if entry_symbol == self.trading_symbol else "1x"
            return Signal(
                timestamp=datetime.now(),
                signal_type=SignalType.BUY,
                symbol=entry_symbol,
                reference_symbol=self.reference_symbol,
                current_price=prices['agq_price'] if entry_symbol == self.trading_symbol else prices['slv_price'],
                reference_close=prices['reference_close'],
                drop_pct=drop_pct,
                master_switch_on=True,
                details=self._filter_to_dict(filters),
                message=f"🟢 BUY {entry_symbol} ({leverage}) - {self.reference_symbol} down {drop_pct:.2%}"
            )
        
        # Master switch ON but no dip
        return Signal(
            timestamp=datetime.now(),
            signal_type=SignalType.NO_SIGNAL,
            symbol="",
            reference_symbol=self.reference_symbol,
            current_price=prices['reference_price'],
            reference_close=prices['reference_close'],
            drop_pct=drop_pct,
            master_switch_on=True,
            details=self._filter_to_dict(filters),
            message=f"🟢 Master switch ON - Waiting for dip (need {self.entry_threshold_min:.0%}+, have {drop_pct:.2%})"
        )
    
    def _check_exit(self, filters: FilterStatus, prices: Dict) -> Signal:
        """Check for exit signal on current position"""
        pos = self.current_position
        current_price = prices['agq_price'] if pos.symbol == self.trading_symbol else prices['slv_price']
        
        pnl_pct = pos.current_pnl_pct(current_price)
        target = self.target_gain
        stop = self._get_stop_loss_for_symbol(pos.symbol)
        
        # Check target
        if pnl_pct >= target:
            return Signal(
                timestamp=datetime.now(),
                signal_type=SignalType.SELL_TARGET,
                symbol=pos.symbol,
                reference_symbol=self.reference_symbol,
                current_price=current_price,
                reference_close=prices['reference_close'],
                drop_pct=prices['drop_pct'],
                master_switch_on=filters.master_switch_on,
                details={'pnl_pct': pnl_pct, 'entry_price': pos.entry_price},
                message=f"🎯 SELL {pos.symbol} - Target hit! +{pnl_pct:.2%}"
            )
        
        # Check stop
        if pnl_pct <= -stop:
            return Signal(
                timestamp=datetime.now(),
                signal_type=SignalType.SELL_STOP,
                symbol=pos.symbol,
                reference_symbol=self.reference_symbol,
                current_price=current_price,
                reference_close=prices['reference_close'],
                drop_pct=prices['drop_pct'],
                master_switch_on=filters.master_switch_on,
                details={'pnl_pct': pnl_pct, 'entry_price': pos.entry_price},
                message=f"🛑 SELL {pos.symbol} - Stop loss! {pnl_pct:.2%}"
            )
        
        # Check time limit
        hold_days = (datetime.now() - pos.entry_time).days
        if hold_days >= config.MAX_HOLD_DAYS:
            return Signal(
                timestamp=datetime.now(),
                signal_type=SignalType.SELL_TIME,
                symbol=pos.symbol,
                reference_symbol=self.reference_symbol,
                current_price=current_price,
                reference_close=prices['reference_close'],
                drop_pct=prices['drop_pct'],
                master_switch_on=filters.master_switch_on,
                details={'pnl_pct': pnl_pct, 'hold_days': hold_days},
                message=f"⏰ SELL {pos.symbol} - Time limit ({hold_days} days), P&L: {pnl_pct:+.2%}"
            )
        
        # Hold position
        return Signal(
            timestamp=datetime.now(),
            signal_type=SignalType.NO_SIGNAL,
            symbol=pos.symbol,
            reference_symbol=self.reference_symbol,
            current_price=current_price,
            reference_close=prices['reference_close'],
            drop_pct=prices['drop_pct'],
            master_switch_on=filters.master_switch_on,
            details={'pnl_pct': pnl_pct, 'hold_days': hold_days},
            message=f"📊 HOLD {pos.symbol} - P&L: {pnl_pct:+.2%} (Day {hold_days + 1})"
        )
    
    def _filter_to_dict(self, filters: FilterStatus) -> Dict:
        """Convert FilterStatus to dict for serialization"""
        return {
            'master_switch_on': filters.master_switch_on,
            'price_psar_green': filters.price_psar_green,
            'rsi_psar_green': filters.rsi_psar_green,
            'current_price': filters.current_price,
            'current_rsi': filters.current_rsi,
            'price_psar_value': filters.price_psar_value,
            'rsi_psar_value': filters.rsi_psar_value
        }
    
    def record_entry(self, symbol: str, price: float, shares: int):
        """Record a new position"""
        self.current_position = Position(
            symbol=symbol,
            entry_price=price,
            entry_time=datetime.now(),
            shares=shares,
            cost_basis=price * shares
        )
    
    def record_exit(self, price: float) -> Dict:
        """Record position exit and return trade summary"""
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
        filters = self.get_filter_status()
        prices = self.get_current_prices()
        
        status = {
            'timestamp': datetime.now().isoformat(),
            'asset': config.ASSET_NAME,
            'symbols': {
                'leveraged': self.trading_symbol,
                'conservative': self.conservative_symbol,
                'reference': self.reference_symbol
            },
            'master_switch': {
                'on': filters.master_switch_on,
                'price_psar_green': filters.price_psar_green,
                'rsi_psar_green': filters.rsi_psar_green
            },
            'indicators': {
                'current_price': filters.current_price,
                'current_rsi': filters.current_rsi,
                'price_psar': filters.price_psar_value,
                'rsi_psar': filters.rsi_psar_value
            },
            'prices': {
                'reference_price': prices['reference_price'],
                'reference_close': prices['reference_close'],
                'drop_pct': prices['drop_pct'],
                'slv_price': prices['slv_price'],
                'agq_price': prices['agq_price'],
                'is_extended_hours': prices['is_extended_hours']
            },
            'thresholds': {
                'entry_slv': f"{self.entry_threshold_min:.0%}-{self.entry_threshold_leveraged:.0%}",
                'entry_agq': f"{self.entry_threshold_leveraged:.0%}+",
                'target': self.target_gain,
                'stop_slv': self.stop_loss_slv,
                'stop_agq': self.stop_loss_agq
            },
            'position': self.current_position.to_dict() if self.current_position else None,
        }
        
        signal = self.generate_signal()
        status['signal'] = signal.to_dict()
        
        return status


def print_status(status: Dict):
    """Pretty print the status"""
    print("\n" + "="*60)
    print(f"  SilverSnap | {status['asset']} Dip Buyer")
    print(f"  {status['timestamp']}")
    print("="*60)
    
    # Master Switch
    ms = status['master_switch']
    switch_icon = '🟢 ON' if ms['on'] else '🔴 OFF'
    print(f"\n  MASTER SWITCH: {switch_icon}")
    print(f"    Price PSAR: {'🟢' if ms['price_psar_green'] else '🔴'}")
    print(f"    RSI PSAR:   {'🟢' if ms['rsi_psar_green'] else '🔴'}")
    
    # Indicators
    ind = status['indicators']
    print(f"\n  Indicators:")
    print(f"    Price: ${ind['current_price']:.2f}")
    print(f"    RSI:   {ind['current_rsi']:.1f}")
    
    # Prices
    p = status['prices']
    print(f"\n  Prices:")
    print(f"    SLV: ${p['slv_price']:.2f}  |  AGQ: ${p['agq_price']:.2f}")
    drop_icon = '📉' if p['drop_pct'] > 0 else '📈'
    print(f"    Drop from close: {drop_icon} {p['drop_pct']:.2%}")
    
    # Thresholds
    t = status['thresholds']
    print(f"\n  Entry Thresholds:")
    print(f"    📉 2-4% drop → Buy SLV (1x)")
    print(f"    📉 4%+  drop → Buy AGQ (2x)")
    print(f"  Exit:")
    print(f"    🎯 +{t['target']:.0%} target")
    print(f"    🛑 -{t['stop_slv']:.0%} stop (SLV) | -{t['stop_agq']:.0%} stop (AGQ)")
    
    # Position
    if status['position']:
        pos = status['position']
        print(f"\n  Position: {pos['symbol']}")
        print(f"    Entry: ${pos['entry_price']:.2f}")
        print(f"    Shares: {pos['shares']}")
    
    # Signal
    sig = status['signal']
    print(f"\n  SIGNAL: {sig['signal_type']}")
    print(f"  {sig['message']}")
    
    print("\n" + "="*60)
