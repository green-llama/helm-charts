# GLerp chart changelog

Notable changes to the `glerp` Helm chart. Chart versions are published automatically by the
`green-llama/glerp-image` pipeline; this file records the meaningful functional changes.

## MinIO encryption at rest (KES + Vault) — final architecture (through chart 1.0.80)

**Encryption at rest for MinIO object storage** (per-tenant user file store) via MinIO KES +
HashiCorp Vault (SSE-KMS, AES-256-GCM). On by default in tenant mode
(`tenant.minio.kes.enabled: true`). Verified in production across GLerp tenant sites and on a clean
fresh install. Full detail: [`docs/DATA-ENCRYPTION.md`](docs/DATA-ENCRYPTION.md) (auditor) and
[`docs/ENCRYPTION-ARCHITECTURE.md`](docs/ENCRYPTION-ARCHITECTURE.md) (engineering).

**Architecture**
- A **KES sidecar** on the MinIO Tenant (replacing the earlier abandoned MinIO-direct-to-Vault KMS
  env). KES is a Vault **KV v2** client (not Transit); the KMS **root key never lands in a K8s
  Secret**. One key per tenant: `<namespace>-minio-key` at `secret/<namespace>/minio-kes/root-key/…`.
- **Shared Vault k8s-auth role** `glerp-minio-kes` (one-time per cluster; policy wildcards the
  namespace path segment) — no per-install Vault commands.
- `requestAutoCert: false` kept — the S3 API stays plain HTTP so `dfp_external_storage` is unchanged;
  only KES's Vault hop uses the service mesh / mTLS.
- KES authorizes MinIO by `sha256(DER pubkey)` of the operator's client cert — the **Opaque** secret
  `<ns>-minio-tenant-client-tls`, key `public.crt` (not a `kubernetes.io/tls` secret / `tls.crt`).
- Templates: `minio-tenant.yaml` (`spec.kes`), `minio-kes-sa.yaml`, `minio-kes-config.yaml`,
  `minio-kes-rbac.yaml`, `job-minio-kes-activate.yaml` (post-install/upgrade hook).

**The activate hook — delayed one-shot (hands-off, no manual steps).** Runs `python3 -u`
(unbuffered logs). In order: (1) resolve the client-cert identity and patch
`kes-config-secret.policy.minio.identities`; (2) wait for KES **and** MinIO pods to be Ready **and**
stable (crash-loop-free for a quiet window); (3) **rolling-bounce KES** (one replica at a time, so
its Service never loses all endpoints) to force a clean Vault re-auth; (4) **rolling-bounce MinIO**
so it re-initializes its IAM subsystem against the now-healthy KMS; (5) **activate** — create the
KMS key (idempotent) and enable bucket SSE-KMS, retried patiently (`ACTIVATE_ATTEMPTS`, default 12).
Tunables: `SETTLE_SECONDS` / `STABLE_QUIET` / `SETTLE_TIMEOUT` / `ACTIVATE_ATTEMPTS`.

**Fresh-install root cause (why the hook bounces both KES and MinIO):** a KMS cold-start race — on a
new tenant MinIO initializes IAM (which needs KMS) before KES's Vault session is usable, leaving
IAM partially initialized; MinIO then rejects `mc encrypt set` with the misleading
`SetEncryption is not supported for filesystem` (the backend is Erasure). Bouncing KES fixes the
Vault session; bouncing MinIO makes it re-init IAM against the healthy KMS. See
`docs/ENCRYPTION-ARCHITECTURE.md` §1.4, which also records the ruled-out dead ends (it is **not**
Istio, **not** the `MINIO_KMS_SECRET_KEY_FILE=kms_master_key` operator default, **not** a DirectPV
space/threshold issue).

**Also in this line of work:**
- MinIO **pool (data-plane) pods** carry `sidecar.istio.io/inject: "false"` — defensive, keeps the
  S3 data path out of any service mesh (matches prod); a no-op where injection is already off.
- `domain` is **validated at render time** — a malformed value (comma/space/underscore, e.g. a
  `dev,greenllama.tech` typo) now fails fast at `helm install` instead of crash-looping MinIO on a
  bad `MINIO_BROWSER_REDIRECT_URL`.

**Operational note:** if a fresh tenant sits at `Initialized` with no KES pods, the MinIO Operator
isn't reconciling `spec.kes` (often a stale operator) — one-time
`kubectl -n minio-operator rollout restart deploy/minio-operator` re-reconciles all tenants and
issues the KES certs. See TENANT.md §3c.

**Not retroactive:** enabling SSE-KMS encrypts only *new* writes; backfill pre-existing objects with
`mc cp --recursive` (TENANT.md). **Deferred:** per-tenant Vault policy/role (tighter cross-namespace
isolation) — needs Vault Enterprise templated ACLs or a CE per-tenant provisioner; the shared-role
model is in production (TENANT.md "Key scoping across namespaces").

## Earlier

For changes before the encryption work (Rancher install form, revisionHistoryLimit + job TTL,
idempotent data-safe create-site, dependency-ordered app install, chart README rewrite, etc.)
see the `green-llama/glerp-image` git history.
