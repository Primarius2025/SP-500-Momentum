#!/usr/bin/env python3
"""Signal Tracker — Postgres-backed web dashboard (deploys on Railway).
Reads signals the scanner writes; lets you mark Win/Loss/Flat and graphs the result.
Watch-only: never trades. Served by gunicorn (see Procfile)."""
import os
from flask import Flask, request, jsonify, render_template_string
import db

WIN_PNL, LOSS_PNL = 1000, -1000
BREAK_EVEN = 0.55
app = Flask(__name__)

@app.route("/")
def index():
    db.init()
    rows = [dict(r) for r in db.all_signals()]
    done = [r for r in rows if r["outcome"] in ("win", "loss")]
    wins = sum(1 for r in done if r["outcome"] == "win")
    wr = (wins / len(done)) if done else None
    net = sum((r["pnl"] or 0) for r in rows)
    by_ticker = {}
    for r in rows:
        by_ticker[r["ticker"]] = by_ticker.get(r["ticker"], 0) + 1
    chron = sorted([r for r in rows if r["pnl"] is not None], key=lambda r: r["ts"])
    cum, run = [], 0
    for r in chron:
        run += r["pnl"]; cum.append({"ts": r["ts"], "y": run})
    counts = {k: sum(1 for r in rows if r["outcome"] == k) for k in ("win", "loss", "flat", "pending")}
    return render_template_string(TEMPLATE, rows=rows, wr=wr, be=BREAK_EVEN, net=net,
        total=len(rows), done=len(done), counts=counts, by_ticker=by_ticker, cum=cum)

@app.route("/api/update", methods=["POST"])
def update():
    d = request.get_json(force=True)
    outcome = d.get("outcome", "pending")
    pnl = {"win": WIN_PNL, "loss": LOSS_PNL, "flat": 0}.get(outcome, None)
    db.set_outcome(d["id"], outcome, pnl)
    return jsonify(ok=True)

