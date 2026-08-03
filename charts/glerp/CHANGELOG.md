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

## Activate hook — also bounce MinIO (real fix for the "filesystem" error)

**Root cause of the misleading `SetEncryption is not supported for filesystem` on a fresh install
(the backend is actually Erasure):** MinIO boots and initializes its **IAM subsystem**, which needs
KMS; but KES's Vault session isn't usable yet (cold-start), so MinIO's IAM stays **partially
initialized** (`unable to write the IAM format: insufficient permissions to perform KMS operation`
in the MinIO log). In that state MinIO rejects `mc encrypt set` with the bogus "filesystem" error.
Bouncing KES fixes the Vault session, but MinIO **does not re-run IAM init on its own** — so
activation only ever succeeded when MinIO happened to recover minutes later (which is why manual
retries "worked").

**Fix:** after the rolling KES bounce, the hook now **also rolling-bounces the MinIO pool pods**
(one at a time, no endpoint gap) so MinIO re-initializes IAM against the now-healthy KMS, then
activates. This is the step that makes fresh-install activation actually complete hands-off. (The
earlier "minimum free drive threshold" reading was wrong — drives had ample free space; the
"filesystem" error is the IAM/KMS init race, not a storage-space issue.)

## Activate hook — correct KES pod selector + patient final retry

- **KES pod selector fix:** the hook selected KES pods with `v1.min.io/tenant=<tenant>`, but the
  operator labels KES pods `v1.min.io/kes=<tenant>-kes` (only the *pool* pods carry
  `v1.min.io/tenant`). The wrong selector returned zero pods, so the Ready/stable waits timed out
  and the hook stalled. `tenant_pods()` now uses the correct label per kind.
- **Patient, idempotent final activation:** `mc admin kms key create` + `mc encrypt set` are both
  idempotent, so the final step now retries patiently (`ACTIVATE_ATTEMPTS`, default 12) rather than
  failing fast. This rides out a **transient** MinIO storage state seen on very small dev drives:
  a "minimum free drive threshold" that surfaces from `mc encrypt set` as the MISLEADING error
  `SetEncryption is not supported for filesystem` even when the backend is Erasure — it clears once
  the drives settle. The log now flags that error as transient. (Guidance: keep MinIO `volumeSize`
  comfortably above MinIO's reserved overhead — ~1Gi+ — to avoid this threshold on tiny drives.)

## Fresh-install KES activation — delayed one-shot (replaces the retry/bounce loop)

**Confirmed root cause of the fresh-install "insufficient permissions to perform KMS operation":**
on a brand-new tenant, KES is pod-Ready before its Vault keystore session is usable (cold-start),
AND MinIO itself crash-loops while its KMS init fails. Every other config artifact (Vault
policy/role, KES client-cert identity, cert CA chain, MinIO `config.env`, the
`MINIO_KMS_SECRET_KEY_FILE=kms_master_key` operator default) is byte-identical to a working
production site and is **not** the cause. A KES restart *after the cluster settles* fixes it.

The previous `job-minio-kes-activate` design retried in a tight loop and bounced KES repeatedly;
that **fought** the fresh-install dynamics — it reset KES's Vault-settle clock, and bouncing both
KES replicas at once opened a `no such host` / connection-refused gap. It did not reliably
self-heal. **Redesigned as a delayed one-shot:** the hook now (1) waits for the KES and MinIO pods
to be Ready *and* stable (past their crash-loop — no restart for a quiet window), (2) does **one
rolling KES bounce** (one replica at a time, so the KES Service never loses all endpoints) to force
a clean Vault re-auth now that the cluster is settled, then (3) does **one** clean activation
(create KMS key + enable bucket SSE-KMS), with only a few short retries to ride out DNS propagation
— not a bounce loop. Also runs Python **unbuffered** (`python3 -u` / `PYTHONUNBUFFERED=1`) so
`kubectl logs` shows live progress. Tunable via `SETTLE_SECONDS` / `STABLE_QUIET` /
`SETTLE_TIMEOUT`. If a fresh install still shows `Encryption ✗`, the TENANT.md §3c manual runbook
(one KES bounce once the cluster is quiet) still applies.

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
