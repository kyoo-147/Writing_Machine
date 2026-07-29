from __future__ import annotations

import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .core import Database
from .pipeline import ContentMachine


PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Content Machine</title><style>
body{margin:0;background:#080a10;color:#edf2ff;font:16px system-ui}.wrap{max-width:1100px;margin:auto;padding:40px}
h1{font-size:48px;margin:0}.sub{color:#91a0bf}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:24px 0}
.card,table{background:#111624;border:1px solid #26314b;border-radius:16px;padding:18px}.n{font-size:36px;color:#72f2c5}
table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:12px;border-bottom:1px solid #25304a}
a{color:#72f2c5}@media(max-width:700px){.cards{grid-template-columns:1fr}}
</style></head><body><div class="wrap"><p class="sub">VN TECH LAB</p><h1>Content Machine</h1>
<p class="sub">Research - Verify - Produce - Publish</p><div class="cards" id="stats"></div>
<table><thead><tr><th>Score</th><th>Topic</th><th>Source</th><th>Status</th></tr></thead><tbody id="rows"></tbody></table>
<script>async function load(){let a=await(await fetch('/api/analytics')).json(),s=await(await fetch('/api/stories')).json();
stats.innerHTML=['stories','packages','published'].map(k=>`<div class=card><div class=n>${a[k]}</div>${k}</div>`).join('');
rows.innerHTML=s.map(x=>`<tr><td>${x.score}</td><td><a href="${x.url}" target=_blank>${x.title}</a></td><td>${x.source}</td><td>${x.status}</td></tr>`).join('')}load()</script>
</div></body></html>"""


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    db = Database()
    machine = ContentMachine(db)

    class Handler(BaseHTTPRequestHandler):
        def _send(self, body: bytes, kind: str = "application/json", status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", f"{kind}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            if path == "/":
                return self._send(PAGE.encode(), "text/html")
            if path == "/api/stories":
                return self._send(json.dumps(db.list_stories(100), ensure_ascii=False).encode())
            if path == "/api/analytics":
                return self._send(json.dumps(machine.analytics(), ensure_ascii=False).encode())
            self._send(b'{"error":"not found"}', status=404)

        def log_message(self, *_):
            pass

    print(f"Dashboard: http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
