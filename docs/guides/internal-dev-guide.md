# ZimaOS AppStore v2 内部开发指导文档

## 1. 背景

### 1.1 现有方案

当前 AppStore 元数据的分发流程：

```
源仓库 (Apps/ + category-list.json + featured-apps.json + recommend-list.json)
    │
    ▼  CI 打包 (release_zip.yml)
main.zip (仅含 YAML + JSON，不含图片)
    │
    ▼  推送到 gh-pages 分支 + 阿里云 OSS
客户端下载整个 zip → 解压到 /var/lib/casaos/appstore/default
```

**存在的问题：**

- 每次更新需下载完整 zip 包（即使只改动一个应用）
- docker-compose.yml 中混合了 Docker 原生定义和 CasaOS 扩展元数据，职责不清晰
- 服务级 `x-casaos` 块（端口/卷/环境变量的 UI 描述）增加了 compose 文件复杂度
- i18n locale key 命名不统一（`en_us` / `en_US` / `zh_cn` / `zh_CN` 混用）
- `featured-apps.json` 和 `recommend-list.json` 作为运营数据放在 Git 仓库中，每次调整需提 PR，流程过重

### 1.2 新方案目标

- 将仓库部署为 GitHub Pages 静态站点，提供在线 JSON API
- 客户端通过索引按需加载应用数据，支持增量更新
- 拆分 docker-compose.yml 为纯净 compose 定义 + 独立 meta.json
- 统一 i18n locale key 为 `ll_CC` 格式（如 `en_US`、`zh_CN`）
- 分离运营数据到 ZimaSpace 服务层
- 定义标准商店源协议，支持三方商店生态

---

## 2. 整体架构

### 2.1 三层架构总览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Official Store (GitHub)                       │
│                                                                         │
│  App Metadata Repo ──▶ GitHub Actions ──┬──▶ GitHub Pages (海外)       │
│  (Apps/ 目录)            (构建脚本)      └──▶ Alibaba OSS  (中国)       │
│                                               index.json + 静态资源     │
└───────────┬─────────────────────────────────────────────────────────────┘
            │
            │  (数据层：纯静态，CDN 分发)
            │
            ├──────────────────────────────────────────┐
            ▼                                          ▼
┌──────────────────────────────┐  ┌──────────────────────────────────────┐
│     ZimaSpace 运营层          │  │         Third-party Stores           │
│     (独立服务，不同步 index)   │  │                                      │
│                              │  │  三方开发者用相同协议搭建自己的商店源  │
│  Operation Config (推荐/权重) │  │  GitHub Pages 部署                   │
│  Star / Comment API          │  │  输出兼容的 store.json + index.json   │
│         │                    │  │                                      │
│         ▼                    │  └──────────────────┬───────────────────┘
│  operations.json             │                     │
│  (仅运营 + 交互数据，~5-10KB) │                     │
└──────────┬───────────────────┘                     │
           │                                         │
           ▼                                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            Consumers                                    │
│                                                                         │
│  客户端并行请求:                                                         │
│  ├── {locale}/index.json ← 直连 CDN（OSS / GitHub Pages）             │
│  └── operations.json   ← ZimaSpace API（可选，失败不影响核心功能）       │
│                                                                         │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────────────┐ │
│  │ Online Web Store │  │ ZimaOS AppStore  │  │ Third-party Consumer   │ │
│  │ (index+运营数据)  │  │ (index+运营数据)  │  │ (只用 {locale}/index.json) │ │
│  └─────────────────┘  └──────────────────┘  └────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据职责分离

| 数据类型 | 归属 | 输出文件 | 说明 |
|----------|------|----------|------|
| App 定义（compose + 元数据） | Official Store | `index.json` + 各应用文件 | 应用是什么、怎么运行、支持什么架构 |
| 应用分类（category 字段） | Official Store | `index.json` + `meta.json` | 结构性标签，随应用元数据维护 |
| 精选/推荐列表 | **ZimaSpace** | `operations.json` | 运营性数据，运营团队动态调整，无需走 Git 流程 |
| Star / Rating / Comments | **ZimaSpace** | `operations.json` + 独立 API | 用户交互数据，存储在数据库中 |
| 首页 Banner / 推广文案 | **ZimaSpace** | `operations.json` | Web 端运营配置 |

**关键设计原则：index.json 与 operations.json 完全分离**

- `index.json` 由 CI 构建、推送到 CDN（GitHub Pages / OSS），客户端直连获取
- `operations.json` 由 ZimaSpace 动态生成，仅包含运营和用户交互数据
- 两者互不依赖——ZimaSpace 不需要同步或代理 index.json
- ZimaSpace 宕机时，商店核心功能（浏览、搜索、安装）不受影响

### 2.3 Official Store 输出结构

```
GitHub Pages (dist/)
├── assets/
│   └── apps/                     # 共享图片资源（仅一份）
│       ├── jellyfin/
│       │   ├── icon.svg
│       │   ├── icon.png
│       │   ├── thumbnail.webp
│       │   └── screenshot-*.webp
│       └── ...
├── en_US/
│   ├── store.json                # 单语言商店信息
│   ├── index.json                # 单语言应用索引
│   └── apps/
│       ├── jellyfin/
│       │   ├── docker-compose.yml
│       │   └── meta.json
│       └── ...
├── zh_CN/
│   └── ...                       # 相同结构，中文字符串
└── de_DE/
    └── ...
```

---

## 3. 文件格式规范

### 3.1 store.json（商店身份标识）

每个商店源在每个语言目录下包含此文件（`dist/{locale}/store.json`），用于标识商店身份。

