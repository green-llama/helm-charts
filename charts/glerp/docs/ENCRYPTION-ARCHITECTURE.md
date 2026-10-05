# Encryption Architecture (engineering)

How GLerp encrypts data at rest, how the chart automates it, and how to operate/troubleshoot it.
For the auditor-facing control summary and the per-site attestation table, see
[`DATA-ENCRYPTION.md`](DATA-ENCRYPTION.md).

There are two independent at-rest mechanisms, owned by different layers:

| Data plane | Mechanism | Owned by |
|---|---|---|
| MinIO object storage (customer files) | SSE-KMS via KES + Vault | **the chart** (templates + activate hook) |
| MariaDB DB + shared assets | Longhorn LUKS/dm-crypt volumes | **the cluster** (chart only *references* the encrypted StorageClasses) |

---

## 0. Image supply chain — all MinIO images self-owned in GHCR (2026-10)

**Context:** MinIO Inc. withdrew the community container images — `docker.io/minio/*` was deleted
(~2026-09-12) and `quay.io/minio/{minio,mc}` went `401`/gone (~2026-09-22). Community MinIO itself is
archived/unmaintained. Any fresh pull (new install, node reschedule, image GC) of a `minio/*` image
now fails `ImagePullBackOff`.

**Principle adopted:** the chart depends on **no registry or prebuilt artifact outside our control.**
Every MinIO image is published to `ghcr.io/green-llama/*`, **multi-arch, public (anonymous pull — no
imagePullSecret), and pinned BY DIGEST** in the chart. They are produced by the
`.github/workflows/mirror-minio-images.yml` workflow (`workflow_dispatch` + monthly refresh):

| Image | Source | Build method | Chart field (default) |
|---|---|---|---|
| **KES** | `github.com/minio/kes` @ `2025-03-12T09-35-18Z` (AGPLv3) | **built from source** (`build/kes/Dockerfile`, `go build ./cmd/kes`, ubi-micro runtime) | `tenant.minio.kes.image` |
| **mc** (activate-hook `fetch-mc`) | `github.com/pgsty/mc` @ `RELEASE.2026-09-16T00-00-00Z` (AGPLv3; upstream `minio/mc` is archived) | **built from source** (`build/mc/Dockerfile`, **busybox runtime** — see note) | `tenant.minio.kes.activateImage` |
| **MinIO server** | `docker.io/pgsty/minio` (silo fork) @ `RELEASE.2026-08-04T00-00-00Z` (AGPLv3) | **mirrored** (crane) | `tenant.minio.image` → `Tenant.spec.image` |

Notes:
- **mc MUST have a shell.** The `fetch-mc` init container stages the static `mc` binary with
  `sh -c "cp /usr/bin/mc /mcbin/mc && chmod ..."`. pgsty/mc's own Dockerfile finishes on `scratch`
  (no `/bin/sh`) → the init container crashes with `exec: "/bin/sh": no such file or directory`.
  `build/mc/Dockerfile` therefore finishes on **busybox** (provides `/bin/sh` + `cp` + `chmod`) with
  `mc` at `/usr/bin/mc`, matching the contract the old `docker.io/minio/mc` satisfied.
- **MinIO server = the pgsty/silo community fork**, not upstream MinIO. silo keeps the `minio`
  binary, `MINIO_*` env, and `/minio/health/*` routes, so **the KES+Vault SSE-KMS design is
  unchanged** (verified end-to-end on the `backuptest` dev tenant: identity patch → KES/MinIO reauth
  → `Encryption ✔ / Decryption ✔` → existing attachments decrypt and serve). The chart now pins the
  server via `Tenant.spec.image` (`tenant.minio.image`); previously this was unset and the MinIO
  Operator injected its own default (now the dead upstream image).
- **Bump procedure:** edit the pinned tag in `mirror-minio-images.yml`, run the workflow, copy the
  reported `@sha256` digests into `values.yaml` (and the template defaults), commit. Never use a
  moving tag without a digest.

**Deferred strategic item:** silo is a community fork of the archived MinIO CE. The
maintained-vs-migrate decision (stay on silo / MinIO AIStor (commercial) / migrate to another S3
store) remains open; the GHCR digest pins are the durable stopgap that de-risk the registry
withdrawal and buy time to decide deliberately.

---

## 1. MinIO object storage — SSE-KMS via KES + Vault

### 1.1 Components

- **MinIO Tenant** (MinIO Operator, `templates/tenant/minio-tenant.yaml`), with a **KES sidecar**
  (`spec.kes`). Gated on `tenant.minio.kes.enabled` (default `true`).
- **KES** is a Vault **KV v2** client (NOT Vault Transit). It stores/retrieves the KMS root key in
  Vault over its own Kubernetes-auth JWT — the root key never lands in a Kubernetes Secret.
- **Vault** (KV v2) is the authoritative key store. Per-tenant key `<namespace>-minio-key` at
  `secret/<namespace>/minio-kes/root-key/…`.

### 1.2 Key design decisions

- **KV v2, not Transit.** KES's `keystore.vault` uses `engine: "secret"`, `version: "v2"`,
  `prefix: "<ns>/minio-kes/root-key"`. Transit produces 404 "unsupported path".
