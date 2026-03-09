# ZimaOS AppStore Source Protocol v2 — Third-party Store Guide

This guide explains how to build a ZimaOS-compatible third-party app store using the AppStore Source Protocol v2.

Scope of this document:
- For operators building/deploying an external third-party store.
- For this repository's PR contribution process and repo-specific rules, use [CONTRIBUTING.md](../../CONTRIBUTING.md).

## Overview

Any static file host (GitHub Pages, Netlify, self-hosted Nginx, etc.) can serve as a ZimaOS app store source. You just need to output a few JSON files and app resources in the correct format.

**Source structure** (what you write):

```
my-appstore/
├── Apps/
│   └── MyApp/
│       ├── docker-compose.yml    # with x-casaos block
│       └── icon.png
├── store-config.json             # store identity (input)
└── scripts/
    └── build_appstore.py         # build script
```

**Output structure** (what gets deployed):

```
dist/
├── store.json              # generated from store-config.json
├── index.json              # app listing with categories + content hashes
└── apps/
    ├── my-app/
    │   ├── docker-compose.yml    # cleaned (minimal x-casaos)
    │   ├── meta.json             # extracted metadata
    │   ├── icon.png
    │   └── screenshot-*.png
    └── another-app/
        └── ...
```

Users add your store in ZimaOS by entering your URL:
```
https://username.github.io/my-appstore
```

---

## Quick Start

### 1. Create your repository

Create a new GitHub repository with this structure:

```
my-appstore/
├── Apps/
│   └── MyApp/
│       ├── docker-compose.yml
│       ├── icon.png
│       ├── thumbnail.png        (optional)
│       ├── screenshot-1.png     (optional)
│       └── screenshot-2.png     (optional)
├── store-config.json
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
- Cannot be `zimaos-official` (reserved)

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
  icon: https://cdn.jsdelivr.net/gh/username/my-appstore@main/Apps/MyApp/icon.png
  title:
    en_US: My App
    zh_CN: 我的应用
  # --- Metadata fields (extracted to meta.json by build script) ---
  author: Your Name
  developer: Original Developer
  category: Utilities
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
    - https://cdn.jsdelivr.net/gh/username/my-appstore@main/Apps/MyApp/screenshot-1.png
  thumbnail: https://cdn.jsdelivr.net/gh/username/my-appstore@main/Apps/MyApp/thumbnail.png
  tips: {}
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
  main: my-wiki           # <- points to the web UI service, not the database
  index: /
  port_map: "3000"
  # ... other fields ...
```

For multi-service apps, `main` must point to the service that provides the web UI.

### 4. Set up CI/CD