```json
{
  "version": 2,
  "store_id": "zimaos-appstore",
  "name": "ZimaOS 官方商店",
  "description": "由 ZimaOS 团队维护的官方应用商店",
  "maintainer": "IceWhaleTech",
  "url": "https://github.com/IceWhaleTech/ZimaOS-AppStore"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `version` | `int` | 是 | 协议版本号，当前为 `2` |
| `store_id` | `string` | 是 | 商店唯一标识，全小写，`[a-z0-9-]` |
| `name` | `string` | 是 | 商店名称（已按目标语言解析） |
| `description` | `string` | 否 | 商店描述（已按目标语言解析） |
| `maintainer` | `string` | 是 | 维护者名称 |
| `url` | `string` | 否 | 商店项目主页 |

### 3.2 index.json（全局索引）

客户端首先请求 `{locale}/index.json`，获取该语言下所有应用摘要信息和变更追踪数据。

```json
{
  "version": 2,
  "updated_at": "2026-03-03T06:05:07Z",
  "base_url": "https://cdn.jsdelivr.net/gh/IceWhaleTech/ZimaOS-AppStore@gh-pages/",
  "app_count": 158,
  "apps": [
    {
      "id": "jellyfin",
      "title": "Jellyfin",
      "tagline": "The personal Media System",
      "category": "Media",
      "author": "CasaOS Team",
      "developer": "Jellyfin",
      "architectures": ["amd64", "arm64"],
      "icon": "assets/apps/jellyfin/icon.svg",
      "thumbnail": "assets/apps/jellyfin/thumbnail.webp",
      "compose_url": "en_US/apps/jellyfin/docker-compose.yml",
      "meta_url": "en_US/apps/jellyfin/meta.json",
      "content_hash": "a1b2c3d4"
    }
  ]
}
```

| 字段 | 说明 |
|------|------|
| `version` | 索引格式版本号，当前为 `2` |
| `updated_at` | 索引构建时间（UTC ISO 8601） |
| `base_url` | 资源基础 URL（以 `/` 结尾） |
| `app_count` | 应用总数 |
| `apps[].id` | 应用唯一标识 |
| `apps[].content_hash` | 该应用 `compose + meta` 的 SHA-256 前 8 位，用于增量更新判断 |
| `apps[].compose_url` | 含语言前缀的 compose 相对路径 |
| `apps[].meta_url` | 含语言前缀的 meta 相对路径 |

### 3.3 docker-compose.yml（拆分后）

保留纯净的 Docker Compose 定义，加上最小的 `x-casaos` 块（仅运行时必需字段）。

**保留在 compose 中的 `x-casaos` 字段：**

| 字段 | 用途 | 示例 |
|------|------|------|
| `main` | 主服务标识（多服务应用的 Web UI 入口） | `jellyfin` |
| `index` | Web UI 根路径 | `/` |
| `port_map` | 主要 Web UI 对外端口 | `"8097"` |
| `scheme` | Web UI 协议（`http` 或 `https`） | `http` |
| `icon` | 应用图标 URL（运行时仪表盘显示用） | `https://cdn.jsdelivr.net/...` |
| `title` | 应用名称（构建后解析为目标语言字符串） | `Jellyfin` |

**移除的内容：**

- 服务级 `services.xxx.x-casaos` 块全部移除
- 顶层 `x-casaos` 中除上述 6 个字段外的所有字段移至 meta.json

**示例：**

```yaml
name: jellyfin
services:
  jellyfin:
    image: linuxserver/jellyfin:10.10.7
    ports:
      - target: 8096
        published: "8097"
        protocol: tcp
    volumes:
      - type: bind
        source: /DATA/AppData/$AppID/config
        target: /config
    environment:
      TZ: $TZ
      PUID: $PUID
    restart: unless-stopped
    container_name: jellyfin
x-casaos:
  main: jellyfin
  index: /
  port_map: "8097"
  scheme: http
  icon: https://cdn.jsdelivr.net/gh/IceWhaleTech/ZimaOS-AppStore@gh-pages/assets/apps/jellyfin/icon.svg
  title: Jellyfin
```

### 3.4 meta.json（商店展示元数据）

基于 `Apps/2FAuth/docker-compose.yml` 的当前定义，`meta.json` 包含从顶层 `x-casaos` 拆分出来的非运行时字段。

| 字段 | 类型 | 说明 |
|------|------|------|
| `tagline` | `string` | 一句话简介（构建后解析为目标语言字符串） |
| `description` | `string` | 详细描述（构建后解析为目标语言字符串，支持 Markdown） |
| `thumbnail` | `string` | 缩略图路径（如 `assets/apps/<app-id>/thumbnail.webp`） |
| `screenshot_link` | `string[]` | 截图路径列表（如 `assets/apps/<app-id>/screenshot-1.webp`） |
| `tips` | `object` | 安装提示（内部值解析为目标语言字符串，可选） |
| `author` | `string` | 打包者 |
| `developer` | `string` | 上游开发者 |
| `category` | `string` | 标准分类名 |
| `architectures` | `string[]` | 支持的 CPU 架构 |
| `store_app_id` | `string` | 商店 App ID（可选，覆盖 compose name） |
| `version` | `string` | **[新增，可选]** 应用版本号，可增强商店展示 |
| `update_at` | `string` | **[新增，可选]** 应用更新日期（建议 ISO 8601 / `YYYY-MM-DD`），可增强商店展示 |
| `release_notes` | `string` | **[新增，可选]** 版本更新日志（构建后解析为目标语言字符串），可增强商店展示 |
| `website` | `string` | **[新增，可选]** 官方网站地址，可增强商店展示 |
| `repo` | `string` | **[新增，可选]** 源码仓库地址，可增强商店展示 |
| `support` | `string` | **[新增，可选]** 支持地址，可增强商店展示 |
| `docs` | `string` | **[新增，可选]** 文档地址，可增强商店展示 |
| `base_url` | `string` | 构建脚本附加的资源基础 URL（以 `/` 结尾） |

> 说明：`title` 与 `icon` 保留在 `docker-compose.yml` 的顶层 `x-casaos` 中，不写入 `meta.json`。

**示例：**

