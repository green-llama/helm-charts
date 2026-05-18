{{/*
Expand the name of the chart.
*/}}
{{- define "glerp-security.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "glerp-security.fullname" -}}
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
{{- define "glerp-security.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to all resources.
*/}}
{{- define "glerp-security.labels" -}}
helm.sh/chart: {{ include "glerp-security.chart" . }}
{{ include "glerp-security.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels.
*/}}
{{- define "glerp-security.selectorLabels" -}}
app.kubernetes.io/name: {{ include "glerp-security.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Service account name used by kube-bench.
*/}}
{{- define "glerp-security.serviceAccountName" -}}
{{- printf "%s-scanner" (include "glerp-security.fullname" .) }}
{{- end }}

{{/*
Pushgateway URL for kube-bench metrics push.
*/}}
{{- define "glerp-security.pushgatewayUrl" -}}
{{- printf "http://%s-prometheus-pushgateway.%s.svc.cluster.local:9091" .Release.Name .Release.Namespace }}
{{- end }}
