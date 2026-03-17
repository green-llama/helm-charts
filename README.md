# green-llama Helm Charts

Centralized Helm chart repository for all `glerp-ai-*` services.

## Add this repository in Rancher or Helm

**Rancher UI:** Apps → Repositories → Create
- Name: `green-llama`
- Index URL: `https://green-llama.github.io/helm-charts/`

**Helm CLI:**
```bash
helm repo add green-llama https://green-llama.github.io/helm-charts/
helm repo update
helm search repo green-llama
```

## Available Charts

| Chart | Description | Source Repo |
|---|---|---|
| `k8-glerp-ai-intake` | Document intelligence service — OCR + LLM extraction for ERPNext | [k8-glerp-ai-intake](https://github.com/green-llama/k8-glerp-ai-intake) |

> Future charts (`glerp-ai-architect`, `glerp-ai-copilot`, `glerp-ai-insights`, `glerp-ai-project-assistant`) will appear here as they are released.

## Install a Chart

```bash
# Install intake service
helm install glerp-ai-intake green-llama/k8-glerp-ai-intake \
  -n glerp-ai-intake \
  --create-namespace \
  --set config.APP_ENV=production \
  --set ingress.host=glerp-ai-intake.yourdomain.com \
  --set image.tag=0.3.0
```

Or override values:
```bash
helm install glerp-ai-intake green-llama/k8-glerp-ai-intake \
  -n glerp-ai-intake \
  -f values-prod.yaml
```

## How This Repository Works

Charts live in the `charts/` directory of this repository. When a change is pushed to `main`, the GitHub Actions workflow:

1. Detects which charts have a new version in `Chart.yaml`
2. Packages each changed chart into a `.tgz` release artifact
3. Creates a GitHub Release tagged `<chart-name>-<version>` with the artifact attached
4. Regenerates `index.yaml` on the `gh-pages` branch pointing to all release assets

The `gh-pages` branch is what Helm and Rancher read. The `index.yaml` there indexes every chart version ever released, so older versions remain installable.

## Adding a New Chart

1. Create `charts/<chart-name>/` in this repo (copy an existing chart as template)
2. Ensure `Chart.yaml` has `name`, `version`, and `appVersion` set correctly
3. Commit to `main` — the release workflow handles the rest

## Updating an Existing Chart

Bump `version` in `charts/<chart-name>/Chart.yaml`, commit to `main`. The workflow detects the version change and publishes a new release. Previous versions are never removed.

## Required GitHub Setup (one-time)

1. **Enable GitHub Pages:** Repository Settings → Pages → Source: `gh-pages` branch, `/ (root)` directory
2. **Workflow permissions:** Repository Settings → Actions → General → Workflow permissions → "Read and write permissions" ✓
3. **Add `HELM_CHARTS_TOKEN` secret to each service repo** (PAT with `repo` scope for `green-llama/helm-charts`) — used by service repos to sync chart changes here automatically
