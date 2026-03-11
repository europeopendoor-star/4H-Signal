"""
strategy.py

Core strategy module for the 4H Candle Forex Signal Bot.
Implements the full ICT/SMC 4H Candle Setup using pandas and numpy.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import pandas as pd
import numpy as np
from datetime import datetime, timezone

class Direction(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"

@dataclass
class CandleZone:
    direction: Direction
    candle_high: float
    candle_low: float
    body_high: float
    body_low: float
    wick_zone_upper: float
    wick_zone_lower: float
    timestamp: pd.Timestamp
    atr: float = 0.0

@dataclass
class LiquiditySweep:
    direction: Direction
    sweep_price: float
    swept_level: float
    timestamp: pd.Timestamp
    confirmed: bool
    sweep_size_atr: float

@dataclass
class OrderBlock:
    direction: Direction
    ob_high: float
    ob_low: float
    ob_mid: float
    timestamp: pd.Timestamp
    is_breaker: bool = False

@dataclass
class FairValueGap:
    direction: Direction
    fvg_high: float
    fvg_low: float
    fvg_mid: float
    timestamp: pd.Timestamp
    filled: bool = False
    ote_entry: float = 0.0

@dataclass
class StructureBreak:
    direction: Direction
    break_level: float
    timestamp: pd.Timestamp
    is_choch: bool = False

@dataclass
class TradeSignal:
    direction: Direction
    entry_price: float
    entry_high: float
    entry_low: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    risk_reward: float
    confidence: str
    confluence_score: int
    confluence_flags: Dict[str, bool]
    candle_zone: CandleZone
    sweep: LiquiditySweep
    fvg: FairValueGap
    structure_break: StructureBreak
    order_block: Optional[OrderBlock]
    pair: str = ""
    timestamp: pd.Timestamp = field(default_factory=pd.Timestamp.utcnow)
    session: str = ""


# FUNCTION 1 — get_current_session
def get_current_session(dt=None) -> str:
    """
    Kill zones (all UTC):
      "London":      07:00–10:00
      "NewYork":     12:00–16:00
      "LondonClose": 15:00–17:00
      "Other":       everything else
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    hour = dt.hour

    if 7 <= hour < 10:
        return "London"
    elif 12 <= hour < 16:
        return "NewYork"
    elif 15 <= hour < 17:
        return "LondonClose"
    else:
        return "Other"


# FUNCTION 2 — is_in_kill_zone
def is_in_kill_zone(dt=None) -> bool:
    """Return True if current session is not 'Other'."""
    return get_current_session(dt) != "Other"


# FUNCTION 3 — get_daily_bias
def get_daily_bias(df_daily: pd.DataFrame) -> Optional[Direction]:
    """
    Requires at least 22 rows.
    Count bullish candles (close > open) in last 5 daily rows.
    Calculate EMA(20) of daily closes using ewm(span=20).
    BULLISH: bullish_count >= 3 AND last close > ema20
    BEARISH: bearish_count >= 3 AND last close < ema20
    Otherwise: return None
    """
    if len(df_daily) < 22:
        return None

    last_5 = df_daily.tail(5)
    bullish_count = sum(last_5['close'] > last_5['open'])
    bearish_count = sum(last_5['close'] < last_5['open'])

    ema20 = df_daily['close'].ewm(span=20, adjust=False).mean()
    last_close = df_daily['close'].iloc[-1]
    last_ema20 = ema20.iloc[-1]

    if bullish_count >= 3 and last_close > last_ema20:
        return Direction.BULLISH
    elif bearish_count >= 3 and last_close < last_ema20:
        return Direction.BEARISH

    return None


# FUNCTION 4 — calculate_atr
def calculate_atr(df: pd.DataFrame, period=14) -> float:
    """
    True Range = max(high, prev_close) - min(low, prev_close)
    Return rolling(period).mean() of TR for last row.
    """
    if len(df) < period + 1:
        return 0.0

    high = df['high']
    low = df['low']
    prev_close = df['close'].shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    return float(atr.iloc[-1])