TEMPLATE = r"""
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Momentum Tracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root{--ink:#0E1117;--panel:#171C26;--line:#252C3A;--text:#E9E6DE;--mut:#8A93A6;
  --amber:#D8A24A;--win:#5FA877;--loss:#C75D5D;--flat:#5B6B86;}
*{box-sizing:border-box} body{margin:0;background:var(--ink);color:var(--text);
  font-family:"IBM Plex Mono",monospace;font-size:14px;line-height:1.5}
.wrap{max-width:1080px;margin:0 auto;padding:32px 20px 80px}
header{display:flex;justify-content:space-between;align-items:baseline;border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:28px;flex-wrap:wrap;gap:12px}
h1{font-family:Archivo,sans-serif;font-weight:800;font-size:22px;letter-spacing:-.02em;margin:0}
h1 .dot{color:var(--amber)} .sub{color:var(--mut);font-size:12px}
.hero{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:28px;margin-bottom:22px;
  display:grid;grid-template-columns:1.2fr 1fr;gap:28px;align-items:center}
.gauge .label{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px}
.gauge .big{font-family:Archivo,sans-serif;font-weight:800;font-size:64px;line-height:1}
.gauge .be{color:var(--mut);font-size:13px;margin-top:8px}
.verdict{font-family:Archivo,sans-serif;font-weight:800;font-size:18px;border-radius:10px;padding:16px 18px;line-height:1.3}
.v-good{background:rgba(95,168,119,.12);border:1px solid var(--win);color:var(--win)}
.v-bad{background:rgba(199,93,93,.10);border:1px solid var(--loss);color:var(--loss)}
.v-wait{background:rgba(216,162,74,.10);border:1px solid var(--amber);color:var(--amber)}
.verdict small{display:block;font-family:"IBM Plex Mono";font-weight:400;font-size:12px;color:var(--mut);margin-top:8px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:22px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}
.stat .k{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.06em}
.stat .v{font-family:Archivo,sans-serif;font-weight:800;font-size:26px;margin-top:4px}
.grid2{display:grid;grid-template-columns:1.4fr 1fr;gap:16px;margin-bottom:22px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px}
.card h2{font-family:Archivo,sans-serif;font-size:13px;text-transform:uppercase;letter-spacing:.07em;color:var(--mut);margin:0 0 14px}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);font-size:13px}
th{color:var(--mut);font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.05em} td.num{text-align:right}
.pill{display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:600}
.p-win{background:rgba(95,168,119,.15);color:var(--win)} .p-loss{background:rgba(199,93,93,.15);color:var(--loss)}
.p-flat{background:rgba(91,107,134,.18);color:#9fb0cc} .p-pending{background:rgba(138,147,166,.12);color:var(--mut)}
select{background:var(--ink);color:var(--text);border:1px solid var(--line);border-radius:6px;padding:5px 8px;font-family:inherit;font-size:12px}
.empty{text-align:center;color:var(--mut);padding:48px 20px}
.empty .big{font-family:Archivo;font-weight:800;color:var(--text);font-size:20px;margin-bottom:8px}
@media(max-width:760px){.hero,.grid2{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,1fr)}}
</style></head><body><div class="wrap">
<header>
  <div><h1>Momentum Tracker<span class="dot">.</span></h1>
  <div class="sub">momentum forward test · S&amp;P 500 · watch-only, no trades</div></div>
</header>

{% set wrpct = (wr*100)|round(1) if wr is not none else None %}
<div class="hero">
  <div class="gauge">
    <div class="label">Win rate (resolved signals)</div>
    <div class="big" style="color:{{ 'var(--win)' if wr is not none and wr>be else ('var(--loss)' if wr is not none else 'var(--mut)') }}">
      {{ wrpct ~ '%' if wr is not none else '—' }}</div>
    <div class="be">break-even to profit: {{ (be*100)|round(0)|int }}% · {{ done }} of {{ total }} signals resolved</div>
  </div>
  {% if wr is none %}
    <div class="verdict v-wait">Not enough data yet
      <small>Mark some signals Win/Loss below and the verdict appears here. Need ~30+ to trust it.</small></div>
  {% elif done < 30 %}
    <div class="verdict v-wait">Too early to call — {{ done }}/30 resolved
      <small>Keep logging outcomes. A win rate over a handful of trades is noise, not edge.</small></div>
  {% elif wr > be %}
    <div class="verdict v-good">Edge holding above break-even
      <small>Promising on {{ done }} resolved signals. Still forward-test more before risking real money.</small></div>
  {% else %}
    <div class="verdict v-bad">Below break-even — no edge yet
      <small>On {{ done }} resolved signals this isn't profitable after costs. Don't risk real money on it as-is.</small></div>
  {% endif %}
</div>

<div class="stats">
  <div class="stat"><div class="k">Signals logged</div><div class="v">{{ total }}</div></div>
  <div class="stat"><div class="k">Resolved</div><div class="v">{{ done }}</div></div>
  <div class="stat"><div class="k">Pending</div><div class="v">{{ counts.pending }}</div></div>
  <div class="stat"><div class="k">Net P&amp;L (sim)</div><div class="v" style="color:{{ 'var(--win)' if net>0 else ('var(--loss)' if net<0 else 'var(--text)') }}">${{ '{:,.0f}'.format(net) }}</div></div>
</div>

{% if total == 0 %}
  <div class="card"><div class="empty">
    <div class="big">No signals yet</div>
    The scanner will write setups here as they fire during market hours.<br>
    Check back, or wait for a phone alert if you set one up.
  </div></div>
{% else %}
<div class="grid2">
  <div class="card"><h2>Cumulative P&amp;L (simulated, $1k per signal)</h2><canvas id="pnl" height="150"></canvas></div>
  <div class="card"><h2>Outcomes</h2><canvas id="donut" height="150"></canvas></div>
</div>
<div class="card" style="margin-bottom:22px"><h2>Signals by ticker</h2><canvas id="bar" height="90"></canvas></div>
<div class="card">
  <h2>Signal log — mark what happened next</h2>
  <table><thead><tr>
    <th>Time</th><th>Ticker</th><th class="num">z</th><th class="num">ER</th><th class="num">Price</th><th>Outcome</th>
  </tr></thead><tbody>
  {% for r in rows %}
    <tr>
      <td>{{ r.ts }}</td><td><strong>{{ r.ticker }}</strong></td>
      <td class="num">{{ '%.2f'|format(r.z) }}</td>
      <td class="num">{{ '%.2f'|format(r.er) }}</td>
      <td class="num">${{ '%.2f'|format(r.price) }}</td>
      <td>
        <span class="pill p-{{ r.outcome }}">{{ r.outcome }}</span>
        <select onchange="setOutcome({{ r.id }}, this.value)">
          {% for o in ['pending','win','loss','flat'] %}
            <option value="{{ o }}" {{ 'selected' if r.outcome==o }}>{{ o }}</option>
          {% endfor %}
        </select>
      </td>
    </tr>
  {% endfor %}
  </tbody></table>
</div>
{% endif %}
</div>
<script>
async function setOutcome(id, outcome){
  await fetch('/api/update',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id, outcome})});
  location.reload();
}
const mono="#8A93A6", grid="#252C3A";
{% if total > 0 %}
const cum={{ cum|tojson }};
new Chart(document.getElementById('pnl'),{type:'line',
  data:{labels:cum.map(p=>p.ts.slice(5,16)),datasets:[{data:cum.map(p=>p.y),
    borderColor:'#D8A24A',backgroundColor:'rgba(216,162,74,.12)',fill:true,tension:.25,pointRadius:2}]},
  options:{plugins:{legend:{display:false}},scales:{x:{ticks:{color:mono,maxTicksLimit:6},grid:{color:grid}},
    y:{ticks:{color:mono,callback:v=>'$'+v},grid:{color:grid}}}}});
const cc={{ counts|tojson }};
new Chart(document.getElementById('donut'),{type:'doughnut',
  data:{labels:['Win','Loss','Flat','Pending'],datasets:[{data:[cc.win,cc.loss,cc.flat,cc.pending],
    backgroundColor:['#5FA877','#C75D5D','#5B6B86','#2A3242'],borderColor:'#171C26',borderWidth:2}]},
  options:{plugins:{legend:{labels:{color:mono,font:{size:11}}}},cutout:'62%'}});
const bt={{ by_ticker|tojson }};
new Chart(document.getElementById('bar'),{type:'bar',
  data:{labels:Object.keys(bt),datasets:[{data:Object.values(bt),backgroundColor:'#3C6E8F'}]},
  options:{plugins:{legend:{display:false}},scales:{x:{ticks:{color:mono},grid:{display:false}},
    y:{ticks:{color:mono,stepSize:1},grid:{color:grid}}}}});
{% endif %}
</script>
</body></html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)))
