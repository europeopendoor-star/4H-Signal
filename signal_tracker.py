"""
signal_tracker.py

Tracks active signals to determine win/loss outcomes.
Updates the database and notifies via Telegram.

Run this SQL in Supabase SQL Editor:
ALTER TABLE signals ADD COLUMN IF NOT EXISTS outcome TEXT DEFAULT 'open';
ALTER TABLE signals ADD COLUMN IF NOT EXISTS tp1_hit BOOLEAN DEFAULT false;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS tp2_hit BOOLEAN DEFAULT false;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS tp3_hit BOOLEAN DEFAULT false;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS stopped_out BOOLEAN DEFAULT false;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS expired BOOLEAN DEFAULT false;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS actual_rr NUMERIC;
ALTER TABLE signals ADD COLUMN IF NOT EXISTS pips_gained NUMERIC;
"""

import os
from dotenv import load_dotenv
load_dotenv()
import time
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Dict

from supabase_writer import _headers, _table_url
from data_fetcher import fetch_latest_candle
from notifier import send_telegram_message

def fetch_open_signals() -> List[Dict]:
    """Fetches open signals created within the last 48 hours."""
    url = f"{_table_url('signals')}?outcome=eq.open"
    headers = _headers()

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching open signals: {e}")
        return []

def check_signal_outcome(signal: Dict, current_price: float) -> Dict:
    """Evaluates if an open signal hit TP or SL."""
    updates = {}
    direction = signal.get("direction", "").upper()
    entry_price = float(signal.get("entry_price", 0))
    stop_loss = float(signal.get("stop_loss", 0))
    take_profit_1 = float(signal.get("take_profit_1", 0))
    take_profit_2 = float(signal.get("take_profit_2", 0))

    tp1_hit = signal.get("tp1_hit", False)
    tp2_hit = signal.get("tp2_hit", False)
    stopped_out = signal.get("stopped_out", False)

    now_iso = datetime.now(timezone.utc).isoformat()

    now_utc = datetime.now(timezone.utc)
    created_at = datetime.fromisoformat(signal.get("created_at", now_utc.isoformat()).replace('Z', '+00:00'))
    if (now_utc - created_at) > timedelta(hours=48):
        updates["expired"] = True
        updates["outcome"] = "expired"
        updates["closed_at"] = now_iso
        updates["actual_rr"] = 0
        updates["pips_gained"] = 0
        return updates

    if direction == "LONG" or direction == "BULLISH":
        if not tp1_hit and take_profit_1 and current_price >= take_profit_1:
            updates["tp1_hit"] = True

        if not tp2_hit and take_profit_2 and current_price >= take_profit_2:
            updates["tp2_hit"] = True
            updates["outcome"] = "win"
            updates["closed_at"] = now_iso
            updates["actual_rr"] = round((take_profit_2 - entry_price) / (entry_price - stop_loss), 2) if entry_price != stop_loss else 0
            updates["pips_gained"] = round((take_profit_2 - entry_price) * 10000, 1)

        if not stopped_out and stop_loss and current_price <= stop_loss:
            updates["stopped_out"] = True
            updates["outcome"] = "loss"
            updates["closed_at"] = now_iso
            updates["actual_rr"] = -1.0
            updates["pips_gained"] = round((current_price - entry_price) * 10000, 1)

    elif direction == "SHORT" or direction == "BEARISH":
        if not tp1_hit and take_profit_1 and current_price <= take_profit_1:
            updates["tp1_hit"] = True

        if not tp2_hit and take_profit_2 and current_price <= take_profit_2:
            updates["tp2_hit"] = True
            updates["outcome"] = "win"
            updates["closed_at"] = now_iso
            updates["actual_rr"] = round((entry_price - take_profit_2) / (stop_loss - entry_price), 2) if entry_price != stop_loss else 0
            updates["pips_gained"] = round((entry_price - take_profit_2) * 10000, 1)

        if not stopped_out and stop_loss and current_price >= stop_loss:
            updates["stopped_out"] = True
            updates["outcome"] = "loss"
            updates["closed_at"] = now_iso
            updates["actual_rr"] = -1.0
            updates["pips_gained"] = round((entry_price - current_price) * 10000, 1)

    return updates

