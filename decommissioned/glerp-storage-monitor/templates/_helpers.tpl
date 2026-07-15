{{/*
Standard labels applied to all resources in this chart.
*/}}
{{- define "glerp-storage-monitor.labels" -}}
app.kubernetes.io/name: glerp-storage-monitor
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{/*
Labels required by Rancher Monitoring's Prometheus to discover PrometheusRule
and ServiceMonitor objects. Defined in values.prometheusRuleLabels.
*/}}
{{- define "glerp-storage-monitor.prometheusRuleLabels" -}}
{{- toYaml .Values.prometheusRuleLabels | nindent 0 }}
{{- end }}

{{/*
VictoriaMetrics cluster-local service URL (used in datasource ConfigMap and NOTES).
*/}}
{{- define "glerp-storage-monitor.vmUrl" -}}
{{- printf "http://%s-victoriametrics.%s.svc:8428" .Release.Name .Values.namespace -}}
{{- end }}
