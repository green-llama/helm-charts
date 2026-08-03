# GLerp chart changelog

Notable changes to the `glerp` Helm chart. Chart versions are published automatically by the
`green-llama/glerp-image` pipeline; this file records the meaningful functional changes.

## MinIO data-plane pods kept out of the service mesh (defensive)

The MinIO **pool (data-plane) pods** now carry `sidecar.istio.io/inject: "false"`. This is a
**defensive** label, not a bug fix: it keeps the high-throughput S3 object path out of the mesh
(mesh is reserved for sensitive traffic; avoids Envoy latency/overhead) and matches production,
where the MinIO pods run un-meshed. The KES pod stays meshed (`.spec.kes.labels`) so its Vault hop
is protected. On our clusters sidecar injection is already default-off, so this is a no-op there;
it exists to guarantee a cluster that default-enables injection can never wrap these pods in an
Envoy. (Note: the "sidecar" container present on every MinIO tenant pod is
`minio/operator-sidecar`, the operator's own config-reload sidecar — **not** Istio.)

## Fresh-install KES encryption activation — KES Vault-session cold-start

**Confirmed root cause of the fresh-install "insufficient permissions to perform KMS operation"
symptom:** on a brand-new tenant, KES can be pod-Ready while its Vault keystore session is not yet
usable, so MinIO's KMS calls fail. A **KES restart after the cluster has settled** re-establishes
the Vault session and encryption immediately works (`mc admin kms key status` →
`Encryption ✔ / Decryption ✔`; a written object shows `Encryption: SSE-KMS`). Every other config
artifact (Vault policy/role, KES client-cert identity, cert CA chain, MinIO `config.env`, the
`MINIO_KMS_SECRET_KEY_FILE=kms_master_key` operator default) is byte-identical to a working
production site and is **not** the cause. The `job-minio-kes-activate` hook already bounces KES and
retries the KMS op for exactly this reason; on a slow-settling fresh cluster it can exhaust its
retry budget before Vault settles — see the hook's `MAX_CYCLES`/`activateBackoffLimit` if a fresh
install still shows `Encryption ✗`, and re-run the hook (or bounce the KES pods) once the cluster
is quiet.

## MinIO encryption at rest (KES + Vault) — chart 1.0.66 → 1.0.71

Introduced and hardened **encryption at rest for MinIO object storage** (per-tenant user file
store) via MinIO KES + HashiCorp Vault (SSE-KMS). On by default in tenant mode
(`tenant.minio.kes.enabled: true`). Verified in production across all GLerp tenant sites.

**Architecture**
- Replaced the earlier (abandoned) MinIO-direct-to-Vault KMS env with a **KES sidecar** on the
  MinIO Tenant. KES is a Vault **KV v2** client; the KMS **root key never lands in a K8s Secret**.
- **One key per tenant:** key `<namespace>-minio-key`, stored at `secret/<namespace>/minio-kes/root-key/…`.
- **Shared Vault k8s-auth role** `glerp-minio-kes` (one-time per cluster; policy wildcards the
  namespace path segment). No per-install Vault commands.
- `requestAutoCert: false` kept — S3 API stays plain HTTP so `dfp_external_storage` is unchanged;
  only KES's Vault hop uses the service mesh / mTLS.
- New templates: `minio-kes-sa.yaml`, `minio-kes-config.yaml`, `minio-kes-rbac.yaml`,
  `job-minio-kes-activate.yaml` (post-install/upgrade hook). Old `MINIO_KMS_VAULT_*` env removed.

**The activate hook** (fully automated, no manual steps) now, in order: resolves the MinIO client
cert identity and patches KES's `policy.minio.identities`; **always bounces KES** so it
re-authenticates to Vault; waits for KES Ready; **creates the KMS key** (idempotent); enables
bucket SSE-KMS.

**Fixes made while rolling this out (each verified against a real prod site):**
- Target the operator's client cert deterministically: Opaque secret
  `<ns>-minio-tenant-client-tls`, key `public.crt` (not a `kubernetes.io/tls` secret / `tls.crt`).
- Create the KMS key explicitly — `mc encrypt set` does **not** create it.
- Always bounce + wait for KES so a stale Vault token doesn't cause "insufficient permissions."
- Removed all reliance on tools absent from the minimal `minio/mc` image (no `grep`/`sed`/`awk`);
  key readiness is verified via `mc admin kms key status`, not by parsing error text.

**Operational note (in TENANT.md §3c):** a long-running MinIO Operator can hold a stale cache and
stop reconciling tenants — a one-time `kubectl -n minio-operator rollout restart
deploy/minio-operator` re-reconciles all tenants and generates the KES certs. This was the sole
reason fresh cert generation didn't fire on some existing prod tenants; the chart config was
correct throughout.

**Deferred:** per-tenant Vault policy/role (tighter cross-namespace isolation) — requires Vault
Enterprise for the clean templated-ACL form, or the CE-compatible per-tenant provisioner hook
(design in `MINIO-KES-VAULT-PROVISIONER-HANDOFF.md`). Current shared-role model is in production;
see TENANT.md "Key scoping across namespaces."

## Earlier

For changes before the encryption work (Rancher install form, revisionHistoryLimit + job TTL,
idempotent data-safe create-site, dependency-ordered app install, chart README rewrite, etc.)
see the `green-llama/glerp-image` git history.
