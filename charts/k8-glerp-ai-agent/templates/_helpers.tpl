{{/* vim: set filetype=mustache: */}}

{{- define "agent.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "agent.fullname" -}}
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

{{- define "agent.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "agent.labels" -}}
helm.sh/chart: {{ include "agent.chart" . }}
{{ include "agent.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/part-of: glerp-ai-agent
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "agent.selectorLabels" -}}
app.kubernetes.io/name: {{ include "agent.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/* Component-scoped names & selectors: pass a dict {"ctx": ., "component": "api"} */}}
{{- define "agent.componentName" -}}
{{- printf "%s-%s" (include "agent.fullname" .ctx) .component | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "agent.componentSelectorLabels" -}}
{{ include "agent.selectorLabels" .ctx }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/* In-cluster service hostnames, derived from the release namespace. */}}
{{- define "agent.postgresHost" -}}
{{- printf "%s-postgres.%s.svc.cluster.local" (include "agent.fullname" .) .Release.Namespace }}
{{- end }}
{{- define "agent.redisHost" -}}
{{- printf "%s-redis.%s.svc.cluster.local" (include "agent.fullname" .) .Release.Namespace }}
{{- end }}
{{- define "agent.qdrantHost" -}}
{{- printf "%s-qdrant.%s.svc.cluster.local" (include "agent.fullname" .) .Release.Namespace }}
{{- end }}
{{- define "agent.embedHost" -}}
{{- printf "%s-embed.%s.svc.cluster.local" (include "agent.fullname" .) .Release.Namespace }}
{{- end }}
{{- define "agent.rerankHost" -}}
{{- printf "%s-rerank.%s.svc.cluster.local" (include "agent.fullname" .) .Release.Namespace }}
{{- end }}
{{- define "agent.vllmLightHost" -}}
{{- printf "%s-vllm-light.%s.svc.cluster.local" (include "agent.fullname" .) .Release.Namespace }}
{{- end }}

{{/*
Soft anti-affinity for the bundled stateful services (postgres/qdrant/redis): prefer a node
not already running one of the OTHER two, so a single node's I/O pressure can't take out
more than one datastore at once. Preferred (not required) so it never blocks scheduling on
a small dev cluster. Pass the calling component's own label value, e.g.
{{ include "agent.statefulAntiAffinity" (dict "ctx" $ "self" "postgres") }}
*/}}
{{- define "agent.statefulAntiAffinity" -}}
{{- $ctx := .ctx -}}
{{- $self := .self -}}
podAntiAffinity:
  preferredDuringSchedulingIgnoredDuringExecution:
    {{- range $other := list "postgres" "qdrant" "redis" }}
    {{- if ne $other $self }}
    - weight: 50
      podAffinityTerm:
        topologyKey: kubernetes.io/hostname
        labelSelector:
          matchExpressions:
            - key: app.kubernetes.io/component
              operator: In
              values: [{{ $other }}]
            - key: app.kubernetes.io/instance
              operator: In
              values: [{{ $ctx.Release.Name }}]
    {{- end }}
    {{- end }}
{{- end }}

{{/*
Soft anti-affinity for the CPU-heavy compute pods (worker/embed/rerank): prefer a node not
already running one of the OTHER two. Docling/RapidOCR (worker) and the two TEI models
(embed/rerank) each want real CPU headroom on this CPU-only hardware -- co-locating any two
of them compounds cgroup CPU throttling on whichever node draws the short straw (confirmed
live 2026-09-12: the worker's own cpu.stat showed ~57% of periods throttled under load).
Preferred, not required, so a small single-node dev cluster still schedules everything.
Pass the calling component's own label value, e.g.
{{ include "agent.computeAntiAffinity" (dict "ctx" $ "self" "worker") }}
*/}}
{{- define "agent.computeAntiAffinity" -}}
{{- $ctx := .ctx -}}
{{- $self := .self -}}
podAntiAffinity:
  preferredDuringSchedulingIgnoredDuringExecution:
    {{- range $other := list "worker" "embed" "rerank" }}
    {{- if ne $other $self }}
    - weight: 50
      podAffinityTerm:
        topologyKey: kubernetes.io/hostname
        labelSelector:
          matchExpressions:
            - key: app.kubernetes.io/component
              operator: In
              values: [{{ $other }}]
            - key: app.kubernetes.io/instance
              operator: In
              values: [{{ $ctx.Release.Name }}]
    {{- end }}
    {{- end }}
{{- end }}

{{- define "agent.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "agent.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "agent.host" -}}
{{- printf "%s.%s" .Release.Namespace .Values.ingress.domain }}
{{- end }}