Copy `scripts/build_appstore.py` from the [official repository](https://github.com/IceWhaleTech/ZimaOS-AppStore).

Create `.github/workflows/deploy.yml`:

```yaml
name: Build and Deploy Store

on:
  push:
    branches: ["main"]

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: pip install pyyaml

      - name: Build store
        run: |
          python3 scripts/build_appstore.py \
            --source . \
            --output dist \
            --base-url https://username.github.io/my-appstore

      - name: Upload Pages artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: dist

      - name: Deploy to GitHub Pages
        uses: actions/deploy-pages@v4
```

### 5. Enable GitHub Pages

Go to your repository **Settings > Pages > Source**, select **GitHub Actions**.

Push your code. The workflow will build and deploy automatically.

### 6. Share your store URL

Your store is now live at:

```
https://username.github.io/my-appstore
```

Users can add this URL as a store source in ZimaOS settings.

---

## File Format Reference

### store-config.json (input) → store.json (output)

You write `store-config.json` in your repository root. The build script copies it to `dist/store.json` (with locale key normalization). When a user adds your store URL, ZimaOS fetches `{url}/store.json` to verify the store identity.

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

Generated automatically by the build script. Contains all app summaries and categories for quick loading.

For third-party stores (without `category-list.json`), categories are auto-extracted from your apps:

```json
{
  "version": 2,
  "updated_at": "2026-03-03T12:00:00Z",
  "categories": [
    { "name": "Utilities" },
    { "name": "Media" }
  ],
  "app_count": 5,
  "apps": [
    {
      "id": "my-app",
      "title": { "en_US": "My App" },
      "tagline": { "en_US": "Does amazing things" },
      "category": "Utilities",
      "author": "Your Name",
      "developer": "Original Developer",
      "architectures": ["amd64", "arm64"],
      "icon": "apps/my-app/icon.png",
      "thumbnail": "apps/my-app/thumbnail.png",
      "compose_url": "apps/my-app/docker-compose.yml",
      "meta_url": "apps/my-app/meta.json",
      "content_hash": "a1b2c3d4"
    }
  ]
}
```

> When `--base-url` is provided, URLs like `icon`, `compose_url`, etc. become absolute (e.g. `https://username.github.io/my-appstore/apps/my-app/icon.png`). Without it, they are relative paths.

### docker-compose.yml (after build)

The build script keeps only these fields in `x-casaos`:

| Field | Purpose | Example |
|-------|---------|---------|
| `main` | Primary service name (web UI entry point) | `my-app` |
| `index` | Web UI root path | `/` |
| `port_map` | Web UI published port (must be a **string**, use quotes) | `"8080"` |
| `scheme` | Web UI protocol (`http` or `https`) | `http` |
| `icon` | Icon URL (shown in ZimaOS dashboard after install) | `https://...` |
| `title` | App name (i18n) | `{ "en_US": "My App" }` |

Everything else is moved to `meta.json`.

> **Important:** `port_map` must be a YAML string, not an integer. Always use quotes: `port_map: "8080"`, not `port_map: 8080`.

### meta.json (after build)

| Field | Type | Description |
|-------|------|-------------|
| `tagline` | `object` | Short description (i18n) |
| `description` | `object` | Full description (i18n, supports Markdown) |
| `thumbnail` | `string` | Thumbnail filename (relative) |
| `screenshot_link` | `string[]` | Screenshot filenames (relative) |
| `tips` | `object` | Install tips (i18n, optional, see below) |
| `author` | `string` | Packager name |
| `developer` | `string` | Upstream developer |
| `category` | `string` | App category |
| `architectures` | `string[]` | Supported CPU architectures |
| `version` | `string` | App version |
| `updateAt` | `string` | Update date (recommended ISO 8601 / `YYYY-MM-DD`) |
| `releaseNotes` | `object` | Release notes (i18n) |
| `website` | `string` | Official website (optional) |
| `repo` | `string` | Source repository (optional) |
| `support` | `string` | Support URL (optional) |
| `docs` | `string` | Documentation URL (optional) |

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

| File | Format | Size | Required |
|------|--------|------|----------|
| `icon.svg` (recommended) / `icon.png` | SVG / PNG | 256×256 px | Yes |
| `thumbnail.jpg` | JPG | 16:10 ratio, width 1280–1920 px (recommended 1920×1200) | No |
| `screenshot-{n}.jpg` | JPG | 16:10 ratio, width 1280–1920 px (recommended 1920×1200) | No |

- If `icon.svg` exists, the build output keeps `icon.svg` and also generates `icon.png` from it
- If no `icon.svg` exists, the build keeps the original icon file as-is
- Thumbnail and screenshots: use JPG to keep file sizes small

---

## Icon URLs: Two Locations, Two Purposes

Your app's icon appears in two places, served from two different URLs:

| Where | URL source | Purpose |
|-------|-----------|---------|
| **Store listing** (before install) | `index.json` → `icon` field | Built by the script, relative or absolute path to the deployed icon file |
| **Dashboard** (after install) | `docker-compose.yml` → `x-casaos.icon` | Embedded in the compose file, used at runtime by ZimaOS |

The compose `icon` URL should point to a stable, publicly accessible location. Using jsDelivr with a pinned branch is recommended:

```
https://cdn.jsdelivr.net/gh/username/my-appstore@main/Apps/MyApp/icon.png
```

This URL points to the icon in your **source repository** (not the built output), so it works even before the store is deployed.

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

The build script normalizes locale keys automatically.

At minimum, provide `en_US` for all i18n fields.

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

Use the standard category names to ensure proper display in ZimaOS:

`Analytics`, `Backup`, `Blog`, `Chat`, `Cloud`, `Developer`, `CRM`, `Documents`, `Email`, `File Sync`, `Finance`, `Forum`, `Gallery`, `Games`, `Learning`, `Media`, `Notes`, `Project Management`, `VPN`, `WEB`, `WiKi`, `Dapps`, `Downloader`, `Utilities`, `Home Automation`, `Network`, `Database`, `AI`

The build script auto-extracts categories from your apps — you don't need to create a `category-list.json` file. Just set the `category` field in each app's `x-casaos` block.

You can also use custom category names — they will appear in your store but may not have an icon in the default ZimaOS UI.

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

When a user opens the app store, ZimaOS requests `index.json` with an HTTP `ETag` header:

```
1. GET index.json (with If-None-Match: <cached ETag>)
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

Yes. If a user has both your store and the official store enabled, ZimaOS will show both versions and let the user choose which one to install. Only one version can be installed at a time.

### What if another third-party store uses the same app ID as mine?

No problem. ZimaOS prefixes the Docker project name with your `store_id` at install time, so `my-store_dashboard` and `other-store_dashboard` are fully isolated at the Docker level.

### Do I need to run the build script?

Yes. The build script:
- Converts `store-config.json` → `store.json`
- Splits `docker-compose.yml` → clean compose + `meta.json`
- Auto-extracts categories from your apps
- Generates `index.json` with content hashes
- Normalizes locale keys
- Copies image assets

You should not create these output files by hand.

### Can I host my store somewhere other than GitHub Pages?

Yes. Any static file hosting works (Netlify, Vercel, Cloudflare Pages, self-hosted Nginx, etc.). Just make sure the files are accessible via HTTPS. ZimaOS fetches store data from the backend (not from a browser), so CORS headers are not required.

### Why is `--base-url` required?

The frontend components that render app cards receive `index.json` data but don't know the host URL of your store. Without `--base-url`, resource paths like `apps/my-app/icon.png` are relative and the frontend cannot resolve them.

`--base-url` makes all resource URLs absolute so they work directly:

```bash
# GitHub Pages hosting
python3 scripts/build_appstore.py --source . --output dist \
  --base-url https://username.github.io/my-appstore
# icon: "https://username.github.io/my-appstore/apps/my-app/icon.png"

# jsDelivr CDN hosting
python3 scripts/build_appstore.py --source . --output dist \
  --base-url https://cdn.jsdelivr.net/gh/username/my-appstore@gh-pages
# icon: "https://cdn.jsdelivr.net/gh/username/my-appstore@gh-pages/apps/my-app/icon.png"
```

### What's the minimum viable store?

```
my-appstore/
├── Apps/
│   └── MyApp/
│       ├── docker-compose.yml    # with x-casaos block
│       └── icon.png
├── store-config.json
└── scripts/
    └── build_appstore.py
```

One app, one icon, one config file. That's it.
