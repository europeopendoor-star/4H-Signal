"""
data_fetcher.py

Fetches historical OHLCV data using the yfinance library.
No API key required.
"""

import yfinance as yf
import pandas as pd
from typing import Tuple

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

def fetch_ohlc(pair: str, interval: str, period: str = "5d") -> pd.DataFrame:
    """
    Fetches OHLCV data from yfinance.
    """
    ticker = FOREX_PAIRS.get(pair)
    if not ticker:
        print(f"Error: {pair} not found in FOREX_PAIRS.")
        return pd.DataFrame()

    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)

        if df.empty:
            print(f"Warning: Empty DataFrame returned for {pair} at {interval}.")
            return df

        # Ensure flat columns for the DataFrame
        if isinstance(df.columns, pd.MultiIndex):
            # If the columns are MultiIndex (which happens in newer yfinance versions), drop the top level.
            # Example: [('Adj Close', 'EURUSD=X'), ('Close', 'EURUSD=X')]
            df.columns = df.columns.droplevel(1)

        # Lowercase all column names
        df.columns = [col.lower() for col in df.columns]

        # Drop NaN rows
        df.dropna(inplace=True)

        return df

    except Exception as e:
        print(f"Error fetching data for {pair} at {interval}: {e}")
        return pd.DataFrame()

def fetch_all_timeframes(pair: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Fetches 4H, 15M, and daily OHLCV data for a given forex pair.
    """
    df_4h = fetch_ohlc(pair, "4h", period="30d")
    df_15m = fetch_ohlc(pair, "15m", period="5d")
    df_daily = fetch_ohlc(pair, "1d", period="60d")

    return df_4h, df_15m, df_daily
