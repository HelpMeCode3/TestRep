#!/usr/bin/env python3
"""
Stock Trading Bot - 3-Minute Candle Scanner
============================================
Data source : Yahoo Finance via yfinance (NO API key required)
After-hours : YES (prepost=True)
Scan interval: Every 3 minutes
Signals      : BUY / SELL / HOLD with entry, stop-loss, and targets

Usage:
    python stock_bot.py
    python stock_bot.py --ticker TSLA
    python stock_bot.py --ticker AAPL --once   (single scan, no loop)
"""

import argparse
import os
import sys
import time
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ── Optional colour support ───────────────────────────────────────────────────
try:
    from colorama import Fore, Style, init
    init(autoreset=True)
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False


# ── Colour helpers ────────────────────────────────────────────────────────────

def _c(text, fg="white", bright=False):
    if not HAS_COLOR:
        return str(text)
    palette = {
        "green":   Fore.GREEN,
        "red":     Fore.RED,
        "yellow":  Fore.YELLOW,
        "cyan":    Fore.CYAN,
        "magenta": Fore.MAGENTA,
        "white":   Fore.WHITE,
    }
    out = palette.get(fg, "") + (Style.BRIGHT if bright else "") + str(text) + Style.RESET_ALL
    return out


# ── Technical indicators ──────────────────────────────────────────────────────

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    line = ema_fast - ema_slow
    sig  = line.ewm(span=signal, adjust=False).mean()
    hist = line - sig
    return line, sig, hist


