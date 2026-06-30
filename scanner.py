#!/usr/bin/env python3
"""
Momentum Scanner (WATCH-ONLY) — S&P 500 stocks being BOUGHT hard, confirmed by VOLUME.
Flags a stock when ALL of:
  - price pushing UP strongly        (z >= Z_ENTRY)
  - the move is a real trend         (efficiency ratio >= ER_MIN)
  - backed by heavy trading          (volume >= VOL_MULT x its recent average)
The volume check is the Tier-2 upgrade: it confirms a move is backed by real activity
rather than a thin drift. NOTE: it does NOT split buy vs sell — that's impossible from
this data (every share traded is both bought and sold). It only measures HOW MUCH traded.

Records signals + volume ratio to Postgres; optional phone alert. Places NO orders.
Quotes from Yahoo (free, read-only). Railway: `python scanner.py`, cron */15 13-20 * * 1-5
"""
import os, io
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import requests
import db

Z_WINDOW, Z_ENTRY = 20, 2.0      # buying pressure: >= +2 std above recent mean
ER_WINDOW, ER_MIN = 12, 0.50     # genuine trend, not chop
VOL_WINDOW, VOL_MULT = 20, 1.5   # volume must be >= 1.5x its recent average
BATCH = 100
NY = ZoneInfo("America/New_York")
ALERT_WEBHOOK = os.environ.get("ALERT_WEBHOOK")

FALLBACK = ["IONQ","RGTI","QBTS","QUBT","NVDA","AMD","AVGO","TSM","MU","SMCI",
            "MRVL","KLAC","AMAT","INTC","ARM","PLTR","GOOGL","MSFT","META","IBM"]

def get_sp500():
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

def evaluate(df):
    """df has Close + Volume. Trigger: strong up move + trend + heavy volume.
    Returns (z, er, vol_ratio, price, triggered)."""
    if df is None or len(df.dropna()) < max(Z_WINDOW, VOL_WINDOW) + 1:
        return None, None, None, None, False
    df = df.dropna()
    close, vol = df["Close"], df["Volume"]
    z = (close - close.rolling(Z_WINDOW).mean()) / close.rolling(Z_WINDOW).std()
    er = efficiency_ratio(close, ER_WINDOW)
    vratio = vol / vol.rolling(VOL_WINDOW).mean()
    zv, ev, vr, px = z.iloc[-1], er.iloc[-1], vratio.iloc[-1], float(close.iloc[-1])
    trig = (pd.notna(zv) and pd.notna(ev) and pd.notna(vr)
            and zv >= Z_ENTRY and ev >= ER_MIN and vr >= VOL_MULT)
    g = lambda x: float(x) if pd.notna(x) else None
    return g(zv), g(ev), g(vr), px, bool(trig)

def download_batch(tickers):
    import yfinance as yf
    out = {}
    data = yf.download(tickers, period="5d", interval="1h", auto_adjust=True,
                       group_by="ticker", progress=False, threads=True)
    for t in tickers:
        try:
            sub = data[t] if isinstance(data.columns, pd.MultiIndex) else data
            d = sub[["Close", "Volume"]].copy()
            d.index = d.index.tz_localize(None)
            out[t] = d
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
    print(f"[{stamp}] scanning {len(tickers)} S&P 500 tickers for volume-confirmed momentum ...")
    hits = scanned = 0
    for i in range(0, len(tickers), BATCH):
        chunk = tickers[i:i+BATCH]
        try:
            bars = download_batch(chunk)
        except Exception as e:
            print(f"  batch {i//BATCH+1} download error: {str(e)[:60]}"); continue
        for t, df in bars.items():
            z, er, vr, px, trig = evaluate(df)
            if z is None:
                continue
            scanned += 1
            if trig:
                print(f"  HOT {t:6} z={z:+.2f} er={er:.2f} vol={vr:.1f}x ${px:.2f}")
                # store volume ratio in the er column-adjacent 'er' is taken; we encode
                # vol ratio into the signal via the price note is not ideal, so we pass
                # vol ratio as a dedicated value through db (see db.insert_signal extended).
                if db.insert_signal(stamp, t, z, er, px, vr):
                    alert(f"{t} momentum: z={z:.2f}, trend er={er:.2f}, volume {vr:.1f}x avg @ ${px:.2f}")
                    hits += 1
    print(f"[{stamp}] done — scanned {scanned}, {hits} new momentum signal(s).")

if __name__ == "__main__":
    main()