```json
{
  "tagline": "A web app to manage your Two-Factor Authentication (2FA) accounts and generate their security codes",
  "description": "2FAuth is a web based self-hosted alternative to One Time Passcode (OTP) generators like Google Authenticator, designed for both mobile and desktop.",
  "thumbnail": "assets/apps/2fauth/thumbnail.webp",
  "screenshot_link": [
    "assets/apps/2fauth/screenshot-1.webp",
    "assets/apps/2fauth/screenshot-2.webp",
    "assets/apps/2fauth/screenshot-3.webp"
  ],
  "tips": {},
  "author": "CasaOS Team",
  "developer": "Bubka",
  "category": "Productivity",
  "architectures": ["amd64", "386", "arm64", "arm"],
  "version": "1.0.0",
  "update_at": "2024-06-01",
  "release_notes": "Initial release",
  "website": "http://www.2fauth.com/",
  "repo": "http://www.2fauth.com/",
  "support": "http://www.2fauth.com/",
  "docs": "http://www.2fauth.com/",
  "base_url": "https://cdn.jsdelivr.net/gh/IceWhaleTech/ZimaOS-AppStore@gh-pages/"
}
```

### 3.5 i18n Locale Key 规范

所有 locale key 统一使用 **`ll_CC` 格式**（语言代码小写 + 国家代码大写）：

| 正确 | 错误 |
|------|------|
| `en_US` | `en_us` |
| `zh_CN` | `zh_cn` |
| `de_DE` | `de_de` |
| `fr_FR` | `fr_fr` |

构建脚本会在输出时自动标准化所有 locale key。

### 3.6 图片资源规范

| 类型 | 文件名 | 源格式 | 构建输出 | 必需 |
|------|--------|--------|----------|------|
| 应用图标 | `icon` | `.svg`（推荐）/`.png`/`.jpg`/`.webp` | 若有 `.svg`：保留 `icon.svg` 并生成 `icon.png`；否则保留源图标 | 是 |
| 介绍图（缩略图） | `thumbnail` | `.png`/`.jpg`/`.jpeg`/`.webp` | 转为 `.webp`（过宽时缩放） | 否 |
| 截图 | `screenshot-{n}` | `.png`/`.jpg`/`.jpeg`/`.webp` | 转为 `.webp`（过宽时缩放） | 否 |

**说明：**
- 若源目录存在 `icon.svg`，构建脚本会输出 `icon.svg`，并同时生成 `icon.png`（由 SVG 转换）
- 若不存在 `icon.svg`，则沿用源目录中的图标文件（如 `icon.png`）
- 非图标图片默认优化后输出 WebP（Pillow 可用时）

---

## 4. 构建脚本

### 4.1 使用方法

```bash
# 安装依赖
pip install pyyaml Pillow

# 构建（建议传 --base-url 生成完整资源 URL）
python3 scripts/build_appstore.py --source . --output dist \
  --base-url https://cdn.jsdelivr.net/gh/IceWhaleTech/ZimaOS-AppStore@gh-pages
```

`--base-url` 当前为可选参数；建议始终传入。构建产物中 `index.json` / `meta.json` 会带 `base_url`，客户端可据此拼接资源地址。

### 4.2 脚本功能

`scripts/build_appstore.py` 执行以下操作：

1. 读取 `store-config.json`，输出 `store.json`（含 i18n 标准化）
2. 遍历 `Apps/` 下所有应用目录
3. 解析每个 `docker-compose.yml`（兼容 `.yaml` 扩展名）
4. 拆分 `x-casaos` 块：运行时字段留在 compose，展示字段输出到 meta.json
5. 移除所有服务级 `services.xxx.x-casaos` 块
6. 标准化 i18n locale key（`en_us` → `en_US`）
7. 将 i18n 字段按目标语言解析为字符串（含回退）
8. 复制/优化图片到共享 `assets/apps/<app-id>/`；存在 `icon.svg` 时额外生成 `icon.png`
9. 为每个语言输出 `dist/{locale}/store.json`、`dist/{locale}/index.json` 与单语言 app 文件
10. 生成 `content_hash` 并写入 `index.json`（当前实现不输出 `categories` 字段）

### 4.3 App ID 解析优先级

```
store_app_id (x-casaos 中显式指定)
    ↓ 未设置
compose name 字段
    ↓ 未设置
目录名小写
```

### 4.4 构建产物统计

| 指标 | 获取方式 |
|------|----------|
| 处理应用数 | 构建日志 `Done! <apps> apps × <languages> languages` |
| 输出总大小 | `du -sh dist` |
| 纯元数据大小 | `find dist -type f \\( -name '*.json' -o -name '*.yml' \\) -exec du -ch {} + | tail -n 1` |
| index.json 大小 | `du -h dist/en_US/index.json`（或目标 locale） |

---

## 5. 客户端缓存机制

### 5.1 增量更新流程

```
┌───────────────────────────────────────────────┐
│ 客户端启动 / 用户打开商店                       │
└──────────┬────────────────────────────────────┘
           ▼
┌───────────────────────────────────────────────┐
│ GET {locale}/index.json                       │
│ 请求头: If-None-Match: <上次的 ETag>           │
│ (GitHub Pages 原生支持 ETag)                   │
└──────────┬──────────────┬─────────────────────┘
           │              │
     304 Not Modified   200 OK (有更新)
           │              │
           ▼              ▼
     使用本地缓存    对比每个 app 的 content_hash
                    与本地缓存的 hash
                         │
                    ┌────┴────┐
                  相同       不同
                    │         │
                  跳过    GET {locale}/apps/{id}/meta.json
                         GET {locale}/apps/{id}/docker-compose.yml
                         (仅变更的应用)
                              │
                              ▼
                         写入本地缓存
```

### 5.2 客户端本地缓存结构

