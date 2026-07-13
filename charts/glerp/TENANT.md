# Provisioning a GLerp tenant with the chart

Set `tenant.enabled=true` to make the chart manage the full per-tenant footprint that used to
be applied by hand (see the historical `helm-charts/docs/glerpSiteInstallTemplate`). One
tenant per namespace; the **release namespace is the tenant name**.

## What the chart creates (when `tenant.enabled=true`)

Gated by `tenant.enabled` and per-object sub-toggles (all default ON except the ZAP label):

| Object | Template | Toggle |
|---|---|---|
| ServiceAccount `<ns>-sa` + `secret-reader` Role/RoleBinding | `serviceaccount.yaml`, `rbac-secret-reader.yaml` | `serviceAccount.create`, `rbac.secretReader.enabled` |
| Traefik IngressRoute → glerp (`<ns>.<domain>`, in `traefik-system`) | `tenant/ingressroute-app.yaml` | `tenant.ingressRoute.enabled` |
| Traefik IngressRoute → MinIO console | `tenant/ingressroute-minio.yaml` | `tenant.minio.enabled` |
| cert-manager Certificate (leaf) | `tenant/certificate.yaml` | `tenant.certificate.enabled` |
| ESO ExternalSecrets: ca-trust, mariadb-root, minio-creds, ghcr-cred | `tenant/externalsecrets.yaml` | `tenant.externalSecrets.enabled` |
| ESO Password Generators + PushSecrets (seed Vault) | `tenant/vault-seed.yaml` | `tenant.vault.pushSecrets.enabled` |
| MinIO Tenant (Vault KMS, DirectPV) | `tenant/minio-tenant.yaml` | `tenant.minio.enabled` |
| Velero daily backup Schedule | `tenant/velero-schedule.yaml` | `tenant.velero.enabled` |
| Uptime-probe Service (labeled for glerp-monitoring) | `tenant/monitoring-probe-service.yaml` | `tenant.monitoringProbe.enabled` |

**Secret seeding is automated.** The ESO `Password` generators create the mariadb-root and
minio access/secret keys in-cluster and `PushSecret` writes them INTO Vault
(`updatePolicy: IfNotExist` — generated once, never overwritten on re-install/upgrade). The
ExternalSecrets then sync them back. **No more manual `openssl rand` in the vault pod.**

## Routing & TLS (IngressRoute)

The app IngressRoute is created in **`traefik-system`** (matching the established pattern) and
serves `https://<ns>.<domain>` using the cluster-wide wildcard TLS secret. Because it lives in
`traefik-system`, **install/upgrade must be run by an admin** (Rancher, or a cluster-admin
kubeconfig) — a namespace-scoped account cannot create it there.

Configurable under `tenant.ingressRoute`:

| Value | Default | Purpose |
|---|---|---|
| `enabled` | `true` | create the app IngressRoute |
| `traefikNamespace` | `traefik-system` | namespace the IngressRoute is created in |
| `entryPoints` | `[websecure]` | Traefik entrypoints |
| `tls.enabled` | `true` | serve TLS |
| `tls.secretName` | `""` → `tenant.tlsSecretName` (`letsencrypt-greenllama-tech-tls`) | per-route TLS secret override |
| `tls.options` | `{}` | merged verbatim into `spec.tls` (e.g. `certResolver`, `domains`) |
| `middlewares` | `[]` | Traefik middlewares (`[{name, namespace}]`) |
| `pathPrefix` | `/` | route `PathPrefix` |
| `matchExtra` | `""` | extra match appended with `&&` (e.g. `Headers(...)`) |
| `annotations` | `{}` | extra annotations on the IngressRoute |

The TLS secret is referenced by name only, so the wildcard `letsencrypt-greenllama-tech-tls`
must be present in `traefik-system` (it is cluster-wide/replicated in prod).

## File attachments → MinIO (DFP External Storage, automated)

`dfp_external_storage` is bundled in the image, and the create-site job (after migrate)
**auto-configures a `DFP External Storage` doc** so file attachments are stored in the
per-tenant MinIO bucket instead of the local volume. It is **idempotent** (upsert keyed by
title `minio-<ns>-attachments`) and runs on every install/upgrade.

Toggle: `tenant.dfp.enabled` (default **true**). It is skipped automatically if the
`dfp_external_storage` app or the `<ns>-minio-creds` secret is absent.

The generated doc uses (`<ns>` = release namespace):