def bollinger(close: pd.Series, period=20, dev=2):
    sma   = close.rolling(period).mean()
    sigma = close.rolling(period).std()
    return sma + dev * sigma, sma, sma - dev * sigma


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period=14) -> pd.Series:
    tr = pd.concat(
        [high - low,
         (high - close.shift()).abs(),
         (low  - close.shift()).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


def stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
               k_period=14, d_period=3):
    lowest  = low.rolling(k_period).min()
    highest = high.rolling(k_period).max()
    k = 100 * (close - lowest) / (highest - lowest).replace(0, np.nan)
    d = k.rolling(d_period).mean()
    return k, d


def vwap(high: pd.Series, low: pd.Series, close: pd.Series,
         volume: pd.Series) -> pd.Series:
    tp = (high + low + close) / 3
    return (tp * volume).cumsum() / volume.cumsum()


def ema(close: pd.Series, span: int) -> pd.Series:
    return close.ewm(span=span, adjust=False).mean()


def support_resistance(df: pd.DataFrame, window=30):
    h = df["High"].rolling(window, center=True).max()
    l = df["Low"].rolling(window, center=True).min()
    return l.dropna().iloc[-window:].min(), h.dropna().iloc[-window:].max()


# ── Data fetcher ──────────────────────────────────────────────────────────────

def fetch_3min_candles(ticker: str) -> tuple[pd.DataFrame | None, object | None]:
    """
    Pull 1-minute bars for the past 2 days (including pre/after-market)
    then resample into 3-minute candles.
    Returns (df_3m, fast_info) or (None, None) on error.
    """
    try:
        t = yf.Ticker(ticker)
        df = t.history(period="2d", interval="1m", prepost=True, auto_adjust=True)

        if df.empty:
            return None, None

        df_3m = (
            df.resample("3min")
            .agg({"Open": "first", "High": "max", "Low": "min",
                  "Close": "last", "Volume": "sum"})
            .dropna(subset=["Open", "Close"])
        )

        info = t.fast_info
        return df_3m, info

    except Exception as exc:
        print(f"[ERROR] yfinance: {exc}")
        return None, None


# ── Signal engine ─────────────────────────────────────────────────────────────

def analyze(df: pd.DataFrame) -> dict | None:
    """Score all indicators and return a structured result dict."""
    if len(df) < 30:
        return None

    o  = df["Open"]
    h  = df["High"]
    l  = df["Low"]
    c  = df["Close"]
    v  = df["Volume"]

    # --- compute indicators ---
    _rsi             = rsi(c)
    _macd, _sig, _hist = macd(c)
    _bb_up, _bb_mid, _bb_lo = bollinger(c)
    _atr             = atr(h, l, c)
    _stk, _std       = stochastic(h, l, c)
    _vwap            = vwap(h, l, c, v)
    _ema9            = ema(c, 9)
    _ema21           = ema(c, 21)
    _ema50           = ema(c, 50)
    _sup, _res       = support_resistance(df)
    _vol_avg         = v.rolling(20).mean()

    # --- latest snapshot ---
    cur = {
        "price":      c.iloc[-1],
        "rsi":        _rsi.iloc[-1],
        "rsi_prev":   _rsi.iloc[-2],
        "macd":       _macd.iloc[-1],
        "macd_sig":   _sig.iloc[-1],
        "hist":       _hist.iloc[-1],
        "hist_prev":  _hist.iloc[-2],
        "bb_up":      _bb_up.iloc[-1],
        "bb_mid":     _bb_mid.iloc[-1],
        "bb_lo":      _bb_lo.iloc[-1],
        "stk_k":      _stk.iloc[-1],
        "stk_d":      _std.iloc[-1],
        "vwap":       _vwap.iloc[-1],
        "ema9":       _ema9.iloc[-1],
        "ema21":      _ema21.iloc[-1],
        "ema50":      _ema50.iloc[-1],
        "atr":        _atr.iloc[-1],
        "volume":     v.iloc[-1],
        "vol_avg":    _vol_avg.iloc[-1],
        "support":    _sup,
        "resistance": _res,
        "candle_body": abs(c.iloc[-1] - o.iloc[-1]),
    }

    atr_v = max(cur["atr"], 0.001)

    # --- scoring ---
    bull = 0
    bear = 0
    signals: list[tuple[str, str]] = []   # (description, direction)

    def add(desc, direction, pts=1):
        nonlocal bull, bear
        if direction == "BULL":
            bull += pts
        elif direction == "BEAR":
            bear += pts
        signals.append((desc, direction))

    # RSI
    if cur["rsi"] < 30:
        add("RSI Oversold (<30)", "BULL", 2)
    elif cur["rsi"] < 40:
        add("RSI Low (30-40)", "BULL", 1)
    elif cur["rsi"] > 70:
        add("RSI Overbought (>70)", "BEAR", 2)
    elif cur["rsi"] > 60:
        add("RSI High (60-70)", "BEAR", 1)

    # MACD histogram cross
    if cur["hist"] > 0 and cur["hist_prev"] <= 0:
        add("MACD Histogram → Bullish Cross", "BULL", 3)
    elif cur["hist"] < 0 and cur["hist_prev"] >= 0:
        add("MACD Histogram → Bearish Cross", "BEAR", 3)
    elif cur["hist"] > 0:
        add("MACD Histogram Positive", "BULL", 1)
    else:
        add("MACD Histogram Negative", "BEAR", 1)

    # EMA stack
    if cur["ema9"] > cur["ema21"] > cur["ema50"]:
        add("EMA 9>21>50 Bullish Stack", "BULL", 2)
    elif cur["ema9"] < cur["ema21"] < cur["ema50"]:
        add("EMA 9<21<50 Bearish Stack", "BEAR", 2)
    elif cur["ema9"] > cur["ema21"]:
        add("EMA 9 above 21", "BULL", 1)
    else:
        add("EMA 9 below 21", "BEAR", 1)

    # Price vs VWAP
    if cur["price"] > cur["vwap"]:
        add("Price above VWAP", "BULL", 1)
    else:
        add("Price below VWAP", "BEAR", 1)

    # Bollinger Bands
    if cur["price"] <= cur["bb_lo"]:
        add("Price at/below BB Lower Band", "BULL", 2)
    elif cur["price"] >= cur["bb_up"]:
        add("Price at/above BB Upper Band", "BEAR", 2)

    # Stochastic
    if cur["stk_k"] < 20 and cur["stk_d"] < 20:
        add("Stochastic Oversold (<20)", "BULL", 2)
    elif cur["stk_k"] > 80 and cur["stk_d"] > 80:
        add("Stochastic Overbought (>80)", "BEAR", 2)
    elif cur["stk_k"] > cur["stk_d"]:
        add("Stochastic K above D", "BULL", 1)
    else:
        add("Stochastic K below D", "BEAR", 1)

    # Support / resistance proximity
    if abs(cur["price"] - cur["support"]) < atr_v * 0.5:
        add("Price near Support level", "BULL", 1)
    if abs(cur["price"] - cur["resistance"]) < atr_v * 0.5:
        add("Price near Resistance level", "BEAR", 1)

    # Volume spike confirmation
    if cur["vol_avg"] and cur["volume"] > cur["vol_avg"] * 1.5:
        direction = "BULL" if bull >= bear else "BEAR"
        add("High Volume Spike (confirms bias)", direction, 1)

    # --- confidence & action ---
    total = bull + bear
    confidence = (max(bull, bear) / total * 100) if total else 0

    if bull > bear and confidence >= 55:
        action = "BUY"
    elif bear > bull and confidence >= 55:
        action = "SELL"
    else:
        action = "HOLD"

    # --- trade levels (ATR-based) ---
    entry = cur["price"]
    if action == "BUY":
        stop_loss = entry - atr_v * 1.5
        target1   = entry + atr_v * 2.0
        target2   = entry + atr_v * 3.5
    elif action == "SELL":
        stop_loss = entry + atr_v * 1.5
        target1   = entry - atr_v * 2.0
        target2   = entry - atr_v * 3.5
    else:
        stop_loss = entry - atr_v * 1.5
        target1   = entry + atr_v * 2.0
        target2   = entry + atr_v * 3.5

    rr = abs(target1 - entry) / max(abs(stop_loss - entry), 0.0001)

    return {
        "action":     action,
        "confidence": confidence,
        "bull":       bull,
        "bear":       bear,
        "signals":    signals,
        "ind":        cur,
        "entry":      entry,
        "stop_loss":  stop_loss,
        "target1":    target1,
        "target2":    target2,
        "rr":         rr,
    }


# ── Display ───────────────────────────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")


def print_header(ticker: str, scan_no: int, num_candles: int, price: float):
    W = 62
    print(_c("═" * W, "cyan"))
    print(_c(f"  STOCK TRADING BOT  │  {ticker}  │  3-MIN CANDLE SCANNER", "cyan", bright=True))
    print(_c("═" * W, "cyan"))
    print(f"  {_c('Time', 'yellow')}        : {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print(f"  {_c('Ticker', 'yellow')}      : {_c(ticker, 'white', bright=True)}")
    print(f"  {_c('Price', 'yellow')}       : {_c(f'${price:,.4f}', 'green', bright=True)}")
    print(f"  {_c('Scan #', 'yellow')}      : {scan_no}   ({num_candles} 3-min candles loaded)")
    print(_c("─" * W, "cyan"))


def print_action(result: dict):
    a  = result["action"]
    cf = result["confidence"]
    W  = 62

    if a == "BUY":
        badge = _c(f"  ▲  BUY   — Confidence {cf:.0f}%  ▲", "green", bright=True)
    elif a == "SELL":
        badge = _c(f"  ▼  SELL  — Confidence {cf:.0f}%  ▼", "red", bright=True)
    else:
        badge = _c(f"  ■  HOLD  — Confidence {cf:.0f}%  ■", "yellow", bright=True)

    print()
    print(badge)
    print(f"  Bull Score : {_c(result['bull'], 'green')}   Bear Score : {_c(result['bear'], 'red')}")


def print_levels(result: dict):
    a   = result["action"]
    ind = result["ind"]
    print()
    print(_c("  TRADE LEVELS", "cyan", bright=True))

    entry_tag  = "  Entry      :"
    sl_tag     = "  Stop Loss  :"
    t1_tag     = "  Target 1   :"
    t2_tag     = "  Target 2   :"
    rr_tag     = "  R/R Ratio  :"

    entry_str = "${:,.4f}".format(result["entry"])
    print(f"{entry_tag} {_c(entry_str, 'white', bright=True)}")

    if a == "BUY":
        sl_str = "${:,.4f}  <- exit if price drops here".format(result["stop_loss"])
        t1_str = "${:,.4f}  <- take partial profit".format(result["target1"])
        t2_str = "${:,.4f}  <- full exit / trail stop".format(result["target2"])
        print(f"{sl_tag} {_c(sl_str, 'red')}")
        print(f"{t1_tag} {_c(t1_str, 'green')}")
        print(f"{t2_tag} {_c(t2_str, 'green')}")
    elif a == "SELL":
        sl_str = "${:,.4f}  <- exit if price rises here".format(result["stop_loss"])
        t1_str = "${:,.4f}  <- cover partial short".format(result["target1"])
        t2_str = "${:,.4f}  <- full cover / trail stop".format(result["target2"])
        print(f"{sl_tag} {_c(sl_str, 'red')}")
        print(f"{t1_tag} {_c(t1_str, 'green')}")
        print(f"{t2_tag} {_c(t2_str, 'green')}")
    else:
        print(f"  (Watch zone: ${result['stop_loss']:,.4f}  →  ${result['target1']:,.4f})")

    print(f"{rr_tag} {result['rr']:.2f} : 1")


def print_indicators(result: dict):
    ind = result["ind"]
    print()
    print(_c("  INDICATOR SNAPSHOT", "cyan", bright=True))

    rsi_col = "green" if ind["rsi"] < 40 else ("red" if ind["rsi"] > 60 else "white")
    rsi_str = "{:.1f}".format(ind["rsi"])
    print(f"  RSI (14)       : {_c(rsi_str, rsi_col)}")
    print(f"  MACD / Signal  : {ind['macd']:.4f} / {ind['macd_sig']:.4f}  hist={ind['hist']:+.4f}")
    print(f"  Stoch  K / D   : {ind['stk_k']:.1f} / {ind['stk_d']:.1f}")
    print(f"  VWAP           : ${ind['vwap']:,.4f}")
    print(f"  EMA 9/21/50    : ${ind['ema9']:.2f} / ${ind['ema21']:.2f} / ${ind['ema50']:.2f}")
    print(f"  BB Upper/Lower : ${ind['bb_up']:.4f} / ${ind['bb_lo']:.4f}")
    print(f"  ATR (14)       : ${ind['atr']:.4f}")
    print(f"  Support/Res    : ${ind['support']:.4f} / ${ind['resistance']:.4f}")
    vol_flag = ""
    if ind["vol_avg"] and ind["volume"] > ind["vol_avg"] * 1.5:
        vol_flag = _c("  ← SPIKE", "yellow")
    print(f"  Volume         : {int(ind['volume']):,}{vol_flag}")


def print_signals(result: dict):
    print()
    print(_c("  ACTIVE SIGNALS", "cyan", bright=True))
    for desc, direction in result["signals"]:
        if direction == "BULL":
            print(f"  {_c('[+]', 'green')} {desc}")
        elif direction == "BEAR":
            print(f"  {_c('[-]', 'red')} {desc}")
        else:
            print(f"  {_c('[i]', 'yellow')} {desc}")


def print_footer():
    W = 62
    print()
    print(_c("═" * W, "cyan"))
    print(_c("  Next scan in 3 minutes...  (Ctrl+C to stop)", "yellow"))
    print(_c("═" * W, "cyan"))


def display(ticker: str, result: dict, scan_no: int, num_candles: int):
    clear()
    print_header(ticker, scan_no, num_candles, result["ind"]["price"])
    print_action(result)
    print_levels(result)
    print_indicators(result)
    print_signals(result)
    print_footer()


# ── Main loop ─────────────────────────────────────────────────────────────────

def run(ticker: str, once: bool = False):
    ticker = ticker.upper().strip()
    scan_no = 0

    print(f"\nInitialising scanner for {_c(ticker, 'cyan', bright=True)}...")
    print("Fetching data from Yahoo Finance (including pre/after-market)...\n")

    while True:
        df, info = fetch_3min_candles(ticker)

        if df is None or df.empty or len(df) < 30:
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] "
                f"No data returned for '{ticker}'. Retrying in 30 s…"
            )
            if once:
                sys.exit(1)
            time.sleep(30)
            continue

        result = analyze(df)

        if result is None:
            print("Not enough candles yet. Waiting 30 s…")
            if once:
                sys.exit(1)
            time.sleep(30)
            continue

        scan_no += 1
        display(ticker, result, scan_no, len(df))

        if once:
            break

        time.sleep(180)   # 3-minute cadence


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Stock Trading Bot — 3-minute candle scanner"
    )
    parser.add_argument(
        "--ticker", "-t",
        help="Ticker symbol (e.g. TSLA, AAPL, SPY)",
        default=None,
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scan and exit (useful for testing)",
    )
    args = parser.parse_args()

    print("\n" + "═" * 62)
    print("  STOCK TRADING BOT  —  3-Minute Candle Scanner")
    print("  Data    : Yahoo Finance (yfinance) — NO API key needed")
    print("  Session : After-hours & pre-market included")
    print("═" * 62)

    ticker = args.ticker or input("\nEnter ticker symbol (e.g. TSLA, AAPL, SPY): ").strip()
    if not ticker:
        print("No ticker provided. Exiting.")
        sys.exit(1)

    try:
        run(ticker, once=args.once)
    except KeyboardInterrupt:
        print("\n\nScanner stopped. Goodbye!")


if __name__ == "__main__":
    main()
