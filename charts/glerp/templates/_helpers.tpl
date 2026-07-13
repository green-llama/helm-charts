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
Tenant name = the release namespace (one tenant per namespace).
*/}}
{{- define "glerp.tenant" -}}
{{- .Release.Namespace -}}
{{- end -}}

{{/*
Tenant domain: tenant.domain, else top-level domain. Required when tenant.enabled.
*/}}
{{- define "glerp.tenantDomain" -}}
{{- $d := .Values.tenant.domain | default .Values.domain -}}
{{- required "tenant.enabled requires tenant.domain (or .Values.domain)" $d -}}
{{- end -}}

{{/*
Tenant FQDN = <namespace>.<domain>
*/}}
{{- define "glerp.tenantFqdn" -}}
{{- printf "%s.%s" .Release.Namespace (include "glerp.tenantDomain" .) -}}
{{- end -}}

{{/*
Public URL for the tenant. Precedence:
  1. tenant.monitoringProbe.publicUrl (full override)
  2. https://<fqdn>[:externalPort]
*/}}
{{- define "glerp.tenantPublicUrl" -}}
{{- $mp := .Values.tenant.monitoringProbe | default dict -}}
{{- if (get $mp "publicUrl") -}}
{{- get $mp "publicUrl" -}}
{{- else if .Values.tenant.externalPort -}}
{{- printf "https://%s:%v" (include "glerp.tenantFqdn" .) .Values.tenant.externalPort -}}
{{- else -}}
{{- printf "https://%s" (include "glerp.tenantFqdn" .) -}}
{{- end -}}
{{- end -}}

{{/*
Resolve mariadb-sts root password secret name. Precedence:
  1. explicit mariadb-sts.existingSecret.name
  2. tenant mode (no explicit name): the Vault-synced "<namespace>-mariadb-root" secret
  3. chart-managed generated secret: "<fullname>"
*/}}
{{- define "glerp.mariadbRootSecretName" -}}
{{- $m := (index .Values "mariadb-sts") | default dict -}}
{{- $existing := (get $m "existingSecret") | default dict -}}
{{- if (get $existing "name") -}}
{{- get $existing "name" -}}
{{- else if (get $m "generateRootSecret") -}}
{{- /* chart-generated secret (dev/test) always lives at <fullname> */ -}}
{{- include "erpnext.fullname" . -}}
{{- else if and .Values.tenant .Values.tenant.enabled -}}
{{- printf "%s-mariadb-root" .Release.Namespace -}}
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