| Field | Value |
|---|---|
| Title | `minio-<ns>-attachments` |
| Write enabled | ✓ |
| Type | S3 Compatible |
| host:port (endpoint) | `minio.<ns>.svc.cluster.local:80` |
| Secure | ✗ |
| Bucket name | `<ns>` |
| Region | `auto` |
| Access / Secret Key | from the `<ns>-minio-creds` secret (Vault-synced in prod) |
| Folder(s) | `Home/Attachments`, `Home` |
| Use presigned urls | ✗ |
| Doctypes ignored | `Data Import`, `Prepared Report` |

Because it's idempotent, editing the doc in the UI is safe until the next upgrade, which
re-asserts these values. To customise per-tenant, either disable `tenant.dfp.enabled` and
configure DFP by hand, or adjust the values in `templates/job-create-site.yaml`.

## External prerequisites (NOT done by the chart)

These require Vault-admin or cluster-admin and stay outside the chart:

### 1. Namespace (create first)
```bash
kubectl create namespace <tenant>
```
Deploy the release into it (`helm install <tenant> green-llama/glerp -n <tenant> ...`).

### 2. Vault policy + k8s-auth role for `<tenant>-app-role`
The chart's ExternalSecrets/PushSecrets and the app pods authenticate to Vault via this role.
Run once per tenant (this is what CI `deploy_image.yml` already does via AppRole; run manually
only if not using that CI path). In the Vault pod / with a Vault token:

```bash
TENANT=<tenant>
cat > /tmp/${TENANT}-policy.hcl <<EOF
path "secret/data/${TENANT}/minio-creds"                 { capabilities = ["read","create","update"] }
path "secret/data/${TENANT}/${TENANT}-mariadb-root"      { capabilities = ["read","create","update"] }
path "secret/metadata/${TENANT}/*"                       { capabilities = ["list"] }
path "auth/kubernetes/role/${TENANT}-app-role"           { capabilities = ["read"] }
path "secret/data/github/ghcr-cred"                      { capabilities = ["read"] }
EOF
vault policy write ${TENANT}-policy /tmp/${TENANT}-policy.hcl

vault write auth/kubernetes/role/${TENANT}-app-role \
  bound_service_account_names=${TENANT}-sa \
  bound_service_account_namespaces=${TENANT} \
  policies=${TENANT}-policy \
  audience="https://kubernetes.default.svc.cluster.local" \
  ttl=24h
```
> Note: the PushSecret path needs `create`/`update` on the tenant kv paths (so ESO can seed
> them); the older read-only policy in the v1.0.26 doc must be widened accordingly.

### 3. Shared cluster resources (one-time per cluster, already present in prod)
ESO ClusterSecretStores (`vault-backend`, `kubernetes-token-auth`), cert-manager
ClusterIssuer (`apps-general-signer`), Traefik, Velero + the `idrive-e2` BSL, the MinIO
operator + DirectPV, and the `letsencrypt-…-tls` secret. The chart consumes these; it does
not install them.

## Install

```bash
helm install <tenant> green-llama/glerp -n <tenant> \
  --set tenant.enabled=true \
  --set tenant.domain=<domain> \                 # e.g. dev.greenllama.tech
  --set tenant.externalDnsTarget=pec.<domain> \  # optional external-dns target
  --set siteName=<tenant>.<domain>
```
`mariadb-sts` is the default DB (official mariadb image, root password from the Vault-synced
`<tenant>-mariadb-root` secret). Cache/queue default to Valkey.

## Upgrades (idempotent, data-safe)

`helm upgrade` (or Rancher "Upgrade" to a newer chart version — e.g. after a new custom-app
release bumps `image.tag`) is safe on a running tenant:
- A `pre-upgrade` hook verifies the DB is reachable and **aborts the upgrade** if not.
- The create-site job detects the existing site and **never** recreates it or runs `--force`
  (even if `jobs.createSite.forceCreate=true` is set — it's refused on an existing site).
  It installs only apps not yet present, then runs `bench migrate`. **All customer data is
  retained.**

## ZAP scan label (opt-in, ONE site per cluster)

The `glerp.io/private-registry: "true"` namespace label (for the security ZAP scan) is only
wanted on the single scanned site per cluster (backuptest in dev, greenllama in prod), so it
is **not** applied by default. When you do want it, label the namespace directly:
```bash
kubectl label namespace <tenant> glerp.io/private-registry=true --overwrite
```
(`tenant.zapScanLabel.enabled` is reserved as documentation of intent; the label is applied
out-of-band because the chart does not own the namespace.)

## Dev/test without the tenant systems

For an isolated namespace that lacks Vault/cert-manager/MinIO (e.g. `glerp-ci`), set
`tenant.enabled=false` and use a chart-generated DB root secret — see
`values.glerp-ci-test.yaml`.