```
~/.casaos/appstore/
├── cache.json              # 缓存元信息
│   {
│     "last_etag": "W/\"abc123\"",
│     "last_updated": "2026-03-03T06:05:07Z",
│     "apps": {
│       "jellyfin": { "content_hash": "a1b2c3d4" },
│       "immich": { "content_hash": "e5f6g7h8" }
│     }
│   }
├── en_US/
│   ├── index.json          # 上次拉取的索引
│   └── apps/
│       ├── jellyfin/
│       │   ├── meta.json
│       │   └── docker-compose.yml
│       └── ...
└── zh_CN/
    └── ...
```

### 5.3 ETag 工作原理

GitHub Pages 原生支持 `ETag` 响应头。客户端请求 `{locale}/index.json` 时带上 `If-None-Match`：

- **304 Not Modified** → 本地索引是最新的，无需进一步请求
- **200 OK** → 索引有更新，解析后对比各应用 `content_hash`

无更新时整个检查过程只有 **1 次 HTTP 请求**，且响应体为空。

### 5.4 content_hash 用途

`content_hash` 是对每个应用的 `docker-compose.yml` + `meta.json` 内容做 SHA-256 取前 8 位生成的。客户端对比本地缓存的 hash 与远程 index.json 中的 hash：

- 相同 → 跳过，不拉取该应用详情
- 不同 → 该应用有更新，拉取新的 compose + meta

这样 158 个应用中如果只更新了 1 个，客户端只需额外请求 2 个小文件。

### 5.5 触发策略：用户触发 + 智能缓存

#### 策略选型

| 策略 | 优点 | 缺点 |
|------|------|------|
| 定期轮询 | 用户打开商店时数据已就绪 | 大量设备无人使用时浪费流量和 GitHub Pages 带宽 |
| 用户请求时拉取 | 零浪费，仅在需要时请求 | 用户打开商店时需等待加载 |
| **用户触发 + 智能缓存** | 兼顾体验和效率 | — |

**选择「用户触发 + 智能缓存」的原因：**

1. **ETag 304 响应极快**（~100-200ms，body 为空），用户打开时实时请求完全可接受，不需要"提前准备"
2. **不再需要后台定时任务**——旧方案用定时轮询是因为下载 zip 代价大，必须提前缓存；新方案 index.json 仅 250 KB，无需提前
3. **避免无意义流量**——很多设备可能数天无人打开商店，定期拉取全是浪费
4. **静态托管带宽配额有限**（以当前托管平台实际配额为准），高频轮询会快速消耗配额
5. **无需更新通知能力**——产品不需要角标提示"有 N 个应用更新"，因此不需要后台检查

#### 完整流程

```
用户打开商店
    │
    ├─ 有本地缓存
    │       │
    │       ▼
    │   立即展示缓存内容（无白屏等待）
    │   同时后台 GET {locale}/index.json（带 If-None-Match: <ETag>）
    │       │
    │       ├─ 304 Not Modified
    │       │   → 缓存即最新，无需任何操作
    │       │
    │       └─ 200 OK（有更新）
    │           → 对比各应用 content_hash
    │           → 仅拉取变更应用的 compose + meta
    │           → 静默刷新 UI，写入本地缓存
    │
    └─ 无本地缓存
            │
            ▼
        GET {locale}/index.json → 加载完成后展示
        （首次使用或缓存被清除时）
```

#### 降级行为

| 网络状态 | 行为 |
|----------|------|
| 正常 | ETag 校验 → 增量更新 → 展示最新数据 |
| 慢/不稳 | 先展示缓存，后台静默同步，完成后刷新 |
| 完全离线 | 展示本地缓存；无缓存则降级到 Layer 1 预置基线 |

#### 关键实现要求

- **不需要任何定时器或后台轮询服务**
- 打开商店 = 触发同步，关闭商店 = 零消耗
- 请求 `{locale}/index.json` 时必须带 `If-None-Match` 头，确保 304 快速返回
- 缓存 TTL 不设置硬性过期——每次打开都做 ETag 校验，由服务端判断是否有更新

### 5.6 流量对比：新旧方案

假设 1000 台设备每天打开一次商店，商店平均每天更新 1 个应用（158 个应用中的 1 个）：

| 场景 | 旧方案（zip 全量） | 新方案（增量） | 节省 |
|------|-------------------|---------------|------|
| 无更新（常见） | 1000 × HEAD 请求 ≈ 0 | 1000 × ETag 304 ≈ 0 | 持平 |
| 1 个应用更新 | 1000 × ~1.5 MB = **1.5 GB** | 1000 × ~255 KB = **250 MB** | **~83%** |
| 10 个应用更新 | 1000 × ~1.5 MB = **1.5 GB** | 1000 × ~280 KB = **273 MB** | **~82%** |

旧方案无论更新几个应用，都是全量下载；新方案流量与变更量成正比。

---

## 6. 离线场景方案

### 6.1 三层数据来源

```
┌─────────────────────────────────────────────────┐
│                三层数据来源                       │
├─────────────────────────────────────────────────┤
│                                                 │
│  Layer 1: 预置基线（随 OS 镜像内置）              │
│  ├── 随系统打包一份 index.json + meta.json 快照  │
│  ├── 不含图片（控制体积）                        │
│  ├── 版本跟随 OS Release                        │
│  └── 压缩后约 2-5 MB                            │
│                                                 │
│  Layer 2: 本地缓存（运行时积累）                  │
│  ├── 用户每次打开商店时增量更新                   │
│  ├── 包含已浏览过的图片缓存                      │
│  └── 包含已下载的 compose + meta                 │
│                                                 │
│  Layer 3: 在线实时（GitHub Pages / ZimaSpace）   │
│  ├── 有网时优先使用，ETag 快速校验               │
│  └── 获取最新应用和更新                          │
│                                                 │
└─────────────────────────────────────────────────┘
```

### 6.2 场景行为矩阵

| 场景 | 行为 |
|------|------|
| **有网络** | ETag 校验 → 增量更新 → 写入 Layer 2 缓存 |
| **网络慢/不稳** | 先展示 Layer 2 缓存，后台静默更新，完成后刷新 |
| **完全离线** | 使用 Layer 2 缓存；若无缓存则降级到 Layer 1 预置基线 |
| **首次开机** | Layer 1 预置基线保证商店可用，联网后立即更新到最新 |

