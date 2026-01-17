"""
Schwab API Integration for SilverSnap
======================================
Execute trades and fetch quotes via Schwab API

Setup:
1. Set SCHWAB_APP_KEY and SCHWAB_APP_SECRET environment variables
2. Run: python main.py auth
3. Complete OAuth flow in browser
4. Tokens saved to schwab_tokens.json

For GitHub Actions, set SCHWAB_TOKEN_FILE secret with contents of schwab_tokens.json
"""

import os
import json
import base64
import webbrowser
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

import config


# Schwab API endpoints
SCHWAB_AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
SCHWAB_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
SCHWAB_BASE_URL = "https://api.schwabapi.com/trader/v1"
SCHWAB_MARKET_URL = "https://api.schwabapi.com/marketdata/v1"


@dataclass
class SchwabCredentials:
    """Schwab API credentials"""
    app_key: str
    app_secret: str
    redirect_uri: str = "https://127.0.0.1:8182/callback"
    
    @classmethod
    def from_env(cls) -> 'SchwabCredentials':
        """Load credentials from environment variables"""
        app_key = os.environ.get('SCHWAB_APP_KEY', '')
        app_secret = os.environ.get('SCHWAB_APP_SECRET', '')
        
        if not app_key or not app_secret:
            raise ValueError(
                "Missing Schwab credentials. Set environment variables:\n"
                "  SCHWAB_APP_KEY\n"
                "  SCHWAB_APP_SECRET"
            )
        
        return cls(app_key=app_key, app_secret=app_secret)


@dataclass
class TokenData:
    """OAuth token data"""
    access_token: str
    refresh_token: str
    expires_at: datetime
    token_type: str = "Bearer"
    
    def is_expired(self) -> bool:
        """Check if access token is expired"""
        return datetime.now() >= self.expires_at
    
    def to_dict(self) -> dict:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.isoformat(),
            "token_type": self.token_type
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "TokenData":
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
            token_type=data.get("token_type", "Bearer")
        )