def update_signal_in_db(signal_id: int, updates: Dict):
    """Updates the signal in Supabase."""
    url = f"{_table_url('signals')}?id=eq.{signal_id}"
    headers = _headers()

    try:
        response = requests.patch(url, headers=headers, json=updates)
        response.raise_for_status()
        print(f"✅ Signal {signal_id} updated with outcomes: {updates}")
    except Exception as e:
        print(f"Error updating signal {signal_id}: {e}")

def send_outcome_alert(signal: Dict, outcome: str):
    """Sends Telegram message when a signal reaches an outcome."""
    pair = signal.get("pair")
    direction = signal.get("direction", "").upper()

    if outcome == "win":
        msg = f"✅ *{pair} {direction} — TARGET HIT*\nTP2 reached · R:R 1:{signal.get('actual_rr')} · +{signal.get('pips_gained')} pips"
    elif outcome == "tp1":
        msg = f"🎯 *{pair} — TP1 HIT* Move SL to breakeven"
    elif outcome == "loss":
        msg = f"🛑 *{pair} {direction} — STOPPED OUT*\nLoss: -1R · {signal.get('pips_gained')} pips"
    else:
        return

    try:
        send_telegram_message(msg)
    except Exception as e:
        print(f"Error sending outcome alert for {pair}: {e}")

def run_tracker():
    """Main function to track active signals."""
    signals = fetch_open_signals()
    if not signals:
        print("No open signals to track.")
        return

    for signal in signals:
        try:
            pair = signal.get("pair")
            current = fetch_latest_candle(pair, "15m")
            if not current or "close" not in current:
                continue

            current_price = current["close"]
            updates = check_signal_outcome(signal, current_price)

            if updates:
                # Merge updates to signal for telegram alert formatting
                updated_signal = signal.copy()
                updated_signal.update(updates)

                update_signal_in_db(signal["id"], updates)

                if "outcome" in updates:
                    send_outcome_alert(updated_signal, updates["outcome"])
                elif updates.get("tp1_hit"):
                    send_outcome_alert(updated_signal, "tp1")
        except Exception as e:
            print(f"Error tracking signal {signal.get('id')}: {e}")

        time.sleep(1)

def calculate_performance_stats() -> Dict:
    """Calculates overall strategy performance stats from Supabase."""
    url = f"{_table_url('signals')}?outcome=neq.open"
    headers = _headers()

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        signals = response.json()

        total_signals = len(signals)
        wins = sum(1 for s in signals if s.get("outcome") == "win")
        losses = sum(1 for s in signals if s.get("outcome") == "loss")

        win_rate = round(wins / total_signals * 100, 1) if total_signals > 0 else 0
        winning_rrs = [float(s.get("actual_rr", 0)) for s in signals if s.get("outcome") == "win" and s.get("actual_rr") is not None]
        avg_rr = sum(winning_rrs) / len(winning_rrs) if winning_rrs else 0
        total_pips = sum(float(s.get("pips_gained", 0)) for s in signals if s.get("pips_gained") is not None)

        return {
            "total_signals": total_signals,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "avg_rr": avg_rr,
            "total_pips": total_pips,
        }
    except Exception as e:
        print(f"Error calculating stats: {e}")
        return {}

def get_pair_stats(pair: str) -> Dict:
    """Calculates strategy performance stats for a specific pair."""
    url = f"{_table_url('signals')}?outcome=neq.open&pair=eq.{pair}"
    headers = _headers()

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        signals = response.json()

        total = len(signals)
        wins = sum(1 for s in signals if s.get("outcome") == "win")
        win_rate = round(wins / total * 100, 1) if total > 0 else 0
        winning_rrs = [float(s.get("actual_rr", 0)) for s in signals if s.get("outcome") == "win" and s.get("actual_rr") is not None]
        avg_rr = sum(winning_rrs) / len(winning_rrs) if winning_rrs else 0
        total_pips = sum(float(s.get("pips_gained", 0)) for s in signals if s.get("pips_gained") is not None)

        return {
            "total": total,
            "win_rate": win_rate,
            "avg_rr": avg_rr,
            "total_pips": total_pips,
        }
    except Exception as e:
        print(f"Error calculating pair stats: {e}")
        return {}
