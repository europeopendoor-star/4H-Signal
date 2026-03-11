"""
supabase_writer.py

Saves trade signals and updates bot status in Supabase.
Uses raw requests (no Supabase Python SDK).

Run this SQL in Supabase SQL Editor to set up tables:

CREATE TABLE IF NOT EXISTS signals (
  id BIGSERIAL PRIMARY KEY,
  pair TEXT NOT NULL,
  direction TEXT NOT NULL,
  confidence TEXT,
  confluence_score INT,
  entry_price NUMERIC,
  entry_high NUMERIC,
  entry_low NUMERIC,
  stop_loss NUMERIC,
  take_profit_1 NUMERIC,
  take_profit_2 NUMERIC,
  take_profit_3 NUMERIC,
  risk_reward NUMERIC,
  session TEXT,
  flags JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE signals ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON signals FOR SELECT USING (true);

CREATE TABLE IF NOT EXISTS bot_status (
  id INT PRIMARY KEY DEFAULT 1,
  last_scan TIMESTAMPTZ,
  pairs TEXT[],
  signals_today INT DEFAULT 0,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE bot_status ENABLE ROW LEVEL SECURITY;
CREATE POLICY "public read" ON bot_status FOR SELECT USING (true);
"""

import os
import json
import requests
from datetime import datetime, timezone, timedelta
from typing import List

from strategy import TradeSignal

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

def _headers() -> dict:
    """Returns headers required for Supabase REST API."""
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

def _table_url(table: str) -> str:
    """Constructs URL for a Supabase table."""
    return f"{SUPABASE_URL}/rest/v1/{table}"

def save_signal(signal: TradeSignal, pair: str):
    """Saves a new signal to the `signals` table."""
    url = _table_url("signals")

    payload = {
        "pair": pair,
        "direction": signal.direction.value,
        "confidence": signal.confidence,
        "confluence_score": signal.confluence_score,
        "entry_price": round(signal.entry_price, 5),
        "entry_high": round(signal.entry_high, 5),
        "entry_low": round(signal.entry_low, 5),
        "stop_loss": round(signal.stop_loss, 5),
        "take_profit_1": round(signal.take_profit_1, 5),
        "take_profit_2": round(signal.take_profit_2, 5),
        "take_profit_3": round(signal.take_profit_3, 5),
        "risk_reward": round(signal.risk_reward, 2),
        "session": signal.session,
        "flags": json.dumps(signal.confluence_flags)
    }

    try:
        response = requests.post(url, headers=_headers(), json=payload)
        response.raise_for_status()
        print(f"[{pair}] Signal saved to Supabase.")
    except Exception as e:
        print(f"Error saving signal for {pair}: {e}")

def update_bot_status(pairs_scanned: List[str], signal_count: int):
    """Updates bot scan status and metrics."""
    url = _table_url("bot_status")

    headers = _headers()
    headers["Prefer"] = "resolution=merge-duplicates"

    payload = {
        "id": 1,
        "last_scan": datetime.now(timezone.utc).isoformat(),
        "pairs": pairs_scanned,
        "signals_today": signal_count,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Error updating bot status: {e}")

def keep_alive_ping():
    """Pings the bot_status table to keep Supabase active."""
    url = _table_url("bot_status") + "?select=id&limit=1"
    headers = _headers()

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        print(f"Supabase keep-alive ping successful (status {response.status_code}).")
    except Exception as e:
        print(f"Supabase keep-alive ping failed: {e}")

def clean_old_signals(days_to_keep=14):
    """Deletes old signals to prevent database bloat."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_to_keep)).isoformat()

    url = f"{_table_url('signals')}?created_at=lt.{cutoff}"
    headers = _headers()

    try:
        response = requests.delete(url, headers=headers)
        response.raise_for_status()
        print(f"Cleaned up signals older than {days_to_keep} days.")
    except Exception as e:
        print(f"Error cleaning old signals: {e}")
