# ZimaOS AppStore Source Protocol v2 — 第三方商店指南

本指南用于说明如何基于 AppStore Source Protocol v2 构建兼容 ZimaOS 的第三方应用商店。

本文档适用范围：
- 面向构建/部署外部第三方商店的维护者。
- 如果你是在本仓库提交 PR，请参考 [CONTRIBUTING.md](../../CONTRIBUTING.md)。

## 概览

只要能托管静态文件（GitHub Pages、Netlify、Cloudflare Pages、自建 Nginx 等），就可以作为 ZimaOS 商店源。

**源目录结构**（你维护的内容）：

```text
my-appstore/
├── Apps/
│   └── MyApp/
│       ├── docker-compose.yml    # 含 x-casaos
│       └── icon.svg              # 推荐
├── store-config.json             # 商店身份信息（输入）
└── scripts/
    └── build_appstore.py         # 构建脚本
```

**输出目录结构**（部署内容）：

```text
dist/
├── store.json
├── index.json
└── apps/
    ├── my-app/
    │   ├── docker-compose.yml    # 仅保留精简 x-casaos
    │   ├── meta.json
    │   ├── icon.svg              # 源有 svg 时保留
    │   ├── icon.png              # 由 svg 生成的兜底图
    │   ├── thumbnail.webp        # 由 thumbnail.* 转换
    │   └── screenshot-*.webp     # 由 screenshot-*.* 转换
    └── another-app/
        └── ...
```

用户在 ZimaOS 中添加商店时，填写你的商店 URL 即可。

---

## 快速开始

### 1. 创建仓库

```text
my-appstore/
├── Apps/
│   └── MyApp/
│       ├── docker-compose.yml
│       ├── icon.svg             (推荐) / icon.png
│       ├── thumbnail.png        (可选，.jpg/.jpeg/.webp 也支持)
│       ├── screenshot-1.png     (可选，.jpg/.jpeg/.webp 也支持)
│       └── screenshot-2.png     (可选)
├── store-config.json
├── scripts/
│   └── build_appstore.py
└── .github/
    └── workflows/
        └── deploy.yml
```

### 2. 编写 store-config.json

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

`store_id` 规则：
- 仅小写字符，匹配 `[a-z0-9-]`
- 必须全局唯一
- 不能使用保留值 `zimaos-official`

### 3. 编写应用 docker-compose.yml

```yaml
name: my-app
services:
  my-app:
    image: myrepo/my-app:1.0.0
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
  main: my-app
  index: /
  port_map: "8080"
  scheme: http
  # 源 compose 可写任意可访问 URL，构建后会被重写为 dist 内资源 URL
  icon: https://cdn.jsdelivr.net/gh/username/my-appstore@main/Apps/MyApp/icon.svg
  title:
    en_US: My App
    zh_CN: 我的应用

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
    - screenshot-1.png
  thumbnail: thumbnail.png
  tips: {}
  version: "1.0.0"
  updateAt: "2026-03-01"
  releaseNotes:
    en_US: First release
```

说明：
- 你只需要维护一份 `docker-compose.yml`。
- 构建脚本会自动拆分出精简 compose + `meta.json`。

### 4. 配置 CI/CD（gh-pages + jsDelivr 示例）

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
          curl -fsSL "https://purge.jsdelivr.net/gh/${{ github.repository }}@gh-pages/index.json" || true