### 6.3 预置基线生成

在 CI 的 `release.yml`（tag 触发）中增加基线快照构建步骤：

```yaml
- name: Generate baseline snapshot
  run: |
    python3 scripts/build_appstore.py --source . --output baseline/
    # 删除图片，只保留元数据
    find baseline/ -type f \( -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.webp' -o -name '*.gif' -o -name '*.svg' \) -delete
    tar czf appstore-baseline.tar.gz baseline/
```

该 `appstore-baseline.tar.gz` 随 ZimaOS 系统镜像打包发布。

---

## 7. ZimaSpace 运营层

### 7.1 设计原则：运营数据与应用元数据完全分离

ZimaSpace 是一个独立的运营服务，**不同步、不代理、不聚合** index.json。它只管理自己的运营数据和用户交互数据。

```
Official Store (CDN)           ZimaSpace (独立服务)
┌────────────────────┐         ┌────────────────────────┐
│ 只负责：            │         │ 只负责：                │
│ • 应用元数据        │         │ • 推荐什么给用户        │
│ • 分类定义          │         │ • 用户怎么评价          │
│ • compose + meta   │         │ • 首页怎么展示          │
│                    │         │ • 运营权重怎么配        │
│ 输出：index.json   │         │                        │
│ 部署：CDN 静态托管  │         │ 输出：operations.json  │
│ 变更频率：低        │         │ 部署：云服务器          │
│ 维护者：开发者      │         │ 变更频率：高            │
└────────────────────┘         │ 维护者：运营团队        │
         │                     └──────────┬─────────────┘
         │                                │
         ▼                                ▼
┌──────────────────────────────────────────────────────────┐
│ 客户端：并行请求两个独立数据源，本地合并渲染                │
│                                                          │
│ • index.json 请求失败 → 用本地缓存 / 预置基线            │
│ • operations.json 请求失败 → 静默忽略，不影响核心功能     │
└──────────────────────────────────────────────────────────┘
```

**为什么不让 ZimaSpace 合并输出 Enhanced JSON？**

| 对比项 | 合并方案 | 分离方案 |
|--------|---------|---------|
| ZimaSpace 是否需要 Sync Service | 是，定时拉取 index.json | **不需要** |
| ZimaSpace 宕机影响 | 商店完全不可用 | **仅缺少推荐和评分** |
| index.json 数据延迟 | 最多 5 分钟同步滞后 | **零延迟，直连 CDN** |
| ZimaSpace 响应体积 | ~250KB+（含完整应用列表） | **~5-10KB（仅运营数据）** |
| 架构复杂度 | 需要 Sync + DB + Aggregation | **只需 Config + API** |

### 7.2 ZimaSpace 内部模块

```
┌──────────────────────────────────────────────────────────┐
│                        ZimaSpace                          │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Admin Panel (管理后台)                                │  │
│  │                                                      │  │
│  │  读取 {locale}/index.json (直接从 OSS CDN，前端 fetch) │  │
│  │    → 展示应用列表供运营人员选择精选/推荐应用           │  │
│  │    → 不存 DB，不做后端同步，浏览器直接拉              │  │
│  │                                                      │  │
│  │  运营人员操作:                                        │  │
│  │    • 从列表中选择精选应用 → 写入 Operation Config DB  │  │
│  │    • 配置推荐权重/理由 → 写入 Operation Config DB     │  │
│  │    • 管理 Banner 图片/文案 → 写入 Operation Config DB │  │
│  └──────────────────────────┬──────────────────────────┘  │
│                             ▼                             │
│  ┌──────────────────┐  ┌───────────────────────┐          │
│  │ Operation Config │  │ User Interaction      │          │
│  │ DB               │  │ DB                    │          │
│  │                  │  │                        │          │
│  │ • featured 列表  │  │ • Stars (用户收藏)     │          │
│  │ • recommended    │  │ • Comments (用户评论)  │          │
│  │ • banner 配置    │  │ • Ratings (用户评分)   │          │
│  │ • 权重/排序      │  │ • Install count 统计  │          │
│  └────────┬─────────┘  └──────────┬────────────┘          │
│           └──────────┬────────────┘                        │
│                      ▼                                    │
│           ┌──────────────────────┐                         │
│           │ API (只读，极简)      │                         │
│           │                      │                         │
│           │ GET /api/v1/operations.json │ ← 从 DB 查询生成  │
│           │ GET /apps/{id}/      │    可缓存为静态文件      │
│           │     comments         │                         │
│           └──────────────────────┘                         │
└──────────────────────────────────────────────────────────┘
```

**注意：** 管理后台加载 `{locale}/index.json` 仅用于展示应用列表（id、title、icon）供运营人员选择。这是管理前端的行为，不是后端同步——运营人员打开管理页面时，浏览器直接从 OSS CDN fetch `{locale}/index.json`，无需后端中转。

### 7.3 operations.json 格式

```json
{
  "version": 1,
  "updated_at": "2026-03-03T12:00:00Z",

  "featured": [
    {
      "app_id": "jellyfin",
      "weight": 100,
      "banner_image": "https://zimaspace.com/banners/jellyfin.png",
      "promotion_text": { "en_US": "Best media server", "zh_CN": "最佳媒体服务器" }
    }
  ],

  "recommended": [
    { "app_id": "immich", "weight": 90, "reason": "new" },
    { "app_id": "teable", "weight": 80, "reason": "trending" }
  ],

  "app_stats": {
    "jellyfin": { "stars": 1234, "avg_rating": 4.7, "install_count": 8900 },
    "immich": { "stars": 890, "avg_rating": 4.5, "install_count": 5600 },
    "nextcloud": { "stars": 670, "avg_rating": 4.2, "install_count": 4300 }
  }
}
```

