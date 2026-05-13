{{/*
Return the Blackbox Exporter service address (used in Probe CRDs and scrape configs).
The service name is derived from the Helm release name + subchart alias.
*/}}
{{- define "glerp-monitoring.blackboxAddress" -}}
{{- printf "%s-blackbox-exporter.%s.svc.cluster.local:9115" .Release.Name .Values.monitoringNamespace -}}
{{- end }}

{{/*
Standard labels applied to all resources in this chart.
*/}}
{{- define "glerp-monitoring.labels" -}}
app.kubernetes.io/name: glerp-monitoring
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{/*
Labels required by Rancher Monitoring's Prometheus to discover PrometheusRule objects.
*/}}
{{- define "glerp-monitoring.prometheusRuleLabels" -}}
{{- toYaml .Values.prometheusRuleLabels | nindent 0 }}
{{- end }}
