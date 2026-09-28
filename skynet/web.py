"""Skynet web dashboard — a live view of the brain over HTTP.

Zero dependencies: uses the standard-library http.server. The data is built by
`dashboard_data(brain)` (easy to unit-test); the server serves a single HTML page
that fetches the JSON endpoints and renders them.

    python3 -m skynet serve            # then open http://127.0.0.1:8787

Endpoints:
    GET /                     the dashboard page
    GET /api/status           brain overview
    GET /api/apps             registered apps
    GET /api/health/summary   latest health metrics
    GET /api/bridge           bridge queue (?status=pending)
    GET /api/memory?ns=health facts for a namespace
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .brain import Brain


def dashboard_data(brain: Brain) -> dict:
    """Everything the dashboard needs, in one JSON-serialisable dict."""
    status = brain.status()
    apps = [
        {
            "id": a.id,
            "name": a.name,
            "status": a.status,
            "summary": a.summary,
            "tags": list(a.tags),
            "functions": [
                {"name": f.name, "summary": f.summary, "usage": f.usage}
                for f in a.functions
            ],
        }
        for a in brain.registry.all()
    ]
    health = brain.dispatch("health", "summary")
    return {
        "status": status,
        "apps": apps,
        "health": health.data if health.ok else {},
        "bridge_pending": brain.bridge_queue(status="pending"),
    }


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Skynet</title>
<style>
  :root{--bg:#0f1115;--card:#171a21;--ink:#e6e8ec;--muted:#9aa3b2;--line:#242833;
        --live:#3fb950;--bridge:#d29922;--other:#6e7681;--accent:#4c8dff}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
       font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
  header{padding:20px 24px;border-bottom:1px solid var(--line);display:flex;
         align-items:baseline;gap:12px}
  h1{font-size:20px;margin:0;letter-spacing:.5px}
  .sub{color:var(--muted)}
  main{padding:24px;max-width:1000px;margin:0 auto;display:grid;gap:20px}
  .row{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
  .stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
  .stat b{display:block;font-size:26px}
  .stat span{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.5px}
  section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 18px}
  h2{font-size:14px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin:0 0 12px}
  .app{display:flex;gap:10px;align-items:flex-start;padding:10px 0;border-top:1px solid var(--line)}
  .app:first-of-type{border-top:none}
  .dot{width:9px;height:9px;border-radius:50%;margin-top:6px;flex:none}
  .live{background:var(--live)}.bridge{background:var(--bridge)}
  .external,.planned{background:var(--other)}
  .app .name{font-weight:600}.app .desc{color:var(--muted)}
  .pill{font-size:11px;color:var(--muted);border:1px solid var(--line);
        border-radius:20px;padding:1px 8px;margin-left:6px}
  table{width:100%;border-collapse:collapse}
  td,th{text-align:left;padding:6px 8px;border-top:1px solid var(--line);font-size:13px}
  th{color:var(--muted);font-weight:500}
  .empty{color:var(--muted);font-style:italic}
  code{background:#0b0d11;padding:1px 5px;border-radius:5px;color:#c9d1d9}
  footer{color:var(--muted);text-align:center;padding:16px;font-size:12px}
</style></head>
<body>
<header><h1>SKYNET</h1><span class="sub">master brain · live dashboard</span></header>
<main>
  <div class="row" id="stats"></div>
  <section><h2>Health</h2><div id="health"></div></section>
  <section><h2>Apps</h2><div id="apps"></div></section>
  <section><h2>Bridge queue (pending)</h2><div id="bridge"></div></section>
</main>
<footer>Auto-refreshes every 15s · served by <code>python3 -m skynet serve</code></footer>
<script>
async function load(){
  const d = await (await fetch('/api/dashboard')).json();
  const s = d.status;
  document.getElementById('stats').innerHTML = [
    ['apps', s.apps_total],
    ['live', s.apps_live.length],
    ['bridge', s.apps_bridge.length],
    ['automations', s.automations],
    ['pending', s.bridge_pending],
  ].map(([k,v])=>`<div class="stat"><b>${v}</b><span>${k}</span></div>`).join('');

  const m = d.health.metrics||{};
  const goals = d.health.goals||{};
  const keys = Object.keys(m).sort();
  document.getElementById('health').innerHTML = keys.length
    ? '<table><tr><th>metric</th><th>latest</th><th>goal</th><th>as of</th></tr>'+
      keys.map(k=>`<tr><td>${k}</td><td>${m[k].value}${m[k].unit||''}</td>`+
        `<td>${goals[k]??'—'}</td><td>${(m[k].at||'').replace('T',' ').replace('Z','')}</td></tr>`).join('')+'</table>'
    : '<p class="empty">No metrics logged yet. Try <code>skynet health log weight 190</code></p>';

  document.getElementById('apps').innerHTML = d.apps.map(a=>
    `<div class="app"><div class="dot ${a.status}"></div><div>`+
    `<div class="name">${a.name}<span class="pill">${a.status}</span></div>`+
    `<div class="desc">${a.summary}</div></div></div>`).join('');

  const b = d.bridge_pending;
  document.getElementById('bridge').innerHTML = b.length
    ? '<table><tr><th>app</th><th>command</th><th>params</th><th>queued</th></tr>'+
      b.map(r=>`<tr><td>${r.app}</td><td>${r.command}</td>`+
        `<td><code>${JSON.stringify(r.params)}</code></td>`+
        `<td>${(r.at||'').replace('T',' ').replace('Z','')}</td></tr>`).join('')+'</table>'
    : '<p class="empty">Nothing waiting for the Mac runner. 🎉</p>';
}
load(); setInterval(load, 15000);
</script>
</body></html>"""


def make_handler(brain: Brain):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj) -> None:
            self._send(200, json.dumps(obj, default=str).encode(), "application/json")

        def do_GET(self):  # noqa: N802 (stdlib naming)
            parsed = urlparse(self.path)
            path, qs = parsed.path, parse_qs(parsed.query)
            if path in ("/", "/index.html"):
                self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            elif path == "/api/dashboard":
                self._json(dashboard_data(brain))
            elif path == "/api/status":
                self._json(brain.status())
            elif path == "/api/apps":
                self._json([a.__dict__ for a in brain.registry.all()])
            elif path == "/api/health/summary":
                r = brain.dispatch("health", "summary")
                self._json(r.data)
            elif path == "/api/bridge":
                self._json(brain.bridge_queue(status=qs.get("status", [None])[0]))
            elif path == "/api/memory":
                ns = qs.get("ns", [""])[0]
                self._json(brain.memory.facts(ns) if ns else {})
            else:
                self._send(404, b"not found", "text/plain")

        def log_message(self, *args):  # silence per-request stderr logging
            pass

    return Handler


def serve(brain: Brain, host: str = "127.0.0.1", port: int = 8787) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(brain))
    print(f"Skynet dashboard on http://{host}:{port}  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        httpd.server_close()
