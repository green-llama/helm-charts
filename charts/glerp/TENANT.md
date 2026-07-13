# Provisioning a GLerp tenant with the chart

Set `tenant.enabled=true` to make the chart manage the full per-tenant footprint that used to
be applied by hand (see the historical `helm-charts/docs/glerpSiteInstallTemplate`). One
tenant per namespace; the **release namespace is the tenant name**.

## What the chart creates (when `tenant.enabled=true`)

Gated by `tenant.enabled` and per-object sub-toggles (all default ON except the ZAP label):

| Object | Template | Toggle |
|---|---|---|
| ServiceAccount `<ns>-sa` + `secret-reader` Role/RoleBinding | `serviceaccount.yaml`, `rbac-secret-reader.yaml` | `serviceAccount.create`, `rbac.secretReader.enabled` |
| Traefik IngressRoute → glerp (`<ns>.<domain>`) | `tenant/ingressroute-app.yaml` | `tenant.ingressRoute.enabled` |
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
