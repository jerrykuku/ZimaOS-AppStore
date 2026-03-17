# ZimaOS AppStore Source Protocol v2 — 第三方商店指南

本指南用于说明如何基于 AppStore Source Protocol v2 构建兼容 ZimaOS 的第三方应用商店。

本文档适用范围：
- 面向构建/部署外部第三方商店的维护者。
- 如果你是在本仓库提交 PR，请参考 [CONTRIBUTING.md](../../CONTRIBUTING.md)。

> **📢 新增内容：** 我们在 `meta.json` 中新增了 7 个可选字段，可增强商店展示效果：`version`、`updateAt`、`releaseNotes`、`website`、`repo`、`support` 和 `docs`。这些字段在 [meta.json 章节](#metajson-after-build)中标注为 **[新增，可选]**。现有商店无需修改即可继续工作，但我们建议添加这些字段以改善应用列表的展示效果。

## 概览

只要能托管静态文件（GitHub Pages、Netlify、Cloudflare Pages、自建 Nginx 等），就可以作为 ZimaOS 商店源。你只需要输出一些 JSON 文件和应用资源，格式正确即可。

**源目录结构**（你维护的内容）：

```text
my-appstore/
├── Apps/
│   └── MyApp/
│       ├── docker-compose.yml    # 含 x-casaos
│       └── icon.svg              # 推荐
├── store-config.json             # 商店身份信息（输入）
├── supported-languages.json      # 输出语言列表（可选）
└── scripts/
    └── build_appstore.py         # 构建脚本
```

**输出目录结构**（部署内容）：

```text
dist/
├── assets/                        # 共享图片资源（仅一份）
│   └── apps/
│       ├── my-app/
│       │   ├── icon.svg
│       │   ├── icon.png
│       │   ├── thumbnail.webp
│       │   └── screenshot-*.webp
│       └── another-app/
│           └── ...
├── en_US/                         # 按语言分目录
│   ├── store.json                 # 单语言商店信息
│   ├── index.json                 # 单语言应用列表
│   └── apps/
│       └── my-app/
│           ├── docker-compose.yml # 精简的单语言 x-casaos
│           └── meta.json          # 单语言元数据
├── zh_CN/
│   └── ...                        # 相同结构，中文字符串
└── de_DE/
    └── ...
```

用户在 ZimaOS 中添加你的商店 URL：
```
https://username.github.io/my-appstore
```

---

## 快速开始

### 1. 创建仓库

创建一个新的 GitHub 仓库，结构如下：

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
├── supported-languages.json     (可选，默认仅生成 en_US)
├── scripts/
│   └── build_appstore.py
└── .github/
    └── workflows/
        └── deploy.yml
```

### 2. 编写 store-config.json

此文件标识你的商店。构建脚本会读取它并将 `store.json` 输出到部署目录。

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

**`store_id` 规则：**
- 仅小写字符，匹配 `[a-z0-9-]`
- 必须全局唯一（选择一个有特色的名称）
- 不能使用保留值 `zimaos-official`

### 3. 编写应用 docker-compose.yml

每个应用都位于 `Apps/` 下的独立目录中。目录名称不重要（应用 ID 来自 compose 文件）。

**docker-compose.yml：**

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
  # --- 运行时字段（构建后保留在 compose 中）---
  main: my-app
  index: /
  port_map: "8080"
  scheme: http
  # 在源 compose 中可以是任何可访问的 URL。
  # 构建输出会将其重写为 --base-url 下的 apps/my-app/icon.svg（或 icon.png）。
  icon: https://cdn.jsdelivr.net/gh/username/my-appstore@main/Apps/MyApp/icon.svg
  title:
    en_US: My App
    zh_CN: 我的应用
  # --- 元数据字段（由构建脚本提取到 meta.json）---
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

> 你可以在一个 docker-compose.yml 中编写所有内容——构建脚本会自动将其拆分为精简的 compose 文件 + meta.json。

**多服务示例**（带数据库的应用）：

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
  main: my-wiki           # <- 指向 Web UI 服务，而不是数据库
  index: /
  port_map: "3000"
  # ... 其他字段 ...
```

对于多服务应用，`main` 必须指向提供 Web UI 的服务。

### 4. 设置 CI/CD

从[官方仓库](https://github.com/IceWhaleTech/ZimaOS-AppStore)复制 `scripts/build_appstore.py`。

创建 `.github/workflows/deploy.yml`：

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

### 5. 商店 URL

工作流运行后，你的商店可通过以下地址访问：

```
https://cdn.jsdelivr.net/gh/username/my-appstore@gh-pages
```

用户可以在 ZimaOS 设置中将此 URL 添加为商店源。

---

### 6. 替代方案：不使用 gh-pages / 不使用 jsDelivr

如果你不想使用 `gh-pages` 或 jsDelivr，仍然可以使用相同的构建脚本，并将 `dist/` 部署到任何静态托管。

使用仅上传构建产物的通用构建工作流：

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
- 自建 Nginx/Caddy（将 `dist/` 作为静态文件在 HTTPS 域名下提供服务）

你的最终商店 URL 将与 `--base-url` 相同（例如 `https://store.example.com`）。
- 自建 Nginx/Caddy（HTTPS 静态站点）

最终商店地址应与 `--base-url` 保持一致。

---

## 从 v1 升级

如果你已有基于旧版 CasaOS AppStore 协议（zip 包分发）构建的第三方商店，按以下步骤升级到 v2。

### 变更概览

| | v1（旧版） | v2（新版） |
|---|----------|----------|
| 分发方式 | zip 包下载 | 静态站点（GitHub Pages、CDN 等） |
| 商店身份 | 无 | `store-config.json` → `store.json` |
| 构建脚本 | 无 | `scripts/build_appstore.py` |
| 元数据 | 全部在 `x-casaos` 块中 | 拆分为 compose + `meta.json` |
| 分类 | 自由定义 | 标准化（9 个官方名称） |
| 更新机制 | 全量 zip 重新下载 | 增量更新（`content_hash`） |

### 现有的 `Apps/` 目录可直接使用

v2 构建脚本读取相同的 `Apps/` 目录结构。你现有的 `docker-compose.yml` 文件完全兼容——构建脚本会自动：

- 移除服务级 `services.xxx.x-casaos` 块
- 将顶层 `x-casaos` 拆分为运行时字段（保留在 compose 中）+ 元数据（提取到 `meta.json`）
- 归一化 i18n 语言键（`en_us` → `en_US`）
- 优化和转换图片资源

### 第 1 步：添加 `store-config.json`

在仓库根目录创建此文件：

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

### 第 2 步：复制构建脚本

从[官方仓库](https://github.com/IceWhaleTech/ZimaOS-AppStore)复制 `scripts/build_appstore.py` 到你的 `scripts/` 目录。

### 第 3 步：更新应用分类

v2 要求使用标准化分类。将每个应用 `x-casaos` 块中的 `category` 字段更新为 9 个官方名称之一。

常见旧分类的映射建议：

| 旧分类 | 新分类 |
|--------|--------|
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

完整的有效分类列表：`Media`、`Productivity`、`Home`、`Networking`、`AI`、`Finance`、`Social`、`Developer`、`Others`

### 第 4 步：添加 CI/CD 工作流

参照[快速开始第 4 步](#4-设置-cicd)设置 GitHub Actions 自动构建和部署。

### 可选改进

- 添加 7 个新增元数据字段（`version`、`updateAt`、`releaseNotes`、`website`、`repo`、`support`、`docs`）以增强商店展示——参见 [meta.json](#metajson构建后)
- 添加 `supported-languages.json` 以支持多语言输出
- 将 PNG 图标替换为 SVG 以获得更好的质量

### 可保留的文件

- `featured-apps.json` 和 `recommend-list.json` 可以保留在仓库中——构建脚本会忽略它们
- `category-list.json` 可以保留但不再必需——分类会从应用中自动提取

---

## 文件格式说明

### store-config.json（输入）→ store.json（输出）

你在仓库根目录编写 `store-config.json`。构建脚本会为每种语言生成 `dist/{locale}/store.json`，其中 i18n 字段已解析为纯字符串。当用户添加你的商店 URL 时，ZimaOS 会获取 `{url}/{locale}/store.json` 来验证商店身份。

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

由构建脚本自动生成，每个语言目录下各一份（`dist/{locale}/index.json`）。包含所有应用摘要，用于快速加载。所有 i18n 字段已解析为目标语言的纯字符串。

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
      "category": "Utilities",
      "author": "Your Name",
      "developer": "Original Developer",
      "architectures": ["amd64", "arm64"],
      "icon": "assets/apps/my-app/icon.svg",
      "thumbnail": "assets/apps/my-app/thumbnail.webp",
      "compose_url": "en_US/apps/my-app/docker-compose.yml",
      "meta_url": "en_US/apps/my-app/meta.json",
      "content_hash": "a1b2c3d4"
    }
  ]
}
```

> 图片路径（如 `icon`、`thumbnail`）指向共享的 `assets/` 目录。`compose_url` 和 `meta_url` 包含语言前缀。所有路径相对于 `base_url`。

### 构建后的 docker-compose.yml

构建脚本在 `x-casaos` 中仅保留以下字段：

| 字段 | 用途 | 示例 |
|------|------|------|
| `main` | 主服务名称（Web UI 入口点） | `my-app` |
| `index` | Web UI 根路径 | `/` |
| `port_map` | Web UI 发布端口（必须是**字符串**，使用引号） | `"8080"` |
| `scheme` | Web UI 协议（`http` 或 `https`） | `http` |
| `icon` | 图标 URL（安装后在 ZimaOS 仪表盘中显示） | `https://...` |
| `title` | 应用名称（解析为目标语言的纯字符串） | `My App` |

其余字段会移至 `meta.json`。

> **重要：** `port_map` 必须是 YAML 字符串，不能是整数。始终使用引号：`port_map: "8080"`，而不是 `port_map: 8080`。

### meta.json（构建后）

| 字段 | 类型 | 说明 |
|------|------|------|
| `tagline` | `string` | 一句话简介（解析为目标语言的纯字符串） |
| `description` | `string` | 详细描述（解析为纯字符串，支持 Markdown，具体渲染由客户端决定） |
| `thumbnail` | `string` | 缩略图路径，相对于 `base_url`（如 `assets/apps/my-app/thumbnail.webp`） |
| `screenshot_link` | `string[]` | 截图路径，相对于 `base_url`（如 `assets/apps/my-app/screenshot-1.webp`） |
| `tips` | `object` | 安装提示（解析为纯字符串，可选） |
| `author` | `string` | 打包者 |
| `developer` | `string` | 上游开发者 |
| `category` | `string` | 应用分类 |
| `architectures` | `string[]` | 支持的 CPU 架构 |
| `version` | `string` | **[新增，可选]** 应用版本号，可增强商店展示 |
| `updateAt` | `string` | **[新增，可选]** 应用更新日期（建议 `YYYY-MM-DD`，如 `"2026-03-01"`），可增强商店展示 |
| `releaseNotes` | `string` | **[新增，可选]** 版本更新日志（解析为纯字符串），可增强商店展示 |
| `website` | `string` | **[新增，可选]** 官方网站地址，可增强商店展示 |
| `repo` | `string` | **[新增，可选]** 源码仓库地址，可增强商店展示 |
| `support` | `string` | **[新增，可选]** 支持地址，可增强商店展示 |
| `docs` | `string` | **[新增，可选]** 文档地址，可增强商店展示 |

> 注意：`title` 与 `icon` 保留在 `docker-compose.yml` 的顶层 `x-casaos` 中，不写入 `meta.json`。

**Tips 格式：**

```yaml
tips:
  before_install:
    en_US: This app requires at least 4GB RAM.
    zh_CN: 此应用需要至少 4GB 内存。
```

Tips 会在安装前显示给用户。`tips` 下的键（例如 `before_install`）支持 i18n 值。

### 图片资源规则

所有图片资源输出到共享的 `assets/apps/{app-id}/` 目录（不会在每个语言目录中重复）。

| 文件 | 源格式 | 构建输出 | 必需 |
|------|--------|----------|------|
| `icon` | `.svg`（推荐）、`.png`、`.jpg`、`.webp` | 如果存在 `.svg`：保留 `icon.svg` 并生成 `icon.png`；否则保留原始图标文件 | 是 |
| `thumbnail` | `.png`、`.jpg`、`.jpeg`、`.webp` | 转换为 `.webp`（宽度过大时会缩放） | 否 |
| `screenshot-{n}` | `.png`、`.jpg`、`.jpeg`、`.webp` | 转换为 `.webp`（宽度过大时会缩放） | 否 |

- 非图标的光栅图像使用 Pillow 优化（WebP 质量 `85`，最大宽度 `1280`）
- SVG 文件按原样复制（但图标在 `rsvg-convert` 可用时也会生成 PNG 兜底）

---

## 图标 URL 行为

应用图标在两个地方使用：

| 位置 | 字段 | 行为 |
|------|------|------|
| **商店列表**（安装前） | `index.json` → `icon` | 从构建输出生成（`assets/apps/<app-id>/icon.svg` 或 `icon.png`） |
| **仪表盘**（安装后） | `docker-compose.yml` → `x-casaos.icon` | 构建脚本会重写为相同的构建输出 URL |

在源 compose 中，你仍可设置稳定 URL。构建时，`x-casaos.icon` 会根据 `--base-url` 替换为构建输出 URL。

---

## ZimaOS 运行时变量

ZimaOS 提供以下在安装时解析的变量：

| 变量 | 说明 | 示例值 |
|------|------|--------|
| `$AppID` | 应用唯一标识（用于数据隔离） | `my-app` |
| `$TZ` | 系统时区 | `America/New_York` |
| `$PUID` | 主机用户 ID | `1000` |
| `$PGID` | 主机组 ID | `1000` |

在卷路径中使用 `$AppID` 来隔离应用数据：

```yaml
volumes:
  - type: bind
    source: /DATA/AppData/$AppID/config
    target: /config
```

---

## i18n 规范

所有语言键必须使用 `ll_CC` 格式（语言小写 + 国家大写）：

| 正确 | 错误 |
|------|------|
| `en_US` | `en_us` |
| `zh_CN` | `zh_cn` |
| `de_DE` | `de_de` |

构建脚本会自动归一化以下字段的语言键：
- `store-config.json`：`name`、`description`
- `x-casaos`：`title`、`tagline`、`description`、`releaseNotes`、`tips` 下的每个嵌套 locale 对象

至少为所有 i18n 字段提供 `en_US`。其他语言缺失的翻译会自动回退到 `en_US`。

### 多语言输出

构建脚本读取 `supported-languages.json`（一个 locale 代码的 JSON 数组），为每种语言生成一套完整的输出文件。在源 `docker-compose.yml` 中，你仍然以 locale 键对象的形式编写 i18n 字段：

```yaml
title:
  en_US: My App
  zh_CN: 我的应用
```

构建脚本会在每个语言目录中将其解析为纯字符串。例如，`dist/zh_CN/apps/my-app/meta.json` 中将包含 `"tagline": "做很棒的事情"` 而不是 `"tagline": { "en_US": "...", "zh_CN": "..." }`。

如果 `supported-languages.json` 不存在，则仅生成 `en_US` 输出。

---

## App ID 规则

应用 ID 决定了 Docker 项目名称以及 ZimaOS 如何识别你的应用。

**解析优先级：**

```
store_app_id  (在 x-casaos 中，如果设置)
    ↓ 未设置
compose name  (顶层 "name:" 字段)
    ↓ 未设置
directory name (转小写)
```

**规则：**
- 必须是小写，匹配 `[a-z0-9-_]`
- 在你的商店内必须唯一
- 不用担心与其他商店冲突——ZimaOS 在安装时会自动通过添加你的 `store_id` 前缀来处理隔离

---

## 分类

ZimaOS 中的应用分类是标准化的。你必须在每个应用的 `x-casaos` 块中将 `category` 字段设置为以下官方分类名称之一：

| 分类 | 说明 |
|------|------|
| `Media` | 视频、音乐、照片、流媒体、字幕工具、媒体服务器 |
| `Productivity` | 笔记、办公工具、项目管理、自动化、实用工具 |
| `Home` | 智能家居、家庭自动化、存储管理、个人仪表盘 |
| `Networking` | VPN、DNS、反向代理、防火墙、网络监控 |
| `AI` | 机器学习、大语言模型、图像生成、AI 工具 |
| `Finance` | 预算、记账、加密货币、财务追踪 |
| `Social` | 聊天、论坛、社交媒体、通讯平台 |
| `Developer` | 代码托管、CI/CD、数据库、开发工具、容器 |
| `Others` | 不属于以上分类的应用 |

不支持自定义分类名称——使用未识别分类的应用将无法在 ZimaOS 中正确显示。

---

## 更新应用

要更新应用（例如升级镜像版本）：

1. 编辑 `docker-compose.yml` —— 更改镜像标签、调整配置等
2. 推送到 `main` 分支 —— CI 会自动重新构建和部署
3. 应用在 `index.json` 中的 `content_hash` 会改变，因此 ZimaOS 设备在用户下次打开商店时会检测到更新

协议中没有单独的版本控制或更新日志机制。`content_hash` 会自动处理变更检测。

---

## 带宽与更新效率

v2 协议使用**增量更新**而非完整包下载，这显著降低了商店维护者和 ZimaOS 设备的带宽消耗。

### 更新工作原理

当用户打开应用商店时，ZimaOS 会使用 HTTP `ETag` 头请求 `{locale}/index.json`：

```
1. GET {locale}/index.json (with If-None-Match: <cached ETag>)
   ├─ 304 Not Modified → 无数据传输，使用本地缓存
   └─ 200 OK → 比较每个应用的 content_hash 与本地缓存
                 ├─ hash 匹配 → 跳过（无需下载）
                 └─ hash 不同 → 仅获取该应用的 compose + meta
```

### 带宽对比

假设你的商店有 20 个应用，你更新了 1 个应用：

| 方式 | 下载内容 | 流量 |
|------|----------|------|
| 旧方式（zip） | 所有 20 个应用作为完整包重新下载 | ~200 KB+ |
| **新方式（v2）** | index.json + 1 个变更应用的 compose + meta | **~15 KB** |

当**完全没有更新**时，v2 协议几乎不消耗流量——`304 Not Modified` 响应的主体为空。

### 为什么这很重要

- **降低托管成本**：GitHub Pages 有 100 GB/月的带宽限制。增量更新意味着你的商店可以在该配额内服务更多设备。
- **用户体验更快**：检查更新只需约 100-200ms（单个 HTTP 请求），因此商店始终感觉很快。
- **扩展性好**：如果 1,000 台设备每天检查你的商店但没有变化，总带宽接近零。使用旧的 zip 方式，将是 1,000 次完整下载。

### 客户端何时检查更新？

ZimaOS **在用户打开应用商店时**检查更新——没有后台轮询，没有定期下载。这意味着：

- 很少打开商店的设备消耗零带宽
- 打开商店的设备始终看到最新数据
- 没有后台同步造成的流量浪费

---

## FAQ

### 第三方商店的应用 ID 可以和官方商店重复吗？

可以。官方商店和第三方商店的应用在 ZimaOS 中是分开显示的，不会出现冲突。即使应用 ID 相同，它们也会在各自的商店页面中独立展示。

### 如果其他第三方商店和我用了同一个应用 ID 会怎样？

没问题。ZimaOS 在安装时会用你的 `store_id` 作为 Docker 项目名称的前缀，因此 `my-store_dashboard` 和 `other-store_dashboard` 在 Docker 层面完全隔离。

### 一定要跑构建脚本吗？

是。构建脚本负责：
- `store-config.json` → 按语言生成 `store.json`
- `docker-compose.yml` → 精简 compose + `meta.json`
- 按语言生成 `index.json`（含 `content_hash`）
- 将 i18n 字段解析为各语言的纯字符串（缺失翻译回退到 `en_US`）
- i18n 归一化
- 资源复制/优化到共享 `assets/` 目录（包含 `icon.svg` 到 `icon.png` 的兜底转换）

你不应该手动创建这些输出文件。

### 可以将商店托管在 GitHub Pages 以外的地方吗？

可以。任何静态文件托管都可以（Netlify、Vercel、Cloudflare Pages、自建 Nginx 等）。只需确保文件可通过 HTTPS 访问。ZimaOS 从后端获取商店数据（不是从浏览器），因此不需要 CORS 头。

### 必须用 jsDelivr 吗？

不是。`jsDelivr` 只是可选 CDN。你可以把 `--base-url` 设为任意可访问 HTTPS 域名，例如：
- `https://username.github.io/my-appstore`
- `https://store.example.com`
- `https://my-store.pages.dev`

### 为什么建议传 `--base-url`？

前端组件接收 `index.json` 数据但不知道你的商店的主机 URL。如果没有 `--base-url`，像 `assets/apps/my-app/icon.svg` 这样的资源路径是相对的，前端无法解析它们。

`--base-url` 使所有资源 URL 变为绝对路径，因此可以直接使用：

```bash
# GitHub Pages 托管
python3 scripts/build_appstore.py --source . --output dist \
  --base-url https://username.github.io/my-appstore
# icon: "https://username.github.io/my-appstore/assets/apps/my-app/icon.svg"

# jsDelivr CDN 托管
python3 scripts/build_appstore.py --source . --output dist \
  --base-url https://cdn.jsdelivr.net/gh/username/my-appstore@gh-pages
# icon: "https://cdn.jsdelivr.net/gh/username/my-appstore@gh-pages/assets/apps/my-app/icon.svg"
```

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

一条应用、一张图标、一个 store 配置文件即可启动。如需多语言输出，添加 `supported-languages.json`。
