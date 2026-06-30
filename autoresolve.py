#!/usr/bin/env python3
"""
Auto-Resolve — scores pending signals automatically (WATCH-ONLY, no trades).
For each pending signal it looks at what the stock did AFTER the signal, on the same
trading day, and marks it:
  win   -> price hit +1% (entry x 1.01) before -1%
  loss  -> price hit -1% (entry x 0.99) first  (same-bar tie -> loss, conservative)
  flat  -> neither hit by the close (you'd have exited flat at end of day)
Only resolves signals whose trading day has fully closed; leaves today's open ones pending.

Drop this file into each agent repo and run it once a day on a Railway cron, e.g.
after the close:  30 20 * * 1-5   (≈ 4:30pm ET).  Uses Yahoo (free, read-only).
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import db

TP_PCT, SL_PCT = 0.01, 0.01
WIN_PNL, LOSS_PNL = 1000, -1000
NY = ZoneInfo("America/New_York")

def parse_ts(ts):
    """'2026-06-30 13:15 EDT' -> naive ET datetime."""
    return datetime.strptime(ts.rsplit(" ", 1)[0], "%Y-%m-%d %H:%M")

def day_complete(sig_dt, now_et):
    """True once the signal's trading day has fully closed (after 16:00 ET)."""
    if sig_dt.date() < now_et.date():
        return True
    if sig_dt.date() == now_et.date() and (now_et.hour, now_et.minute) >= (16, 0):
        return True
    return False

def download(tickers):
    import yfinance as yf
    out = {}
    data = yf.download(tickers, period="1mo", interval="1h", auto_adjust=True,
                       group_by="ticker", progress=False, threads=True)
    for t in tickers:
        try:
            sub = data[t] if isinstance(data.columns, pd.MultiIndex) else data
            d = sub[["High", "Low", "Close"]].copy()
            d.index = d.index.tz_localize(None)
            out[t] = d
        except Exception:
            out[t] = None
    return out

def classify(df, entry, sig_dt):
    """Walk the same-day bars after the signal; return (outcome, pnl)."""
    if df is None or df.empty:
        return None
    same_day = df[(df.index.normalize() == pd.Timestamp(sig_dt).normalize()) &
                  (df.index > pd.Timestamp(sig_dt))]
    if same_day.empty:
        return None
    tp, sl = entry * (1 + TP_PCT), entry * (1 - SL_PCT)
    for bar in same_day.itertuples():
        hit_tp, hit_sl = bar.High >= tp, bar.Low <= sl
        if hit_tp and hit_sl:
            return ("loss", LOSS_PNL)          # tie in one bar -> assume stop first
        if hit_tp:
            return ("win", WIN_PNL)
        if hit_sl:
            return ("loss", LOSS_PNL)
    return ("flat", 0)                          # neither hit -> flat by close

def main():
    db.init()
    rows = db.all_signals()
    pending = [r for r in rows if r["outcome"] == "pending"]
    now = datetime.now(NY)
    todo = [r for r in pending if day_complete(parse_ts(r["ts"]), now)]
    print(f"{len(pending)} pending, {len(todo)} resolvable (closed trading day).")
    if not todo:
        return
    tickers = sorted({r["ticker"] for r in todo})
    bars = {}
    for i in range(0, len(tickers), 100):
        bars.update(download(tickers[i:i+100]))
    wins = losses = flats = skipped = 0
    for r in todo:
        res = classify(bars.get(r["ticker"]), r["price"], parse_ts(r["ts"]))
        if res is None:
            skipped += 1; continue
        outcome, pnl = res
        db.set_outcome(r["id"], outcome, pnl)
        wins += outcome == "win"; losses += outcome == "loss"; flats += outcome == "flat"
        print(f"  {r['ticker']:6} {r['ts']}  ${r['price']:.2f} -> {outcome}")
    print(f"done — {wins} win, {losses} loss, {flats} flat, {skipped} skipped (no data).")

if __name__ == "__main__":
    main()
