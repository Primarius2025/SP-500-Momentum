"""Shared Postgres access for the signal agent (Railway sets DATABASE_URL)."""
import os
import psycopg2
import psycopg2.extras

DB_URL = os.environ.get("DATABASE_URL")

def conn():
    if not DB_URL:
        raise RuntimeError("DATABASE_URL not set — add a Postgres plugin in Railway and reference it.")
    return psycopg2.connect(DB_URL)

def init():
    with conn() as c, c.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS signals(
                id      SERIAL PRIMARY KEY,
                ts      TEXT,
                ticker  TEXT,
                z       REAL,
                er      REAL,
                price   REAL,
                outcome TEXT DEFAULT 'pending',
                pnl     REAL,
                UNIQUE(ts, ticker)
            )""")
        c.commit()

def insert_signal(ts, ticker, z, er, price):
    """Insert one signal; ignore if (ts,ticker) already logged. Returns True if new."""
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "INSERT INTO signals(ts,ticker,z,er,price) VALUES(%s,%s,%s,%s,%s) "
            "ON CONFLICT (ts,ticker) DO NOTHING",
            (ts, ticker, z, er, price))
        c.commit()
        return cur.rowcount > 0

def all_signals():
    with conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM signals ORDER BY ts DESC, ticker")
        return cur.fetchall()

def set_outcome(sig_id, outcome, pnl):
    with conn() as c, c.cursor() as cur:
        cur.execute("UPDATE signals SET outcome=%s, pnl=%s WHERE id=%s", (outcome, pnl, sig_id))
        c.commit()
