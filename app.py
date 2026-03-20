#!/usr/bin/env python3
"""
Stock Trading Bot - Web GUI
============================
Run:  python app.py
Then open http://localhost:5000 in your browser
"""

from flask import Flask, render_template, jsonify, request
from datetime import datetime
import math
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from stock_bot import fetch_3min_candles, analyze, vwap as compute_vwap

app = Flask(__name__)

CHART_CANDLES = 80  # number of 3-min candles to send for charting


def safe_float(v, decimals=4):
    try:
        val = float(v)
        return round(val, decimals) if not math.isnan(val) else 0.0
    except (TypeError, ValueError):
        return 0.0


def safe_int(v):
    try:
        val = float(v)
        return int(val) if not math.isnan(val) else 0
    except (TypeError, ValueError):
        return 0


def to_unix(idx):
    """Convert a pandas Timestamp index entry to a Unix timestamp (seconds)."""
    try:
        return int(idx.timestamp())
    except Exception:
        import pandas as pd
        return int(pd.Timestamp(idx).timestamp())


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/scan")
def scan():
    ticker = request.args.get("ticker", "").strip().upper()
    if not ticker:
        return jsonify({"error": "No ticker provided"}), 400

    df, info = fetch_3min_candles(ticker)

    if df is None or df.empty or len(df) < 30:
        return jsonify({"error": f"No data for '{ticker}'. Check the symbol."}), 404

    result = analyze(df)

    if result is None:
        return jsonify({"error": "Not enough candle data yet. Try again shortly."}), 503

    ind = result["ind"]
    f = safe_float
    i = safe_int

    # ── Chart data ─────────────────────────────────────────────────────────────
    df_chart   = df.tail(CHART_CANDLES)
    vwap_full  = compute_vwap(df["High"], df["Low"], df["Close"], df["Volume"])
    vwap_chart = vwap_full.tail(CHART_CANDLES)

    candles = [
        {
            "time":  to_unix(row.Index),
            "open":  round(float(row.Open),  4),
            "high":  round(float(row.High),  4),
            "low":   round(float(row.Low),   4),
            "close": round(float(row.Close), 4),
        }
        for row in df_chart.itertuples()
    ]

    vwap_data = [
        {"time": to_unix(idx), "value": round(float(val), 4)}
        for idx, val in zip(df_chart.index, vwap_chart)
        if not math.isnan(float(val))
    ]

    return jsonify({
        "ticker":      ticker,
        "scan_time":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "num_candles": len(df),

        "action":     result["action"],
        "confidence": f(result["confidence"], 1),
        "bull":       int(result["bull"]),
        "bear":       int(result["bear"]),

        "price":     f(ind["price"],        4),
        "entry":     f(result["entry"],     4),
        "stop_loss": f(result["stop_loss"], 4),
        "target1":   f(result["target1"],   4),
        "target2":   f(result["target2"],   4),
        "rr":        f(result["rr"],        2),

        "indicators": {
            "rsi":        f(ind["rsi"],        2),
            "macd":       f(ind["macd"],       4),
            "macd_sig":   f(ind["macd_sig"],   4),
            "macd_hist":  f(ind["hist"],       4),
            "stk_k":      f(ind["stk_k"],      1),
            "stk_d":      f(ind["stk_d"],      1),
            "vwap":       f(ind["vwap"],       4),
            "ema9":       f(ind["ema9"],       2),
            "ema21":      f(ind["ema21"],      2),
            "ema50":      f(ind["ema50"],      2),
            "bb_upper":   f(ind["bb_up"],      4),
            "bb_mid":     f(ind["bb_mid"],     4),
            "bb_lower":   f(ind["bb_lo"],      4),
            "atr":        f(ind["atr"],        4),
            "support":    f(ind["support"],    4),
            "resistance": f(ind["resistance"], 4),
            "volume":     i(ind["volume"]),
            "vol_avg":    i(ind["vol_avg"]),
        },

        "signals": [
            {"desc": desc, "direction": direction}
            for desc, direction in result["signals"]
        ],

        "chart": {
            "candles": candles,
            "vwap":    vwap_data,
        },
    })


if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  Stock Trading Bot  —  Web Dashboard")
    print("  Open your browser to:  http://localhost:5000")
    print("=" * 55 + "\n")
    app.run(debug=True, host="0.0.0.0", port=5000)
