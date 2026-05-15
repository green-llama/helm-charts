# k8-glerp-monitoring

Kubernetes-native uptime monitoring for GLerp (ERPNext v16) sites and ISP connectivity.
Designed for RKE2 clusters running Rancher Monitoring (kube-prometheus-stack).

## What This Does

- **Monitors all GLerp sites automatically** — add one label and one annotation to a site's Service; Prometheus discovers it within 60 seconds, no per-site config files needed.
- **Three-tier health checks** — detects complete outages (Nginx down) AND partial outages (ERPNext workers degraded, login page malformed).
- **ISP vs. application differentiation** — distinguishes your site being down from your ISP being down; suppresses site alerts during ISP outages.
- **90-day SLA retention** — VictoriaMetrics stores probe metrics long-term so 30-day SLA reports are accurate (Prometheus alone only retains ~8-10 days).
- **Grafana dashboards** — real-time status grid, 30-day SLA compliance table (CSV export), internet connectivity history.
- **Email alerts** — after 2 minutes down (critical) or 5 minutes degraded (warning); clears when restored.

## Prerequisites

- Rancher Monitoring (kube-prometheus-stack) installed in `cattle-monitoring-system`
- Helm v3+ with the Green Llama chart repo:
  ```bash
  helm repo add green-llama https://green-llama.github.io/helm-charts/
  helm repo update
  ```
- A Kubernetes Secret with your SMTP password (create **before** installing the chart):
  ```bash
  kubectl create secret generic alertmanager-smtp-secret \
    --namespace cattle-monitoring-system \
    --from-literal=smtp_auth_password='YOUR_PASSWORD'
  ```

## Installation

### Step 1 — Install the chart

```bash
helm install glerp-monitoring green-llama/glerp-monitoring \
  --namespace cattle-monitoring-system \
  --set cluster.name=gl-prod \
  --set cluster.domain=greenllama.tech \
  --set alertmanager.email.smarthost="smtp.example.com:587" \
  --set alertmanager.email.from="alerts@greenllama.tech" \
  --set alertmanager.email.to="ops@greenllama.tech" \
  --set alertmanager.email.authUsername="alerts@greenllama.tech"
```

Or use a values override file — copy and edit `charts/glerp-monitoring/values.yaml`.

### Step 2 — Configure rancher-monitoring to pick up our scrape jobs

The chart creates a Secret (`glerp-monitoring-scrape-configs`) containing the Prometheus scrape config for all GLerp sites and ISP probes. Prometheus needs to be pointed at it. Add the following to the **rancher-monitoring** Helm values (Rancher UI → Apps → rancher-monitoring → Edit/Upgrade → Edit YAML):

```yaml
prometheus:
  prometheusSpec:
    additionalScrapeConfigsSecret:
      enabled: true
      name: glerp-monitoring-scrape-configs
      key: scrape-configs.yaml
    remoteWrite:
      - url: http://glerp-monitoring-victoriametrics.cattle-monitoring-system.svc.cluster.local:8428/api/v1/write
        writeRelabelConfigs:
          - sourceLabels: [job]
            regex: "glerp-sites-basic|glerp-sites-login|glerp-sites-internal|internet-connectivity"
            action: keep
```

The `remoteWrite` block forwards probe metrics to VictoriaMetrics for 90-day retention.
Without it, SLA dashboards will only show data for the last 8-10 days.

### Step 3 — Verify

Within ~60 seconds of saving the rancher-monitoring values:

- **Prometheus UI → Status → Targets** — you should see `internet-connectivity` with 3 UP targets (Google, Cloudflare, Microsoft). The `glerp-sites-*` jobs appear empty until a site is labeled (Step 4).
- **Grafana → Dashboards → GLerp Monitoring** — the Internet Connectivity dashboard should show data immediately. Site dashboards populate after a site is labeled.

## Adding a New GLerp Site

Add these two fields to the site's Kubernetes **Service** (in your GLerp Helm chart values or via `extraObjects`):

```yaml
service:
  labels:
    glerp-monitoring: "enabled"
  annotations:
    glerp-monitoring/public-url: "https://company.greenllama.tech"
```

