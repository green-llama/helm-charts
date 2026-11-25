# GLerp chart changelog

Notable changes to the `glerp` Helm chart. Chart versions are published automatically by the
`green-llama/glerp-image` pipeline; this file records the meaningful functional changes.

## frappe_theme removed from the image; transition steps removed

Every site has uninstalled frappe_theme, so the 1.0.82 / 1.0.108 transition is over.

- Image: `glerp_frappe_theme` is gone from `apps.json`. glerp_branding is v2.0.1, which drops its
  one-time My Theme migration code.
- Image: glerp_fitness v0.15.6 (Feature access, own-logging choice, add-on end-date fix). Needs
  `bench migrate`; the migrate job runs it.
- Chart: `jobs.retiredApps` and the retire step in the new-site and migrate jobs are removed.
  Stored values that still set `jobs.retiredApps` are ignored.
- Kept, because they help with any future app change: the `sites/apps.txt` sync, the Redis app-cache
  clear, and skipping `installApps` entries whose code isn't in the image.

**Before upgrading:** frappe_theme must be uninstalled on the site
(`bench --site <site> uninstall-app frappe_theme --yes` on 1.0.108). A site, or a restored backup,
that still lists it will fail to migrate on this release.

## fix: migrate existing sites before installing new apps

Upgrading production sites from Frappe 16.26 to 16.60 (chart 1.0.108) failed in the new-site job
with `Table '...tabFlow Tool' doesn't exist` while installing insights. The job installed new apps
before migrating, so the new app's install ran against the old database schema. The job then
stopped before migrating, leaving 16.60 code on a 16.26 database.

- On an existing site, the new-site job now runs `bench migrate` first, then installs any new apps.
- It migrates a second time only if it installed something (to run their after_migrate hooks).
- New sites are unchanged: create, install apps, migrate once.

**Sites left un-migrated by 1.0.108:** in the gunicorn pod run `bench --site <site> migrate`, then
`bench --site <site> install-app insights`, then `bench --site <site> migrate` again.

## fix: keep sites/apps.txt in step with the image (adds back apps it had dropped)

Upgrading a site that had already been through chart 1.0.106/1.0.107 failed on 1.0.108 with
`Module Frappe Theme not found`. Those charts removed frappe_theme from `sites/apps.txt` while its
code was out of the image. When the code came back in 1.0.108, nothing re-added it, so Frappe still
treated the installed app as absent.

- The new-site and migrate jobs now make `sites/apps.txt` match the apps in the image before any
  bench command. They add shipped apps that are missing and remove entries whose code isn't in the
  image. Listing a shipped app that isn't installed on the site is harmless; the site's data and
  installed apps are untouched.

## Transition: frappe_theme's code is back in the image so sites can uninstall it cleanly

Removing frappe_theme's code (1.0.78) before existing sites had uninstalled it broke their
upgrades in four ways, one after another:
- `sites/apps.txt` still listed it;
- Frappe's cached app list in Redis still named it;
- Insights' install/migrate hooks import every app on the site's installed-apps list;
- 30 frappe_theme DocTypes stay in the database until the end of migrate. hrms's
  `rename_identification_document_type` patch updates Link fields on them, which imports
  frappe_theme ("Module Frappe Theme not found").

So this image ships **glerp_frappe_theme v1.0.2** again (098bda5), **only as a transition**:
- It is NOT in `installApps`, so new sites never install it; they start on glerp_branding's
  GLerp Theme.
- Existing sites keep working with it installed, then uninstall it the way that was tested.

**Per existing site (anything installed before image 1.0.78):**
1. Back up: `bench --site <site> backup --with-files`.
2. If the release stores its own `installApps`, remove `frappe_theme` and add `insights` after
   `hrms`.
3. Upgrade to this chart. migrate runs, including glerp_branding 2.0's import of My Theme into
   GLerp Theme.
4. `bench --site <site> uninstall-app frappe_theme --yes`. glerp_branding's before-uninstall hook
   copies My Theme again and moves its logo/background files first, so nothing is lost.
5. `bench --site <site> clear-cache`, restart the Frappe deployments, and check Desk → GLerp Theme.

frappe_theme comes out of the image in a later release, once every site has uninstalled it.

Also in this chart: `jobs.retiredApps` (default `[frappe_theme]`) is the safety net for that later
removal. Before installing apps or migrating, the jobs take each listed app off a site's
installed-apps list, but only once its code is no longer in the image. It does nothing while
frappe_theme is shipped. It edits the stored list directly, because
`bench remove-from-installed-apps` re-saves a record, and on a site not yet migrated to Frappe
16.60 that fails with "DocType Flow Trigger not found".

## fix: also clear Frappe's cached app list when upgrading a site that still lists frappe_theme

The previous fix cleaned `sites/apps.txt`, but upgraded sites still failed with
`No module named 'frappe_theme'`. Frappe also caches its app list (`all_apps`), the installed apps
and the loaded hooks in the Redis cache, and the copies from the old image still named
frappe_theme. `bench clear-cache` can't remove them, because it loads every app's hooks first and
crashes the same way.

- The new-site and migrate jobs now delete those cached keys from the Redis cache before running
  any bench command. The keys are `all_apps`, `installed_apps`, `app_hooks`, `app_modules`,
  `installed_app_modules`, `module_app`, `module_installed_app` and `scheduler_events`.
  - Frappe rebuilds them on demand.
  - Sessions and per-user caches are untouched.
  - The step never fails the job.

