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
{{- $d = required "tenant.enabled requires tenant.domain (or .Values.domain)" $d -}}
{{/* Fail fast on a malformed domain (e.g. a comma/space typo like "dev,greenllama.tech").
     Left unchecked it flows into MINIO_BROWSER_REDIRECT_URL and MinIO crash-loops at boot with
     "FATAL Invalid MINIO_BROWSER_REDIRECT_URL: invalid hostname". A valid DNS domain is dot-
     separated labels of [a-z0-9-]; catch the common typos here with a clear message. */}}
{{- if not (regexMatch "^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$" $d) -}}
{{- fail (printf "invalid domain %q: must be a dot-separated DNS name (lowercase letters, digits, hyphens) with no commas, spaces, or underscores — e.g. dev.greenllama.tech" $d) -}}
{{- end -}}
{{- $d -}}
{{- end -}}

{{/*
Tenant FQDN = <namespace>.<domain>
*/}}
{{- define "glerp.tenantFqdn" -}}
{{- printf "%s.%s" .Release.Namespace (include "glerp.tenantDomain" .) -}}
{{- end -}}

{{/*
Frappe site name for this release. Precedence:
  1. jobs.createSite.siteName  (explicit per-install override)
  2. siteName                  (explicit chart-level override)
  3. <namespace>.<domain>      (Green Llama convention — derived when a domain is set)
  4. <namespace>               (last resort so a bare dev install still gets a name)
Never empty, so the create-site job no longer hard-fails on a blank siteName.
*/}}
{{- define "glerp.siteName" -}}
{{- $explicit := .Values.jobs.createSite.siteName | default .Values.siteName -}}
{{- if $explicit -}}
{{- $explicit -}}
{{- else -}}
{{- $d := .Values.tenant.domain | default .Values.domain -}}
{{- if $d -}}
{{- printf "%s.%s" .Release.Namespace $d -}}
{{- else -}}
{{- .Release.Namespace -}}
{{- end -}}
{{- end -}}
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

{{/*
Render one MinIO Tenant pool entry. Context (dict): name, spec (this pool's overrides, may be
empty), defaults (tenant.minio, for servers/volumesPerServer/volumeSize/storageClass fallback).
Used for both the uniform base pools and tenant.minio.extraPools entries so the two loops in
minio-tenant.yaml can't drift out of sync (mesh-exclusion labels, security contexts, etc.).
*/}}
{{- define "glerp.minioPool" -}}
{{- $spec := .spec | default dict -}}
{{- $defaults := .defaults | default dict -}}
- name: {{ .name }}
  servers: {{ $spec.servers | default $defaults.servers | default 2 }}
  volumesPerServer: {{ $spec.volumesPerServer | default $defaults.volumesPerServer | default 2 }}
  # Keep the service mesh OFF the MinIO data-plane pods: the mesh is reserved for sensitive
  # traffic only, not the high-throughput S3 object path (avoids Envoy latency/overhead), and
  # this matches production, where the MinIO pods run un-meshed. The KES pod DOES stay meshed
  # (see .spec.kes.labels in minio-tenant.yaml) so its Vault hop is protected. This label is a
  # no-op on clusters where sidecar injection is already default-off; it is a guard so that a
  # cluster which default-enables injection can never wrap these pods in an Envoy.
  labels:
    sidecar.istio.io/inject: "false"
  volumeClaimTemplate:
    metadata:
      name: data
    spec:
      accessModes:
        - ReadWriteOnce
      storageClassName: {{ $spec.storageClass | default $defaults.storageClass | default "directpv-min-io" }}
      resources:
        requests:
          # NOTE: MinIO Operator treats this as immutable once the pool exists — for an
          # existing pool, a size mismatch against its live PVCs fails/is rejected on upgrade,
          # not silently resized. Grow capacity via tenant.minio.extraPools (a new pool),
          # never by editing an already-created pool's size here.
          storage: {{ $spec.volumeSize | default $defaults.volumeSize | default "3Gi" }}
  securityContext:
    fsGroup: 1000
  containerSecurityContext:
    runAsUser: 1000
    runAsGroup: 1000
    runAsNonRoot: true
    allowPrivilegeEscalation: false
{{- end -}}