Prometheus discovers the site automatically within ~60 seconds. It will appear in the Uptime Overview and SLA Compliance dashboards.

**Using `extraObjects` in the GLerp chart** (recommended — survives Helm upgrades):

```yaml
extraObjects:
  - apiVersion: v1
    kind: Service
    metadata:
      name: nginx-monitoring
      labels:
        glerp-monitoring: "enabled"
      annotations:
        glerp-monitoring/public-url: "https://company.greenllama.tech"
    spec:
      selector:
        app: nginx
      ports:
        - port: 80
          targetPort: 8080
```

## Maintenance Windows

The **Maintenance Admin** tool is an optional browser-based form included in the chart. On submit it simultaneously:

- Writes the `glerp_maintenance_window` metric to VictoriaMetrics (the adjusted SLA panels automatically exclude this period from calculations)
- Creates a blue shaded annotation band on all monitoring dashboards
- Creates an AlertManager silence so no alert emails are sent during the window

Windows can be deleted from the same UI — deletion expires the silence, removes the metric, and hides the annotation band from dashboards.

### Enabling the Maintenance Admin

```yaml
maintenanceAdmin:
  enabled: true
  hostname: "maintenance.monitoring.greenllama.tech"   # must be accessible from admin's browser
  grafanaToken: "<Grafana service account token — Editor role>"
  auth:
    password: "<strong password>"
```

See the deployment guide for the full setup procedure, including how to create the Grafana service account token and add the maintenance admin link to your dashboards.

## Customer Reporting

### Dashboards

The **Customer SLA Report** dashboard (`GLerp Monitoring → GLerp — Customer SLA Report`) is designed for customer-facing use:
- Select the customer's site from the **Site** dropdown (no "All" option — prevents seeing other customers' data)
- Set the time range to the reporting period (default: last 30 days)
- Data is sourced from VictoriaMetrics for accurate long-range calculations

### Sharing a live link

1. Open the Customer SLA Report dashboard with the correct site selected
2. Go to **Share → Public Dashboard → Enable**
3. Copy the public URL — customers can view it without a Grafana login
4. For a direct per-customer link, append `?var-site=<namespace>` to pre-select their site

### PDF export

Requires enabling the Grafana image renderer in rancher-monitoring values:

```yaml
grafana:
  imageRenderer:
    enabled: true
```

After enabling: **Share → Export as PDF** becomes available on any dashboard.

## Alert Summary

| Alert | Condition | Severity |
|---|---|---|
| `GLerpSiteDown` | Site HTTP probe fails 2+ min, ISP healthy | Critical |
| `GLerpSiteDegraded` | Site up but login page malformed 5+ min | Warning |
| `ISPConnectivityLost` | Majority of external probes fail 2+ min | Critical |
| `ISPConnectivityRestored` | External probes recover | Info |

During an ISP outage, `GLerpSiteDown` and `GLerpSiteDegraded` are **suppressed** — only `ISPConnectivityLost` fires.

## SLA Target

**99.5% monthly uptime** (≤ 3.6 hours downtime per month per site).
The SLA signal uses the login-tier probe — both complete outages and degraded states count against SLA.

Export the SLA Compliance dashboard to CSV from Grafana for client reporting.

## Repository Structure

```
charts/
└── glerp-monitoring/
    ├── Chart.yaml
    ├── values.yaml                   ← all configurable settings
    ├── files/dashboards/             ← Grafana dashboard JSON files
    └── templates/
        ├── additional-scrape-configs-secret.yaml  ← site + ISP probe jobs
        ├── alertmanager-config.yaml               ← email routing + ISP inhibition
        ├── grafana-dashboards-configmap.yaml       ← dashboard import (cattle-dashboards)
        ├── grafana-datasource-configmap.yaml       ← VictoriaMetrics datasource
        ├── prometheusrule-alerts-glerp.yaml        ← site alert rules
        ├── prometheusrule-alerts-internet.yaml     ← ISP alert rules
        ├── prometheusrule-recording.yaml           ← site health state recording rule
        └── victoriametrics.yaml                    ← VM deployment + PVC + service
```

## License

Internal use — Green Llama Technologies.
