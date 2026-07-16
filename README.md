# Green Llama Helm Charts

The centralized Helm chart repository for **all Green Llama applications** deployed on our
Rancher-managed RKE2 clusters. Any application Green Llama builds is packaged as a Helm chart
here, published to a single catalog, and installed from the Rancher **Apps → Charts** screen.

This repo is the one place a Green Llama chart lives once it is ready to ship. It is not tied to
any single application — as new Green Llama apps are created, their charts are added here.

## What this repo is for

- **One catalog for every Green Llama app.** Each application gets a chart under `charts/`; they
  are published together as the `green-llama` Helm repository.
- **Rancher / RKE2 native.** The catalog is registered in Rancher so operators install and upgrade
  our applications from the Rancher UI, with each chart's values exposed as a form.
- **Versioned and self-serve.** Every chart change is published as a versioned release, so
  operators can install a specific version or upgrade in place.

## Using the catalog

**In Rancher (normal path):** the `green-llama` repository is registered as a cluster/global
repo. Install or upgrade any chart from **Apps → Charts → green-llama**.

**With the Helm CLI:**

```bash
helm repo add green-llama https://green-llama.github.io/helm-charts/
helm repo update
helm search repo green-llama          # list the available charts + versions
helm install <release> green-llama/<chart> --namespace <ns> --create-namespace
```

Each chart carries its own `README.md` (and, where applicable, form questions and a
tenant/production guide) with the configuration specific to that application. Refer to the chart's
own documentation for its values and prerequisites.

## Repository layout

```
charts/            Published charts — one directory per Green Llama application.
                   Each has its own Chart.yaml, values.yaml, templates/, and README.
decommissioned/    Retired charts, kept for history only. NOT published to the catalog;
                   superseded by another chart (see each folder's README banner).
icons/             Per-chart SVG icons (referenced by each Chart.yaml `icon:` URL).
docs/              Cross-chart documentation.
.github/workflows/ Publishing automation (see below).
```

## How charts get published

Publishing is automated — you do not hand-edit the catalog index.

1. **Add or update a chart** under `charts/<chart>/` and merge to `main`
   (bump the chart `version:` in its `Chart.yaml` — chart-releaser will not re-publish an
   existing version).
2. **`Release Charts`** (`.github/workflows/release.yml`) runs on the push: chart-releaser
   packages each changed chart, creates a GitHub Release for it, and updates the Helm repo
   index on the `gh-pages` branch.
3. **GitHub Pages** serves that index at `https://green-llama.github.io/helm-charts/`, which is
   what Rancher and the Helm CLI read.
4. **`Prune old chart versions`** (`.github/workflows/prune-charts.yml`) then trims each chart to
   its newest N versions so the catalog's version list stays manageable.

> Some charts are built and synced here automatically by their source repo's pipeline rather than
> edited directly (their `charts/<chart>/` directory is generated). Check a chart's own README
> before hand-editing it — edit it at its source of truth if it has one.

### Adding a new Green Llama application

Create `charts/<app-name>/` with a standard Helm chart (`Chart.yaml`, `values.yaml`,
`templates/`, a chart `README.md`, and — for a good Rancher experience — a `questions.yaml`),
add an icon under `icons/<app-name>.svg` referenced from the chart's `icon:` field, and merge to
`main`. The automation above publishes it to the catalog.

### Retiring a chart

Move it from `charts/` to `decommissioned/` (so it is no longer published), add a short README
banner explaining what supersedes it, and remove its entry from the `gh-pages` `index.yaml`. Its
past GitHub Releases are kept as history.

## License

Internal use — Green Llama Technologies.