| 字段 | 说明 |
|------|------|
| `featured` | 精选应用列表，含 Banner 图和推广文案，按 weight 降序 |
| `recommended` | 推荐应用列表，含推荐理由（new/trending/popular） |
| `app_stats` | 按 app_id 索引的用户交互统计（stars/评分/安装量） |

**不包含任何应用元数据**（title、category、icon 等）——这些信息全部来自 index.json，客户端本地合并。

### 7.4 API 端点

| 端点 | 方法 | 说明 | 消费者 |
|------|------|------|--------|
| `/api/v1/operations.json` | GET | 运营数据 + 交互统计 | 所有客户端 |
| `/api/v1/apps/{id}/comments` | GET | 应用评论列表（分页） | 按需加载 |
| `/api/v1/apps/{id}/star` | POST | 收藏/取消收藏 | 已登录用户 |
| `/api/v1/apps/{id}/comment` | POST | 提交评论 | 已登录用户 |
| `/api/v1/apps/{id}/rate` | POST | 提交评分 | 已登录用户 |

### 7.5 客户端合并流程

```
用户打开商店
    │
    │  并行发起两个请求:
    │
    ├── GET {locale}/index.json (from OSS CDN / GitHub Pages)
    │     → 应用列表、分类、content_hash
    │     → 失败时用本地缓存 / 预置基线
    │
    └── GET /api/v1/operations.json (from ZimaSpace)
          → 精选、推荐、评分统计
          → 失败时静默忽略
    │
    ▼
客户端本地合并:
    for app in index.apps:
        if app.id in operations.app_stats:
            app.stars = operations.app_stats[app.id].stars
            app.avg_rating = operations.app_stats[app.id].avg_rating

    featured_apps = match operations.featured with index.apps
    recommended_apps = match operations.recommended with index.apps

    渲染 UI
```

合并逻辑非常简单——只是按 app_id 做 key-value 匹配，无需复杂的数据聚合。

### 7.6 中国区部署方案

为解决中国用户访问 GitHub Pages 不稳定的问题，CI 构建产物同时推送到国内对象存储（阿里云 OSS / 腾讯云 COS），ZimaSpace 也部署在国内云服务器上。

#### 部署拓扑

```
┌───────────────────────────────────────────────────────────────────────┐
│                        CI/CD (GitHub Actions)                         │
│                                                                       │
│  build_appstore.py ──▶ dist/                                         │
│                          │                                            │
│              ┌───────────┼───────────┐                                │
│              ▼           ▼           ▼                                │
│        GitHub Pages  Alibaba OSS  (备选: Tencent COS)                │
│        (海外 CDN)    (中国 CDN)                                       │
└───────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────┐
│                    ZimaSpace (阿里云 ECS，中国区)                      │
│                                                                       │
│  Admin Panel:                                                         │
│    前端直接 fetch OSS 上的 {locale}/index.json（同区域，毫秒级）        │
│    运营人员选择应用 → 写入 DB → 生成 operations.json                   │
│                                                                       │
│  API:                                                                 │
│    GET /api/v1/operations.json                                       │
│    GET /api/v1/apps/{id}/comments                                    │
└───────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────┐
│                          Client Routing                               │
│                                                                       │
│  ZimaOS 设备首次联网时探测连通性（一次性，结果缓存）:                   │
│                                                                       │
│  ├─ GitHub Pages 可达 → 使用海外端点                                  │
│  │   {locale}/index.json ← GitHub Pages                              │
│  │   静态资源             ← GitHub Pages / jsDelivr                   │
│  │   operations    ← ZimaSpace API                                   │
│  │                                                                    │
│  └─ GitHub Pages 不可达 → 使用中国端点                                │
│      {locale}/index.json ← Alibaba OSS CDN                           │
│      静态资源             ← Alibaba OSS CDN                           │
│      operations    ← ZimaSpace API                                   │
└───────────────────────────────────────────────────────────────────────┘
```

#### OSS 缓存策略

| 文件类型 | Cache-Control | 原因 |
|----------|---------------|------|
| `{locale}/index.json` | `no-cache, must-revalidate` | 必须实时，支持 ETag 304 |
| `{locale}/store.json` | `no-cache, must-revalidate` | 商店身份信息需实时 |
| `{locale}/apps/*/docker-compose.yml` | `public, max-age=3600` | 通过 content_hash 保证一致性 |
| `{locale}/apps/*/meta.json` | `public, max-age=3600` | 通过 content_hash 保证一致性 |
| `assets/apps/*/icon.*` | `public, max-age=86400` | 图片变更极少 |
| `assets/apps/*/screenshot-*.*` | `public, max-age=86400` | 图片变更极少 |

#### CI 推送到 OSS 的工作流

```yaml
# 在 release.yml 中追加步骤

- name: Sync to Alibaba OSS
  if: github.ref == 'refs/heads/main'
  env:
    OSS_KEY_ID: ${{ secrets.ALIYUN_OSS_KEY_ID }}
    OSS_KEY_SECRET: ${{ secrets.ALIYUN_OSS_KEY_SECRET }}
  run: |
    # 安装 ossutil
    pip install ossutil2

    # 元数据文件: 禁止缓存
    ossutil cp dist/en_US/index.json oss://zimaos-appstore/en_US/index.json -f \
      --meta "Cache-Control:no-cache,must-revalidate"
    ossutil cp dist/en_US/store.json oss://zimaos-appstore/en_US/store.json -f \
      --meta "Cache-Control:no-cache,must-revalidate"

    # 应用静态资源: 增量同步 + 长缓存（示例仅演示 en_US 和 assets）
    ossutil sync dist/en_US/apps/ oss://zimaos-appstore/en_US/apps/ \
      --meta "Cache-Control:public,max-age=3600" \
      --update
    ossutil sync dist/assets/apps/ oss://zimaos-appstore/assets/apps/ \
      --meta "Cache-Control:public,max-age=86400" \
      --update
```

