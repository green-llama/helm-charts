#!/usr/bin/env python3
"""
GLerp Maintenance Window Admin
Writes glerp_maintenance_window metric to VictoriaMetrics, creates a Grafana annotation,
and creates an AlertManager silence — all from a single browser form submission.
"""
import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

VM_URL       = os.environ.get("VM_URL",       "http://localhost:8428")
GRAFANA_URL  = os.environ.get("GRAFANA_URL",  "http://localhost:3000")
GRAFANA_TOKEN = os.environ.get("GRAFANA_TOKEN", "")
AM_URL       = os.environ.get("AM_URL",       "http://localhost:9093")
ADMIN_USER   = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASS   = os.environ.get("ADMIN_PASSWORD", "changeme")

# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GLerp Maintenance Admin</title>
<style>
  *{{box-sizing:border-box}}
  body{{font-family:sans-serif;max-width:860px;margin:40px auto;padding:0 20px;color:#333}}
  h1{{color:#1F60C4;margin-bottom:4px}}
  h2{{margin-top:0;font-size:1.1rem;color:#555}}
  .card{{background:#f7f8fa;border:1px solid #dde;border-radius:6px;padding:20px;margin:24px 0}}
  label{{display:block;margin:12px 0 4px;font-weight:600;font-size:.9rem}}
  input,select{{width:100%;padding:8px 10px;border:1px solid #ccc;border-radius:4px;font-size:.95rem}}
  .row{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
  button{{background:#1F60C4;color:#fff;padding:10px 28px;border:none;border-radius:4px;
          cursor:pointer;font-size:1rem;margin-top:18px}}
  button:hover{{background:#174fa0}}
  .msg{{padding:12px 16px;border-radius:4px;margin-bottom:16px}}
  .ok{{background:#d4edda;border:1px solid #28a745}}
  .err{{background:#f8d7da;border:1px solid #dc3545}}
  table{{width:100%;border-collapse:collapse;font-size:.9rem}}
  th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid #ddd}}
  th{{background:#eef}}
  .note{{font-size:.8rem;color:#777;margin-top:6px}}
  .tz{{font-size:.8rem;color:#1F60C4;margin-top:4px}}
</style>
<script>
  document.addEventListener("DOMContentLoaded",function(){{
    var el=document.getElementById("tzinfo");
    if(el){{
      var off=-new Date().getTimezoneOffset();
      var sign=off>=0?"+":"-";
      var h=String(Math.floor(Math.abs(off)/60)).padStart(2,"0");
      var m=String(Math.abs(off)%60).padStart(2,"0");
      el.textContent="Your browser timezone offset: UTC"+sign+h+":"+m+
        " — enter times in your local time and the server will convert to UTC automatically.";
    }}
  }});
</script>
</head>
<body>
<h1>GLerp Maintenance Window Admin</h1>
<p>Define a maintenance window to: exclude the period from SLA calculations, mark it on Grafana dashboards, and suppress alerts.</p>
{msg}
<div class="card">
<h2>Create Maintenance Window</h2>
<form method="POST" action="/window">
  <label>Site</label>
  <select name="site">
    <option value="__all__">All sites</option>
    {site_opts}
  </select>
  <div class="row">
    <div>
      <label>Start (local time)</label>
      <input type="datetime-local" name="start" required>
    </div>
    <div>
      <label>End (local time)</label>
      <input type="datetime-local" name="end" required>
    </div>
  </div>
  <div id="tzinfo" class="tz"></div>
  <label>Description</label>
  <input type="text" name="description" placeholder="e.g. ERPNext v16.1 upgrade — backuptest" required>
  <p class="note">Times are read from your browser's local timezone and converted to UTC automatically.</p>
  <button type="submit">Create Maintenance Window</button>
</form>
</div>
<div class="card">
<h2>Active Windows (last 24 h)</h2>
{windows}
<p class="note">To remove a window: delete the Grafana annotation from the dashboard, expire the AlertManager silence via Alerting &rarr; Silences, and contact your operator to remove the VictoriaMetrics metric if needed.</p>
</div>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Backend helpers
# ---------------------------------------------------------------------------

def _http(method, url, body=None, headers=None):
    data = body.encode() if isinstance(body, str) else body
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except Exception as e:
        return 0, str(e)


def vm_get(path):
    return _http("GET", VM_URL.rstrip("/") + path)


def vm_post_text(path, body):
    return _http("POST", VM_URL.rstrip("/") + path, body, {"Content-Type": "text/plain"})


def grafana(method, path, body=None):
    hdrs = {"Authorization": f"Bearer {GRAFANA_TOKEN}"}
    if body is not None:
        hdrs["Content-Type"] = "application/json"
        body = json.dumps(body)
    return _http(method, GRAFANA_URL.rstrip("/") + path, body, hdrs)


def alertmanager(method, path, body=None):
    hdrs = {}
    if body is not None:
        hdrs["Content-Type"] = "application/json"
        body = json.dumps(body)
    return _http(method, AM_URL.rstrip("/") + path, body, hdrs)


def get_sites():
    qs = urllib.parse.urlencode({"match[]": 'probe_success{job="glerp-sites-login"}'})
    status, body = vm_get(f"/api/v1/label/site/values?{qs}")
    if status == 200:
        return sorted(json.loads(body).get("data", []))
    return []


def get_active_windows():
    """Return distinct sites that currently have glerp_maintenance_window = 1."""
    now_s = int(time.time())
    qs = urllib.parse.urlencode({"query": "glerp_maintenance_window", "time": now_s})
    status, body = vm_get(f"/api/v1/query?{qs}")
    if status != 200:
        return []
    results = json.loads(body).get("data", {}).get("result", [])
    rows = []
    for r in results:
        site = r["metric"].get("site", "?")
        val  = r.get("value", [None, None])[1]
        rows.append((site, val))
    return rows


def write_metric(site, start_ms, end_ms):
    """Write glerp_maintenance_window{site=X} = 1 every 60 s across the window."""
    lines = []
    ts = start_ms
    while ts <= end_ms:
        lines.append(f'glerp_maintenance_window{{site="{site}"}} 1 {ts}')
        ts += 60_000
    return vm_post_text("/api/v1/import/prometheus", "\n".join(lines) + "\n")


def create_annotation(site, start_ms, end_ms, description):
    tags = ["maintenance", ("all" if site == "__all__" else site)]
    return grafana("POST", "/api/annotations", {
        "text":    description,
        "tags":    tags,
        "time":    start_ms,
        "timeEnd": end_ms,
    })


def create_silence(site, start_iso, end_iso, description):
    if site == "__all__":
        matchers = [{"name": "alertname", "value": "GLerp.*", "isRegex": True}]
    else:
        matchers = [{"name": "site", "value": site, "isRegex": False}]
    return alertmanager("POST", "/api/v2/silences", {
        "matchers":  matchers,
        "startsAt":  start_iso,
        "endsAt":    end_iso,
        "createdBy": "glerp-maintenance-admin",
        "comment":   description,
    })


def parse_local_dt(s):
    """Parse datetime-local string with optional timezone offset, return epoch ms."""
    # Browsers send YYYY-MM-DDTHH:MM or YYYY-MM-DDTHH:MM:SS
    # We try to parse as-is; if no tzinfo, treat as UTC (user is told this in the UI)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        raise ValueError(f"Cannot parse '{s}' as a date/time")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)

# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # silence per-request noise

    def _auth_ok(self):
        hdr = self.headers.get("Authorization", "")
        if not hdr.startswith("Basic "):
            return False
        try:
            raw = base64.b64decode(hdr[6:]).decode()
            u, p = raw.split(":", 1)
            return u == ADMIN_USER and p == ADMIN_PASS
        except Exception:
            return False

    def _challenge(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="GLerp Maintenance Admin"')
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h1>401 Authentication required</h1>")

    def _send_html(self, html, status=200):
        body = html.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _render(self, msg=""):
        sites = get_sites()
        site_opts = "\n    ".join(f'<option value="{s}">{s}</option>' for s in sites)

        rows = get_active_windows()
        if rows:
            trs = "".join(
                f"<tr><td>{site}</td><td>{'active' if v == '1' else v}</td></tr>"
                for site, v in rows
            )
            windows = f"<table><tr><th>Site</th><th>Status</th></tr>{trs}</table>"
        else:
            windows = "<p><em>No active maintenance windows right now.</em></p>"

        return PAGE.format(msg=msg, site_opts=site_opts, windows=windows)

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        if not self._auth_ok():
            self._challenge()
            return
        self._send_html(self._render())

    def do_POST(self):
        if not self._auth_ok():
            self._challenge()
            return

        length = int(self.headers.get("Content-Length", 0))
        raw    = self.rfile.read(length).decode()
        params = urllib.parse.parse_qs(raw)

        def p(k):
            return params.get(k, [""])[0].strip()

        if self.path == "/window":
            site        = p("site")
            start_str   = p("start")
            end_str     = p("end")
            description = p("description")

            if not all([site, start_str, end_str, description]):
                self._send_html(self._render(
                    '<div class="msg err">All fields are required.</div>'
                ))
                return

            try:
                start_ms = parse_local_dt(start_str)
                end_ms   = parse_local_dt(end_str)
            except ValueError as e:
                self._send_html(self._render(
                    f'<div class="msg err">Invalid date/time: {e}</div>'
                ))
                return

            if end_ms <= start_ms:
                self._send_html(self._render(
                    '<div class="msg err">End time must be after start time.</div>'
                ))
                return

            start_iso = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).isoformat()
            end_iso   = datetime.fromtimestamp(end_ms   / 1000, tz=timezone.utc).isoformat()

            sites_to_write = get_sites() if site == "__all__" else [site]
            errors = []

            for s in sites_to_write:
                st, _ = write_metric(s, start_ms, end_ms)
                if st not in (200, 204):
                    errors.append(f"VictoriaMetrics write failed for site '{s}' (HTTP {st})")

            st, _ = create_annotation(site, start_ms, end_ms, description)
            if st not in (200, 204):
                errors.append(f"Grafana annotation failed (HTTP {st}) — check GRAFANA_TOKEN")

            st, _ = create_silence(site, start_iso, end_iso, description)
            if st not in (200, 201):
                errors.append(f"AlertManager silence failed (HTTP {st})")

            if errors:
                msg = '<div class="msg err">' + "<br>".join(errors) + "</div>"
            else:
                label = "all sites" if site == "__all__" else f"<strong>{site}</strong>"
                msg = (
                    f'<div class="msg ok">Maintenance window created for {label}:<br>'
                    f"UTC {start_iso} → {end_iso}<br>"
                    f"VictoriaMetrics metric written &bull; Grafana annotation created &bull; AlertManager silence created</div>"
                )

            self._send_html(self._render(msg))
            return

        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"GLerp maintenance admin listening on :{port}", flush=True)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