- **`requestAutoCert: false`.** The S3 API stays plain HTTP on `:80` so `dfp_external_storage`
  (`endpoint:80 / secure=0`) works unchanged. The MinIO↔KES leg still uses the operator-issued
  client/KES certs; only KES's Vault hop rides the service mesh (mTLS). Flipping `requestAutoCert`
  to `true` switches the S3 Service to `:443` and breaks DFP uploads — do not do it.
- **One shared Vault auth role, per-tenant key paths.** The k8s-auth role `glerp-minio-kes` is
  created **once per cluster**; its policy wildcards the namespace path segment, so no per-install
  Vault commands are needed. Residual: a KES pod could, with its own credential, reach another
  namespace's key path — accepted; tighter isolation needs Vault Enterprise templated ACLs. See
  TENANT.md "Key scoping across namespaces."
- **Client-cert identity.** KES authorizes MinIO by the SHA-256 of the DER public key of the MinIO
  Operator's client cert — the Opaque secret `<ns>-minio-tenant-client-tls`, key `public.crt`
  (NOT a `kubernetes.io/tls` secret, NOT `tls.crt`). The activate hook resolves this and patches it
  into `kes-config-secret`'s `policy.minio.identities`.

### 1.3 The activate hook — delayed one-shot

`templates/tenant/job-minio-kes-activate.yaml` is a `post-install,post-upgrade` Helm hook that turns
"Tenant created" into "encryption actually working", with no manual steps. It runs as the tenant KES
ServiceAccount (RBAC in `minio-kes-rbac.yaml`: get/list/patch secrets + get/list/delete pods, this
namespace only). One container (the glerp image: python3/openssl/curl) with the static `mc` binary
copied in by an initContainer from our GHCR mc image (`ghcr.io/green-llama/mc`, busybox-based so the
`sh -c cp` works — see §0). Runs `python3 -u` (unbuffered) so `kubectl logs` shows live progress.

Sequence:

1. **Resolve identity & patch** `kes-config-secret.policy.minio.identities` with
   `sha256(DER pubkey)` of `<ns>-minio-tenant-client-tls/public.crt`.
2. **Wait for Ready _and_ stable** — all KES and MinIO pods Running+Ready and crash-loop-free for a
   quiet window (`STABLE_QUIET`, default 45s), up to `SETTLE_TIMEOUT` (600s).
3. **Rolling-bounce KES** (one replica at a time, waiting each back Ready — the KES Service never
   loses all endpoints) so KES re-authenticates to Vault now that the cluster is settled.
4. **Rolling-bounce MinIO** (same, one pod at a time) so MinIO **re-initializes its IAM subsystem**
   against the now-healthy KMS — see the root-cause note below.
5. **Activate** (idempotent, patient — `ACTIVATE_ATTEMPTS`, default 12): `mc admin kms key create`
   then `mc encrypt set sse-kms` on the tenant bucket.

Pod selectors: KES pods carry `v1.min.io/kes=<tenant>-kes`; pool (MinIO) pods carry
`v1.min.io/tenant=<tenant>`. (They are labeled differently — selecting the wrong one returns zero
pods.) Tunables: `SETTLE_SECONDS`, `STABLE_QUIET`, `SETTLE_TIMEOUT`, `ACTIVATE_ATTEMPTS`.

### 1.4 Fresh-install root cause (why steps 3–4 exist)

On a brand-new tenant there is a KMS cold-start race:

- MinIO boots and initializes its **IAM subsystem**, which needs KMS.
- KES is pod-Ready but its **Vault keystore session isn't usable yet** (cold-start), so KMS calls
  fail. MinIO's IAM ends up **partially initialized** — its log shows
  `IAM sub-system is partially initialized, unable to write the IAM format: insufficient
  permissions to perform KMS operation`.
- In that state MinIO rejects `mc encrypt set` with the **misleading** error
  `SetEncryption is not supported for filesystem` **even though the backend is Erasure-coded**.

Bouncing **KES** fixes the Vault session, but MinIO does **not** re-run IAM init on its own — so the
hook must **also** bounce MinIO (step 4). Before this was understood, activation only succeeded when
MinIO happened to recover minutes later (hence "it works when I retry it by hand"). The delayed
one-shot (wait until settled → bounce KES → bounce MinIO → activate once, patiently) is the reliable
fix — a tight retry/bounce loop is worse, because it resets KES's settle clock and, if it deletes
both KES replicas at once, opens a DNS/endpoint gap (`no such host`).

**Dead ends ruled out** (recorded so they aren't re-investigated): it is NOT an Istio sidecar (the
`sidecar` container on MinIO pods is `minio/operator-sidecar`, the operator's own; there is no
istio-proxy and mesh injection is off); NOT the `MINIO_KMS_SECRET_KEY_FILE=kms_master_key` env (a
harmless MinIO-Operator default present on working sites too); NOT a DirectPV space/threshold issue
(the `filesystem` error is the IAM/KMS race, not storage capacity). Every config artifact on a
failing fresh tenant was byte-identical to a working production site.

### 1.5 Not retroactive — backfill

