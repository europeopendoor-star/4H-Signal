"""
news_filter.py

Fetches high-impact economic news events from Twelve Data and blocks
signals from firing within 30 minutes before or after these events.
"""

import os
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Tuple

TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")

FOREX_CURRENCY_MAP = {
    "EURUSD": ["EUR", "USD"],
    "GBPUSD": ["GBP", "USD"],
    "USDJPY": ["JPY", "USD"],
    "AUDUSD": ["AUD", "USD"],
    "USDCAD": ["CAD", "USD"],
    "GBPJPY": ["GBP", "JPY"],
    "NZDUSD": ["NZD", "USD"],
    "USDCHF": ["USD", "CHF"]
}

HIGH_IMPACT_KEYWORDS = [
    "Non-Farm Payrolls", "NFP", "FOMC", "Fed Rate Decision",
    "CPI", "GDP", "Interest Rate Decision", "Unemployment Rate",
    "Retail Sales", "PMI"
]

_news_cache = []
_cache_timestamp = None

def fetch_todays_news_events() -> List[Dict]:
    """Fetches today's high-impact news events from Twelve Data."""
    global _news_cache, _cache_timestamp

    now = datetime.now(timezone.utc)

    if _cache_timestamp and (now - _cache_timestamp) < timedelta(hours=1):
        return _news_cache

    if not TWELVEDATA_API_KEY:
        print("Warning: TWELVEDATA_API_KEY not set. Skipping news filter.")
        return []

    today_str = now.strftime('%Y-%m-%d')
    url = f"https://api.twelvedata.com/economic_calendar?start_date={today_str}&end_date={today_str}&importance=High&apikey={TWELVEDATA_API_KEY}"

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()

        if "status" in data and data["status"] == "error":
            print(f"Warning: Twelve Data news fetch error: {data.get('message')}")
            return []

        events = data.get("events", [])
        parsed_events = []

        for event in events:
            date_str = event.get("date")
            time_str = event.get("time")
            if not date_str or not time_str:
                continue

            try:
                # Twelve Data returns time in HH:mm format, assume UTC or adjust if API docs specify
                dt_str = f"{date_str} {time_str}"
                try:
                    event_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                except ValueError:
                    event_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            except Exception as e:
                continue

            parsed_events.append({
                "event_name": event.get("event"),
                "country": event.get("country"),
                "currency": event.get("currency"),
                "datetime": event_dt
            })

        _news_cache = parsed_events
        _cache_timestamp = now
        return _news_cache

    except Exception as e:
        print(f"Warning: Error fetching news events: {e}")
        return []

def is_news_blackout(pair: str, check_time: datetime = None) -> Tuple[bool, str]:
    """Checks if a given pair is within a 30-minute blackout window around high-impact news."""
    if not check_time:
        check_time = datetime.now(timezone.utc)

    pair_currencies = FOREX_CURRENCY_MAP.get(pair, [])
    events = fetch_todays_news_events()

    blackout_window = 30

    for event in events:
        if event.get("currency") in pair_currencies or any(kw.lower() in event.get("event_name", "").lower() for kw in HIGH_IMPACT_KEYWORDS):
            event_dt = event.get("datetime")
            time_diff = abs((check_time - event_dt).total_seconds() / 60)

            if time_diff <= blackout_window:
                return True, f"{event.get('event_name')} in {int(time_diff)}min"

    return False, ""

def get_upcoming_events_for_pair(pair: str) -> List[Dict]:
    """Returns the next 3 high-impact events for a specific pair today."""
    now = datetime.now(timezone.utc)
    pair_currencies = FOREX_CURRENCY_MAP.get(pair, [])
    events = fetch_todays_news_events()
    upcoming = []

    for event in events:
        event_dt = event.get("datetime")
        if event_dt >= now and event.get("currency") in pair_currencies:
            minutes_away = int((event_dt - now).total_seconds() / 60)
            upcoming.append({
                "name": event.get("event_name"),
                "time_utc": event_dt.isoformat(),
                "minutes_away": minutes_away
            })

    upcoming.sort(key=lambda x: x["minutes_away"])
    return upcoming[:3]
