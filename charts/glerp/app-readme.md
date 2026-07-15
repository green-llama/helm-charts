# GLerp — ERPNext v16 + Green Llama custom apps

A single Helm chart that stands up (and upgrades) a complete GLerp site: stock
Frappe/ERPNext v16 plus the Green Llama custom apps, backed by an in-cluster
database and cache — no external Redis or Bitnami images required.

## Quick start — the two things you usually set

**1. Site name (required).** The chart does **not** derive the site name from the
namespace. Set it before installing:

```yaml
siteName: acme.dev.greenllama.tech
```

**2. Apps (optional).** By **default every app baked into the image is installed**,
so the site always matches the image and there is nothing to maintain. To install
only a curated subset, set an explicit list instead:

```yaml
jobs:
  createSite:
    installApps:
      - erpnext
      - glerp_ai_intake
      - glerp_branding
```

That's usually all you need. Everything else has working defaults.

## What runs by default

| Component | Default | Notes |
|---|---|---|
| Database | In-cluster MariaDB StatefulSet | Official `mariadb` image (no Bitnami) |
| Cache & queue | **Valkey** | Open-source Redis fork, Frappe-16 RESP3 compatible. DragonflyDB is opt-in; Bitnami Redis was removed (now paywalled) |
| Site provisioning | Automatic | A create-site job creates the site, installs the apps, and runs `bench migrate` |

## Install and upgrade are the same action

The create-site job is **idempotent**:

- **New namespace** → creates the site, installs apps, migrates.
- **Existing site** → never recreates it. Installs only the apps that are new in
  the newer image, runs `bench migrate`, and **retains all existing data.**

To upgrade a running site, just select a newer chart version and click **Upgrade**
(the site name and your values carry over).

## Tenant mode (production)

Set `tenant.enabled=true` to also manage the per-tenant infrastructure (Traefik
IngressRoute, cert-manager Certificate, ESO/Vault secrets, MinIO, Velero backups).
This requires cluster prerequisites (a Vault policy/role and the `vault-pushwriter`
store) — see **TENANT.md** in the chart before enabling it. Leave it `false` for
simple/dev installs.

## Documentation

- **README.md** (this chart) — full values reference and configuration.
- **TENANT.md** (this chart) — production tenant setup and prerequisites.
- **FRAPPE_CUSTOM_APP_DEVELOPMENT_GUIDE.md** in
  [`green-llama/glerp_development_standards`](https://github.com/green-llama/glerp_development_standards)
  — how the image/chart pipeline works and how to release a new app version.
