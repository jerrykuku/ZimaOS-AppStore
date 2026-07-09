# ZimaOS AppStore Source Protocol v2 — Third-party Store Guide

This guide explains how to build a ZimaOS-compatible third-party app store using the AppStore Source Protocol v2.

Scope of this document:
- For operators building/deploying an external third-party store.
- For this repository's PR contribution process and repo-specific rules, use [CONTRIBUTING.md](../../CONTRIBUTING.md).

> **📢 What's New:** We've added 7 new optional fields to `meta.json` that enhance store display: `version`, `update_at`, `release_notes`, `website`, `repo`, `support`, and `docs`. These fields are marked with **[New]** in the [meta.json section](#metajson-after-build). Existing stores continue to work without changes, but we recommend adding these fields to improve your app listings.

## Overview

Any static file host (GitHub Pages, Netlify, self-hosted Nginx, etc.) can serve as a ZimaOS app store source. You just need to output a few JSON files and app resources in the correct format.

**Source structure** (what you write):

```
my-appstore/
├── Apps/
│   └── MyApp/
│       ├── docker-compose.yml    # with x-casaos block
│       └── icon.svg              # recommended
├── store-config.json             # store identity (input)
├── supported-languages.json      # list of output locales (optional)
└── scripts/
    └── build_appstore.py         # build script
```

**Output structure** (what gets deployed):

```text
dist/
├── index.json                     # default locale app listing (en_US fallback)
├── index.zh_CN.json               # generated only when locale is explicitly defined
├── store.json                     # default locale store info
├── store.zh_CN.json               # generated only when locale is explicitly defined
└── apps/
    └── my-app/
        ├── docker-compose.yml     # one runtime compose per app
        ├── meta.json              # default locale metadata
        ├── meta.zh_CN.json        # generated only when locale is explicitly defined
        └── assets/
            ├── icon.svg
            ├── icon.png
            ├── thumbnail.webp
            └── screenshot-*.webp
```

Users add your store in ZimaOS by entering your URL:
```
https://username.github.io/my-appstore
```

---

## Quick Start

### 1. Create your repository

Create a new GitHub repository with this structure:

```text
my-appstore/
├── Apps/
│   └── MyApp/
│       ├── docker-compose.yml
│       ├── icon.svg             (recommended) / icon.png
│       ├── thumbnail.png        (optional, .jpg/.jpeg/.webp also supported)
│       ├── screenshot-1.png     (optional, .jpg/.jpeg/.webp also supported)
│       └── screenshot-2.png     (optional)
├── store-config.json
├── supported-languages.json     (optional, defaults to en_US only)
├── scripts/
│   └── build_appstore.py        (copy from official repo)
└── .github/
    └── workflows/
        └── deploy.yml
```

### 2. Write store-config.json

This file identifies your store. The build script reads it and outputs `store.json` to the deploy directory.

```json
{
  "version": 2,
  "store_id": "my-awesome-apps",
  "name": {
    "en_US": "My Awesome Apps",
    "zh_CN": "我的应用商店"
  },
  "description": {
    "en_US": "A collection of apps for home server enthusiasts"
  },
  "maintainer": "your-github-username",
  "url": "https://github.com/username/my-appstore"
}
```

**Rules for `store_id`:**
- Lowercase only, `[a-z0-9-]`
- Must be globally unique (choose something distinctive)
- Cannot be `zimaos-appstore` (reserved; also avoid historical reserved value `zimaos-official`)

### 3. Create your app

Each app lives in its own directory under `Apps/`. The directory name doesn't matter (app ID comes from the compose file).

**docker-compose.yml:**

```yaml
name: my-app
services:
  my-app:
    image: myrepo/my-app:latest
    ports:
      - target: 8080
        published: "8080"
        protocol: tcp
    volumes:
      - type: bind
        source: /DATA/AppData/$AppID/config
        target: /config
    restart: unless-stopped
x-casaos:
  # --- Runtime fields (kept in compose after build) ---
  main: my-app
  index: /
  port_map: "8080"
  scheme: http
  # In source compose this can be any reachable URL.
  # Build output rewrites it to apps/my-app/assets/icon.svg (or icon.png) under your --base-url.
  icon: https://cdn.jsdelivr.net/gh/username/my-appstore@main/Apps/MyApp/icon.svg
  title:
    en_US: My App
    zh_CN: 我的应用
  # --- Metadata fields (extracted to meta.json by build script) ---
  author: Your Name
  developer: Original Developer
  category: Productivity
  architectures:
    - amd64
    - arm64
  description:
    en_US: A great app that does amazing things.
    zh_CN: 一个很棒的应用。
  tagline:
    en_US: Does amazing things
    zh_CN: 做很棒的事情
  screenshot_link:
    - screenshot-1.png
  thumbnail: thumbnail.png
  tips: {}
  version: "1.0.0"
  update_at: "2026-03-01"
  release_notes:
    en_US: First release
```

> You can write everything in one docker-compose.yml — the build script will automatically split it into a clean compose file + meta.json.

**Multi-service example** (app with database):

```yaml
name: my-wiki
services:
  my-wiki:
    image: requarks/wiki:2
    ports:
      - target: 3000
        published: "3000"
        protocol: tcp
    environment:
      DB_TYPE: postgres
      DB_HOST: my-wiki-db
      DB_PORT: "5432"
      DB_USER: wiki
      DB_PASS: wikisecret
      DB_NAME: wiki
    depends_on:
      - my-wiki-db
    restart: unless-stopped
  my-wiki-db:
    image: postgres:15
    volumes:
      - type: bind
        source: /DATA/AppData/$AppID/db
        target: /var/lib/postgresql/data
    environment:
      POSTGRES_USER: wiki
      POSTGRES_PASSWORD: wikisecret
      POSTGRES_DB: wiki
    restart: unless-stopped
x-casaos:
  main: my-wiki           # <- points to the web UI service（service name）, not the database
  index: /
  port_map: "3000"
  # ... other fields ...
```

For multi-service apps, `main` must point to the service that provides the web UI.

### 4. Set up CI/CD

Copy `scripts/build_appstore.py` from the [official repository](https://github.com/IceWhaleTech/ZimaOS-AppStore).

Create `.github/workflows/deploy.yml`:

```yaml
name: Build And Publish Dist

on:
  push:
    branches:
      - main
  workflow_dispatch:
    inputs:
      base_url:
        description: "Base URL used by build_appstore.py"
        required: false
        default: "https://cdn.jsdelivr.net/gh/username/my-appstore@gh-pages"

permissions:
  contents: write

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          sudo apt-get update && sudo apt-get install -y librsvg2-bin
          pip install pyyaml Pillow

      - name: Build static appstore dist
        env:
          BASE_URL_INPUT: ${{ inputs.base_url }}
        run: |
          BASE_URL="${BASE_URL_INPUT:-https://cdn.jsdelivr.net/gh/${{ github.repository }}@gh-pages}"
          python3 scripts/build_appstore.py \
            --source . \
            --output dist \
            --base-url "${BASE_URL}"
          touch dist/.nojekyll

      - name: Deploy dist to gh-pages
        uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_branch: gh-pages
          publish_dir: ./dist

      - name: Refresh jsDelivr cache
        run: |
          curl -fsSL "https://purge.jsdelivr.net/gh/${{ github.repository }}@gh-pages/en_US/index.json" || true
```

#### Optional: use the official GitHub Action directly (recommended for fast adoption)

If you don't want to maintain build-step details yourself, you can use the official action:

```yaml
name: Build And Publish Dist

on:
  push:
    branches:
      - main
  workflow_dispatch:
    inputs:
      base_url:
        description: "Base URL used by build_appstore.py"
        required: false
        default: "https://cdn.jsdelivr.net/gh/username/my-appstore@gh-pages"

permissions:
  contents: write

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build dist via official action
        uses: IceWhaleTech/build-appstore-action@v1
        with:
          source: .
          output: dist
          base-url: ${{ inputs.base_url }}

      - name: Disable Jekyll
        run: touch dist/.nojekyll

      - name: Deploy dist to gh-pages
        uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_branch: gh-pages
          publish_dir: ./dist
```

> Recommendation: start with `@v1`; switch to a pinned commit SHA for reproducible production builds.
> When using this action, you usually do not need to copy `scripts/build_appstore.py` into your own repository.

### 5. Share your store URL

After workflow runs, your store is available at:

```
https://cdn.jsdelivr.net/gh/username/my-appstore@gh-pages
```

Users can add this URL as a store source in ZimaOS settings.

### 6. Alternative: No gh-pages, No jsDelivr

If you don't want to use `gh-pages` or jsDelivr, you can still use the same build script and deploy `dist/` to any static host.

Use a generic build workflow that only uploads artifacts:

```yaml
name: Build Store Dist

on:
  push:
    branches:
      - main
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          sudo apt-get update && sudo apt-get install -y librsvg2-bin
          pip install pyyaml Pillow

      - name: Build dist for your own domain
        run: |
          python3 scripts/build_appstore.py \
            --source . \
            --output dist \
            --base-url "https://store.example.com"

      - name: Upload dist artifact
        uses: actions/upload-artifact@v4
        with:
          name: appstore-dist
          path: dist
```

Then deploy `dist/` using your preferred platform:

- Netlify: set publish directory to `dist`
- Cloudflare Pages: set output directory to `dist`
- Self-hosted Nginx/Caddy: serve `dist/` as static files under your HTTPS domain

Your final store URL will be the same as `--base-url` (for example, `https://store.example.com`).

---

## Upgrading from v1

If you already have a third-party store built for the old CasaOS AppStore protocol (zip-based distribution), follow these steps to upgrade to v2.

If you only want the minimum required changes first, start here:
- [v1 -> v2 Migration Checklist (Minimum Changes)](./v1-to-v2-migration-checklist.md)

### What changed

| | v1 (old) | v2 (new) |
|---|----------|----------|
| Distribution | zip package download | Static site (GitHub Pages, CDN, etc.) |
| Store identity | None | `store-config.json` → `store.json` |
| Build script | None | `scripts/build_appstore.py` |
| Metadata | All in `x-casaos` block | Split into compose + `meta.json` |
| Categories | Free-form | Standardized (9 official names) |
| Update mechanism | Full zip re-download | Incremental (`content_hash`) |

### Your existing `Apps/` directory works as-is

The v2 build script reads the same `Apps/` directory structure. Your existing `docker-compose.yml` files are fully compatible — the build script will automatically:

- Remove service-level `services.xxx.x-casaos` blocks
- Split top-level `x-casaos` into runtime fields (kept in compose) + metadata (extracted to `meta.json`)
- Normalize i18n locale keys (`en_us` → `en_US`)
- Optimize and convert image assets

### Step 1: Add `store-config.json`

Create this file in your repository root:

```json
{
  "version": 2,
  "store_id": "your-store-id",
  "name": {
    "en_US": "Your Store Name"
  },
  "maintainer": "your-github-username",
  "url": "https://github.com/username/your-appstore"
}
```

### Step 2: Copy the build script

Copy `scripts/build_appstore.py` from the [official repository](https://github.com/IceWhaleTech/ZimaOS-AppStore) into your `scripts/` directory.

### Step 3: Update app categories

v2 requires standardized categories. Update the `category` field in each app's `x-casaos` block to one of the 9 official names.

Common mappings from old category names:

| Old category | New category |
|-------------|-------------|
| `Utilities` | `Productivity` |
| `Tools` | `Productivity` |
| `Entertainment` | `Media` |
| `Music` | `Media` |
| `Video` | `Media` |
| `Photos` | `Media` |
| `Cloud` | `Networking` |
| `Storage` | `Home` |
| `Security` | `Networking` |
| `Communication` | `Social` |
| `Games` | `Others` |

Full list of valid categories: `Media`, `Productivity`, `Home`, `Networking`, `AI`, `Finance`, `Social`, `Developer`, `Others`

### Step 4: Add CI/CD workflow

Follow [Quick Start Step 4](#4-set-up-cicd) to set up GitHub Actions for automated builds and deployment.

### Step 5 (Recommended): Keep v1 -> v2 migration hints for existing users

In the v1/v2 coexistence phase, `store-config.json` is already required for v2 stores.

For migration reminders, the only extra requirement is:

- Include the same `store-config.json` file in your v1 zip package

Why this matters:

- After users upgrade AppStore to v2, the client scans legacy zip-extracted third-party store records
- The one-click "restore old store" prompt is available only when `store-config.json` is detected in legacy v1 zip content
- If v1 zip does not include `store-config.json`, users can still re-add manually, but no migration reminder will be shown

### Optional improvements

- Add the 7 new metadata fields (`version`, `update_at`, `release_notes`, `website`, `repo`, `support`, `docs`) to enhance store display — see [meta.json](#metajson-after-build)
- Add `supported-languages.json` for multi-language output
- Replace PNG icons with SVG for better quality

### Files you can keep

- `featured-apps.json` and `recommend-list.json` can stay in your repository — the build script ignores them
- `category-list.json` can stay but is no longer required — categories are auto-extracted from apps

---

## File Format Reference

### store-config.json (input) → store.json (output)

You write `store-config.json` in your repository root. The build script always generates `dist/store.json` (default locale) and additionally generates `dist/store.{locale}.json` only for locales explicitly defined in store i18n fields (`name`, `description`). When a user adds your store URL, the client can fetch `store.json` or a locale-specific `store.{locale}.json`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | `int` | Yes | Protocol version, must be `2` |
| `store_id` | `string` | Yes | Unique store identifier, `[a-z0-9-]` |
| `name` | `object` | Yes | Store display name (i18n) |
| `description` | `object` | No | Store description (i18n) |
| `maintainer` | `string` | Yes | Maintainer name |
| `url` | `string` | No | Project homepage URL |
| `icon` | `string` | No | Store icon URL |

### index.json

Generated automatically by the build script as `dist/index.json` (default locale) and `dist/index.{locale}.json` (only when at least one app explicitly defines that locale in `title`/`tagline`). Each generated index includes the full app list.

```json
{
  "version": 2,
  "updated_at": "2026-03-03T12:00:00Z",
  "app_count": 5,
  "apps": [
    {
      "id": "my-app",
      "title": "My App",
      "tagline": "Does amazing things",
      "category": "Productivity",
      "version": "1.0.0",
      "author": "Your Name",
      "developer": "Original Developer",
      "architectures": ["amd64", "arm64"],
      "icon": "apps/my-app/assets/icon.svg",
      "thumbnail": "apps/my-app/assets/thumbnail.webp",
      "compose_url": "apps/my-app/docker-compose.yml",
      "meta_url": "apps/my-app/meta.json",
      "content_hash": "a1b2c3d4"
    }
  ]
}
```

> Image paths (like `icon`, `thumbnail`) point to `apps/{app-id}/assets/`. `compose_url` and `meta_url` are app-relative paths without locale prefix. All paths are relative to `base_url`.
> `content_hash` is computed from all files under `apps/{app-id}/` (compose, meta variants, and assets).

### docker-compose.yml (after build)

The build script keeps only these fields in `x-casaos`:

| Field | Purpose | Example |
|-------|---------|---------|
| `main` | Primary service name (web UI entry point) | `my-app` |
| `index` | Web UI root path | `/` |
| `port_map` | Web UI published port (must be a **string**, use quotes) | `"8080"` |
| `scheme` | Web UI protocol (`http` or `https`) | `http` |
| `icon` | Icon URL (shown in ZimaOS dashboard after install) | `https://...` |
| `title` | App name (resolved to plain string for the target locale) | `My App` |

Everything else is moved to `meta.json`.

> **Important:** `port_map` must be a YAML string, not an integer. Always use quotes: `port_map: "8080"`, not `port_map: 8080`.

### meta.json (after build)

| Field | Type | Description |
|-------|------|-------------|
| `tagline` | `string` | Short description (resolved to plain string for the target locale) |
| `description` | `string` | Full description (resolved to plain string; markdown text is allowed, rendering depends on client) |
| `thumbnail` | `string` | Thumbnail path relative to `base_url` (e.g. `apps/my-app/assets/thumbnail.webp`) |
| `screenshot_link` | `string[]` | Screenshot paths relative to `base_url` (e.g. `apps/my-app/assets/screenshot-1.webp`) |
| `tips` | `object` | Install tips (resolved to plain strings, optional, see below) |
| `author` | `string` | Packager name |
| `developer` | `string` | Upstream developer |
| `category` | `string` | App category |
| `architectures` | `string[]` | Supported CPU architectures |
| `version` | `string` | **[New, optional]** App version, enhances store display |
| `update_at` | `string` | **[New, optional]** Update date (recommended `YYYY-MM-DD`, e.g. `"2026-03-01"`), enhances store display |
| `release_notes` | `string` | **[New, optional]** Release notes (resolved to plain string), enhances store display |
| `website` | `string` | **[New, optional]** Official website, enhances store display |
| `repo` | `string` | **[New, optional]** Source repository, enhances store display |
| `support` | `string` | **[New, optional]** Support URL, enhances store display |
| `docs` | `string` | **[New, optional]** Documentation URL, enhances store display |

> Note: `title` and `icon` stay in top-level `x-casaos` inside `docker-compose.yml`; they are not written to `meta.json`.

**Tips format:**

```yaml
tips:
  before_install:
    en_US: This app requires at least 4GB RAM.
    zh_CN: 此应用需要至少 4GB 内存。
```

Tips are shown to the user before installation. The keys under `tips` (e.g. `before_install`) support i18n values.

### Image Assets

All image assets are output to `apps/{app-id}/assets/` (not duplicated per locale).

| File | Source Formats | Build Output | Required |
|------|----------------|--------------|----------|
| `icon` | `.svg` (recommended), `.png`, `.jpg`, `.webp` | if `.svg` exists: keep `icon.svg` and generate `icon.png`; otherwise keep original icon file | Yes |
| `thumbnail` | `.png`, `.jpg`, `.jpeg`, `.webp` | converted to `.webp` (and resized when too wide) | No |
| `screenshot-{n}` | `.png`, `.jpg`, `.jpeg`, `.webp` | converted to `.webp` (and resized when too wide) | No |

- Non-icon raster images are optimized with Pillow (WebP quality `85`, max width `1280`)
- SVG files are copied as-is (except icon also gets PNG fallback when `rsvg-convert` is available)

---

## Icon URL Behavior

Your app's icon is used in two places:

| Where | Field | Behavior |
|-------|-------|----------|
| **Store listing** (before install) | `index.json` → `icon` | generated from build output (`apps/<app-id>/assets/icon.svg` or `icon.png`) |
| **Dashboard** (after install) | `docker-compose.yml` → `x-casaos.icon` | rewritten by build script to the same built icon URL |

In source compose, you can still set a stable URL. During build, `x-casaos.icon` is replaced with the built output URL based on `--base-url`.

---

## ZimaOS Runtime Variables

ZimaOS provides these variables that are resolved at install time:

| Variable | Description | Example value |
|----------|-------------|---------------|
| `$AppID` | The app's unique identifier (used for data isolation) | `my-app` |
| `$TZ` | System timezone | `America/New_York` |
| `$PUID` | Host user ID | `1000` |
| `$PGID` | Host group ID | `1000` |

Use `$AppID` in volume paths to isolate app data:

```yaml
volumes:
  - type: bind
    source: /DATA/AppData/$AppID/config
    target: /config
```

---

## i18n Locale Key Format

All locale keys must use `ll_CC` format (language lowercase + country uppercase):

| Correct | Incorrect |
|---------|-----------|
| `en_US` | `en_us` |
| `zh_CN` | `zh_cn` |
| `de_DE` | `de_de` |

The build script normalizes locale keys automatically for:
- `store-config.json`: `name`, `description`
- `x-casaos`: `title`, `tagline`, `description`, `release_notes`, and each nested locale object under `tips`

At minimum, provide `en_US` for all i18n fields. For generated locale-specific files, only explicitly defined locales are emitted.

### Multi-language Output

The build script reads `supported-languages.json` (a JSON array of locale codes) as a candidate locale list. In the source `docker-compose.yml`, you still write i18n fields as locale-keyed objects:

```yaml
title:
  en_US: My App
  zh_CN: 我的应用
```

The build script always emits `dist/apps/my-app/meta.json` (default locale) and emits `dist/apps/my-app/meta.{locale}.json` only when that locale is explicitly defined in app i18n fields.

If `supported-languages.json` is not present, only `en_US` output is generated.

---

## App ID

The app ID determines the Docker project name and how ZimaOS identifies your app.

**Resolution priority:**

```
store_app_id  (in x-casaos, if set)
    ↓ not set
compose name  (top-level "name:" field)
    ↓ not set
directory name (lowercased)
```

**Rules:**
- Must be lowercase, `[a-z0-9-_]`
- Must be unique within your store
- Don't worry about conflicts with other stores — ZimaOS handles isolation automatically by prefixing your `store_id` at install time

---

## Categories

App categories in ZimaOS are standardized. You must use one of the following official category names in the `category` field of each app's `x-casaos` block:

| Category | Description |
|----------|-------------|
| `Media` | Video, music, photos, streaming, subtitle tools, media servers |
| `Productivity` | Note-taking, office tools, project management, automation, utilities |
| `Home` | Smart home, home automation, storage management, personal dashboards |
| `Networking` | VPN, DNS, reverse proxy, firewalls, network monitoring |
| `AI` | Machine learning, LLMs, image generation, AI-powered tools |
| `Finance` | Budgeting, accounting, cryptocurrency, financial tracking |
| `Social` | Chat, forums, social media, communication platforms |
| `Developer` | Code hosting, CI/CD, databases, dev tools, containers |
| `Others` | Anything that doesn't fit the above categories |

Custom category names are not supported — apps with unrecognized categories will not display correctly in ZimaOS.

---

## Updating Apps

To update an app (e.g. bump the image version):

1. Edit the `docker-compose.yml` — change the image tag, adjust config, etc.
2. Push to `main` — CI rebuilds and redeploys automatically
3. The app's `content_hash` in `index.json` changes, so ZimaOS devices will pick up the update next time a user opens the store

There is no separate versioning or changelog mechanism in the protocol. The `content_hash` handles change detection automatically.

---

## Bandwidth & Update Efficiency

The v2 protocol uses **incremental updates** instead of full-package downloads, which significantly reduces bandwidth consumption for both store maintainers and ZimaOS devices.

### How updates work

When a user opens the app store, ZimaOS requests `index.json` or `index.{locale}.json` with an HTTP `ETag` header:

```
1. GET index.{locale}.json (with If-None-Match: <cached ETag>)
   ├─ 304 Not Modified → no data transferred, use local cache
   └─ 200 OK → compare each app's content_hash with local cache
                 ├─ hash matches → skip (no download)
                 └─ hash differs → fetch only that app's compose + meta
```

### Bandwidth comparison

Suppose your store has 20 apps and you update 1 app:

| Approach | What gets downloaded | Traffic |
|----------|---------------------|---------|
| Old (zip) | All 20 apps re-downloaded as a full package | ~200 KB+ |
| **New (v2)** | index.json + 1 changed app's compose + meta | **~15 KB** |

When there are **no updates at all**, the v2 protocol costs almost nothing — the `304 Not Modified` response has an empty body.

### Why this matters

- **Lower hosting costs**: GitHub Pages has a 100 GB/month bandwidth limit. Incremental updates mean your store can serve far more devices within that quota.
- **Faster for users**: Checking for updates takes ~100-200ms (a single HTTP request), so the store always feels instant.
- **Scales well**: If 1,000 devices check your store daily with no changes, total bandwidth is near zero. With the old zip approach, it would be 1,000 full downloads.

### When does the client check for updates?

ZimaOS checks for updates **when the user opens the app store** — no background polling, no periodic downloads. This means:

- Devices that rarely open the store consume zero bandwidth
- Devices that open the store always see the latest data
- No wasted traffic from background syncing

---

## FAQ

### Can I use the same app ID as the official store?

Yes. Official store apps and third-party store apps are displayed separately in ZimaOS, so there's no conflict. Even if the app IDs are identical, they will be shown independently in their respective store pages.

### What if another third-party store uses the same app ID as mine?

No problem. ZimaOS prefixes the Docker project name with your `store_id` at install time, so `my-store_dashboard` and `other-store_dashboard` are fully isolated at the Docker level.

### Do I need to run the build script?

Yes. The build script:
- Converts `store-config.json` → `store.json` plus on-demand `store.{locale}.json`
- Splits `docker-compose.yml` → clean compose + `meta.json`
- Generates `index.json` and on-demand `index.{locale}.json` with content hashes
- Resolves i18n fields to plain strings (default outputs use `en_US` fallback; locale-suffixed files are generated only for explicitly defined locales)
- Normalizes locale keys
- Copies/optimizes image assets to `apps/{app-id}/assets/` (including `icon.svg` → `icon.png` fallback when possible)

You should not create these output files by hand.

### Can I host my store somewhere other than GitHub Pages?

Yes. Any static file hosting works (Netlify, Vercel, Cloudflare Pages, self-hosted Nginx, etc.). Just make sure the files are accessible via HTTPS. ZimaOS fetches store data from the backend (not from a browser), so CORS headers are not required.

### Do I have to use jsDelivr?

No. jsDelivr is only one optional CDN path. You can use any HTTPS URL as `--base-url`, including:
- `https://username.github.io/my-appstore`
- `https://store.example.com`
- `https://my-store.pages.dev`

### Why is `--base-url` required?

The frontend components that render app cards receive `index.json` data but don't know the host URL of your store. Without `--base-url`, resource paths like `apps/my-app/assets/icon.svg` are relative and the frontend cannot resolve them.

`--base-url` makes all resource URLs absolute so they work directly:

```bash
# GitHub Pages hosting
python3 scripts/build_appstore.py --source . --output dist \
  --base-url https://username.github.io/my-appstore
# icon: "https://username.github.io/my-appstore/apps/my-app/assets/icon.svg"

# jsDelivr CDN hosting
python3 scripts/build_appstore.py --source . --output dist \
  --base-url https://cdn.jsdelivr.net/gh/username/my-appstore@gh-pages
# icon: "https://cdn.jsdelivr.net/gh/username/my-appstore@gh-pages/apps/my-app/assets/icon.svg"
```

### What's the minimum viable store?

```text
my-appstore/
├── Apps/
│   └── MyApp/
│       ├── docker-compose.yml    # with x-casaos block
│       └── icon.svg (or icon.png)
├── store-config.json
└── scripts/
    └── build_appstore.py
```

One app, one icon, one config file. That's it. Add `supported-languages.json` if you want multi-language output.