#### 为什么 ZimaSpace 从 OSS 读取而不是 GitHub Pages

ZimaSpace 部署在阿里云 ECS，管理后台前端直接 fetch 同区域 OSS 上的 `{locale}/index.json`：

| 对比 | 从 GitHub Pages 读取 | 从 OSS 读取 |
|------|---------------------|-------------|
| 延迟 | 200-2000ms（跨境） | **<10ms（同区域内网）** |
| 可靠性 | 受 GFW 影响 | **99.99% SLA** |
| 带宽成本 | 消耗 GitHub Pages 配额 | **OSS 内网流量免费** |

#### 客户端端点配置

ZimaOS 设备内置两组端点：

```json
{
  "endpoints": {
    "global": {
      "index": "https://cdn.jsdelivr.net/gh/IceWhaleTech/ZimaOS-AppStore@gh-pages/en_US/index.json",
      "assets_base": "https://cdn.jsdelivr.net/gh/IceWhaleTech/ZimaOS-AppStore@gh-pages/"
    },
    "china": {
      "index": "https://zimaos-appstore.oss-cn-hangzhou.aliyuncs.com/en_US/index.json",
      "assets_base": "https://zimaos-appstore.oss-cn-hangzhou.aliyuncs.com/"
    },
    "operations": "https://api.zimaspace.com/api/v1/operations.json"
  }
}
```

`operations` 端点不区分区域——ZimaSpace 部署在中国，海外用户访问延迟略高但 operations.json 仅 ~5-10KB，影响可忽略。

#### 客户端域名替换策略

CI 使用 `--base-url` 作为资源基准。`index.json` 中的资源字段为相对路径，客户端应结合 `index.base_url`（或端点配置）拼接完整 URL。

客户端在使用中国端点时，需要对 `index.base_url` 做**条件替换**，再拼接 `index.json` 中的相对路径字段。

**受影响的字段：** `icon`、`thumbnail`、`compose_url`、`meta_url`，以及未来新增的相对路径资源字段。

**替换规则：**

```
仅替换 `index.base_url`；字段值保持相对路径不改写。

示例 1 — 拼接后 URL（中国区）：
  base_url: https://zimaos-appstore.oss-cn-hangzhou.aliyuncs.com/
  icon: assets/apps/my-app/icon.png
  结果: https://zimaos-appstore.oss-cn-hangzhou.aliyuncs.com/assets/apps/my-app/icon.png

示例 2 — 不替换（外部 CDN URL，如 jsDelivr）：
  原始: https://cdn.jsdelivr.net/gh/username/my-appstore@main/Apps/MyApp/icon.png
  保留: https://cdn.jsdelivr.net/gh/username/my-appstore@main/Apps/MyApp/icon.png
```

**伪代码：**

```python
def build_url(base_url, rel):
    """将 index.base_url 与相对路径拼接为绝对地址。"""
    if rel.startswith("http://") or rel.startswith("https://"):
        return rel
    return base_url.rstrip("/") + "/" + rel.lstrip("/")
```

端点配置中的 `assets_base` 可作为 `base_url` 的区域覆盖值，客户端统一使用“base + 相对路径”规则。

---

## 8. 多商店源与 App ID 冲突处理

### 8.1 商店源注册

用户在 ZimaOS 中添加商店源，只需要输入一个 URL：

```
https://username.github.io/my-appstore
```

客户端处理流程：

```
输入 URL
  ├─ GET {url}/{locale}/store.json  → 验证合法性，获取 store_id 和名称
  └─ GET {url}/{locale}/index.json  → 加载应用列表
```

### 8.2 App ID 冲突场景

**场景 A：同一个应用出现在多个商店**

例如 `jellyfin` 同时存在于官方商店和三方商店（不同打包配置）。

处理方式：按商店优先级排序，用户选择安装来源。同一个 app_id 只能安装一份。

```
已安装：jellyfin (来自 Official Store)

用户想从三方商店安装 jellyfin：
  → "Jellyfin 已从 Official Store 安装，是否替换为 NAS Community Apps 的版本？"
  → 替换 = 卸载旧的 + 安装新的（保留数据卷）
```

**场景 B：不同应用碰巧使用了相同的 app_id**

例如两个三方商店各自有一个完全不同的应用，但都叫 `dashboard`。

处理方式：客户端安装时注入 store_id 前缀作为 Docker 项目名来隔离。

### 8.3 Docker 项目名规则

| 来源 | compose 中 name | 实际 Docker 项目名 |
|------|----------------|-------------------|
| 官方商店 | `jellyfin` | `jellyfin`（不加前缀，向后兼容） |
| 三方商店 A | `dashboard` | `community-nas-apps_dashboard` |
| 三方商店 B | `dashboard` | `awesome-homelab_dashboard` |

compose 源文件中 `name` 保持简洁，前缀由客户端安装时动态注入：

```
compose 原文:      name: dashboard
客户端安装时改写:   name: {store_id}_{app_id}
```

### 8.4 冲突规则总结

| 场景 | 规则 |
|------|------|
| 同一商店内 | app_id 必须唯一（构建脚本校验） |
| 跨商店同 app | 同一个应用不同源 → 只能装一个，可替换 |
| 跨商店撞车 | 不同应用碰巧同 ID → 客户端注入 store_id 前缀隔离 |
| 官方商店 | 不加前缀，保持向后兼容 |

三方开发者完全不需要关心冲突问题，ID 随便取，隔离由客户端处理。

---

## 9. CI/CD 集成

### 9.1 GitHub Actions 工作流（当前实现）

当前仓库以 `.github/workflows/release.yml` 作为发布工作流，以 `.github/workflows/validator.yml` 作为 PR 校验工作流。

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
        default: "https://cdn.jsdelivr.net/gh/IceWhaleTech/ZimaOS-AppStore@gh-pages"

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

### 9.2 向后兼容策略

如需兼容旧版 zip 客户端，建议单独增加兼容工作流，不要影响当前 `release.yml` 的静态站点发布主流程。