# FUNCTION 5 — detect_large_4h_candle
def detect_large_4h_candle(df_4h: pd.DataFrame, size_percentile=75) -> List[CandleZone]:
    """
    Detects large 4H candles representing significant institutional displacement.
    """
    zones = []
    if len(df_4h) < 2:
        return zones

    body_size = (df_4h['close'] - df_4h['open']).abs()
    candle_range = df_4h['high'] - df_4h['low']

    if len(body_size) == 0:
        return zones

    threshold = body_size.quantile(size_percentile / 100.0)
    body_ratio = body_size / candle_range.replace(0, np.nan)

    atr = calculate_atr(df_4h)

    for timestamp, row in df_4h.iterrows():
        b_size = abs(row['close'] - row['open'])
        c_range = row['high'] - row['low']
        b_ratio = b_size / c_range if c_range > 0 else 0

        if b_size > threshold and b_ratio > 0.5:
            is_bullish = row['close'] > row['open']
            direction = Direction.BULLISH if is_bullish else Direction.BEARISH

            body_high = max(row['open'], row['close'])
            body_low = min(row['open'], row['close'])

            if direction == Direction.BULLISH:
                wick_zone_upper = body_low
                wick_zone_lower = row['low']
            else:
                wick_zone_upper = row['high']
                wick_zone_lower = body_high

            zone = CandleZone(
                direction=direction,
                candle_high=row['high'],
                candle_low=row['low'],
                body_high=body_high,
                body_low=body_low,
                wick_zone_upper=wick_zone_upper,
                wick_zone_lower=wick_zone_lower,
                timestamp=timestamp,
                atr=atr
            )
            zones.append(zone)

    return zones


# FUNCTION 6 — detect_liquidity_sweep
def detect_liquidity_sweep(df_15m: pd.DataFrame, zone: CandleZone, lookback_candles=20) -> Optional[LiquiditySweep]:
    """
    Checks if 15M candles sweep the liquidity pool below/above the 4H zone.
    """
    # Look only at candles after the zone
    df_post_zone = df_15m[df_15m.index >= zone.timestamp].head(lookback_candles)
    if len(df_post_zone) == 0:
        return None

    sweep_buffer = zone.atr * 0.1 if zone.atr > 0 else 0.0003

    for i in range(len(df_post_zone)):
        timestamp = df_post_zone.index[i]
        row = df_post_zone.iloc[i]

        if zone.direction == Direction.BULLISH:
            if row['low'] < (zone.candle_low - sweep_buffer):
                # Candle or next candle must close > zone.candle_low
                closed_above = row['close'] > zone.candle_low
                if not closed_above and i + 1 < len(df_post_zone):
                    closed_above = df_post_zone.iloc[i+1]['close'] > zone.candle_low

                if closed_above:
                    sweep_size_atr = (zone.candle_low - row['low']) / zone.atr if zone.atr > 0 else 0
                    return LiquiditySweep(
                        direction=Direction.BULLISH,
                        sweep_price=row['low'],
                        swept_level=zone.candle_low,
                        timestamp=timestamp,
                        confirmed=True,
                        sweep_size_atr=sweep_size_atr
                    )

        else: # BEARISH
            if row['high'] > (zone.candle_high + sweep_buffer):
                # Candle or next candle must close < zone.candle_high
                closed_below = row['close'] < zone.candle_high
                if not closed_below and i + 1 < len(df_post_zone):
                    closed_below = df_post_zone.iloc[i+1]['close'] < zone.candle_high

                if closed_below:
                    sweep_size_atr = (row['high'] - zone.candle_high) / zone.atr if zone.atr > 0 else 0
                    return LiquiditySweep(
                        direction=Direction.BEARISH,
                        sweep_price=row['high'],
                        swept_level=zone.candle_high,
                        timestamp=timestamp,
                        confirmed=True,
                        sweep_size_atr=sweep_size_atr
                    )

    return None


