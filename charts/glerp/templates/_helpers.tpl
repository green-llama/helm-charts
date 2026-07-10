{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "erpnext.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "erpnext.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "erpnext.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels
*/}}
{{- define "erpnext.labels" -}}
helm.sh/chart: {{ include "erpnext.chart" . }}
{{ include "erpnext.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels
*/}}
{{- define "erpnext.selectorLabels" -}}
app.kubernetes.io/name: {{ include "erpnext.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Create the name of the service account to use
*/}}
{{- define "erpnext.serviceAccountName" -}}
{{- $defaultName := printf "%s-sa" .Release.Namespace -}}
{{- if .Values.serviceAccount.create -}}
{{ default $defaultName .Values.serviceAccount.name }}
{{- else -}}
{{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{/*
Create redis host name
*/}}
{{- define "redis.fullname" -}}
{{- printf "%s-%s" .Release.Name "redis" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Gets the mariadb host name
*/}}
{{- define "erpnext.mariadbHost" -}}
{{ .Values.mariadbHost }}
{{- end -}}

{{/*
Gets the redis socketio host name
*/}}
{{- define "erpnext.redisSocketIOHost" -}}
{{ .Values.redisSocketIOHost }}
{{- end -}}

{{/*
Gets the redis queue host name
*/}}
{{- define "erpnext.redisQueueHost" -}}
{{ .Values.redisQueueHost }}
{{- end -}}

{{/*
Gets the redis cache host name
*/}}
{{- define "erpnext.redisCacheHost" -}}
{{ .Values.redisCacheHost }}
{{- end -}}

{{/*
Resolve mariadb-sts root password secret name.
`mariadb-sts.existingSecret.name` takes precedence over chart-managed secret.
*/}}
{{- define "glerp.mariadbRootSecretName" -}}
{{- $m := (index .Values "mariadb-sts") | default dict -}}
{{- $existing := (get $m "existingSecret") | default dict -}}
{{- if (get $existing "name") -}}
{{- get $existing "name" -}}
{{- else -}}
{{- include "erpnext.fullname" . -}}
{{- end -}}
{{- end -}}

{{/*
Resolve mariadb-sts root password secret key.
*/}}
{{- define "glerp.mariadbRootSecretKey" -}}
{{- $m := (index .Values "mariadb-sts") | default dict -}}
{{- $existing := (get $m "existingSecret") | default dict -}}
{{- default "mariadb-root-password" (get $existing "key") -}}
{{- end -}}
