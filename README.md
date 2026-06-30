# Momentum Agent — "what's being bought" forward test

Watch-only **momentum** scanner for the S&P 500. Mirror image of the oversold tracker:
it flags stocks pushing UP hard (z >= +2.0) in a genuine trending move (efficiency
ratio >= 0.50), records them to Postgres, optionally pings your phone, and shows them
on a web dashboard. **It places no trades and connects to no brokerage.**

Same two-service setup as the oversold agent (dashboard + scanner + shared Postgres).
See the oversold repo's README for the exact Railway steps — identical, just a new
project/repo. Cron suggestion: `*/15 13-20 * * 1-5`.

## How it differs from the oversold scanner
| | Oversold (mean reversion) | Momentum (this one) |
|---|---|---|
| Trigger | z <= -2.0 (sold off)      | z >= +2.0 (bought up)  |
| Regime  | efficiency ratio < 0.30 (choppy) | efficiency ratio >= 0.50 (trending) |
| Idea    | buy the dip, sell the bounce | ride strength while it lasts |

## Honest note
Momentum is a real effect, but riding trends means letting winners run and cutting
losers — not the symmetric +1%/-1% the dashboard scores. Treat the win-rate gauge here
loosely: "win" = the name kept climbing after the signal, "loss" = it reversed. It's a
tracker to see whether hot names keep going, not a complete trading system.
