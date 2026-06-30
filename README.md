# Momentum Agent (volume-confirmed) — "what's being bought" forward test

Watch-only momentum scanner for the S&P 500. Flags a stock when ALL of:
  - price pushing UP hard           (z >= +2.0)
  - the move is a real trend        (efficiency ratio >= 0.50)
  - backed by heavy trading         (volume >= 1.5x its recent average)

Records signals (with the volume ratio) to Postgres, optional phone alert, web dashboard.
Places no trades, connects to no brokerage. Quotes from Yahoo (free, read-only).

## What the volume check is — and is NOT
The volume gate (Tier 2) confirms a price move is backed by real activity instead of a
thin drift. It measures HOW MUCH traded. It does NOT, and cannot, split "buy volume" vs
"sell volume" — every share traded is simultaneously bought by one side and sold by the
other, so total volume has no buy/sell split. Estimating which side was the aggressor
("order flow") needs paid tick/order-book data (Polygon, Databento, broker feeds) and is
a separate, larger build — and even then it's an estimate, not ground truth.

## Railway setup
Same two-service pattern as the other agents: dashboard (gunicorn) + scanner (cron
`*/15 13-20 * * 1-5`) + shared Postgres. On each service set
DATABASE_URL = ${{Postgres.DATABASE_URL}}.

## Honest note
Momentum is real but you ride winners / cut losers — not the symmetric +1%/-1% the
dashboard scores. Read the win-rate gauge loosely: "win" = kept climbing, "loss" =
reversed. It's a tracker to see whether volume-backed hot names keep running.
