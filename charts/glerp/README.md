# GLerp — ERPNext v16 + Green Llama custom apps

A single Helm chart that installs and upgrades a complete GLerp site: stock
Frappe/ERPNext v16 plus the Green Llama custom apps, from one container image
(`ghcr.io/green-llama/glerp-image`), backed by an in-cluster database and cache.
No external Redis, no Bitnami images, no NFS setup required.

---

## Quick start — the two settings you usually change

**1. Site name (required).** The chart does **not** derive it from the namespace.
Set the chart-level `siteName` (or `jobs.createSite.siteName`, which wins if both set):

```yaml
siteName: acme.dev.greenllama.tech
```

**2. Apps (optional).** By **default every app baked into the image is installed**
(ERPNext + all Green Llama custom apps), so the site always matches the image and
there is nothing to maintain. To install only a curated subset, set an explicit list:

```yaml
jobs:
  createSite:
    installApps:
      - erpnext
      - glerp_ai_intake
      - glerp_branding
```

Everything else has working defaults.

## Install and upgrade — the same command

The create-site job is **idempotent**, so install and upgrade are one action:

- **New namespace** → creates the site, installs the apps, runs `bench migrate`.
- **Existing site** → **never recreates it.** Installs only apps that are new in the
  newer image, runs `bench migrate`, and **retains all existing data.**

To roll a running site to a newer version, just pick the new chart version and click
**Upgrade** in Rancher (the site name and your values carry over), or:

```shell
helm upgrade --install glerp <chart> \
  --namespace <your-namespace> \
  --set siteName=acme.dev.greenllama.tech
# add --set tenant.enabled=true for a full production tenant (read TENANT.md first)
```

Watch it converge:

```shell
kubectl -n <your-namespace> get pods -w
kubectl -n <your-namespace> logs job/glerp-new-site -f
```

## Backends (defaults — nothing to configure)

| Component | Default | Notes |
|---|---|---|
| Database | In-cluster **MariaDB** StatefulSet (official `mariadb` image) | Encrypted Longhorn volume (`longhorn-crypto-mariadb-rwo`, 10Gi). Not a subchart. |
| Cache & queue | **Valkey** | Open-source Redis fork, Frappe-16 RESP3 compatible. The default — free and correct. |
| Shared config/sites | Longhorn RWX (`longhorn-crypto-rwm`, 2Gi) | bench config only; **user files go to MinIO**, so no NFS/large RWX volume is needed. |
| User file storage | Per-tenant **MinIO** (tenant mode) | DirectPV-backed; auto-wired to Frappe by the create-site job via `dfp_external_storage`. |

> **Cache/queue choice:** Valkey is the default and recommended backend. DragonflyDB is
> an **opt-in alternative** (`dragonfly-cache`/`dragonfly-queue`), but it does **not**
> support Frappe 16's RESP3 client-side cache invalidation, so `bench migrate` runs
> noticeably slower and it needs a `redis_wrapper` patch — prefer Valkey unless you have
> a specific reason. The Bitnami MariaDB/PostgreSQL/Redis subcharts were removed
> (Broadcom moved those images behind a paywall).

## Encryption at rest (MinIO object storage)

User file storage (the per-tenant MinIO object store, where `dfp_external_storage` puts
Frappe attachments) is **encrypted at rest with SSE-KMS**, enabled by default in tenant mode
(`tenant.minio.kes.enabled: true`). Design:

- **KES + HashiCorp Vault.** MinIO's KES (Key Encryption Service) sidecar holds the data keys;
  the KMS **root key never lands in a Kubernetes Secret** — KES stores/retrieves it directly in
  Vault (KV v2) over its own Kubernetes-auth JWT.
- **One encryption key per tenant.** Key name `<namespace>-minio-key`, stored at the per-tenant
  Vault path `secret/<namespace>/minio-kes/root-key/…`. Tenants do not share a key.
- **Automatic, no manual steps.** A post-install/upgrade hook resolves the MinIO↔KES cert
  identity, ensures the KMS key exists, and turns on bucket SSE-KMS — every new object write is
  encrypted from install onward.
- **`requestAutoCert: false`** by design — the S3 API stays plain HTTP internally (the trust
  boundary is Traefik→browser TLS + the single trusted cluster), so `dfp_external_storage` works
  unchanged. KES's own Vault hop is the one leg that gets mTLS via the service mesh.

Verify on a running tenant (from a MinIO pod, container `minio`):
`mc admin kms key status <alias>` → `Encryption ✔ / Decryption ✔`.

**One-time-per-cluster prerequisite:** the `glerp-minio-kes` Vault policy + Kubernetes-auth role
(shared by all tenants; the policy wildcards the namespace path segment). See
[TENANT.md](TENANT.md) §3b. **Not retroactive:** enabling SSE-KMS encrypts only *new* writes;
backfill pre-existing objects with `mc cp --recursive` (TENANT.md).

## Tenant mode (production)

Set `tenant.enabled=true` to also have the chart manage the per-tenant infrastructure:
Traefik IngressRoute, cert-manager Certificate, ESO/Vault secrets, MinIO Tenant, Velero
backups, and DFP external-storage auto-config.

Tenant mode consumes cluster-level resources it does **not** create — they must already
exist. Chiefly: ESO with a **`vault-pushwriter`** ClusterSecretStore (write-capable — the
default `vault-backend` reader is read-only and cannot seed the generated MariaDB/MinIO
creds), the **`glerp-minio-kes`** Vault policy + role (one-time per cluster, for MinIO
encryption-at-rest via KES), the per-tenant Vault policy/role, cert-manager, Traefik, the
MinIO operator + DirectPV, Velero, and the wildcard TLS secret. **Read [TENANT.md](TENANT.md)
for the exact one-time setup before enabling.** Leave `tenant.enabled=false` for isolated/dev
installs (e.g. `glerp-ci`) that lack these systems.

## Values you'll actually set

| Key | Default | Description |
|---|---|---|
| `siteName` | `""` | **Required.** Frappe site name, e.g. `acme.dev.greenllama.tech`. Not derived from the namespace. |
| `jobs.createSite.installApps` | `[]` | Empty = install **all** apps in the image. Set a list for a curated subset. |
| `jobs.createSite.adminPassword` | `changeit` | Administrator password (or use `jobs.createSite.adminExistingSecret`). |
| `image.tag` | managed | Image/app version. Managed by the release pipeline; override to pin. |
| `tenant.enabled` | `false` | Turn on per-tenant infra (see TENANT.md). |
| `valkey-cache.enabled` / `valkey-queue.enabled` | `true` | Default cache/queue backend. |
| `dragonfly-cache.enabled` / `dragonfly-queue.enabled` | `false` | Opt-in DragonflyDB (slower migrate; needs redis_wrapper patch). |
| `externalRedis.cache` / `externalRedis.queue` | `""` | Use an external Redis/Valkey instead of the in-chart backend. |
| `mariadb-sts.enabled` | `true` | In-cluster MariaDB. Set `dbHost`/`dbPort` to use an external DB instead. |

The site name and image tag are the two that matter for a normal install/upgrade;
the rest are defaulted for the Green Llama cluster.

## More documentation

- **[TENANT.md](TENANT.md)** — production tenant setup and cluster prerequisites.
- **FRAPPE_CUSTOM_APP_DEVELOPMENT_GUIDE.md** in
  [`green-llama/glerp_development_standards`](https://github.com/green-llama/glerp_development_standards)
  — how the image/chart pipeline works and how to release a new app version into GLerp.
