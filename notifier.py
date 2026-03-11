"""
notifier.py

Telegram notification logic for the Forex Signal Bot.
Uses the Telegram Bot API to send trade signals.
"""

import os
import requests
from dotenv import load_dotenv
load_dotenv()
from strategy import TradeSignal, Direction

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def send_signal(signal: TradeSignal, pair: str):
    """Sends a formatted trade signal via Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram configuration missing. Skipping alert.")
        return

    direction_emoji = "🟢" if signal.direction == Direction.BULLISH else "🔴"
    conf_emoji = "🔥" if signal.confidence == "HIGH" else "⚡"

    flag_labels = {
        "4h_candle": "4H CANDLE",
        "liq_sweep": "LIQ SWEEP",
        "struct_break": "BOS/CHoCH",
        "fvg_entry": "FVG",
        "kill_zone": "KILL ZONE",
        "daily_bias": "DAILY BIAS",
        "choch": "CHOCH",
        "order_block": "OB ALIGN"
    }

    confluences = []
    for flag, passed in signal.confluence_flags.items():
        icon = "✅" if passed else "❌"
        confluences.append(f"{icon} {flag_labels.get(flag, flag)}")

    confluences_text = "\n".join(confluences)

    message = f"""{direction_emoji} *{pair} — {signal.direction.value.upper()} SIGNAL*
{conf_emoji} Confidence: *{signal.confidence}* ({signal.confluence_score}/8)

📍 *Entry Zone (OTE)*
`{signal.entry_low:.5f}` → `{signal.entry_high:.5f}`
OTE: `{signal.entry_price:.5f}`

🛑 *Stop Loss*
`{signal.stop_loss:.5f}`

🎯 *Take Profit*
TP1 (1:1) : `{signal.take_profit_1:.5f}`
TP2 (4H)  : `{signal.take_profit_2:.5f}`
TP3 (3R)  : `{signal.take_profit_3:.5f}`

📊 *R:R*  1:{signal.risk_reward}
⏰ Session: {signal.session}

✅ *Confluences ({signal.confluence_score}/8)*
{confluences_text}

🕐 {signal.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}"""

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print(f"[{pair}] Telegram alert sent.")
    except Exception as e:
        print(f"Error sending Telegram alert for {pair}: {e}")

def send_startup_message():
    """Sends a startup message to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    message = """🤖 *Forex Signal Bot v2 Started*
Scanning: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD
Strategy: 4H Candle + 8-filter ICT/SMC
Database: Supabase
Kill Zones: London (07–10 UTC) · NY (12–16 UTC)"""

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("Startup message sent to Telegram.")
    except Exception as e:
        print(f"Error sending Telegram startup message: {e}")

def send_telegram_message(message: str):
    """Sends a raw text message to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Error sending Telegram message: {e}")
