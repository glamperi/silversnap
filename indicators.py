"""
Technical Indicators for SilverSnap - Long-Only
================================================
PSAR on Price + PSAR on RSI = Master Switch for dip buying
"""

import numpy as np
from typing import Tuple, List, Optional
from dataclasses import dataclass


@dataclass
class PSARResult:
    """Result of PSAR calculation"""
    value: float
    trend: str  # 'bullish' or 'bearish'
    is_green: bool  # True if bullish (dots below price)


@dataclass
class FilterStatus:
    """Current filter status for trading"""
    master_switch_on: bool
    price_psar_green: bool
    rsi_psar_green: bool
    current_price: float
    current_rsi: float
    price_psar_value: float
    rsi_psar_value: float


def calculate_rsi(prices: List[float], period: int = 14) -> List[Optional[float]]:
    """
    Calculate RSI (Relative Strength Index)
    """
    if len(prices) < period + 1:
        return [None] * len(prices)
    
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    rsi_values = [None] * period
    
    # First RSI uses simple average
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    
    if avg_loss == 0:
        rsi_values.append(100.0)
    else:
        rs = avg_gain / avg_loss
        rsi_values.append(100 - (100 / (1 + rs)))
    
    # Subsequent RSI uses smoothed average
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        if avg_loss == 0:
            rsi_values.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(100 - (100 / (1 + rs)))
    
    return rsi_values


def calculate_psar(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    af_start: float = 0.02,
    af_increment: float = 0.02,
    af_max: float = 0.20
) -> List[PSARResult]:
    """
    Calculate Parabolic SAR
    
    Returns list of PSARResult with value, trend, and is_green flag
    """
    n = len(closes)
    if n < 2:
        return []
    
    af = af_start
    trend = 'bullish'
    ep = highs[0]
    psar_value = lows[0]
    
    results = []
    
    for i in range(1, n):
        prev_psar = psar_value
        
        if trend == 'bullish':
            psar_value = prev_psar + af * (ep - prev_psar)
            psar_value = min(psar_value, lows[i-1])
            if i >= 2:
                psar_value = min(psar_value, lows[i-2])
            
            if lows[i] < psar_value:
                trend = 'bearish'
                psar_value = ep
                ep = lows[i]
                af = af_start
            else:
                if highs[i] > ep:
                    ep = highs[i]
                    af = min(af + af_increment, af_max)
        else:
            psar_value = prev_psar - af * (prev_psar - ep)
            psar_value = max(psar_value, highs[i-1])
            if i >= 2:
                psar_value = max(psar_value, highs[i-2])
            
            if highs[i] > psar_value:
                trend = 'bullish'
                psar_value = ep
                ep = highs[i]
                af = af_start
            else:
                if lows[i] < ep:
                    ep = lows[i]
                    af = min(af + af_increment, af_max)
        
        is_green = trend == 'bullish'
        results.append(PSARResult(
            value=psar_value,
            trend=trend,
            is_green=is_green
        ))
    
    return results


def calculate_psar_on_rsi(
    prices: List[float],
    rsi_period: int = 14,
    af_start: float = 0.02,
    af_increment: float = 0.02,
    af_max: float = 0.20
) -> List[PSARResult]:
    """
    Calculate PSAR on RSI values (treating RSI as a price series)
    """
    rsi_values = calculate_rsi(prices, rsi_period)
    valid_rsi = [r for r in rsi_values if r is not None]
    
    if len(valid_rsi) < 2:
        return []
    
    # Create pseudo-OHLC from RSI
    rsi_highs = [r + 0.5 for r in valid_rsi]
    rsi_lows = [r - 0.5 for r in valid_rsi]
    
    return calculate_psar(
        rsi_highs, rsi_lows, valid_rsi,
        af_start, af_increment, af_max
    )


def get_filter_status(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    rsi_period: int = 14,
    psar_af_start: float = 0.02,
    psar_af_increment: float = 0.02,
    psar_af_max: float = 0.20
) -> FilterStatus:
    """
    Get the current status of both PSAR filters
    
    Master Switch ON = Both filters green = Safe to buy dips
    """
    price_psar = calculate_psar(
        highs, lows, closes,
        psar_af_start, psar_af_increment, psar_af_max
    )
    
    rsi_psar = calculate_psar_on_rsi(
        closes, rsi_period,
        psar_af_start, psar_af_increment, psar_af_max
    )
    
    price_green = price_psar[-1].is_green if price_psar else False
    rsi_green = rsi_psar[-1].is_green if rsi_psar else False
    
    rsi_values = calculate_rsi(closes, rsi_period)
    current_rsi = rsi_values[-1] if rsi_values and rsi_values[-1] is not None else 50
    
    return FilterStatus(
        master_switch_on=price_green and rsi_green,
        price_psar_green=price_green,
        rsi_psar_green=rsi_green,
        current_price=closes[-1] if closes else 0,
        current_rsi=current_rsi,
        price_psar_value=price_psar[-1].value if price_psar else 0,
        rsi_psar_value=rsi_psar[-1].value if rsi_psar else 0
    )


def master_switch_active(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    **kwargs
) -> Tuple[bool, dict]:
    """
    Check if the master switch is ON (both filters green)
    
    Returns:
        Tuple of (is_active, details_dict)
    """
    status = get_filter_status(highs, lows, closes, **kwargs)
    
    details = {
        'price_filter_green': status.price_psar_green,
        'rsi_filter_green': status.rsi_psar_green,
        'master_switch_active': status.master_switch_on,
        'price_psar_value': status.price_psar_value,
        'rsi_psar_value': status.rsi_psar_value,
        'current_rsi': status.current_rsi,
        'current_price': status.current_price,
    }
    
    return status.master_switch_on, details
