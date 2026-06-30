#!/usr/bin/env python3
"""
Momentum Scanner (WATCH-ONLY) — finds S&P 500 stocks being BOUGHT hard right now.
Flags a stock when it is pushing UP strongly (z >= Z_ENTRY) AND the move is a genuine
trend, not noise (efficiency ratio >= ER_MIN). This is the mirror image of the oversold
mean-reversion scanner: momentum wants strength + trend, not weakness + chop.

Records signals in Postgres and (if ALERT_WEBHOOK is set) pings your phone.
Places NO orders, connects to no brokerage. Quotes from Yahoo (free, read-only).

Railway: Start command `python scanner.py`, cron e.g.  */15 13-20 * * 1-5
"""
import os, io
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import requests
import db

Z_WINDOW, Z_ENTRY = 20, 2.0     # buying pressure: price >= +2 std above its recent mean
ER_WINDOW, ER_MIN = 12, 0.50    # real trend, not chop: efficiency ratio AT or ABOVE this
BATCH = 100
NY = ZoneInfo("America/New_York")
ALERT_WEBHOOK = os.environ.get("ALERT_WEBHOOK")

FALLBACK = ["IONQ","RGTI","QBTS","QUBT","NVDA","AMD","AVGO","TSM","MU","SMCI",
            "MRVL","KLAC","AMAT","INTC","ARM","PLTR","GOOGL","MSFT","META","IBM"]

def get_sp500():
    """Live S&P 500 constituents from Wikipedia; '.' tickers (BRK.B) -> '-' for Yahoo."""
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        html = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15).text
        tables = pd.read_html(io.StringIO(html))
        syms = (tables[0]["Symbol"].astype(str)
                .str.replace(".", "-", regex=False).str.strip().tolist())
        if len(syms) >= 400:
            return syms
    except Exception as e:
        print("S&P 500 list fetch failed, using fallback:", str(e)[:80])
    return FALLBACK

def market_open(now=None):
    now = now or datetime.now(NY)
    if now.weekday() >= 5:
        return False
    return (9, 30) <= (now.hour, now.minute) <= (16, 0)

def efficiency_ratio(close, window):
    return (close.diff(window).abs() / close.diff().abs().rolling(window).sum()
            ).replace([np.inf, -np.inf], np.nan)

def evaluate(close):
    """Return (z, er, price, triggered). Triggers on strong UP move in a trending regime."""
    if close is None or len(close.dropna()) < Z_WINDOW + 1:
        return None, None, None, False
    close = close.dropna()
    z = (close - close.rolling(Z_WINDOW).mean()) / close.rolling(Z_WINDOW).std()
    er = efficiency_ratio(close, ER_WINDOW)
    zv, ev, px = z.iloc[-1], er.iloc[-1], float(close.iloc[-1])
    trig = pd.notna(zv) and pd.notna(ev) and zv >= Z_ENTRY and ev >= ER_MIN
    return (float(zv) if pd.notna(zv) else None,
            float(ev) if pd.notna(ev) else None, px, bool(trig))

def download_batch(tickers):
    import yfinance as yf
    out = {}
    data = yf.download(tickers, period="5d", interval="1h", auto_adjust=True,
                       group_by="ticker", progress=False, threads=True)
    for t in tickers:
        try:
            sub = data[t] if isinstance(data.columns, pd.MultiIndex) else data
            s = sub["Close"].copy()
            s.index = s.index.tz_localize(None)
            out[t] = s
        except Exception:
            out[t] = None
    return out

def alert(msg):
    if not ALERT_WEBHOOK:
        return
    try:
        requests.post(ALERT_WEBHOOK, json={"content": msg, "text": msg}, timeout=8)
    except Exception as e:
        print("alert failed:", e)

def main():
    now = datetime.now(NY)
    if not market_open(now):
        print(f"[{now:%Y-%m-%d %H:%M %Z}] market closed — nothing to do.")
        return
    db.init()
    stamp = now.strftime("%Y-%m-%d %H:%M %Z")
    tickers = get_sp500()
    print(f"[{stamp}] scanning {len(tickers)} S&P 500 tickers for momentum ...")
    hits = scanned = 0
    for i in range(0, len(tickers), BATCH):
        chunk = tickers[i:i+BATCH]
        try:
            bars = download_batch(chunk)
        except Exception as e:
            print(f"  batch {i//BATCH+1} download error: {str(e)[:60]}"); continue
        for t, close in bars.items():
            z, er, px, trig = evaluate(close)
            if z is None:
                continue
            scanned += 1
            if trig:
                print(f"  HOT {t:6} z={z:+.2f} er={er:.2f} ${px:.2f}")
                if db.insert_signal(stamp, t, z, er, px):
                    alert(f"{t} momentum: buying pressure z={z:.2f}, trend er={er:.2f} @ ${px:.2f}")
                    hits += 1
    print(f"[{stamp}] done — scanned {scanned}, {hits} new momentum signal(s).")

if __name__ == "__main__":
    main()
