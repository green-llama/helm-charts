#!/usr/bin/env python3
"""
GLerp Maintenance Window Admin
Create / list / delete maintenance windows.
Each window writes a VictoriaMetrics metric, a Grafana annotation, and an
AlertManager silence.  Deletion expires the silence, removes the VM samples,
and moves the annotation to the "maintenance-deleted" tag so it disappears
from dashboards but remains visible in this admin GUI.
"""
import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

VM_URL        = os.environ.get("VM_URL",        "http://localhost:8428")
GRAFANA_URL   = os.environ.get("GRAFANA_URL",   "http://localhost:3000")
GRAFANA_TOKEN = os.environ.get("GRAFANA_TOKEN", "")
AM_URL        = os.environ.get("AM_URL",        "http://localhost:9093")
ADMIN_USER    = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASS    = os.environ.get("ADMIN_PASSWORD", "changeme")

# ── HTML ─────────────────────────────────────────────────────────────────────

PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GLerp Maintenance Admin</title>
<style>
*{{box-sizing:border-box}}
body{{font-family:sans-serif;max-width:980px;margin:40px auto;padding:0 20px;color:#333}}
h1{{color:#1F60C4;margin-bottom:4px}}
h2{{margin-top:0;font-size:1.05rem;color:#555}}
.card{{background:#f7f8fa;border:1px solid #dde;border-radius:6px;padding:20px;margin:24px 0}}
label{{display:block;margin:12px 0 4px;font-weight:600;font-size:.9rem}}
input,select{{width:100%;padding:8px 10px;border:1px solid #ccc;border-radius:4px;font-size:.95rem}}
.row{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.btn{{display:inline-block;padding:8px 20px;border:none;border-radius:4px;cursor:pointer;font-size:.9rem;color:#fff}}
.btn-blue{{background:#1F60C4}}.btn-blue:hover{{background:#174fa0}}
.btn-red{{background:#dc3545}}.btn-red:hover{{background:#b02a37}}
.btn-grey{{background:#6c757d}}.btn-grey:hover{{background:#545b62}}
.msg{{padding:12px 16px;border-radius:4px;margin-bottom:16px}}
.ok{{background:#d4edda;border:1px solid #28a745}}
.err{{background:#f8d7da;border:1px solid #dc3545}}
.info{{background:#d1ecf1;border:1px solid #17a2b8}}
table{{width:100%;border-collapse:collapse;font-size:.84rem;margin-top:8px}}
th,td{{text-align:left;padding:7px 10px;border-bottom:1px solid #ddd;vertical-align:top}}
th{{background:#eef;font-size:.8rem}}
.s-active{{color:#28a745;font-weight:700}}
.s-upcoming{{color:#fd7e14;font-weight:700}}
.s-past{{color:#6c757d}}
.s-deleted{{color:#aaa;text-decoration:line-through}}
.del-panel{{display:none;margin-top:8px;padding:10px;background:#fff3cd;
             border:1px solid #ffc107;border-radius:4px}}
.del-panel input{{margin-bottom:8px}}
.note{{font-size:.8rem;color:#777;margin-top:6px}}
.tz{{font-size:.8rem;color:#1F60C4;margin-top:4px}}
</style>
<script>
document.addEventListener("DOMContentLoaded",function(){{
  var rawOff=new Date().getTimezoneOffset();
  var tzField=document.getElementById("tz_offset");
  if(tzField) tzField.value=rawOff;
  var el=document.getElementById("tzinfo");
  if(el){{
    var off=-rawOff;
    var sign=off>=0?"+":"-";
    var h=String(Math.floor(Math.abs(off)/60)).padStart(2,"0");
    var m=String(Math.abs(off)%60).padStart(2,"0");
    el.textContent="Browser timezone: UTC"+sign+h+":"+m+
      " — enter times in your local time, the server converts to UTC automatically.";
  }}
}});
function showDel(id){{document.getElementById("del-"+id).style.display="block";}}
function hideDel(id){{document.getElementById("del-"+id).style.display="none";}}
</script>
</head>
<body>
<h1>GLerp Maintenance Window Admin</h1>
<p>Define a maintenance window to exclude the period from SLA calculations,
mark it on Grafana dashboards, and suppress alerts.</p>
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
  <input type="text" name="description"
         placeholder="e.g. ERPNext v16.1 upgrade" required>
  <input type="hidden" name="tz_offset" id="tz_offset" value="0">
  <p class="note">Times are read from your browser's local timezone and
  converted to UTC automatically.</p>
  <button type="submit" class="btn btn-blue">Create Maintenance Window</button>
</form>
</div>
<div class="card">
<h2>Maintenance Windows</h2>
{windows}
<p class="note">
  <strong>Active</strong> = window is ongoing now (alerts suppressed)&nbsp;·&nbsp;
  <strong>Upcoming</strong> = starts in the future&nbsp;·&nbsp;
  <strong>Past</strong> = completed&nbsp;·&nbsp;
  <span class="s-deleted">Deleted</span> = removed from SLA and dashboards,
  retained here for audit.
  All times shown in UTC.
</p>
</div>
</body>
</html>
"""

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _http(method, url, body=None, headers=None):
    data = body.encode() if isinstance(body, str) else body
    req  = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except Exception as e:
        return 0, str(e)


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


def vm_post_text(path, body):
    return _http("POST", VM_URL.rstrip("/") + path, body,
                 {"Content-Type": "text/plain"})

# ── Domain helpers ────────────────────────────────────────────────────────────

def get_sites():
    qs  = urllib.parse.urlencode({"match[]": 'probe_success{job="glerp-sites-login"}'})
    st, body = _http("GET", VM_URL.rstrip("/") + f"/api/v1/label/site/values?{qs}")
    if st == 200:
        return sorted(json.loads(body).get("data", []))
    return []


def write_metric(site, start_ms, end_ms):
    lines = []
    ts = start_ms
    while ts <= end_ms:
        lines.append(f'glerp_maintenance_window{{site="{site}"}} 1 {ts}')
        ts += 60_000
    return vm_post_text("/api/v1/import/prometheus", "\n".join(lines) + "\n")


def delete_metric(site, start_ms, end_ms):
    """Remove glerp_maintenance_window samples for a site within the time range."""
    if site == "all":
        selector = "glerp_maintenance_window"          # all sites
    else:
        selector = f'glerp_maintenance_window{{site="{site}"}}'
    qs = urllib.parse.urlencode({
        "match[]": selector,
        "start":   int(start_ms / 1000),
        "end":     int(end_ms   / 1000),
    })
    return _http("POST", VM_URL.rstrip("/") + f"/api/v1/admin/tsdb/delete_series?{qs}")


def create_annotation(site, start_ms, end_ms, description, silence_id=""):
    tags = ["maintenance", ("all" if site == "__all__" else site)]
    if silence_id:
        tags.append(f"silence:{silence_id}")
    return grafana("POST", "/api/annotations", {
        "text":    description,
        "tags":    tags,
        "time":    start_ms,
        "timeEnd": end_ms,
    })


def get_annotation(ann_id):
    st, body = grafana("GET", f"/api/annotations/{ann_id}")
    if st == 200:
        return json.loads(body)
    return None


def mark_annotation_deleted(ann_id, original_ann, delete_comment):
    """Move annotation from 'maintenance' to 'maintenance-deleted' tag."""
    old_tags = original_ann.get("tags", [])
    new_tags = ["maintenance-deleted"] + [
        t for t in old_tags
        if t != "maintenance" and not t.startswith("silence:")
    ]
    original_text = original_ann.get("text", "")
    new_text = f"[DELETED: {delete_comment}]\n\n{original_text}"
    return grafana("PUT", f"/api/annotations/{ann_id}", {
        "time":    original_ann.get("time",    0),
        "timeEnd": original_ann.get("timeEnd", 0),
        "tags":    new_tags,
        "text":    new_text,
    })


def create_silence(site, start_iso, end_iso, description):
    if site == "__all__":
        matchers = [{"name": "alertname", "value": "GLerp.*",
                     "isRegex": True,  "isEqual": True}]
    else:
        matchers = [{"name": "site", "value": site,
                     "isRegex": False, "isEqual": True}]
    st, body = alertmanager("POST", "/api/v2/silences", {
        "matchers":  matchers,
        "startsAt":  start_iso,
        "endsAt":    end_iso,
        "createdBy": "glerp-maintenance-admin",
        "comment":   description,
    })
    silence_id = ""
    if st in (200, 201):
        try:
            silence_id = json.loads(body).get("silenceID", "")
        except Exception:
            pass
        return st, "", silence_id
    return st, body[:300], ""


def expire_silence(silence_id):
    """Expire an AlertManager silence immediately."""
    return alertmanager("DELETE", f"/api/v2/silences/{silence_id}")


def parse_local_dt(s, tz_offset_minutes=0):
    """
    Parse a naive datetime-local browser string and return UTC epoch ms.
    tz_offset_minutes = browser's getTimezoneOffset():
      positive for UTC-N zones (e.g. CDT/UTC-5 → +300)
      negative for UTC+N zones (e.g. UTC+2 → -120)
    UTC = local + tz_offset_minutes.
    """
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        raise ValueError(f"Cannot parse '{s}' as a date/time")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc) + timedelta(minutes=tz_offset_minutes)
    return int(dt.timestamp() * 1000)

# ── Window listing ────────────────────────────────────────────────────────────

def _ann_site(ann):
    for t in ann.get("tags", []):
        if t not in ("maintenance", "maintenance-deleted") and not t.startswith("silence:"):
            return t
    return "?"


def _ann_silence_id(ann):
    for t in ann.get("tags", []):
        if t.startswith("silence:"):
            return t[len("silence:"):]
    return None


def _fmt_utc(ms):
    if not ms:
        return "—"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def get_all_windows():
    windows = {}
    for tag in ("maintenance", "maintenance-deleted"):
        st, body = grafana("GET", f"/api/annotations?tags={tag}&limit=200")
        if st == 200:
            for ann in json.loads(body):
                windows[ann["id"]] = ann   # deduplicate by id
    return sorted(windows.values(), key=lambda x: x.get("time", 0), reverse=True)


def render_windows():
    try:
        anns = get_all_windows()
    except Exception as e:
        return f"<p class='err'>Could not load windows: {e}</p>"

    if not anns:
        return "<p><em>No maintenance windows recorded yet.</em></p>"

    now_ms = int(time.time() * 1000)
    rows   = []
    for ann in anns:
        tags    = ann.get("tags", [])
        deleted = "maintenance-deleted" in tags
        site    = _ann_site(ann)
        start   = ann.get("time",    0)
        end     = ann.get("timeEnd", start)
        text    = ann.get("text",    "")
        ann_id  = ann["id"]

        if deleted:
            css, label = "s-deleted",  "Deleted"
        elif start > now_ms:
            css, label = "s-upcoming", "Upcoming"
        elif end > now_ms:
            css, label = "s-active",   "Active"
        else:
            css, label = "s-past",     "Past"

        display = (text[:72] + "…") if len(text) > 72 else text

        if deleted:
            action = ""
        else:
            action = (
                f'<button class="btn btn-red" onclick="showDel({ann_id})">Delete…</button>'
                f'<div class="del-panel" id="del-{ann_id}">'
                f'<form method="POST" action="/delete">'
                f'<input type="hidden" name="annotation_id" value="{ann_id}">'
                f'<label style="font-size:.8rem;margin-top:0">Deletion reason (required)</label>'
                f'<input type="text" name="delete_comment"'
                f'       placeholder="e.g. Window cancelled — upgrade postponed" required>'
                f'<div style="margin-top:8px">'
                f'<button type="submit" class="btn btn-red">Confirm Delete</button>'
                f'&nbsp;<button type="button" class="btn btn-grey"'
                f'        onclick="hideDel({ann_id})">Cancel</button>'
                f'</div></form></div>'
            )

        rows.append(
            f"<tr>"
            f"<td>{site}</td>"
            f"<td>{_fmt_utc(start)}</td>"
            f"<td>{_fmt_utc(end)}</td>"
            f"<td>{display}</td>"
            f'<td class="{css}">{label}</td>'
            f"<td>{action}</td>"
            f"</tr>"
        )

    return (
        "<table>"
        "<tr><th>Site</th><th>Start (UTC)</th><th>End (UTC)</th>"
        "<th>Description</th><th>Status</th><th>Action</th></tr>"
        + "".join(rows)
        + "</table>"
    )

# ── HTTP handler ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

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
        sites     = get_sites()
        site_opts = "\n    ".join(
            f'<option value="{s}">{s}</option>' for s in sites
        )
        return PAGE.format(msg=msg, site_opts=site_opts, windows=render_windows())

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

        # ── CREATE ──────────────────────────────────────────────────────────
        if self.path == "/window":
            site        = p("site")
            start_str   = p("start")
            end_str     = p("end")
            description = p("description")
            try:
                tz_offset = int(p("tz_offset") or "0")
            except ValueError:
                tz_offset = 0

            if not all([site, start_str, end_str, description]):
                self._send_html(self._render(
                    '<div class="msg err">All fields are required.</div>'))
                return

            try:
                start_ms = parse_local_dt(start_str, tz_offset)
                end_ms   = parse_local_dt(end_str,   tz_offset)
            except ValueError as e:
                self._send_html(self._render(
                    f'<div class="msg err">Invalid date/time: {e}</div>'))
                return

            if end_ms <= start_ms:
                self._send_html(self._render(
                    '<div class="msg err">End time must be after start time.</div>'))
                return

            start_iso = datetime.fromtimestamp(
                start_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            end_iso   = datetime.fromtimestamp(
                end_ms   / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            sites_to_write = get_sites() if site == "__all__" else [site]
            errors  = []
            notices = []

            # 1. Write VictoriaMetrics metric
            for s in sites_to_write:
                st, _ = write_metric(s, start_ms, end_ms)
                if st not in (200, 204):
                    errors.append(f"VictoriaMetrics write failed for '{s}' (HTTP {st})")

            # 2. Create AlertManager silence (do this before annotation so we
            #    can store the silence ID in the annotation tags)
            st, am_err, silence_id = create_silence(site, start_iso, end_iso, description)
            if st not in (200, 201):
                if st == 400 and "past" in am_err.lower():
                    notices.append(
                        "AlertManager silence was not created because the window end time "
                        "is in the past — this is expected for retroactive entries. "
                        "No silence is needed since the period has already ended."
                    )
                else:
                    errors.append(f"AlertManager silence failed (HTTP {st}): {am_err}")

            # 3. Create Grafana annotation (carries silence ID in tags)
            st, _ = create_annotation(site, start_ms, end_ms, description, silence_id)
            if st not in (200, 204):
                errors.append(f"Grafana annotation failed (HTTP {st}) — check GRAFANA_TOKEN")

            notice_html = (
                '<div class="msg info">' + "<br>".join(notices) + "</div>"
            ) if notices else ""

            if errors:
                msg = '<div class="msg err">' + "<br>".join(errors) + "</div>" + notice_html
            else:
                label = "all sites" if site == "__all__" else f"<strong>{site}</strong>"
                silence_note = f" · AlertManager silence created (ID: {silence_id})" if silence_id else ""
                msg = (
                    f'<div class="msg ok">Maintenance window created for {label}:<br>'
                    f"UTC {start_iso} → {end_iso}<br>"
                    f"VictoriaMetrics metric written · Grafana annotation created"
                    f"{silence_note}</div>"
                    + notice_html
                )

            self._send_html(self._render(msg))
            return

        # ── DELETE ──────────────────────────────────────────────────────────
        if self.path == "/delete":
            ann_id_str     = p("annotation_id")
            delete_comment = p("delete_comment")

            if not ann_id_str or not delete_comment:
                self._send_html(self._render(
                    '<div class="msg err">Annotation ID and deletion reason are required.</div>'))
                return

            try:
                ann_id = int(ann_id_str)
            except ValueError:
                self._send_html(self._render(
                    '<div class="msg err">Invalid annotation ID.</div>'))
                return

            ann = get_annotation(ann_id)
            if not ann:
                self._send_html(self._render(
                    '<div class="msg err">Maintenance window not found in Grafana.</div>'))
                return

            site       = _ann_site(ann)
            silence_id = _ann_silence_id(ann)
            start_ms   = ann.get("time",    0)
            end_ms     = ann.get("timeEnd", start_ms)

            notices = []
            errors  = []

            # 1. Expire AlertManager silence
            if silence_id:
                st, _ = expire_silence(silence_id)
                if st in (200, 204):
                    notices.append("AlertManager silence expired")
                else:
                    notices.append(
                        "Note: AlertManager silence may have already expired "
                        f"(HTTP {st}) — check Alerting → Silences if needed")
            else:
                notices.append(
                    "Note: no silence ID recorded on this window — "
                    "expire any active silence manually via Alerting → Silences")

            # 2. Remove VictoriaMetrics metric samples for the window
            st, _ = delete_metric(site, start_ms, end_ms)
            if st in (200, 204):
                notices.append("VictoriaMetrics metric samples deleted")
            else:
                notices.append(
                    f"Note: VictoriaMetrics delete returned HTTP {st} — "
                    "samples may persist until background merge completes")

            # 3. Mark Grafana annotation as deleted (removes blue band from dashboards)
            st, body = mark_annotation_deleted(ann_id, ann, delete_comment)
            if st in (200, 204):
                notices.append("Grafana annotation updated (no longer shown on dashboards)")
            else:
                errors.append(f"Could not update Grafana annotation (HTTP {st}): {body[:120]}")

            if errors:
                msg = '<div class="msg err">' + "<br>".join(errors + notices) + "</div>"
            else:
                msg = (
                    '<div class="msg ok">Window deleted successfully:<br>'
                    + " · ".join(notices) + "</div>"
                )

            self._send_html(self._render(msg))
            return

        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"GLerp maintenance admin listening on :{port}", flush=True)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
