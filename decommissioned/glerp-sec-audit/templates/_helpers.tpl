{{/*
Expand the name of the chart.
*/}}
{{- define "glerp-sec-audit.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "glerp-sec-audit.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Chart label including version.
*/}}
{{- define "glerp-sec-audit.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to all resources.
*/}}
{{- define "glerp-sec-audit.labels" -}}
helm.sh/chart: {{ include "glerp-sec-audit.chart" . }}
{{ include "glerp-sec-audit.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels.
*/}}
{{- define "glerp-sec-audit.selectorLabels" -}}
app.kubernetes.io/name: {{ include "glerp-sec-audit.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Service account name used by kube-bench.
*/}}
{{- define "glerp-sec-audit.serviceAccountName" -}}
{{- printf "%s-scanner" (include "glerp-sec-audit.fullname" .) }}
{{- end }}

{{/*
Pushgateway URL for kube-bench metrics push.
*/}}
{{- define "glerp-sec-audit.pushgatewayUrl" -}}
{{- printf "http://%s-prometheus-pushgateway.%s.svc.cluster.local:9091" .Release.Name .Release.Namespace }}
{{- end }}