**After the upgrade jobs finish**, restart the Frappe deployments (gunicorn, scheduler, socketio,
workers), so no process keeps an old copy. Then retire frappe_theme on each site:
`bench --site <site> remove-from-installed-apps frappe_theme`, `bench --site <site> clear-cache`,
and restart web.

## fix: upgrading a site that still lists frappe_theme (removed from the image in 1.0.78)

Upgrading an existing site from chart ≤ 1.0.103 failed in the new-site job with
`ModuleNotFoundError: No module named 'frappe_theme'`. Frappe treats an app as present if it's in
`sites/apps.txt`, whether or not its code is in the image. The site's apps.txt still listed
frappe_theme, and the job also re-added any app from a stored `installApps` list. So every bench
command imported frappe_theme's hooks and crashed.

- The new-site and migrate jobs now remove `sites/apps.txt` entries whose code isn't in the image,
  before running any bench command. The site's data and its installed-apps list are unchanged.
  Frappe then skips the missing app, so `migrate` can run, including glerp_branding's import of the
  old My Theme settings into GLerp Theme.
- `installApps` entries that aren't in the image are skipped with a warning, rather than being
  added to apps.txt and installed.
- Fixed the "already installed" check. `bench list-apps` prints `<app> <version> <branch>`, so the
  old exact-line match never matched and every upgrade re-ran `install-app` on every app.

**If your release stores its own `installApps` list** (e.g. one that enables glerp_ai_agent), update
it: remove `frappe_theme` and add `insights` after `hrms`.

## glerp_fitness v0.15.5 + glerp_ai_agent v2.4.0; every frappe app pinned exactly

Same base as the previous release (Frappe 16.60.2, erpnext/hrms 16.60.0, Insights 3.50.3,
glerp_branding 2.0.0, frappe_theme removed).

- **glerp_fitness `v0.15.4 → v0.15.5`** (82ca53c): packages cover sessions by date (oldest package
  → earliest sessions); a session's Package is now set automatically; packages show
  item · hours · date; Benchmarks get full-width charts, period buttons and CSV; client page lists
  collapse to 3; the Add-ons list shows current ones only; iPhone home-screen tip; trainer activity
  fix.