```

### 5. 商店 URL

部署完成后可使用类似 URL：

```text
https://cdn.jsdelivr.net/gh/username/my-appstore@gh-pages
```

---

### 6. 替代方案：不使用 gh-pages / 不使用 jsDelivr

你可以只构建 `dist/`，再部署到任意静态托管。

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

随后将 `dist/` 部署到：
- Netlify（发布目录 `dist`）
- Cloudflare Pages（输出目录 `dist`）
- 自建 Nginx/Caddy（HTTPS 静态站点）

最终商店地址应与 `--base-url` 保持一致。

---

## 文件格式说明

### store-config.json（输入）→ store.json（输出）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `version` | `int` | 是 | 协议版本，必须为 `2` |
| `store_id` | `string` | 是 | 商店唯一标识，`[a-z0-9-]` |
| `name` | `object` | 是 | 商店名称（i18n） |
| `description` | `object` | 否 | 商店描述（i18n） |
| `maintainer` | `string` | 是 | 维护者 |
| `url` | `string` | 否 | 项目地址 |
| `icon` | `string` | 否 | 商店图标 URL |

### index.json

自动生成，包含分类和应用摘要列表。

说明：
- 有 `category-list.json` 时，分类按该文件输出。
- 无 `category-list.json` 时，按应用 `x-casaos.category` 自动提取。

### 构建后的 docker-compose.yml

构建后 `x-casaos` 仅保留以下字段：
- `main`
- `index`
- `port_map`
- `scheme`
- `icon`
- `title`

注意：
- `port_map` 必须是字符串，建议写成 `"8080"`。
- 其余字段会进入 `meta.json`。

### meta.json

常见字段：
- `title/icon` 不在 `meta.json`，保留在 compose 的 `x-casaos`。
- `description`、`releaseNotes` 可写 Markdown 文本（具体渲染由客户端决定）。
- `updateAt` 建议使用 `YYYY-MM-DD`，如 `"2026-03-01"`。
- `thumbnail`、`screenshot_link` 在传入 `--base-url` 时会被写成绝对 URL。

### 图片资源规则

- `icon`：
  - 若存在 `icon.svg`：保留 `icon.svg`，并尝试生成 `icon.png`。
  - 若不存在 `icon.svg`：直接使用现有 `icon.*`，不额外转换。
- `thumbnail`/`screenshot-*`：
  - 支持 `.png/.jpg/.jpeg/.webp`
  - 构建时会优化并输出 `.webp`（宽度过大会缩放）

---

## i18n 规范

语言键统一使用 `ll_CC`：
- 正确：`en_US`、`zh_CN`
- 错误：`en_us`、`zh_cn`

构建脚本会自动归一化：
- `store-config.json`：`name`、`description`
- `x-casaos`：`title`、`tagline`、`description`、`tips` 内嵌 i18n

建议所有 i18n 字段至少提供 `en_US`。

---

## App ID 规则

优先级：
1. `x-casaos.store_app_id`
2. 顶层 `name`
3. 目录名（转小写）

约束：
- 建议匹配 `[a-z0-9-_]`
- 在同一商店内必须唯一

---

## FAQ

### 第三方商店的应用 ID 可以和官方商店重复吗？
可以。即使应用 ID 相同，运行层会通过 `store_id` 做隔离（例如 Docker project name 带前缀），不会直接冲突。

### 如果其他第三方商店和我用了同一个应用 ID 会怎样？
通常也不会冲突。安装时会基于各自的 `store_id` 做隔离，例如 `my-store_dashboard` 与 `other-store_dashboard` 会分开。

### 可以不用 GitHub Pages 吗？
可以，任何 HTTPS 静态托管都可用。

### 必须用 jsDelivr 吗？
不是。`jsDelivr` 只是可选 CDN。你可以把 `--base-url` 设为任意可访问 HTTPS 域名，例如：
- `https://username.github.io/my-appstore`
- `https://store.example.com`
- `https://my-store.pages.dev`

### 一定要跑构建脚本吗？
是。构建脚本负责：
- `store-config.json` → `store.json`
- `docker-compose.yml` → 精简 compose + `meta.json`
- 分类提取
- 生成带 `content_hash` 的 `index.json`
- i18n 归一化
- 资源复制/优化（包含 `icon.svg` 到 `icon.png` 的兜底转换）

### 为什么建议传 `--base-url`？
因为可将资源路径输出为绝对 URL，前端解析更稳定。若不传，`apps/my-app/icon.svg` 这类相对路径在某些前端上下文中可能无法正确解析。

### 最小可用商店结构是什么？

```text
my-appstore/
├── Apps/
│   └── MyApp/
│       ├── docker-compose.yml    # 含 x-casaos
│       └── icon.svg (或 icon.png)
├── store-config.json
└── scripts/
    └── build_appstore.py
```

一条应用、一张图标、一个 store 配置文件即可启动。
