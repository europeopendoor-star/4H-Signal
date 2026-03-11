"""
data_fetcher.py

Fetches historical OHLCV data.
Primary source: Twelve Data API (free tier).
Fallback source: yfinance.
"""

import os
import time
import requests
import yfinance as yf
import pandas as pd
from typing import Tuple

TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")

FOREX_PAIRS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "USDCAD=X",
    "GBPJPY": "GBPJPY=X",
    "NZDUSD": "NZDUSD=X",
    "USDCHF": "USDCHF=X"
}

TWELVE_DATA_SYMBOLS = {
    "EURUSD": "EUR/USD",
    "GBPUSD": "GBP/USD",
    "USDJPY": "USD/JPY",
    "AUDUSD": "AUD/USD",
    "USDCAD": "USD/CAD",
    "GBPJPY": "GBP/JPY",
    "NZDUSD": "NZD/USD",
    "USDCHF": "USD/CHF"
}

INTERVAL_MAP_TD = {
    "4h": "4h",
    "15m": "15min",
    "1d": "1day"
}

def fetch_from_twelvedata(pair: str, interval: str, outputsize: int = 100) -> pd.DataFrame:
    """Fetches OHLCV data from Twelve Data."""
    symbol = TWELVE_DATA_SYMBOLS.get(pair)
    td_interval = INTERVAL_MAP_TD.get(interval)

    if not symbol or not td_interval:
        raise ValueError(f"Invalid pair or interval for Twelve Data: {pair}, {interval}")
    if not TWELVEDATA_API_KEY:
        raise ValueError("TWELVEDATA_API_KEY is not set.")

    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={td_interval}&outputsize={outputsize}&apikey={TWELVEDATA_API_KEY}"

    response = requests.get(url, timeout=15)
    response.raise_for_status()
    data = response.json()

    if data.get("status") == "error" or "values" not in data:
        raise Exception(f"Twelve Data error: {data.get('message', 'Unknown error')}")

    df = pd.DataFrame(data["values"])

    # Twelve Data returns strings for prices, convert to float
    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].astype(float)

    if 'volume' in df.columns:
        df['volume'] = df['volume'].astype(float)

    df['datetime'] = pd.to_datetime(df['datetime'])
    df.set_index('datetime', inplace=True)
    df.sort_index(ascending=True, inplace=True)
    df.dropna(inplace=True)

    return df

def fetch_from_yfinance(pair: str, interval: str, period: str) -> pd.DataFrame:
    """Fetches OHLCV data from yfinance."""
    ticker = FOREX_PAIRS.get(pair)
    if not ticker:
        print(f"Error: {pair} not found in FOREX_PAIRS.")
        return pd.DataFrame()

    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)

        if df.empty:
            return df

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

        df.columns = [col.lower() for col in df.columns]
        df.dropna(inplace=True)

        return df

    except Exception as e:
        return pd.DataFrame()

def fetch_ohlc(pair: str, interval: str, period: str = "5d", outputsize: int = 100) -> pd.DataFrame:
    """Fetches OHLCV data, trying Twelve Data first, then yfinance."""
    try:
        df = fetch_from_twelvedata(pair, interval, outputsize)
        if not df.empty:
            print(f"✅ {pair} — Fetched {interval} from Twelve Data")
            return df
    except Exception as e:
        print(f"⚠️ {pair} — Twelve Data failed for {interval} ({e}), using yfinance fallback")

    return fetch_from_yfinance(pair, interval, period)

def fetch_all_timeframes(pair: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fetches 4H, 15M, and daily OHLCV data with rate limit awareness."""
    df_4h = fetch_ohlc(pair, "4h", period="30d", outputsize=200)
    time.sleep(1)
    df_15m = fetch_ohlc(pair, "15m", period="5d", outputsize=300)
    time.sleep(1)
    df_daily = fetch_ohlc(pair, "1d", period="60d", outputsize=100)
    time.sleep(1)

    return df_4h, df_15m, df_daily

def fetch_latest_candle(pair: str, interval: str) -> dict:
    """Fetches the latest single candle for tracker updates."""
    try:
        df = fetch_from_twelvedata(pair, interval, outputsize=1)
        if not df.empty:
            latest = df.iloc[-1]
            return {
                "open": latest['open'],
                "high": latest['high'],
                "low": latest['low'],
                "close": latest['close'],
                "datetime": latest.name
            }
    except Exception as e:
        # Fallback to yfinance if TWELVEDATA fails
        df = fetch_from_yfinance(pair, interval, period="1d")
        if not df.empty:
            latest = df.iloc[-1]
            return {
                "open": latest['open'],
                "high": latest['high'],
                "low": latest['low'],
                "close": latest['close'],
                "datetime": latest.name
            }
    return {}