class SchwabClient:
    """
    Schwab API client for trading and market data
    
    Usage:
        client = SchwabClient()
        client.authenticate()  # First time opens browser
        accounts = client.get_accounts()
    """
    
    def __init__(self, credentials: SchwabCredentials = None, token_path: str = "schwab_tokens.json"):
        self.credentials = credentials or SchwabCredentials.from_env()
        self.token_path = Path(token_path)
        self.token_data: Optional[TokenData] = None
        self.account_hash: Optional[str] = None
        self._load_tokens()
    
    def _get_auth_header(self) -> str:
        """Get base64 encoded auth header"""
        auth_string = f"{self.credentials.app_key}:{self.credentials.app_secret}"
        return base64.b64encode(auth_string.encode()).decode()
    
    def _load_tokens(self):
        """Load saved tokens from file or environment"""
        # First try environment variable (for GitHub Actions)
        token_json = os.environ.get('SCHWAB_TOKEN_FILE', '')
        if token_json:
            try:
                data = json.loads(token_json)
                self.token_data = TokenData.from_dict(data)
                self.account_hash = data.get('account_hash')
                print("✓ Loaded tokens from environment")
                return
            except Exception as e:
                print(f"⚠️ Failed to parse SCHWAB_TOKEN_FILE: {e}")
        
        # Then try file
        if self.token_path.exists():
            try:
                with open(self.token_path) as f:
                    data = json.load(f)
                self.token_data = TokenData.from_dict(data)
                self.account_hash = data.get('account_hash')
                print("✓ Loaded tokens from file")
            except Exception as e:
                print(f"⚠️ Failed to load tokens: {e}")
    
    def _save_tokens(self):
        """Save tokens to file"""
        if self.token_data:
            data = self.token_data.to_dict()
            if self.account_hash:
                data['account_hash'] = self.account_hash
            with open(self.token_path, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"✓ Tokens saved to {self.token_path}")
    
    def authenticate(self, auth_code: Optional[str] = None) -> bool:
        """
        Authenticate with Schwab API
        
        First time: Opens browser for OAuth flow
        Subsequent: Refreshes existing tokens
        """
        # Always try to refresh if we have a refresh token (resets 7-day clock)
        if self.token_data and self.token_data.refresh_token:
            if self._refresh_tokens():
                # Fetch account hash if we don't have it
                if not self.account_hash:
                    self._fetch_account_hash()
                    self._save_tokens()  # Save with hash included
                return True
            if not self.token_data.is_expired():
                print("⚠️ Refresh failed but access token still valid")
                if not self.account_hash:
                    self._fetch_account_hash()
                    self._save_tokens()
                return True
        
        # Need to do full OAuth flow
        if not auth_code:
            auth_url = (
                f"{SCHWAB_AUTH_URL}?"
                f"client_id={self.credentials.app_key}&"
                f"redirect_uri={self.credentials.redirect_uri}&"
                f"response_type=code"
            )
            
            print("\n" + "="*60)
            print("SCHWAB AUTHENTICATION REQUIRED")
            print("="*60)
            print("\n1. Opening browser for Schwab login...")
            print("2. After login, you'll be redirected to a URL")
            print("3. Copy the ENTIRE URL and paste it here")
            print(f"\nAuth URL: {auth_url}\n")
            
            webbrowser.open(auth_url)
            
            callback_url = input("Paste the callback URL here: ").strip()
            
            # Extract code from URL
            if "code=" in callback_url:
                auth_code = callback_url.split("code=")[1].split("&")[0]
            else:
                auth_code = callback_url
        
        return self._exchange_code_for_tokens(auth_code)
    
    def _exchange_code_for_tokens(self, auth_code: str) -> bool:
        """Exchange authorization code for access tokens"""
        # URL decode the auth code if needed
        from urllib.parse import unquote
        auth_code = unquote(auth_code)
        
        headers = {
            "Authorization": f"Basic {self._get_auth_header()}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": self.credentials.redirect_uri
        }
        
        response = requests.post(SCHWAB_TOKEN_URL, headers=headers, data=data)
        
        if response.status_code == 200:
            token_response = response.json()
            self.token_data = TokenData(
                access_token=token_response["access_token"],
                refresh_token=token_response["refresh_token"],
                expires_at=datetime.now() + timedelta(seconds=token_response["expires_in"] - 60)
            )
            
            # Fetch account hash
            self._fetch_account_hash()
            
            self._save_tokens()
            print("✓ Authentication successful")
            return True
        else:
            print(f"✗ Authentication failed: {response.status_code}")
            print(response.text)
            return False
    
    def _refresh_tokens(self) -> bool:
        """Refresh access token using refresh token"""
        if not self.token_data or not self.token_data.refresh_token:
            return False
        
        # Save old token in case refresh fails validation
        old_token_data = self.token_data
        
        headers = {
            "Authorization": f"Basic {self._get_auth_header()}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.token_data.refresh_token
        }
        
        response = requests.post(SCHWAB_TOKEN_URL, headers=headers, data=data)
        
        if response.status_code == 200:
            token_response = response.json()
            new_token_data = TokenData(
                access_token=token_response["access_token"],
                refresh_token=token_response.get("refresh_token", self.token_data.refresh_token),
                expires_at=datetime.now() + timedelta(seconds=token_response["expires_in"] - 60)
            )
            
            # Verify the new token works before saving
            self.token_data = new_token_data
            try:
                # Test with a simple API call
                test_response = requests.get(
                    f"{SCHWAB_BASE_URL}/accounts",
                    headers={"Authorization": f"Bearer {new_token_data.access_token}"}
                )
                if test_response.status_code == 200:
                    self._save_tokens()
                    print("✓ Tokens refreshed and verified")
                    return True
                else:
                    # New token doesn't work, restore old one
                    print(f"⚠️ New token failed verification: {test_response.status_code}")
                    self.token_data = old_token_data
                    return False
            except Exception as e:
                print(f"⚠️ Token verification failed: {e}")
                self.token_data = old_token_data
                return False
        else:
            print(f"✗ Token refresh failed: {response.status_code}")
            return False
    
    def _fetch_account_hash(self):
        """Fetch and store account hash using accountNumbers endpoint"""
        if not self.token_data:
            return
            
        try:
            # Use accountNumbers endpoint - this returns the hash
            response = requests.get(
                f"{SCHWAB_BASE_URL}/accounts/accountNumbers",
                headers={"Authorization": f"Bearer {self.token_data.access_token}"}
            )
            if response.status_code == 200:
                account_numbers = response.json()
                if account_numbers:
                    self.account_hash = account_numbers[0].get('hashValue')
                    account_num = account_numbers[0].get('accountNumber')
                    print(f"✓ Account #{account_num} hash: {self.account_hash[:12]}...")
            else:
                print(f"⚠️ Could not fetch account numbers: {response.status_code}")
                print(f"   Response: {response.text[:200]}")
        except Exception as e:
            print(f"⚠️ Could not fetch account hash: {e}")
    
    def _ensure_authenticated(self):
        """Ensure we have valid authentication"""
        if not self.token_data:
            raise Exception("Not authenticated. Run: python main.py auth")
        
        if self.token_data.is_expired():
            if not self._refresh_tokens():
                raise Exception("Token expired and refresh failed. Run: python main.py auth")
    
    def _get_headers(self) -> Dict:
        """Get headers with valid access token"""
        self._ensure_authenticated()
        return {
            "Authorization": f"Bearer {self.token_data.access_token}",
            "Content-Type": "application/json"
        }
    
    def _get_account_hash(self) -> str:
        """Get account hash, fetching if needed"""
        if not self.account_hash:
            self._fetch_account_hash()
        if not self.account_hash:
            raise Exception("No account hash. Run: python main.py auth")
        return self.account_hash
    
    # =========================================================================
    # Account Data
    # =========================================================================
    
    def get_accounts(self) -> list:
        """Get all accounts"""
        self._ensure_authenticated()
        
        response = requests.get(
            f"{SCHWAB_BASE_URL}/accounts",
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json()
    
    def get_account(self) -> Dict:
        """Get account details including balances and positions"""
        account_hash = self._get_account_hash()
        
        # Use token directly - don't call _ensure_authenticated which might refresh again
        response = requests.get(
            f"{SCHWAB_BASE_URL}/accounts/{account_hash}",
            headers={"Authorization": f"Bearer {self.token_data.access_token}"},
            params={"fields": "positions"}
        )
        
        if response.status_code != 200:
            print(f"⚠️ get_account failed: {response.status_code}")
            print(f"   URL: {SCHWAB_BASE_URL}/accounts/{account_hash[:20]}...")
            print(f"   Response: {response.text[:300]}")
        
        response.raise_for_status()
        return response.json()
    
    def get_positions(self) -> Dict:
        """Get current positions"""
        account = self.get_account()
        positions = account.get("securitiesAccount", {}).get("positions", [])
        
        result = {}
        for pos in positions:
            symbol = pos["instrument"]["symbol"]
            result[symbol] = {
                "symbol": symbol,
                "quantity": pos["longQuantity"] - pos.get("shortQuantity", 0),
                "averagePrice": pos["averagePrice"],
                "marketValue": pos["marketValue"],
                "currentDayProfitLoss": pos.get("currentDayProfitLoss", 0),
                "currentDayProfitLossPercentage": pos.get("currentDayProfitLossPercentage", 0),
            }
        
        return result
    
    def get_buying_power(self) -> float:
        """Get available buying power"""
        account = self.get_account()
        balances = account.get("securitiesAccount", {}).get("currentBalances", {})
        return balances.get("buyingPower", 0)
    
    # =========================================================================
    # Market Data
    # =========================================================================
    
    def get_quote(self, symbol: str) -> Dict:
        """Get real-time quote for a symbol"""
        response = requests.get(
            f"{SCHWAB_MARKET_URL}/quotes",
            headers={"Authorization": f"Bearer {self.token_data.access_token}"},
            params={"symbols": symbol}
        )
        
        if response.status_code != 200:
            print(f"⚠️ get_quote failed for {symbol}: {response.status_code}")
            print(f"   Response: {response.text[:300]}")
        
        response.raise_for_status()
        
        data = response.json()
        if symbol not in data:
            raise ValueError(f"No quote data for {symbol}")
        
        return data[symbol]["quote"]
    
    def get_quotes(self, symbols: list) -> Dict:
        """Get quotes for multiple symbols"""
        response = requests.get(
            f"{SCHWAB_MARKET_URL}/quotes",
            headers={"Authorization": f"Bearer {self.token_data.access_token}"},
            params={"symbols": ",".join(symbols)}
        )
        response.raise_for_status()
        
        data = response.json()
        return {sym: data[sym]["quote"] for sym in symbols if sym in data}
    
    # =========================================================================
    # Order Execution
    # =========================================================================
    
    def place_market_order(
        self,
        symbol: str,
        quantity: int,
        side: str,
        session: str = "NORMAL"
    ) -> Dict:
        """Place a market order"""
        account_hash = self._get_account_hash()
        
        order = {
            "orderType": "MARKET",
            "session": session,
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": side,
                    "quantity": quantity,
                    "instrument": {
                        "symbol": symbol,
                        "assetType": "EQUITY"
                    }
                }
            ]
        }
        
        response = requests.post(
            f"{SCHWAB_BASE_URL}/accounts/{account_hash}/orders",
            headers=self._get_headers(),
            json=order
        )
        
        if response.status_code == 201:
            location = response.headers.get("Location", "")
            order_id = location.split("/")[-1] if location else "unknown"
            return {"success": True, "orderId": order_id, "status": "CREATED"}
        else:
            response.raise_for_status()
    
    def place_limit_order(
        self,
        symbol: str,
        quantity: int,
        side: str,
        limit_price: float,
        session: str = "NORMAL"
    ) -> Dict:
        """Place a limit order"""
        account_hash = self._get_account_hash()
        
        order = {
            "orderType": "LIMIT",
            "price": str(limit_price),
            "session": session,
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": side,
                    "quantity": quantity,
                    "instrument": {
                        "symbol": symbol,
                        "assetType": "EQUITY"
                    }
                }
            ]
        }
        
        response = requests.post(
            f"{SCHWAB_BASE_URL}/accounts/{account_hash}/orders",
            headers=self._get_headers(),
            json=order
        )
        
        if response.status_code == 201:
            location = response.headers.get("Location", "")
            order_id = location.split("/")[-1] if location else "unknown"
            return {"success": True, "orderId": order_id, "status": "CREATED"}
        else:
            response.raise_for_status()