SSE-KMS encrypts objects written after enablement. Enabling it does not change any object's S3
key/path. Backfill pre-existing plaintext objects in place with `mc cp --recursive <alias>/<bucket>/
<alias>/<bucket>/`, scheduled per site (I/O-bound; use a maintenance window for large/live sites).

## 2. MariaDB DB + shared assets — Longhorn LUKS

The chart provisions the MariaDB volume (`data-glerp-mariadb-sts-0`) on StorageClass
`longhorn-crypto-mariadb-rwo` and the shared-assets RWX volume (`glerp`) on `longhorn-crypto-rwm`.
Both classes are Longhorn (`driver.longhorn.io`) with `encrypted: "true"`, `fsType: ext4`,
`numberOfReplicas: 2`. Longhorn encrypts each volume with LUKS/dm-crypt; the CSI driver unlocks it
at mount time using the passphrase in the cluster Secret `longhorn-crypto` (`longhorn-system`, key
`CRYPTO_KEY_VALUE`), referenced via the classes' node-stage/node-publish secret parameters.

This is **cluster infrastructure**, not chart-owned: the `longhorn-crypto` Secret and the
`longhorn-crypto-*` StorageClasses must exist before installing a tenant. The chart's only
responsibility is to **reference the encrypted classes** for these workloads (never an unencrypted
class).

## 3. Cluster prerequisites (one-time, not created by the chart)

- **Vault** policy + Kubernetes-auth role `glerp-minio-kes` (shared; policy wildcards the namespace
  path segment). See TENANT.md §3b.
- **`longhorn-crypto`** Secret in `longhorn-system` + the `longhorn-crypto-*` StorageClasses.
- Platform: DirectPV (MinIO drives), the MinIO Operator, Vault, External Secrets Operator, Traefik.

## 4. Troubleshooting

Verify first (from a MinIO pod, container `minio`; creds in `<ns>-minio-creds`):
`mc alias set l http://localhost:9000 <ak> <sk>` then `mc admin kms key status l` → expect
`Encryption ✔ / Decryption ✔`.

- **`insufficient permissions to perform KMS operation` / `SetEncryption is not supported for
  filesystem` on a fresh tenant** → the KMS cold-start race (§1.4). The activate hook handles it by
  bouncing KES then MinIO once the cluster is settled. If it still shows `✗` after the Job runs
  (e.g. a very slow-settling cluster), bounce the KES pods, then the MinIO pool pods, once the
  cluster is quiet, and re-run the hook. Confirm the Vault side with:
  `vault read auth/kubernetes/role/glerp-minio-kes` (should list the `glerp-minio-kes` policy);
  prove the write path with `vault write auth/kubernetes/login role=glerp-minio-kes
  jwt=$(kubectl -n <ns> create token <ns>-minio-tenant-kes)` then
  `vault kv put secret/<ns>/minio-kes/root-key/probe x=1`.
- **No KES pods / Tenant stuck at `Initialized`** → the MinIO Operator isn't reconciling `spec.kes`
  (often a stale operator). Fix once per cluster: `kubectl -n minio-operator rollout restart
  deploy/minio-operator`; within ~2 min it issues the KES certs and starts KES pods.
- **`MinIO … invalid hostname` / crash-loop at boot** → a malformed `domain` value (e.g. a comma
  typo) rendered into `MINIO_BROWSER_REDIRECT_URL`. The chart now fails fast on this at
  `helm install`; fix the `domain` value.
- **DirectPV `no drive found for requested topology; requested size …`** → the requested
  `tenant.minio.volumeSize` exceeds the DirectPV drives' free space (check
  `kubectl directpv list drives`). Not a chart bug — set a sane `volumeSize`.
- **`ImagePullBackOff` on a `minio/*` image (`repository does not exist` / `insufficient_scope`)**
  → an image still points at the withdrawn Docker Hub / quay `minio/*` repos. All MinIO images must
  come from `ghcr.io/green-llama/*` pinned by digest (§0). Upgrade to a chart version that carries
  the GHCR pins; if overriding, use the GHCR refs.
- **`fetch-mc` init container `exec: "/bin/sh": no such file or directory`** → the mc image lacks a
  shell (a `scratch`-based build). The activate hook needs a shell to copy the binary; use the
  busybox-based `ghcr.io/green-llama/mc` (§0).
- **Existing attachments 404 in GLerp after an upgrade, but the objects exist in MinIO** → not data
  loss and not a DFP/key problem. It is the KMS decrypt path failing: after an upgrade rolls the KES
  pods, `kes-config-secret`'s `policy.minio.identities` can be reset to `_pending_` and must be
  re-patched to the client-cert hash (the activate hook does this). Symptom: `mc stat` succeeds but
  `mc get`/read fails with `kms:NotAuthorized / insufficient permissions to perform KMS operation`,
  and `mc admin kms key status` shows `Encryption ✗`. Re-run the activate hook (re-run the helm
  upgrade) so it re-patches the identity and reauths KES+MinIO. DFP keys, object names, and the
  `{site}/{base}-{name}.ext` naming are unchanged — no per-site datafill or URL rewrites needed.
