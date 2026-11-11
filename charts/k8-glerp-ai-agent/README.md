# k8-glerp-ai-agent (Helm chart)

Deploys the **GLerp AI Agent** agentic RAG engine: `agent-api` (FastAPI + MCP + LangGraph),
`ingestion-worker` (connectors + parse/chunk/embed pipeline), and the bundled datastores
(Qdrant, PostgreSQL, Redis) plus self-hosted embedding (HuggingFace TEI) and reranking
(`rerank-api` — transformers+PyTorch on CUDA; NOT TEI, whose GPU backend doesn't support
this cluster's V100, see `templates/rerank-gpu.yaml`).

Source of truth: <https://github.com/green-llama/k8-glerp-ai-agent> — this chart directory is
synced into `green-llama/helm-charts` by that repo's `chart-publish.yml` on a `Chart.yaml`
version bump. Edit it there, not here.

## Prerequisites

Same platform as `k8-glerp-ai-intake`:

- Traefik ingress controller (IngressRoute CRD).
- cert-manager + the wildcard TLS secret `letsencrypt-greenllama-tech-tls` in the namespace.
- External Secrets Operator with `ClusterSecretStore`s `vault-backend` (read) and
  `vault-pushwriter` (write). With `eso.enabled=true` (default) the chart generates the JWT
  signing key + bundled Postgres password and pushes them to Vault once
  (`updatePolicy: IfNotExists`); `ghcr-cred` is pulled from the shared
  `secret/data/github/ghcr-cred` path.
- external-dns (for the IngressRoute CNAME).
- A `StorageClass` for the four PVCs (Qdrant, Postgres, Redis, TEI model cache).

For `eso.enabled=false` (dev / CI) the chart writes in-cluster fallback Secrets instead —
never use that in a real environment.

## Install

```bash
helm repo add green-llama https://green-llama.github.io/helm-charts/
helm upgrade --install glerp-ai-agent green-llama/k8-glerp-ai-agent \
  -n glerp-ai-agent --create-namespace \
  --set ingress.domain=greenllama.tech
```

Dev cluster: set `ingress.domain=dev.greenllama.tech`; the external endpoint is then
`https://glerp-ai-agent.dev.greenllama.tech:10443/agent` (`:10443` NATs to `:443`).

## Key values

| Key | Default | Notes |
|---|---|---|
| `ingress.domain` | `greenllama.tech` | FQDN = `<namespace>.<domain>` |
| `config.DEFAULT_LLM_MODEL` | `gemini/gemini-3.5-flash-lite` | LiteLLM model name; **keys come from GLerp AI Agent Settings**, not the chart |
| `frappe.baseUrl` | `""` | single-tenant GLerp URL fallback; per-tenant values arrive via `/agent/admin/config` |
| `gdrive.enabled` | `false` | Google Shared Drive connector; needs the SA key in Vault at `eso.gdriveVaultKey` |
| `eso.enabled` | `true` | Vault-managed secrets; off = in-cluster fallback (dev only) |
| `api.autoscaling.*` | on, 2–8 | HPA on CPU/mem |
| `qdrant.enabled` / `postgres.enabled` / `redis.enabled` | `true` | set `false` to use an external instance (point `config.*_URL` / DSN at it) |
| `embed.enabled` | `true` | TEI pod (CPU); add `embed.nodeSelector` + a CUDA image tag for GPU — not yet done, see values.yaml note |
| `rerank.enabled` | `true` | `rerank-api` pod (GPU-only, `services/rerank-api`) — targets the V100 via `rerank.nodeSelector` |

## Interfaces

`https://<host>/agent/api/v1/chat` (SSE), `/agent/api/v1/threads/{id}`,
`/agent/api/v1/ingest`, `/agent/api/v1/sources`, `/agent/mcp` (streamable-HTTP),
`/agent/admin/config`, `/agent/admin/reindex`, `/agent/healthz`, `/agent/readyz`.
All authenticated with a bearer JWT signed with the key shared via Vault.
