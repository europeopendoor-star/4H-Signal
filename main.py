"""
main.py

Orchestrates the 4H Candle Forex Signal Bot.
Handles fetching data, running strategy, saving to Supabase,
and sending notifications via Telegram.
"""

import time
import schedule
from datetime import datetime, timezone

from data_fetcher import fetch_all_timeframes
from strategy import run_strategy_scan, get_current_session
from supabase_writer import save_signal, update_bot_status, clean_old_signals, keep_alive_ping
from notifier import send_signal, send_startup_message

PAIRS_TO_SCAN = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]
sent_signals = {}
daily_signal_count = 0

def scan_pair(pair: str) -> int:
    """Scans a single forex pair for trading signals."""
    global daily_signal_count

    try:
        df_4h, df_15m, df_daily = fetch_all_timeframes(pair)
    except Exception as e:
        print(f"Error fetching timeframes for {pair}: {e}")
        return 0

    if df_4h.empty or df_15m.empty or df_daily.empty:
        print(f"Warning: Empty DataFrame returned for {pair}. Skipping scan.")
        return 0

    try:
        signals = run_strategy_scan(df_4h, df_15m, df_daily, pair=pair, enforce_kill_zone=True)
    except Exception as e:
        print(f"Error running strategy scan for {pair}: {e}")
        return 0

    new_signals = 0

    for signal in signals:
        key = f"{pair}_{signal.direction.value}_{signal.timestamp.floor('4h')}"

        if key not in sent_signals:
            try:
                send_signal(signal, pair)
            except Exception as e:
                print(f"Error sending signal for {pair}: {e}")

            try:
                save_signal(signal, pair)
            except Exception as e:
                print(f"Error saving signal for {pair}: {e}")

            sent_signals[key] = True
            new_signals += 1
            daily_signal_count += 1

    return new_signals

def scan_all():
    """Scans all configured forex pairs."""
    now_utc = datetime.now(timezone.utc)
    session = get_current_session(now_utc)

    print(f"\n[{now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}] Starting scan (Session: {session})...")

    for pair in PAIRS_TO_SCAN:
        try:
            scan_pair(pair)
            time.sleep(2)
        except Exception as e:
            print(f"Error scanning {pair}: {e}")

    try:
        update_bot_status(PAIRS_TO_SCAN, daily_signal_count)
    except Exception as e:
        print(f"Error updating bot status: {e}")

    try:
        from signal_tracker import run_tracker
        run_tracker()
    except Exception as e:
        print(f"Error running signal tracker: {e}")

    try:
        clean_old_signals(days_to_keep=14)
    except Exception as e:
        print(f"Error cleaning old signals: {e}")

    now_utc_end = datetime.now(timezone.utc)
    print(f"[{now_utc_end.strftime('%Y-%m-%d %H:%M:%S UTC')}] Scan complete.")

def daily_reset():
    """Resets daily metrics and pings Supabase."""
    global daily_signal_count
    daily_signal_count = 0
    try:
        keep_alive_ping()
    except Exception as e:
        print(f"Error during daily reset ping: {e}")
    print("Daily reset completed.")

def main():
    """Main execution loop for the Forex Signal Bot."""
    print("╔═════════════════════════════════════════╗")
    print("║      4H CANDLE FOREX SIGNAL BOT v2      ║")
    print("╚═════════════════════════════════════════╝")

    try:
        send_startup_message()
    except Exception as e:
        print(f"Error sending startup message: {e}")

    scan_all()

    schedule.every(15).minutes.do(scan_all)
    schedule.every().day.at("00:01").do(daily_reset)

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        print("\nBot stopped by user.")

if __name__ == "__main__":
    main()
