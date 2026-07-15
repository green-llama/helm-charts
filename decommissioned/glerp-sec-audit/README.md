# ⛔ SUPERSEDED — use `glerp-monitoring` instead

> # This chart is decommissioned.
> ## All of its features (Trivy operator, kube-bench CIS scans, OWASP ZAP scans, the report server, and the security Grafana dashboard) have been merged into the **`glerp-monitoring`** chart (v2+).
>
> **Do not install `glerp-sec-audit`.** It has been removed from the Green Llama
> Helm catalog and is no longer published. It is kept here only as a historical
> record and is scheduled for deletion in a few months if unused.
>
> ➡ **Install [`glerp-monitoring`](../../charts/glerp-monitoring) instead** — it is the
> single unified monitoring + security + storage chart.

---

## What moved to glerp-monitoring

| glerp-sec-audit feature | Now in glerp-monitoring |
|---|---|
| Trivy operator (vulnerability scanning) | `trivy-operator` subchart |
| kube-bench CIS benchmark cronjob | `kube-bench-cronjob.yaml` |
| OWASP ZAP DAST scans | `zap-cronjob.yaml` / `zap-configmap.yaml` |
| Report server + ingress + cleanup | `report-server*.yaml`, `report-cleanup-cronjob.yaml` |
| Security Grafana dashboard | `grafana-security-dashboard-configmap.yaml` |

All nine dashboards (uptime, storage, security) now live in one unified Grafana folder
managed by `glerp-monitoring`.