### 9.3 面向三方开发者的 v1 -> v2 迁移兼容约定

v1 商店从 zip 分发迁移到 v2 后，请求方式从“下载并解压 zip”切换为“按语言加载 JSON”。为了让已有用户在升级 AppStore 后能收到“一键恢复旧商店”的提示，三方开发者需要在 v1 产物中保留可识别的迁移信息。

#### 三方开发者需要做什么

- 在 v1 zip 解压目录中保留 `store-config.json`
- 确保 `store-config.json` 中提供可访问的 `url`（指向你的 v2 商店根地址）
- 确保该地址可返回 `{url}/{locale}/store.json` 与 `{url}/{locale}/index.json`
- 建议 `store_id`、`maintainer` 与历史商店身份保持一致，减少用户困惑

#### 用户侧会发生什么

- v2 客户端首次进入 AppStore 时，会扫描旧 zip 解压目录中的三方商店记录
- 仅当检测到 `store-config.json.url` 时，客户端才会提示“可迁移”
- 用户可在迁移面板中执行：一键恢复全部 / 恢复单个 / 失败重试 / 忽略
- 缺少 `store-config.json` 或缺少 `url` 的旧商店，不具备迁移提醒能力

#### 客户端一键恢复流程（供联调）

1. 从 `store-config.json.url` 读取候选 v2 源地址
2. 校验目标地址可访问，且 `{url}/{locale}/store.json` 可解析
3. 校验通过后添加为 v2 商店源
4. 成功后写入本地迁移状态（`migrated`），避免重复提示
5. 失败记录错误原因（`failed`），并提供重试入口

#### 推荐约束

- 不自动静默切换，必须用户确认后执行
- 迁移流程需幂等：已存在同 URL 时可直接标记为已恢复
- 迁移失败不影响当前商店可用性

---

## 10. 改动清单

### 10.1 仓库侧（本项目）

| 改动项 | 文件 | 状态 |
|--------|------|------|
| 构建脚本 | `scripts/build_appstore.py` | 已完成 |
| 多语言 store/index 生成 | `scripts/build_appstore.py` | 已完成 |
| 共享 assets 输出 | `scripts/build_appstore.py` | 已完成 |
| CI workflow（GitHub Pages） | `.github/workflows/release.yml` | 已完成 |
| CI workflow（构建校验） | `.github/workflows/validator.yml` | 已完成 |
| CI workflow（OSS 同步） | `.github/workflows/release.yml` | 视部署策略可选 |
| 基线快照 | `.github/workflows/release.yml` | 视发布策略可选 |

### 10.2 系统侧（casaos-app-management）

| 改动项 | 说明 | 工作量 |
|--------|------|--------|
| 在线索引加载 | 替换 zip 下载为 GET `{locale}/index.json` | 中 |
| 增量更新逻辑 | 对比 content_hash，按需拉取 | 中 |
| ETag 缓存 | HTTP 条件请求支持 | 小 |
| 三层降级 | 在线 → 本地缓存 → 预置基线 | 中 |
| meta.json 解析 | 适配新的独立元数据格式 | 小 |
| compose 解析 | 适配精简后的 x-casaos 字段 | 小 |
| 多商店源管理 | 注册/删除商店源，store.json 解析 | 中 |
| App ID 隔离 | 安装时注入 store_id 前缀 | 小 |
| 端点路由 | 探测网络环境，选择海外/中国端点 | 小 |
| operations.json 消费 | 并行请求运营数据，本地合并，失败静默忽略 | 小 |

### 10.3 ZimaSpace 服务侧

| 改动项 | 说明 | 工作量 |
|--------|------|--------|
| Admin Panel | 管理后台（前端直接读 OSS 上的 index.json 供选择） | 中 |
| Operation Config Service | 精选/推荐/Banner 后台管理 + DB | 大 |
| User Interaction Service | Star / Comment / Rating API + DB | 中 |
| operations.json API | 从 DB 查询生成运营数据 JSON | 小 |
| 中国区部署 | 阿里云 ECS + OSS 配置 | 小 |

---

## 11. API 端点总览

### 11.1 Official Store（GitHub Pages / Alibaba OSS）

| 资源 | URL 路径 | 大小 | 缓存 |
|------|----------|------|------|
| 商店身份 | `/{locale}/store.json` | ~0.5 KB | no-cache |
| 全局索引 | `/{locale}/index.json` | ~250 KB | no-cache (ETag 304) |
| 应用 compose | `/{locale}/apps/{app_id}/docker-compose.yml` | ~0.5-2 KB | 1h |
| 应用元数据 | `/{locale}/apps/{app_id}/meta.json` | ~5-30 KB | 1h |
| 应用图标 | `/assets/apps/{app_id}/icon.*` | ~10-50 KB | 24h |
| 应用缩略图 | `/assets/apps/{app_id}/thumbnail.webp` | ~50-200 KB | 24h |
| 应用截图 | `/assets/apps/{app_id}/screenshot-{n}.webp` | ~100-500 KB | 24h |

GitHub Pages 和 Alibaba OSS 托管完全相同的文件，客户端根据网络环境选择端点。

### 11.2 ZimaSpace（运营数据）

| 资源 | URL 路径 | 方法 | 说明 |
|------|----------|------|------|
| 运营数据 | `/api/v1/operations.json` | GET | 精选/推荐/评分统计（~5-10 KB） |
| 评论列表 | `/api/v1/apps/{id}/comments` | GET | 分页加载 |
| 收藏 | `/api/v1/apps/{id}/star` | POST | 已登录用户 |
| 评论 | `/api/v1/apps/{id}/comment` | POST | 已登录用户 |
| 评分 | `/api/v1/apps/{id}/rate` | POST | 已登录用户 |

ZimaSpace 不代理 index.json，不输出应用元数据。客户端并行请求 index.json（CDN）和 operations.json（ZimaSpace），本地合并渲染。