- **glerp_ai_agent `v2.3.0 → v2.4.0`** (d81dac1): `allowed_roles` lets a trainer who also has a
  client login (or front desk who also trains) use suggested plans and voice notes (fixes "You can't
  use this AI task"); the AI button follows the secondary-button colour with no frappe_theme
  dependency (fixes the default colour on sites that uninstalled frappe_theme); speaker-labels
  switch, off everywhere. glerp_ai_core v2.2.0 and glerp_ai_intake v2.2.0 unchanged. Orchestrator
  floor ≥ 2.7.1.
- **Every frappe app is now pinned exactly — no more floating `version-16`.** payments
  `version-16 → v16.0.1` (its release tag; same code). newsletter, blog, eps, offsite_backups and
  webshop publish no release tags, so they're pinned by exact commit (apps.json `"commit"`, checked
  out by `scripts/checkout_commit_pins.py` right after `bench init`): newsletter 642986c,
  blog a88363c, eps 9ad8f3b, offsite_backups 4764d43, webshop 5d14c61 — the same code the previous
  image built from. CI now fails the build if any github.com/frappe/* app floats.

**Run `bench migrate` per site.** It adds the Package `title` field and runs patch
`glerp_fitness.patches.v0_15.packages_by_date`, which re-assigns each client's package hours by
session date. **Client balances don't change, but some sessions move to a different package** (on a
test site: 17 sessions across 8 clients).

**⚠️ Sites still on image 1.0.77 or earlier** (chart ≤ 1.0.103) must uninstall frappe_theme before
upgrading, exactly as for the previous release (see below).

## Frappe 16.60 framework jump + Insights + glerp_branding 2.0 (frappe_theme removed)

**⚠️ FRAMEWORK JUMP — test on non-critical sites first.** Bumps the Frappe framework and core apps
from the 16.26 line to **16.60**, adds Insights, and replaces AGPL `frappe_theme` with the proprietary
`glerp_branding` 2.0 "GLerp Theme".

- **Frappe `v16.26.1 → v16.60.2`** (build.yml FRAPPE_BRANCH). Needs Python 3.14 / Node 24 from the
  base image; adds litellm, onnxruntime, pyarrow, duckdb, frappe-flow, typst. Enables **Frappe Flow**
  (needed by glerp_fitness v0.15.4's personal-training Flow Skill).
- **erpnext `v16.26.2 → v16.60.0`**, **hrms `v16.54.1 → v16.60.0`** (hrms now ships two frontends:
  frontend/ + roster/). Migrate removes orphaned upstream DocTypes and reorganises workspaces/reports.
- **NEW: Insights `v3.50.3`** (d733108, AGPL-3.0) — installed by default on every site, **after hrms**
  (both erpnext and hrms ship Insights workbooks that must install first). Install order:
  frappe → erpnext → hrms → insights → payments → rest.
- **glerp_branding `v1.2.1 → v2.0.0`** (1622795) — proprietary "GLerp Theme" DocType; no longer
  requires frappe_theme.
- **frappe_theme REMOVED from the image entirely** (was `glerp_frappe_theme v1.0.1`, AGPL). Also
  removed from installApps.
- **glerp_fitness `v0.15.3 → v0.15.4`** (3f60f31): trainer "Insights" page → "Client review" at
  `/pt-review` (old `/pt-insights` redirects); new `skills/personal-training/SKILL.md` loads as a
  locked Frappe Flow Skill on Frappe ≥16.60 (inert without Flow set up). Migrate syncs pages, removes
  the old `/pt-insights` Web Page. No DocTypes/patches. Orchestrator floor ≥2.7.1 (unchanged).
- All other GLerp apps held at their 1.0.77 pins (glerp_ai_core v2.2.0, glerp_ai_agent v2.3.0,
  glerp_ai_intake v2.2.0, glerp_bigbulk_import main, etc.).

**⚠️ UPGRADE HAZARD — existing sites with frappe_theme installed:** removing frappe_theme's code from
the image breaks any site that still has the app installed. Per site, BEFORE/at upgrade: back up →
deploy's migrate runs glerp_branding's `v2_0.import_my_theme` (copies My Theme + attached files into
GLerp Theme) → `bench uninstall-app frappe_theme --yes` (branding's before_app_uninstall hook re-imports
first so logo/background files aren't lost) → `clear-cache` + restart web. GLerp Theme then switches on.
New sites are clean (frappe_theme never installed). Cosmetic note: glerp_ai_agent v2.3.0's AI button
falls back to its default color on sites without frappe_theme (fixed in the next agent release).

## glerp_fitness v0.15.3 (+ glerp_bigbulk_import S3 fix)

Bumps **glerp_fitness v0.15.2 → v0.15.3** (4d602ab). Other apps unchanged: glerp_ai_core v2.2.0,
glerp_ai_agent v2.3.0, glerp_ai_intake v2.2.0, hrms pinned v16.54.1, Frappe as-is.

**Also ships the glerp_bigbulk_import S3 fix** (merge 0c8d1df on `main`, which apps.json pins): prod
sites with S3 attachments (dfp_external_storage) no longer get "Cannot access file path" on Generate
Column Mappings / Preview / Import (now reads via `File.get_content()`); unmatched CSV columns are
skipped and listed instead of failing. Python only — no DocType/patch/migration changes in that app.
After deploy, verify on the prod BigBulk Import Profile with the S3 attachment PTBR_RB1.csv: Generate
Column Mappings should map columns with no file-path error.

glerp_fitness 0.15.3: "About the client" in plans (client-editable; trainer notes stay out of
clients' own plans); trainers get the full Exercise catalog; the session Plan card starts folded;
clients edit their usual week; voice status keeps updating after Stop on phones; add-ons that haven't
started say so; benchmark readings can be imported; new agreement wording for new sites.

**Run `bench migrate` per site.** It syncs DocType changes (new Client Profile fields, new defaults
in Personal Training Settings, Benchmark Reading `allow_import`). **No patches.**

**⚠️ Orchestrator floor:** the "About the client" plan feature needs **GLerp AI orchestrator ≥ 2.7.1**
(live in the RKE2 sandbox). With an older orchestrator the app still works, but plans ignore "About
the client" and may name the product. Orchestrator is deployed in its own lane — not gated by this
build.

## glerp_fitness v0.15.2 (review fixes)

Bumps **glerp_fitness v0.15.1 → v0.15.2** (0fd4fe2). Everything else is unchanged from 1.0.75:
glerp_ai_core v2.2.0, glerp_ai_agent v2.3.0, glerp_ai_intake v2.2.0, hrms pinned v16.54.1, Frappe
as-is (no floating upstream branches).

0.15.2 is review fixes only — **no patches, no DocType changes**, so `bench migrate` just syncs the
pages: a security fix for client saves, faster staff Insights, a self-coaching Home for clients who
never trained, and sign-in link timing. The sign-in link email now goes through the `short`
background queue, so the site's workers must be running (as they normally are).

Versions confirmed with the HB-PT and GLerp AI Agent sessions and against GitHub before building.

## Pin hrms to v16.54.1 (fix: migrate crash in 1.0.74)

**Fixes a `bench migrate` failure introduced in image 1.0.74 / chart 1.0.100.** hrms was pinned to
the rolling `version-16` branch, which advanced to **16.60.0** (released 2026-11-17 20:41 UTC, ~19 h
after the 1.0.73 build) and added patch `hrms.patches.v16_0.add_employee_profile_fields`. That patch
creates a custom field of type **"Vue Component"** — a field type that exists only in newer Frappe 16
(≥ 16.60.x). The Frappe framework baked into these images is older, so migrate aborted with
`ValidationError: Field Type cannot be "Vue Component"` in the hrms post-model-sync patches.

Fix: pin **hrms to tag v16.54.1** (a0103235) — the last release before the break; its `patches.txt`
does not contain `add_employee_profile_fields`. **Frappe is intentionally left where it is** — moving
it to 16.60.x would be a large unplanned framework jump for production. The four GLerp app tags are
unchanged (fitness v0.15.1, core v2.2.0, agent v2.3.0, intake v2.2.0); only hrms moves off the
floating branch to a fixed tag.

Re-run `bench migrate` on the fixed image: the doctype sync had already run, so migrate resumes at the
hrms patches and then runs the GLerp app patches (fitness `v0_15.*`, the AI-usage conversions). A site
left in maintenance mode by the failed run must have it cleared:
`bench --site <site> set-maintenance-mode off`.

## GLerp AI 2.2/2.3 + glerp_fitness v0.15.1 (shipped together)

Pins **glerp_ai_core v2.2.0** (5953774), **glerp_ai_agent v2.3.0** (798e651),
**glerp_ai_intake v2.2.0** (4189ca9) and **glerp_fitness v0.15.1** (f95a68d; 0.15.0 + one UI change,
same day). installApps unchanged (agent shipped-but-not-installed; fitness enabled per-site).

**⚠️ Release together — hard coupling:**
- Agent 2.3.0 and intake 2.2.0 require **glerp_ai_core ≥ 2.2**.
- Agent 2.3.0 requires **glerp_fitness ≥ 0.15.0 on the same site**: every trainer voice note and plan
  profile now requires the user agreement (the disclaimer flag), which only fitness ≥ 0.15.0 sends.
  With an older fitness, trainers' voice notes and plans are **refused**.

**Usage is in contexts, never dollars:**
- Core adds the **AI Usage** page (Settings → AI Usage) and a monthly context cap, default **33,000K**
  (GLerp AI Usage Settings, now owned by Core). Migrate converts the old $ budget to contexts, then
  deletes the $ budget and its change history; converts voice/task job costs to contexts and drops
  the agent's `cost_usd` column. The **GLerp AI Administrator** role goes to support@greenllama.tech.
- Intake stops at the cap: new documents go to **Needs Review** with a comment.

**Service floors:** usage reports need engine ≥ 2.3 and intake **service** ≥ 2.3 (an older service
shows "unavailable" on the page, never zero); clients' own voice notes and plans need
**orchestrator ≥ 2.4.1**. Client features are **Off** until a manager turns them on.

**Each site: `bench migrate`.** fitness runs patches `v0_15.own_workouts`, `v0_15.feature_trainers`
and `v0_15.agreements` and adds two DocTypes; the AI-usage conversions above run on the same migrate.
Nothing manual after migrate.

## glerp_fitness v0.14.0

Pins glerp_fitness **v0.14.0** (c95be6b). glerp_ai_agent stays **v2.2.0**; glerp_ai_core and
glerp_ai_intake stay **v2.1.0**. fitness 0.14.0 works with agent 2.2.0. installApps unchanged
(fitness enabled per-site; agent shipped-but-not-installed).

0.14.0 adds the one-list session editor, Wathan 1RM estimation (replacing Epley), volume charts,
the "voice notes / suggested plans" wording, the exercise-picker fix, equipment for trainers, and
the schedule Week view.

**Run `bench migrate` per site after upgrading.** Migrate:
- adds two hidden Workout fields (`voice_reviewed`, `voice_undo`);
- runs patch `glerp_fitness.patches.v0_14.wathan_estimates` — switches estimated-1RM benchmark types
  from Epley to Wathan, recalculates those readings and recomputes personal records (a few seconds
  on a dev site).

## host_name set to https://<site> on every site (fix)

Both the create-site and migrate-site jobs now ensure each site's `host_name` is set to
`https://<site>`. Behind TLS-terminating Traefik, Frappe's `frappe.utils.get_url()` otherwise falls
back to `http://<site>`, so backend callbacks, email links and print links come out as plain http.
This broke glerp_ai_agent voice notes: the agent syncs `get_url()` to the orchestrator as the site's
callback address, and the orchestrator hit a `ConnectTimeout` on port 80 fetching audio / posting
results (https on 443 answers in ~0.08 s).

- **New installs:** create-site sets `host_name` after app sync.
- **Existing sites:** back-filled at upgrade by the migrate job.
- **MERGE, not overwrite:** the value is set only when currently unset (checked by reading
  `site_config.json` directly, unambiguous across bench versions), so a site with a custom domain or
  port keeps its own `host_name`. Safe to re-run; idempotent.

To unblock a site immediately without waiting for this release:
`bench --site <site> set-config host_name "https://<site>"`.

## glerp_fitness v0.13.0 + glerp_ai_agent v2.2.0 (shipped together)

Pins glerp_fitness **v0.13.0** (1a805cb; rolls up 0.11.0 + 0.12.0 + 0.13.0) and glerp_ai_agent
**v2.2.0** (9a2ba60). glerp_ai_core and glerp_ai_intake stay at **v2.1.0**. installApps unchanged —
the agent stays shipped-but-not-installed; glerp_fitness is enabled per-site via installApps.

glerp_fitness 0.13.0: experimental workout tracking, voice notes, AI plans and the planning
profile — **all OFF by default** (a site looks unchanged until a manager switches them on). Adds new
DocTypes and 4 desk reports; patches `v0_13.workout_settings_defaults` and `v0_13.reports_data` seed
the new Single defaults / report data on existing sites. Workout tracking and reports work on their
own; the voice and AI features need glerp_ai_agent (shipped here) plus a GLerp AI backend service.

glerp_ai_agent 2.2.0 — version floors for its features (the agent requires glerp_ai_core ≥ 2.1,
already satisfied):
- Voice notes require **GLerp AI orchestrator ≥ 2.1.1**.
- AI workout suggestions require **orchestrator ≥ 2.2.1**.
- Production has no GLerp AI backend service yet, so on beltonparks the voice/AI features report
  "aren't available yet" — expected. Workout tracking and reports do not depend on them.
- Migrate adds the **GLerp AI Voice Job**, **Task Job** and **Usage Settings** DocTypes and the
  **"GLerp AI Administrator"** role (granted to support@greenllama.tech if that user exists).
  Default monthly AI budget is **$10**.

Run `bench migrate` on sites after upgrading.

## GLerp AI 2.1.0 (core v2.1.0, agent v2.1.0, intake v2.1.0 — shared major version)

Pins all three GLerp AI apps to **v2.1.0** (core 3d9a9d2, agent d9b8527, intake 1142304). From
2.1.0, every GLerp AI component shares one major version (2.x): Test Connection now shows each
service's version and warns on a major mismatch. **agent and intake now require glerp_ai_core ≥ 2.1**
— so the three must move together (this pin does). installApps unchanged (core+intake enabled,
agent shipped-not-installed); positions/order unchanged. No new patches, DocType changes or
required_apps beyond the core ≥ 2.1 floor. Supersedes the never-built intake v2.0.1 pin.

New since 2.0.x: intake webhooks accept failed-job payloads; "Shipping Document" results map to
Shipment; plus the 2.0.1 fixes (a result that can't be applied is marked Failed with a comment +
Activity Log row instead of retrying hourly forever; a Purchase Invoice whose due date precedes the
invoice date is saved Needs Review instead of failing; the "confidence below threshold" comment
appears only when confidence was actually low).

**⚠️ DEPLOYMENT COUPLING — run the 2.x services alongside these apps (shared-major rule).**
- Intake SERVICE: chart **k8-glerp-ai-intake 2.0.0 (app 2.0.1)** — the renumbered 0.4.12 line. Keep
  the upgrade-together-with-GLerp rule: prod intake has no default Gemini key, so if the intake
  service goes live before sites migrate to GLerp 2.1.0, intake jobs fail until each site's intake
  settings are saved; upgrade both together (GLerp migrate pushes each site's config on
  after_migrate; failures surface in "Last Sync Status"). Never use the old intake chart 0.4.9.
- Engine (agent backend): chart **k8-glerp-ai-agent 2.0.0 (app 2.0.1)** — only matters on sites that
  install the agent; no prod site has it yet.

Run `bench migrate` on sites after upgrading.

## GLerp AI 2.0.0 (glerp_ai_core v2.0.1, glerp_ai_agent v2.0.0, glerp_ai_intake v2.0.0)

Pins the three GLerp AI apps to their 2.0.0 line: glerp_ai_core **v2.0.1** (2.0.0 + a truly-free
ISC-licensed SVG "GLerp AI" icon; core now ships a `public/` folder for the first time),
glerp_ai_agent **v2.0.0**, glerp_ai_intake **v2.0.0**. installApps is unchanged — core and intake
are enabled by default; the agent stays shipped-but-not-installed (add it to `installApps` to enable).
No module/directory renames and no new required_apps (agent and intake still require only
glerp_ai_core). Titles/labels only: intake's app_title is now "GLerp AI Intake"; core now owns the
"GLerp AI" apps-screen tile (intake dropped its add_to_apps_screen). After migrate, core idempotently
cleans up the desktop icons and sets the GLerp AI logo.

**⚠️ DEPLOYMENT COUPLING — upgrade the intake SERVICE together with this GLerp image.** The
standalone GLerp AI Intake service (separate repo k8-glerp-ai-intake, published by the engine peer)
must go to **image 0.3.12 / chart 0.4.12** alongside this release (0.3.12 stores config per site).
Notes:
- The prod intake deployment has **no default Gemini key**. If intake chart **0.4.12** goes live
  BEFORE sites migrate to app-2.0.0, intake jobs fail until each site's intake settings are saved.
- Upgrading **both together is fine**: the GLerp 2.0.0 migrate pushes each site's config to the
  intake service on `after_migrate` (it never raises; failures surface in "Last Sync Status").
- **Never use intake chart 0.4.9** (it pins a stale image and a nonexistent OCR tag).
- The agent's own backend (engine chart k8-glerp-ai-agent 0.2.0, orchestrator 0.10.30) only matters
  on sites that install the agent; no prod site has it yet.

Migrate adds idempotent patches (`glerp_ai_intake.patches.keep_own_provider_keys` — no-op unless a
dev-only flag was set; `glerp_ai_agent.patches.copy_platform_providers` — copies keys/models from the
retired GLerp AI Platform Settings into Agent Settings where shared keys were used, no-op where the
agent isn't installed). Run `bench migrate` on sites after upgrading.

## MinIO default topology → 1 pool × 4 servers × 1 volume × 6Gi (simpler, 4-node-idiomatic)

The default per-tenant MinIO shape changes from `2 pools × 2 servers × 2 volumes × 3Gi` to
`1 pool × 4 servers × 1 volume × 6Gi`. Both are 24Gi raw ≈ 12Gi usable (EC:2+2) and both
encrypt — this is a simplicity/operability change, not a capacity or durability one. The new
shape is one erasure set of four DirectPV drives, one drive per node on a 4-node cluster, so
losing any single node keeps read+write quorum; it maps 1:1 onto a one-drive-per-node fleet
instead of stacking two virtual volumes per physical drive across two erasure sets.

Set `tenant.minio.servers` to the storage-node count on a differently-sized cluster. **Only
affects new installs** — MinIO pools are immutable, so existing tenants stay on whatever shape
they were created with (reshaping needs delete + recreate; leave working tenants as-is).

## tenant.externalDnsTarget now defaults to pec.greenllama.tech (DNS works out of the box)

Since the native tenant templates split routing into separate app (`traefik-system/<ns>`) and
minio (`<ns>/minio-<ns>`) IngressRoutes, the site's Cloudflare record is created only when those
routes carry the `external-dns.alpha.kubernetes.io/{hostname,target}` annotations — which the
templates emit only when `tenant.externalDnsTarget` is set. It shipped defaulting to `""`, so any
install that didn't explicitly set it got a site that came up but was **unreachable** (external-dns
generated no endpoint, no error anywhere). Default is now `pec.greenllama.tech` (the cluster's
standard ingress target); override only for a cluster whose external-dns points elsewhere.

## Image: MariaDB client no longer demands TLS (fixes `bench new-site` / `bench backup`)

`bench new-site` (and `bench backup`) shell out to the `mariadb` / `mariadb-dump` CLI, whose
base image now ships **MariaDB client 11.8**. MariaDB client **>= 11.4 requires TLS by default**
and aborts against a server that offers no TLS with:

```
ERROR 2026 (HY000): TLS/SSL error: SSL is required, but the server does not support it
```

Our in-cluster MariaDB is plain by design — internal cluster traffic is not MariaDB-native-TLS'd
(if that ever changes it is done at the mesh layer via Istio mTLS, not MariaDB TLS). The fix bakes
`~/.my.cnf` (`[client]\nssl=0`) into the image so the CLI tools do not demand TLS. This affects
only the CLI DB tools that read `~/.my.cnf`; the app's own PyMySQL connections do not read this
file and were never affected (which is why DB creation succeeded but the CLI import failed).

Image-level (not a chart mount), so every pod/job — create-site, backup, migrate — inherits it.
No server-side or native-TLS change; the server stays plain.

## MinIO images: self-owned in GHCR, digest-pinned (quay also went dark)

MinIO Inc. completed its withdrawal of community images — after Docker Hub (~2026-09-12),
**quay.io/minio/{minio,mc} went 401** (~2026-09-22; verified 2026-10-05). quay minio/kes still
pulls but is a dead-repo neighbor. The prior quay repoint is therefore no longer safe, and the
MinIO server image (never pinned by the chart — injected by the Operator) is on borrowed node-cache
time.

**glerp now owns every MinIO image under `ghcr.io/green-llama/*`, pinned by digest** — the chart
depends on no registry or prebuilt artifact outside our control:
- **kes** — BUILT FROM SOURCE (`github.com/minio/kes` @ `2025-03-12T09-35-18Z`, `go build ./cmd/kes`)
  via `build/kes/Dockerfile` → `ghcr.io/green-llama/kes@sha256:856b20e0…`.
- **mc** (activate-hook `fetch-mc`) — BUILT FROM SOURCE (`github.com/pgsty/mc` — maintained AGPL
  fork; upstream `minio/mc` is archived) via `build/mc/Dockerfile` →
  `ghcr.io/green-llama/mc@sha256:71074435…`. Finished on **busybox** (NOT `scratch`) because the
  `fetch-mc` init container stages the binary with `sh -c "cp … && chmod …"` and needs `/bin/sh`;
  binary path `/usr/bin/mc` unchanged.
- **minio server** — the chart now sets `Tenant.spec.image` (new `tenant.minio.image` value;
  previously unset → Operator default). Pinned to the **pgsty/silo** community fork mirrored to
  `ghcr.io/green-llama/minio@sha256:b6bfe723…`. silo keeps the `minio` binary + `MINIO_*` env +
  `/minio/health/*`, so the KES+Vault SSE-KMS design is unchanged.

All three images are multi-arch (amd64+arm64), public (anonymous pull — no imagePullSecret),
Trivy-scanned, and produced by the new `mirror-minio-images` workflow (build kes+mc from source,
mirror silo server). Override via `tenant.minio.image` / `tenant.minio.kes.image` /
`tenant.minio.kes.activateImage`; empty `tenant.minio.image` falls back to the Operator default.

**Proven end-to-end on the `backuptest` dev tenant (2026-10):** upgrade → activate hook patches the
KES identity (off `_pending_`) → rolling-bounces KES then MinIO → `SSE-KMS enabled`, `Encryption ✔ /
Decryption ✔`, and pre-existing attachments decrypt and serve in GLerp (confirmed by viewing old
files). The SSE-KMS control, DFP object keys, and `{site}/{base}-{name}.ext` naming are unchanged —
no per-site datafill or URL rewrites. NOTE for fleet upgrades: an upgrade that rolls the KES pods can
reset `kes-config-secret` identities to `_pending_`; the activate hook re-patches it, so if existing
attachments briefly 404 after an upgrade, re-run the upgrade (hook) rather than touching data. Full
detail in `docs/ENCRYPTION-ARCHITECTURE.md` §0.

**Deferred strategic item:** silo is a community fork of the now-archived MinIO CE. The
maintained-vs-migrate decision (silo / MinIO AIStor / migrate off MinIO) remains open; this pin is
the durable Phase-1 stopgap. **SSE-KMS must be proven on a dev tenant (backuptest) before prod** —
the silo server + from-source KES/mc have not yet been validated end-to-end against the Vault key
path.

## Fix: MinIO images (kes + mc) moved to quay.io (Docker Hub repos removed)

MinIO **removed both the `minio/kes` and `minio/mc` repositories from Docker Hub** — pulling
`docker.io/minio/kes:...` or `docker.io/minio/mc:...` now fails with
`pull access denied, repository does not exist ... insufficient_scope` (the Hub API returns
`object not found` for each repo). This breaks encryption on any fresh install, or any node that no
longer has the image cached (already-running tenants keep working until a pod is rescheduled onto a
node without the cached image — e.g. the `backuptest` dev tenant hit this for `kes`, then the
activate hook hit it for `mc`).

Both images — **and their exact tags — are public on quay.io**, so the chart's defaults are changed
from Docker Hub to quay.io (same pinned tags, multi-arch):
- KES server: `minio/kes:2025-03-12T09-35-18Z` → **`quay.io/minio/kes:2025-03-12T09-35-18Z`**
  (`values.yaml` `tenant.minio.kes.image` + the `minio-tenant.yaml` template default).
- Activate-hook `mc` (init container that copies the `mc` binary):
  `minio/mc:RELEASE.2025-03-12T17-29-24Z` → **`quay.io/minio/mc:RELEASE.2025-03-12T17-29-24Z`**
  (the `job-minio-kes-activate.yaml` `$kes.activateImage` default).

Override via `tenant.minio.kes.image` / `tenant.minio.kes.activateImage` as before. Quay allows
anonymous public pulls — no pull secret needed. Existing installs: upgrade to this chart version so
both images pull from quay.

## MariaDB fast failover — 30s eviction tolerations (default on)

`mariadb-sts` now ships with `tolerations` by default (in `values.yaml`, injected into the
StatefulSet pod spec) so `glerp-mariadb-sts-0` is evicted quickly when its node drops:

```
- key: node.kubernetes.io/unreachable   effect: NoExecute  operator: Exists  tolerationSeconds: 30
- key: node.kubernetes.io/not-ready     effect: NoExecute  operator: Exists  tolerationSeconds: 30
```

By default Kubernetes waits **300s** before evicting a pod from an unreachable/not-ready node; these
30s tolerations mark the pod `Terminating` almost immediately, letting the StatefulSet controller
reschedule it onto a node with a live storage replica. Target DB downtime on a host failure:
**~30–45s**, with no extra disk footprint and no node-fencing operator.

**Cluster dependency (NOT set by this chart):** the fast reschedule also requires Longhorn's
pod-deletion policy `node-down-pod-deletion-policy = delete-statefulset-pod` so Longhorn breaks the
RWO volume lock and lets the replacement pod attach. The tolerations alone only speed up eviction;
without that Longhorn setting the new pod can't mount the volume until the old node returns. This is
a one-time cluster-level Longhorn setting the operator manages.

Override or empty `mariadb-sts.tolerations` to disable. Applied to the pod template only — safe on
upgrade.

## Trivy scan-skip label on the 6 non-gunicorn Deployments

Added the pod label `glerp.io/trivy-skip: "true"` to the `spec.template.metadata.labels` of the six
non-gunicorn GLerp Deployments — **nginx, socketio, scheduler, worker-default, worker-short,
worker-long** — so Trivy Operator excludes those pods from vulnerability scans (via its
`skipResourceByLabels: "glerp.io/trivy-skip"` setting, configured on the Trivy Operator side, not in
this chart). **gunicorn is intentionally left unlabeled** so it continues to be scanned. The label is
on the pod template only (not the Deployment metadata, not the immutable selector), so it is safe to
apply on upgrade.

## Fix: Vault seed PushSecret paths no longer double the mount (`secret/secret/…`)

The three `PushSecret` `remoteKey` values in `templates/tenant/vault-seed.yaml` (mariadb-root,
minio accesskey, minio secretkey) incorrectly included the mount prefix
(`{{ $mount }}/{{ $ns }}/…`). ESO handles the two path styles differently:

- **ExternalSecret** `remoteRef.key` is the **full KV v2 API path** — includes the mount and
  `/data/` (e.g. `secret/data/<ns>/minio-creds`). *(unchanged — already correct)*
- **PushSecret** `remoteRef.remoteKey` is a **logical path within the mount** — ESO **prepends the
  mount** from the ClusterSecretStore automatically. Including it yourself **doubles** it.

So the seed wrote each credential to `secret/data/secret/<ns>/…` while the ExternalSecret read from
`secret/data/<ns>/…`. No functional breakage (the ExternalSecret always read the correct
pre-existing path, and `updatePolicy: IfNotExists` meant the stray copy was written once then
ignored), but it left a **duplicate credential** at a stray path — a hygiene/audit/rotation and
Vault-policy-surface concern.

**Fix:** drop the `{{ $mount }}/` prefix from all three `remoteKey`s so the PushSecret writes to the
exact path the ExternalSecret reads (`<ns>/…` → mount-prepended → `secret/data/<ns>/…`). Verified by
`helm template`: PushSecret `remoteKey: <ns>/minio-creds` and ExternalSecret
`key: secret/data/<ns>/minio-creds` now resolve to the same Vault path.

**Cleanup for existing installs (manual, one-time per affected site):** the stray copies at
`secret/<ns>/secret/<ns>/…` (i.e. `secret/data/secret/<ns>/…` via the API) are orphaned — delete
them after confirming the authoritative `secret/<ns>/…` path holds the live values:
`vault kv list secret/<ns>` will show a nested `secret/` folder if a stray copy exists;
`vault kv delete secret/<ns>/<ns>-mariadb-root` etc. against the **stray** path removes it. The
chart change stops new installs/upgrades from creating them.

## MinIO encryption at rest (KES + Vault) — final architecture (through chart 1.0.80)

**Encryption at rest for MinIO object storage** (per-tenant user file store) via MinIO KES +
HashiCorp Vault (SSE-KMS, AES-256-GCM). On by default in tenant mode
(`tenant.minio.kes.enabled: true`). Verified in production across GLerp tenant sites and on a clean
fresh install. Full detail: [`docs/DATA-ENCRYPTION.md`](docs/DATA-ENCRYPTION.md) (auditor) and
[`docs/ENCRYPTION-ARCHITECTURE.md`](docs/ENCRYPTION-ARCHITECTURE.md) (engineering).

**Architecture**
- A **KES sidecar** on the MinIO Tenant (replacing the earlier abandoned MinIO-direct-to-Vault KMS
  env). KES is a Vault **KV v2** client (not Transit); the KMS **root key never lands in a K8s
  Secret**. One key per tenant: `<namespace>-minio-key` at `secret/<namespace>/minio-kes/root-key/…`.
- **Shared Vault k8s-auth role** `glerp-minio-kes` (one-time per cluster; policy wildcards the
  namespace path segment) — no per-install Vault commands.
- `requestAutoCert: false` kept — the S3 API stays plain HTTP so `dfp_external_storage` is unchanged;
  only KES's Vault hop uses the service mesh / mTLS.
- KES authorizes MinIO by `sha256(DER pubkey)` of the operator's client cert — the **Opaque** secret
  `<ns>-minio-tenant-client-tls`, key `public.crt` (not a `kubernetes.io/tls` secret / `tls.crt`).
- Templates: `minio-tenant.yaml` (`spec.kes`), `minio-kes-sa.yaml`, `minio-kes-config.yaml`,
  `minio-kes-rbac.yaml`, `job-minio-kes-activate.yaml` (post-install/upgrade hook).

**The activate hook — delayed one-shot (hands-off, no manual steps).** Runs `python3 -u`
(unbuffered logs). In order: (1) resolve the client-cert identity and patch
`kes-config-secret.policy.minio.identities`; (2) wait for KES **and** MinIO pods to be Ready **and**
stable (crash-loop-free for a quiet window); (3) **rolling-bounce KES** (one replica at a time, so
its Service never loses all endpoints) to force a clean Vault re-auth; (4) **rolling-bounce MinIO**
so it re-initializes its IAM subsystem against the now-healthy KMS; (5) **activate** — create the
KMS key (idempotent) and enable bucket SSE-KMS, retried patiently (`ACTIVATE_ATTEMPTS`, default 12).
Tunables: `SETTLE_SECONDS` / `STABLE_QUIET` / `SETTLE_TIMEOUT` / `ACTIVATE_ATTEMPTS`.

**Fresh-install root cause (why the hook bounces both KES and MinIO):** a KMS cold-start race — on a
new tenant MinIO initializes IAM (which needs KMS) before KES's Vault session is usable, leaving
IAM partially initialized; MinIO then rejects `mc encrypt set` with the misleading
`SetEncryption is not supported for filesystem` (the backend is Erasure). Bouncing KES fixes the
Vault session; bouncing MinIO makes it re-init IAM against the healthy KMS. See
`docs/ENCRYPTION-ARCHITECTURE.md` §1.4, which also records the ruled-out dead ends (it is **not**
Istio, **not** the `MINIO_KMS_SECRET_KEY_FILE=kms_master_key` operator default, **not** a DirectPV
space/threshold issue).

**Also in this line of work:**
- MinIO **pool (data-plane) pods** carry `sidecar.istio.io/inject: "false"` — defensive, keeps the
  S3 data path out of any service mesh (matches prod); a no-op where injection is already off.
- `domain` is **validated at render time** — a malformed value (comma/space/underscore, e.g. a
  `dev,greenllama.tech` typo) now fails fast at `helm install` instead of crash-looping MinIO on a
  bad `MINIO_BROWSER_REDIRECT_URL`.

**Operational note:** if a fresh tenant sits at `Initialized` with no KES pods, the MinIO Operator
isn't reconciling `spec.kes` (often a stale operator) — one-time
`kubectl -n minio-operator rollout restart deploy/minio-operator` re-reconciles all tenants and
issues the KES certs. See TENANT.md §3c.

**Not retroactive:** enabling SSE-KMS encrypts only *new* writes; backfill pre-existing objects with
`mc cp --recursive` (TENANT.md). **Deferred:** per-tenant Vault policy/role (tighter cross-namespace
isolation) — needs Vault Enterprise templated ACLs or a CE per-tenant provisioner; the shared-role
model is in production (TENANT.md "Key scoping across namespaces").

## Earlier

For changes before the encryption work (Rancher install form, revisionHistoryLimit + job TTL,
idempotent data-safe create-site, dependency-ordered app install, chart README rewrite, etc.)
see the `green-llama/glerp-image` git history.