class SchwabDataFetcher:
    """
    Data fetcher using Schwab API instead of Twelve Data
    Drop-in replacement for signals.py
    """
    
    def __init__(self, client: SchwabClient = None):
        self.client = client or SchwabClient()
        self.client.authenticate()
    
    def get_quote(self, symbol: str):
        """Get quote in format compatible with signals.py"""
        from data_fetcher import Quote
        
        quote_data = self.client.get_quote(symbol)
        
        last_price = quote_data.get("lastPrice", quote_data.get("mark", 0))
        close_price = quote_data.get("closePrice", quote_data.get("regularMarketLastPrice", last_price))
        
        change = last_price - close_price
        change_pct = (change / close_price * 100) if close_price > 0 else 0
        
        # Check if extended hours
        now = datetime.now()
        hour = now.hour
        is_extended = hour < 9 or hour >= 16 or (hour == 9 and now.minute < 30)
        
        return Quote(
            symbol=symbol,
            last_price=last_price,
            regular_close=close_price,
            change_from_close=change,
            change_pct=change_pct,
            timestamp=datetime.now(),
            is_extended_hours=is_extended
        )
    
    def get_filter_data(self, symbol: str, days: int = 60) -> Dict:
        """Get historical data for filter calculations"""
        from data_fetcher import DataFetcher
        td_fetcher = DataFetcher()
        return td_fetcher.get_filter_data(symbol, days)