# FUNCTION 7 — detect_structure_break
def detect_structure_break(df_15m: pd.DataFrame, sweep: LiquiditySweep, lookforward_candles=15) -> Optional[StructureBreak]:
    """
    Finds Break of Structure (BOS) or Change of Character (CHoCH) after a sweep.
    """
    post_sweep = df_15m[df_15m.index > sweep.timestamp].head(lookforward_candles)
    pre_sweep = df_15m[df_15m.index <= sweep.timestamp].tail(10)

    if len(post_sweep) == 0 or len(pre_sweep) == 0:
        return None

    if sweep.direction == Direction.BULLISH: # looking for BULLISH structure break
        swing_high = post_sweep['high'].head(5).max()
        prev_high = pre_sweep['high'].max()

        for timestamp, row in post_sweep.iterrows():
            if row['close'] > swing_high:
                is_choch = row['close'] > prev_high
                return StructureBreak(
                    direction=Direction.BULLISH,
                    break_level=swing_high,
                    timestamp=timestamp,
                    is_choch=is_choch
                )
    else: # BEARISH
        swing_low = post_sweep['low'].head(5).min()
        prev_low = pre_sweep['low'].min()

        for timestamp, row in post_sweep.iterrows():
            if row['close'] < swing_low:
                is_choch = row['close'] < prev_low
                return StructureBreak(
                    direction=Direction.BEARISH,
                    break_level=swing_low,
                    timestamp=timestamp,
                    is_choch=is_choch
                )

    return None


# FUNCTION 8 — detect_fvg
def detect_fvg(df_15m: pd.DataFrame, structure_break: StructureBreak, lookback=10) -> Optional[FairValueGap]:
    """
    Detects a Fair Value Gap (FVG) for an Optimal Trade Entry (OTE).
    """
    df_lookback = df_15m[df_15m.index <= structure_break.timestamp].tail(lookback)

    if len(df_lookback) < 3:
        return None

    candles = df_lookback.to_dict('records')
    timestamps = df_lookback.index

    for i in range(len(candles) - 2):
        if structure_break.direction == Direction.BULLISH:
            if candles[i]['high'] < candles[i+2]['low']:
                fvg_low = candles[i]['high']
                fvg_high = candles[i+2]['low']
                fvg_mid = (fvg_high + fvg_low) / 2
                ote_entry = fvg_high - ((fvg_high - fvg_low) * 0.618)

                return FairValueGap(
                    direction=Direction.BULLISH,
                    fvg_high=fvg_high,
                    fvg_low=fvg_low,
                    fvg_mid=fvg_mid,
                    timestamp=timestamps[i+2],
                    ote_entry=ote_entry
                )
        else: # BEARISH
            if candles[i]['low'] > candles[i+2]['high']:
                fvg_high = candles[i]['low']
                fvg_low = candles[i+2]['high']
                fvg_mid = (fvg_high + fvg_low) / 2
                ote_entry = fvg_low + ((fvg_high - fvg_low) * 0.618)

                return FairValueGap(
                    direction=Direction.BEARISH,
                    fvg_high=fvg_high,
                    fvg_low=fvg_low,
                    fvg_mid=fvg_mid,
                    timestamp=timestamps[i+2],
                    ote_entry=ote_entry
                )

    return None


