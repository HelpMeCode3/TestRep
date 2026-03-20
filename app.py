#!/usr/bin/env python3
"""
Stock Trading Bot - Web GUI
============================
Run:  python app.py
Then open http://localhost:5000 in your browser
"""

from flask import Flask, render_template, jsonify, request
from datetime import datetime
import sys
import os

# Import analysis functions from the existing bot
sys.path.insert(0, os.path.dirname(__file__))
from stock_bot import fetch_3min_candles, analyze

app = Flask(__name__)


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
        return jsonify({"error": f"No data available for '{ticker}'. Check the ticker symbol."}), 404

    result = analyze(df)

    if result is None:
        return jsonify({"error": "Not enough candle data to generate a signal yet. Try again shortly."}), 503

    ind = result["ind"]

    payload = {
        "ticker":     ticker,
        "scan_time":  datetime.now().strftime("%Y-%m-%d  %H:%M:%S"),
        "num_candles": len(df),

        # Signal
        "action":     result["action"],
        "confidence": round(result["confidence"], 1),
        "bull":       result["bull"],
        "bear":       result["bear"],

        # Trade levels
        "price":      round(ind["price"], 4),
        "entry":      round(result["entry"], 4),
        "stop_loss":  round(result["stop_loss"], 4),
        "target1":    round(result["target1"], 4),
        "target2":    round(result["target2"], 4),
        "rr":         round(result["rr"], 2),

        # Indicators
        "indicators": {
            "rsi":        round(ind["rsi"], 2),
            "macd":       round(ind["macd"], 4),
            "macd_sig":   round(ind["macd_sig"], 4),
            "macd_hist":  round(ind["hist"], 4),
            "stk_k":      round(ind["stk_k"], 1),
            "stk_d":      round(ind["stk_d"], 1),
            "vwap":       round(ind["vwap"], 4),
            "ema9":       round(ind["ema9"], 2),
            "ema21":      round(ind["ema21"], 2),
            "ema50":      round(ind["ema50"], 2),
            "bb_upper":   round(ind["bb_up"], 4),
            "bb_mid":     round(ind["bb_mid"], 4),
            "bb_lower":   round(ind["bb_lo"], 4),
            "atr":        round(ind["atr"], 4),
            "support":    round(ind["support"], 4),
            "resistance": round(ind["resistance"], 4),
            "volume":     int(ind["volume"]),
            "vol_avg":    int(ind["vol_avg"]) if ind["vol_avg"] else 0,
        },

        # Active signals list
        "signals": [
            {"desc": desc, "direction": direction}
            for desc, direction in result["signals"]
        ],
    }

    return jsonify(payload)


if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  Stock Trading Bot  —  Web Dashboard")
    print("  Open your browser to:  http://localhost:5000")
    print("=" * 55 + "\n")
    app.run(debug=False, host="0.0.0.0", port=5000)
