"""
Technical Indicators for SilverSnap
====================================
PSAR on Price and PSAR on RSI filters
"""

import numpy as np
from typing import Tuple, List
from dataclasses import dataclass


@dataclass
class PSARResult:
    """Result of PSAR calculation"""
    value: float
    trend: str  # 'bullish' or 'bearish'
    is_green: bool  # True if bullish (dots below)


def calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
    """
    Calculate RSI (Relative Strength Index)
    
    Args:
        prices: List of closing prices
        period: RSI period (default 14)
        
    Returns:
        List of RSI values (first 'period' values will be None)
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
    
    Args:
        highs: List of high prices
        lows: List of low prices
        closes: List of close prices
        af_start: Starting acceleration factor
        af_increment: AF increment on new extreme
        af_max: Maximum AF
        
    Returns:
        List of PSARResult objects
    """
    n = len(closes)
    if n < 2:
        return []
    
    psar = [None] * n
    af = af_start
    trend = 'bullish'  # Start assuming bullish
    ep = highs[0]  # Extreme point
    psar_value = lows[0]
    
    results = []
    
    for i in range(1, n):
        # Previous values
        prev_psar = psar_value
        
        if trend == 'bullish':
            # PSAR below price in bullish trend
            psar_value = prev_psar + af * (ep - prev_psar)
            
            # PSAR can't be above prior two lows
            psar_value = min(psar_value, lows[i-1])
            if i >= 2:
                psar_value = min(psar_value, lows[i-2])
            
            # Check for trend reversal
            if lows[i] < psar_value:
                trend = 'bearish'
                psar_value = ep
                ep = lows[i]
                af = af_start
            else:
                # Update extreme point
                if highs[i] > ep:
                    ep = highs[i]
                    af = min(af + af_increment, af_max)
        else:
            # PSAR above price in bearish trend
            psar_value = prev_psar - af * (prev_psar - ep)
            
            # PSAR can't be below prior two highs
            psar_value = max(psar_value, highs[i-1])
            if i >= 2:
                psar_value = max(psar_value, highs[i-2])
            
            # Check for trend reversal
            if highs[i] > psar_value:
                trend = 'bullish'
                psar_value = ep
                ep = highs[i]
                af = af_start
            else:
                # Update extreme point
                if lows[i] < ep:
                    ep = lows[i]
                    af = min(af + af_increment, af_max)
        
        is_green = trend == 'bullish'  # Green when dots are below price
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
    
    This creates a trend filter based on RSI momentum
    
    Args:
        prices: List of closing prices
        rsi_period: Period for RSI calculation
        af_start: Starting acceleration factor for PSAR
        af_increment: AF increment
        af_max: Maximum AF
        
    Returns:
        List of PSARResult objects for PSAR applied to RSI
    """
    # Calculate RSI
    rsi_values = calculate_rsi(prices, rsi_period)
    
    # Filter out None values for PSAR calculation
    valid_rsi = [r for r in rsi_values if r is not None]
    
    if len(valid_rsi) < 2:
        return []
    
    # For PSAR on RSI, we treat RSI as the price
    # Use RSI as high, low, and close (it's a single line)
    # Small variation to create high/low spread
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
) -> Tuple[bool, bool, dict]:
    """
    Get the current status of both PSAR filters
    
    Args:
        highs: List of high prices
        lows: List of low prices  
        closes: List of close prices
        rsi_period: Period for RSI
        psar_*: PSAR parameters
        
    Returns:
        Tuple of (psar_price_green, psar_rsi_green, details_dict)
    """
    # PSAR on Price
    price_psar = calculate_psar(
        highs, lows, closes,
        psar_af_start, psar_af_increment, psar_af_max
    )
    
    # PSAR on RSI
    rsi_psar = calculate_psar_on_rsi(
        closes, rsi_period,
        psar_af_start, psar_af_increment, psar_af_max
    )
    
    price_green = price_psar[-1].is_green if price_psar else False
    rsi_green = rsi_psar[-1].is_green if rsi_psar else False
    
    # Calculate current RSI for reference
    rsi_values = calculate_rsi(closes, rsi_period)
    current_rsi = rsi_values[-1] if rsi_values and rsi_values[-1] is not None else None
    
    details = {
        'price_psar_value': price_psar[-1].value if price_psar else None,
        'price_psar_trend': price_psar[-1].trend if price_psar else None,
        'rsi_psar_value': rsi_psar[-1].value if rsi_psar else None,
        'rsi_psar_trend': rsi_psar[-1].trend if rsi_psar else None,
        'current_rsi': current_rsi,
        'current_price': closes[-1] if closes else None,
    }
    
    return price_green, rsi_green, details


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
    price_green, rsi_green, details = get_filter_status(
        highs, lows, closes, **kwargs
    )
    
    is_active = price_green and rsi_green
    
    details['price_filter_green'] = price_green
    details['rsi_filter_green'] = rsi_green
    details['master_switch_active'] = is_active
    
    return is_active, details
