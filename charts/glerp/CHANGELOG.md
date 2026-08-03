# GLerp chart changelog

Notable changes to the `glerp` Helm chart. Chart versions are published automatically by the
`green-llama/glerp-image` pipeline; this file records the meaningful functional changes.

## MinIO KES on Istio-meshed clusters — keep the sidecar off the data plane

**Fix:** the MinIO **pool (data-plane) pods** now carry `sidecar.istio.io/inject: "false"`, so no
Envoy sidecar is injected onto them. On clusters where sidecar injection is on by default (our dev
cluster), an injected Envoy intercepted MinIO's **outbound** call to KES on `:7373` and
re-originated the TLS **without MinIO's client certificate**. KES requires mTLS client auth and
rejected it (`tls: client didn't provide a certificate`), which surfaced to `mc` as the generic
`insufficient permissions to perform KMS operation` — encryption silently never activated on a
fresh install. The **KES pod itself stays meshed** (`.spec.kes.labels sidecar.istio.io/inject:
"true"` + `excludeInboundPorts: 7373`) so its Vault hop is still protected; only the
high-throughput S3 data path is kept out of the mesh — matching production and avoiding Envoy
latency/overhead on object I/O.

This was the true root cause of the fresh-install "insufficient permissions" symptom (NOT a KES
Vault-keystore cold-start, as earlier suspected). All structural config — Vault policy/role, KES
client identity, cert CA chain, MinIO config/mounts — was correct throughout; the only broken leg
was the meshed MinIO→KES connection, which is why bouncing KES never helped.

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
