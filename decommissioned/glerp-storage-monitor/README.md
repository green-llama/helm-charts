# ⛔ SUPERSEDED — use `glerp-monitoring` instead

> # This chart is decommissioned.
> ## All of its features (Longhorn / DirectPV / MinIO monitoring, VictoriaMetrics long-term storage, storage alerts & recording rules, and the storage Grafana dashboards) have been merged into the **`glerp-monitoring`** chart (v2+).
>
> **Do not install `glerp-storage-monitor`.** It has been removed from the Green
> Llama Helm catalog and is no longer published. It is kept here only as a
> historical record and is scheduled for deletion in a few months if unused.
>
> ➡ **Install [`glerp-monitoring`](../../charts/glerp-monitoring) instead** — it is the
> single unified monitoring + security + storage chart.

---

## What moved to glerp-monitoring

| glerp-storage-monitor feature | Now in glerp-monitoring |
|---|---|
| Longhorn ServiceMonitor | `longhorn-servicemonitor.yaml` |
| DirectPV PodMonitor | `directpv-podmonitor.yaml` |
| MinIO ServiceMonitors | `minio-servicemonitors.yaml` |
| VictoriaMetrics long-term storage | `victoriametrics.yaml` |
| Storage alerts / recording rules | `prometheusrule-alerts-storage.yaml`, `prometheusrule-recording-storage.yaml` |
| Storage Grafana dashboards (customer/fleet/growth/namespaces) | `files/dashboards/glerp-storage-*.json` |

All nine dashboards (uptime, storage, security) now live in one unified Grafana folder
managed by `glerp-monitoring`.