def calculate_shares(capital: float, price: float) -> int:
    """Calculate number of shares to buy"""
    return int(capital // price)


def execute_entry(
    client: SchwabClient,
    symbol: str,
    capital: float,
    use_limit: bool = True,
    session: str = "SEAMLESS"
) -> Dict:
    """Execute an entry order"""
    quote = client.get_quote(symbol)
    price = quote.get("lastPrice", quote.get("mark"))
    
    shares = calculate_shares(capital, price)
    if shares < 1:
        return {"success": False, "error": f"Insufficient capital for 1 share at ${price:.2f}"}
    
    if use_limit:
        limit_price = quote.get("askPrice", price * 1.001)
        result = client.place_limit_order(symbol, shares, "BUY", limit_price, session)
    else:
        result = client.place_market_order(symbol, shares, "BUY", session)
    
    result["symbol"] = symbol
    result["shares"] = shares
    result["price"] = price
    result["capital_used"] = shares * price
    
    return result


def execute_exit(
    client: SchwabClient,
    symbol: str,
    shares: int,
    use_limit: bool = True,
    session: str = "SEAMLESS"
) -> Dict:
    """Execute an exit order"""
    quote = client.get_quote(symbol)
    price = quote.get("lastPrice", quote.get("mark"))
    
    if use_limit:
        limit_price = quote.get("bidPrice", price * 0.999)
        result = client.place_limit_order(symbol, shares, "SELL", limit_price, session)
    else:
        result = client.place_market_order(symbol, shares, "SELL", session)
    
    result["symbol"] = symbol
    result["shares"] = shares
    result["price"] = price
    
    return result