# FUNCTION 9 — detect_order_blocks
def detect_order_blocks(df_15m: pd.DataFrame, direction: Direction, lookback=20) -> List[OrderBlock]:
    """
    Identifies institutional Order Blocks based on body size and sequence.
    """
    df_lookback = df_15m.tail(lookback)
    if len(df_lookback) < 3:
        return []

    avg_body = (df_lookback['close'] - df_lookback['open']).abs().mean()
    obs = []

    candles = df_lookback.to_dict('records')
    timestamps = df_lookback.index

    for i in range(len(candles) - 2):
        c0 = candles[i]
        c1 = candles[i+1]
        c2 = candles[i+2]

        c0_bullish = c0['close'] > c0['open']
        c1_bullish = c1['close'] > c1['open']
        c2_bullish = c2['close'] > c2['open']

        c1_body = abs(c1['close'] - c1['open'])

        if direction == Direction.BULLISH:
            if not c0_bullish and c1_bullish and c2_bullish:
                if c1_body > avg_body * 1.5:
                    ob_high = max(c0['open'], c0['close'])
                    ob_low = min(c0['open'], c0['close'])
                    obs.append(OrderBlock(
                        direction=Direction.BULLISH,
                        ob_high=ob_high,
                        ob_low=ob_low,
                        ob_mid=(ob_high + ob_low) / 2,
                        timestamp=timestamps[i]
                    ))
        else: # BEARISH
            if c0_bullish and not c1_bullish and not c2_bullish:
                if c1_body > avg_body * 1.5:
                    ob_high = max(c0['open'], c0['close'])
                    ob_low = min(c0['open'], c0['close'])
                    obs.append(OrderBlock(
                        direction=Direction.BEARISH,
                        ob_high=ob_high,
                        ob_low=ob_low,
                        ob_mid=(ob_high + ob_low) / 2,
                        timestamp=timestamps[i]
                    ))

    return obs


# FUNCTION 10 — identify_breaker_blocks
def identify_breaker_blocks(obs: List[OrderBlock], df_15m: pd.DataFrame) -> List[OrderBlock]:
    """
    Marks Order Blocks that have been broken, acting as Breaker Blocks.
    """
    if len(df_15m) == 0:
        return obs

    current_high = df_15m['high'].max()
    current_low = df_15m['low'].min()

    for ob in obs:
        if ob.direction == Direction.BULLISH and current_low < ob.ob_low:
            ob.is_breaker = True
        elif ob.direction == Direction.BEARISH and current_high > ob.ob_high:
            ob.is_breaker = True

    return obs


# FUNCTION 11 — check_breaker_blocks
def check_breaker_blocks(df_15m: pd.DataFrame, direction: Direction, entry_price: float, obs: List[OrderBlock]) -> bool:
    """
    Returns False if entry path is blocked by a Breaker Block.
    """
    for ob in obs:
        if ob.is_breaker:
            if direction == Direction.BULLISH:
                if ob.direction == Direction.BEARISH and ob.ob_low > entry_price and ob.ob_low < entry_price * 1.003:
                    return False
            else: # BEARISH
                if ob.direction == Direction.BULLISH and ob.ob_high < entry_price and ob.ob_high > entry_price * 0.997:
                    return False
    return True


