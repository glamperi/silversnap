"""
Data Fetching for SilverSnap
=============================
Fetch price data from Twelve Data API and Schwab
"""

import os
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import time

import config


@dataclass
class PriceBar:
    """Single price bar"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0


@dataclass
class Quote:
    """Current quote with extended hours data"""
    symbol: str
    last_price: float
    regular_close: float  # 4 PM close
    change_from_close: float  # Absolute change
    change_pct: float  # Percentage change
    timestamp: datetime
    is_extended_hours: bool


def get_twelve_data_api_key() -> str:
    """Get API key from config or environment"""
    key = config.TWELVE_DATA_API_KEY or os.environ.get('TWELVE_DATA_API_KEY', '')
    if not key:
        raise ValueError("TWELVE_DATA_API_KEY not set in config or environment")
    return key


def fetch_daily_bars(
    symbol: str,
    days: int = 60,
    api_key: str = None
) -> List[PriceBar]:
    """
    Fetch daily OHLCV bars from Twelve Data
    
    Args:
        symbol: Ticker symbol
        days: Number of days of history
        api_key: Twelve Data API key (uses config/env if not provided)
        
    Returns:
        List of PriceBar objects, oldest first
    """
    api_key = api_key or get_twelve_data_api_key()
    
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": "1day",
        "outputsize": days,
        "apikey": api_key,
        "timezone": "America/New_York"
    }
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    
    if "values" not in data:
        error_msg = data.get("message", "Unknown error")
        raise ValueError(f"Twelve Data API error: {error_msg}")
    
    bars = []
    for item in reversed(data["values"]):  # Reverse to get oldest first
        bars.append(PriceBar(
            timestamp=datetime.strptime(item["datetime"], "%Y-%m-%d"),
            open=float(item["open"]),
            high=float(item["high"]),
            low=float(item["low"]),
            close=float(item["close"]),
            volume=int(item.get("volume", 0))
        ))
    
    return bars


def fetch_current_quote(
    symbol: str,
    api_key: str = None
) -> Quote:
    """
    Fetch current quote including extended hours price
    
    Args:
        symbol: Ticker symbol
        api_key: Twelve Data API key
        
    Returns:
        Quote object with current and regular session prices
    """
    api_key = api_key or get_twelve_data_api_key()
    
    # Get real-time quote
    url = "https://api.twelvedata.com/quote"
    params = {
        "symbol": symbol,
        "apikey": api_key
    }
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    
    if "code" in data:  # Error response
        raise ValueError(f"Twelve Data API error: {data.get('message', 'Unknown')}")
    
    # Parse response
    last_price = float(data.get("close", data.get("price", 0)))
    prev_close = float(data.get("previous_close", last_price))
    
    # Determine if extended hours
    # Twelve Data includes 'is_market_open' field
    is_market_open = data.get("is_market_open", False)
    
    # For extended hours detection, check current time
    now = datetime.now()
    # Regular market hours: 9:30 AM - 4:00 PM ET (simplified check)
    hour = now.hour
    is_extended = hour < 9 or hour >= 16 or (hour == 9 and now.minute < 30)
    
    change = last_price - prev_close
    change_pct = (change / prev_close * 100) if prev_close > 0 else 0
    
    return Quote(
        symbol=symbol,
        last_price=last_price,
        regular_close=prev_close,
        change_from_close=change,
        change_pct=change_pct,
        timestamp=datetime.now(),
        is_extended_hours=is_extended and not is_market_open
    )


def fetch_intraday_bars(
    symbol: str,
    interval: str = "5min",
    outputsize: int = 78,  # Full trading day at 5min
    api_key: str = None
) -> List[PriceBar]:
    """
    Fetch intraday bars for today
    
    Args:
        symbol: Ticker symbol
        interval: Bar interval (1min, 5min, 15min, etc.)
        outputsize: Number of bars
        api_key: Twelve Data API key
        
    Returns:
        List of PriceBar objects
    """
    api_key = api_key or get_twelve_data_api_key()
    
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": api_key,
        "timezone": "America/New_York"
    }
    
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    
    if "values" not in data:
        error_msg = data.get("message", "Unknown error")
        raise ValueError(f"Twelve Data API error: {error_msg}")
    
    bars = []
    for item in reversed(data["values"]):
        # Parse datetime with time
        dt_str = item["datetime"]
        if " " in dt_str:
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        else:
            dt = datetime.strptime(dt_str, "%Y-%m-%d")
            
        bars.append(PriceBar(
            timestamp=dt,
            open=float(item["open"]),
            high=float(item["high"]),
            low=float(item["low"]),
            close=float(item["close"]),
            volume=int(item.get("volume", 0))
        ))
    
    return bars


def get_todays_close(symbol: str, api_key: str = None) -> Tuple[float, datetime]:
    """
    Get today's regular session close price (4 PM ET)
    
    If market is still open, returns the most recent price as reference.
    
    Returns:
        Tuple of (close_price, close_time)
    """
    bars = fetch_daily_bars(symbol, days=1, api_key=api_key)
    if not bars:
        raise ValueError(f"No data available for {symbol}")
    
    latest_bar = bars[-1]
    return latest_bar.close, latest_bar.timestamp


def calculate_drop_from_close(
    current_price: float,
    close_price: float
) -> Tuple[float, float]:
    """
    Calculate the drop from close
    
    Returns:
        Tuple of (absolute_drop, percentage_drop)
        Percentage is positive when price is DOWN
    """
    drop = close_price - current_price
    drop_pct = (drop / close_price) if close_price > 0 else 0
    return drop, drop_pct


class DataFetcher:
    """
    Convenience class to fetch and cache data
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or get_twelve_data_api_key()
        self._cache = {}
        self._cache_time = {}
        self.cache_duration = 60  # seconds
    
    def get_daily_bars(self, symbol: str, days: int = 60) -> List[PriceBar]:
        """Get daily bars with caching"""
        cache_key = f"daily_{symbol}_{days}"
        now = time.time()
        
        if cache_key in self._cache:
            if now - self._cache_time[cache_key] < self.cache_duration:
                return self._cache[cache_key]
        
        bars = fetch_daily_bars(symbol, days, self.api_key)
        self._cache[cache_key] = bars
        self._cache_time[cache_key] = now
        return bars
    
    def get_quote(self, symbol: str) -> Quote:
        """Get current quote with caching"""
        cache_key = f"quote_{symbol}"
        now = time.time()
        
        if cache_key in self._cache:
            if now - self._cache_time[cache_key] < 30:  # 30 second cache for quotes
                return self._cache[cache_key]
        
        quote = fetch_current_quote(symbol, self.api_key)
        self._cache[cache_key] = quote
        self._cache_time[cache_key] = now
        return quote
    
    def get_filter_data(self, symbol: str, days: int = 60) -> Dict:
        """
        Get data formatted for filter calculations
        
        Returns dict with 'highs', 'lows', 'closes' lists
        """
        bars = self.get_daily_bars(symbol, days)
        return {
            'highs': [b.high for b in bars],
            'lows': [b.low for b in bars],
            'closes': [b.close for b in bars],
            'bars': bars
        }