# FUNCTION 12 — generate_signal
def generate_signal(zone: CandleZone, sweep: LiquiditySweep, structure_break: StructureBreak,
                    fvg: FairValueGap, order_block: Optional[OrderBlock], daily_bias: Optional[Direction],
                    session: str, pair: str) -> Optional[TradeSignal]:
    """
    Generates a TradeSignal if confluences are sufficient.
    """
    entry_price = fvg.ote_entry if fvg.ote_entry > 0 else fvg.fvg_mid
    atr = zone.atr if zone.atr > 0 else 0.001
    sl_buffer = atr * 0.5

    confluence_flags = {
        "4h_candle": True,
        "liq_sweep": True,
        "struct_break": True,
        "fvg_entry": True,
        "kill_zone": session != "Other",
        "daily_bias": daily_bias == structure_break.direction if daily_bias else False,
        "choch": structure_break.is_choch,
        "order_block": order_block is not None
    }

    score = sum(confluence_flags.values())

    if score < 5:
        print(f"Skipping signal: score {score}/8 is below threshold.")
        return None

    if structure_break.direction == Direction.BULLISH:
        stop_loss = sweep.sweep_price - sl_buffer
        risk = entry_price - stop_loss
        if risk <= 0: return None
        tp1 = entry_price + risk
        tp2 = zone.candle_high
        tp3 = entry_price + (risk * 3)
    else: # BEARISH
        stop_loss = sweep.sweep_price + sl_buffer
        risk = stop_loss - entry_price
        if risk <= 0: return None
        tp1 = entry_price - risk
        tp2 = zone.candle_low
        tp3 = entry_price - (risk * 3)

    rr = round(abs(tp2 - entry_price) / risk, 2)
    confidence = "HIGH" if score >= 7 else "MEDIUM"

    signal = TradeSignal(
        direction=structure_break.direction,
        entry_price=entry_price,
        entry_high=fvg.fvg_high,
        entry_low=fvg.fvg_low,
        stop_loss=stop_loss,
        take_profit_1=tp1,
        take_profit_2=tp2,
        take_profit_3=tp3,
        risk_reward=rr,
        confidence=confidence,
        confluence_score=score,
        confluence_flags=confluence_flags,
        candle_zone=zone,
        sweep=sweep,
        fvg=fvg,
        structure_break=structure_break,
        order_block=order_block,
        pair=pair,
        timestamp=pd.Timestamp.utcnow(),
        session=session
    )

    return signal


# FUNCTION 13 — run_strategy_scan
def run_strategy_scan(df_4h: pd.DataFrame, df_15m: pd.DataFrame, df_daily: pd.DataFrame, pair: str = "", enforce_kill_zone: bool = True) -> List[TradeSignal]:
    """
    Full scanning pipeline for a given pair.
    """
    signals = []

    session = get_current_session()
    if enforce_kill_zone and session == "Other":
        return signals

    is_blackout, reason = news_filter.is_news_blackout(pair)
    if is_blackout:
        print(f"  📰 {pair} blocked — news blackout: {reason}")
        return []

    daily_bias = get_daily_bias(df_daily)
    zones = detect_large_4h_candle(df_4h.tail(10))

    for zone in zones:
        if daily_bias is not None and zone.direction != daily_bias:
            continue

        sweep = detect_liquidity_sweep(df_15m, zone)
        if not sweep:
            continue

        structure_break = detect_structure_break(df_15m, sweep)
        if not structure_break:
            continue

        fvg = detect_fvg(df_15m, structure_break)
        if not fvg:
            continue

        obs = detect_order_blocks(df_15m, structure_break.direction)
        obs = identify_breaker_blocks(obs, df_15m)

        # Find matching_ob: first non-breaker OB
        matching_ob = None
        for ob in obs:
            if not ob.is_breaker:
                matching_ob = ob
                break

        entry_price = fvg.ote_entry if fvg.ote_entry > 0 else fvg.fvg_mid

        if not check_breaker_blocks(df_15m, structure_break.direction, entry_price, obs):
            print(f"[{pair}] Blocked by breaker block.")
            continue

        signal = generate_signal(zone, sweep, structure_break, fvg, matching_ob, daily_bias, session, pair)

        if signal:
            # Print ASCII box
            print(f"╔{'═'*40}╗")
            print(f"║ {pair} - {signal.direction.value.upper()} SIGNAL")
            print(f"║ Confidence: {signal.confidence} ({signal.confluence_score}/8)")
            print(f"║ Entry: {signal.entry_price:.5f}")
            print(f"║ Stop Loss: {signal.stop_loss:.5f}")
            print(f"║ TP1: {signal.take_profit_1:.5f}")
            print(f"║ TP2: {signal.take_profit_2:.5f}")
            print(f"║ TP3: {signal.take_profit_3:.5f}")
            print(f"║ R:R: 1:{signal.risk_reward}")
            print(f"╚{'═'*40}╝")
            signals.append(signal)

    return signals
