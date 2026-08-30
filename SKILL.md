---
name: zhihu-fetcher
description: "知乎收藏夹与文章内容抓取：API/Playwright 多级降级、Cookie 持久化与保活、批量正文与图片、断点续传、可选写入 Obsidian。| Zhihu collection scraping, batch article fetch, Obsidian export."
version: "2.2.0"
user-invocable: true
argument-hint: "[知乎链接：收藏夹/专栏/文章/回答/问题页/个人页；或输出目录、Vault 路径]"
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, WebFetch
---

# 知乎数据抓取

从知乎获取**收藏夹文章列表**与**正文 Markdown**（含图片本地化），支持写入 **Obsidian** 知识库。命令与路径约定见下文；可视化说明见仓库根目录 [`README.md`](README.md)。

---

## 环境与约定

- **语言**：默认与用户语种一致。
- **技能根目录**：本仓库根目录（含 `SKILL.md` 与 `scripts/`）。下文命令均从该目录执行，写作 `python scripts/...`。
- **工作区目录**：Cookie、浏览器用户数据、默认文章输出等放在工作区（已 gitignore，勿提交）。
  - 环境变量 **`ZHIHU_WORKSPACE`** 优先；
  - 未设置时默认为技能根目录下的 **`zhihu-fetch-workspace/`**。
- **依赖**：在 **`scripts/`** 下执行 **`pip install -r requirements.txt`**，并 **`playwright install chromium`**。
- **命令入口**：根目录只留 [`scripts/zhihu.py`](scripts/zhihu.py)；业务代码在 [`scripts/zhihu_fetch/`](scripts/zhihu_fetch/) 分模块。统一写成 `python scripts/zhihu.py <命令>`。

### 抓取上限（配置优先，对话可固化）

不带条数时**不会全量爬**。读取顺序：当次命令行 → 工作区配置 → 技能根配置 → 代码默认值。

| 文件 / 命令 | 作用 |
|------|------|
| [`zhihu_fetch_config.json`](zhihu_fetch_config.json) | **技能级**默认上限；用户说「以后默认…」时改这个并保存 |
| `{workspace}/zhihu_fetch_config.json` | **本机覆盖**（在 gitignore 的工作区内） |
| `python scripts/zhihu.py limits` | 查看当前生效值 |
| `python scripts/zhihu.py limits --set collection.max_items=10` | 写入技能根配置（默认 `--where skill`） |
| `--where workspace` | 只改本机覆盖 |
| `--all` 或配置 `"unlimited": true` | 取消上限 |

用户说「这次多抓一点」→ 命令行 `--max-items` / `--all`。用户说「以后默认每夹 10 篇」→ **改配置并固化**，不要只改当次命令。

默认：收藏夹最多 10 个、每夹 20 篇；专栏最多 5 个、每栏 20 篇；个人文章/回答各 20 篇；问题页回答 20 条；历史/批量各 20 篇。

**增量**：列表脚本支持 **`--since-last`**，对照工作区 `zhihu_url_index.json`（含 `content_updated`）、已有 `zhihu_*.json`、`_progress.json` 与 Markdown frontmatter 的 `url:`。未更新的已见 URL 跳过；列表里的更新时间**新于索引**则标 `refresh` 再抓，`batch` **不会**因 `_progress.json` 的 `completed` 跳过这些条。个人「文章」默认还会按 URL 排除已在专栏 JSON 里的篇目（两者重叠，有更新仍会刷新）。

**列表过滤**（条数上限之外）：`--min-voteup N`、`--days N`、`--since ISO`。配置 `filter.min_voteup` / `filter.since_days`（`0` = 不过滤）。作用在收藏夹 / 专栏 / 文章 / 回答 / 问题页 / 跟读包。`max_items` 只计通过过滤且为 new/refresh 的条目。

**登录态正文**：工作区有 Cookie 时，API / 页面 / 批量图片下载都会自动带上，降低专栏文章 403。未登录先跑 `python scripts/zhihu.py login` / `relogin`。

**每次 run 摘要**：列表与 batch 结束会打印并写入 `{workspace}/zhihu_run_summary.json`（成功 / 跳过空项 / 跳过已抓 / 失败 / 403 / 需登录）。Agent 回复用户时读这份摘要；失败项仍可用 `python scripts/zhihu.py failures` 写入 Vault。

### 登录与可选页面验证

- **`python scripts/zhihu.py login`**：打开浏览器等待登录，默认以检测到 **`z_c0`** 为成功条件即可结束（不要求额外跳转）。
- **可选二次校验**：若用户希望登录后再确认「某一内需登录页」是否可访问（如某收藏夹页、专栏后台、关注动态等），属**可选项**，不设则不执行：
  - **环境变量** **`ZHIHU_VERIFY_URL`**：值为完整 **`http://` 或 `https://`** URL；
  - **或**命令行第一个参数传入同一完整 URL：`python scripts/zhihu.py login "https://www.zhihu.com/..."`。
  - 脚本会访问该 URL，若正文仍出现知乎通用提示「请登录后查看」，则提示可能未登录完成；否则认为当前会话可访问该页。**不限定于收藏夹**，任意知乎链接均可（只要登录态相关）。
- **`python scripts/zhihu.py relogin`**：Cookie 失效、需重新登录并写回 **`zhihu_cookies.json`** 时使用（会打开浏览器）。

---

## 触发条件

在用户使用以下任一方式时启用本技能：

- 明确提及：知乎、Zhihu、专栏、收藏夹、文章抓取、批量下载、Cookie、验证码、Obsidian、知识库同步等
- 粘贴 **zhihu.com** / **zhuanlan.zhihu.com** 链接并希望获取正文或列表
- 需要 **断点续传**、**图片落盘**、**反爬 / Stealth** 相关协助

---

## 工具与脚本路由

按任务选用能力；具体工具名以当前 Agent 环境为准。

### 统一入口（先识别链接，再调现有脚本）

用户丢什么链接就走哪条流水线。**优先** `python scripts/zhihu.py route <URL> [原命令参数]`（`fetch` 遇到非单篇链接也会转过来）。受 `zhihu_fetch_config.json` 上限约束。

| 用户丢的链接 | kind | 调用 |
|--------------|------|------|
| `/p/` 或 `zhuanlan.zhihu.com/p/{id}` | article | `zhihu.py fetch` |
| `/question/{qid}/answer/{aid}` | answer | `zhihu.py fetch`（回答 API，带 Cookie） |
| `/collection/{id}` | collection | `zhihu.py collection` |
| `/people/{slug}/collections` | collections | `zhihu.py collection`；`--collection 名称` 只爬一夹 |
| `/people/{slug}/columns` 或 `/column/{id}` | columns / column | `zhihu.py columns`；`--column 名称` 只爬一栏 |
| `/people/{slug}/posts` | posts | `zhihu.py posts --kind articles` |
| `/people/{slug}/answers` | answers | `zhihu.py posts --kind answers` |
| `/question/{id}`（无 `/answer/`） | question | `zhihu.py question`：默认排序回答列表 → JSON，再 `batch`；上限 `question.max_answers` |
| 裸 `/people/{slug}` | people | **跟读包**：专栏 + 文章 + 回答（默认 `--since-last`，可用 `--no-since-last` 关掉）。单栏目仍用 `--posts` / `--answers` / `--columns` / `--collections` / `--history` |

### 常见任务与建议方式

| 任务 | 建议方式 |
|------|----------|
| 任意知乎链接（不知道类型） | **`Bash`** → `python scripts/zhihu.py route <URL>` |
| 获取收藏夹 JSON 列表 | **`Bash`** → `python scripts/zhihu.py collection <收藏夹URL或ID>`；个人页加 `--collection CS` 只爬该夹；`--since-last` 只补新 |
| 获取用户专栏列表与文章 | **`Bash`** → `python scripts/zhihu.py columns <people URL 或 /columns>`；`--column 名称` 只爬指定专栏；`--since-last` 只补新；层级 JSON + 每栏 `zhihu_column_{id}.json` 可交给 batch |
| 获取个人页文章 / 回答 | **`Bash`** → `python scripts/zhihu.py posts <people URL> --kind articles\|answers\|both`；文章默认排除已在专栏里的 URL；`--since-last` 只补新 |
| 裸个人页跟读 | **`Bash`** → `python scripts/zhihu.py route <people URL>` 或 `follow`；默认专栏+文章+回答+增量 |
| 问题页回答列表 | **`Bash`** → `python scripts/zhihu.py route <question URL>` 或 `question`；再 `batch` |
| 获取个人主页点赞/收藏历史 | **`Bash`** → `python scripts/zhihu.py history <people URL 或 slug> <起始时间ISO> <输出.json> [--until <结束时间ISO>]`；按活动时间保留 `interaction_*` 元数据，支持断点续跑 |
| 批量抓取正文与图片 | **`Bash`** → `python scripts/zhihu.py batch <列表.json> [输出目录] [图片目录]`；默认输出目录见「路径约定」；结束写 `zhihu_run_summary.json` |
| 写入 Obsidian 原文镜像 | **`Bash`** → `python scripts/zhihu.py obsidian <文章目录> [Vault路径]`；写入 **`{Vault}/知乎收藏/{分类}/`**（会删工作区源 md）；Vault：命令行优先，否则 **`OBSIDIAN_VAULT`** |
| 从镜像生成笔记 | **`Bash`** → `python scripts/zhihu.py notes [Vault路径]`；扫描「知乎收藏」，写入并列根目录 **`{Vault}/知乎笔记/`**，**不改、不删镜像**；已有笔记默认跳过，`--force` 覆盖 |
| 写入个人历史到 Obsidian | **`Bash`** → `python scripts/zhihu.py history-obsidian <文章目录> <Vault路径> [.]`；默认写入 `{Vault}/知乎收藏/{分类}/`，按 URL 去重更新 |
| 写入失败项清单 | **`Bash`** → `python scripts/zhihu.py failures <Vault路径> <标签>:<progress.json> ...`；生成 `{Vault}/知乎收藏/抓取失败.md` |
| Cookie 失效需人工登录 | **`Bash`** → `python scripts/zhihu.py relogin`（会打开浏览器窗口） |
| 首次登录辅助（可选验证页） | **`Bash`** → `python scripts/zhihu.py login`；可选 **`ZHIHU_VERIFY_URL`** 或首个参数传入完整 http(s) 链接，见「登录与可选页面验证」 |
| 单篇快速验证 | **`Bash`** → `python scripts/zhihu.py fetch`（文章/回答；其它 URL 转路由）或 `api` / `stealth` / `interactive` |
| 查看 / 固化抓取上限 | **`Bash`** → `python scripts/zhihu.py limits`；改默认用 `--set key=value`（见「抓取上限」） |

---

## 模块一览

根入口：`python scripts/zhihu.py <命令>`。实现按目录划分：

```
scripts/
  zhihu.py                 # 唯一 CLI
  requirements.txt
  zhihu_fetch/
    core/                  # paths, limits, url, seen, times, filters, summary
    fetch/                 # route, collection, columns, posts, follow, question, history, batch, single
    body/                  # api, stealth, interactive
    auth/                  # login, relogin, login_save
    export/                # obsidian, notes, history, failures, classify
```

| 命令 | 模块 | 用途 |
|------|------|------|
| `route` | `fetch/route.py` | 识别链接后转调对应流水线 |
| `collection` | `fetch/collection.py` | 收藏夹列表；`--collection`、`--since-last` |
| `columns` | `fetch/columns.py` | 用户专栏；`--column`、`--since-last` |
| `posts` | `fetch/posts.py` | 个人文章 / 回答；与专栏 URL 去重 |
| `follow` | `fetch/follow.py` | 裸主页跟读包（专栏+文章+回答） |
| `question` | `fetch/question.py` | 问题页默认排序回答列表 |
| `history` | `fetch/history.py` | 点赞/收藏动态 |
| `batch` | `fetch/batch.py` | 批量正文、图片、断点续传、摘要 |
| `fetch` | `fetch/single.py` | 单篇文章/回答 |
| `api` / `stealth` / `interactive` | `body/` | 单篇调试 |
| `login` / `relogin` / `login-save` | `auth/` | 登录与 Cookie |
| `obsidian` / `notes` / `history-obsidian` / `failures` | `export/` | 原文镜像 / 并列笔记 / 历史 / 失败清单 |
| `limits` | `core/limits.py` | 抓取上限配置 |

---

## 主流程（推荐执行顺序）

1. **安装依赖**：`scripts/requirements.txt` + Chromium。
2. **用户给出链接**：**`python scripts/zhihu.py route <URL>`**（不要凭印象选模块）。
3. 列表得到 JSON 后 **`python scripts/zhihu.py batch`** → **`zhihu_articles_*/`**（含 **`_progress.json`**、**`images/`**、编号 **`*.md`**）。
4. （可选）**`python scripts/zhihu.py obsidian`** → 原文镜像到 **`{Vault}/知乎收藏/{分类}/`**。
5. （可选）**`python scripts/zhihu.py notes`** → 从「知乎收藏」生成并列的 **`{Vault}/知乎笔记/`**（不改镜像）。
6. 回复用户前读 **`zhihu_run_summary.json`**。

中断批量任务时：**重新运行同一条** `python scripts/zhihu.py batch` 命令即可续跑（已完成 URL 记录在 `_progress.json`）。

### 个人历史流程（点赞 / 收藏）

适用于个人主页动态中的 **赞同了回答 / 赞同了文章 / 收藏了回答 / 收藏了文章**。时间采用 ISO 格式，**建议显式带时区**（如 `+08:00`）；若省略时区，默认按 **Asia/Shanghai** 解释，可用环境变量 **`ZHIHU_TIMEZONE`** 或 **`TZ`** 覆盖。

```bash
# 1. 收集活动列表（起始时间含，结束时间不含）
python scripts/zhihu.py history \
  https://www.zhihu.com/people/<slug> \
  2026-01-01T00:00:00+08:00 \
  /path/to/runtime/zhihu_history_2026-01-01_to_2026-04-05.json \
  --until 2026-04-05T00:00:00+08:00

# 2. 抓取正文与图片；失败默认自动重试 3 次
python scripts/zhihu.py batch \
  /path/to/runtime/zhihu_history_2026-01-01_to_2026-04-05.json \
  /path/to/runtime/zhihu_articles_history_2026-01-01_to_2026-04-05

# 3. 写入 Obsidian 的知乎收藏根目录分类文件夹
python scripts/zhihu.py history-obsidian \
  /path/to/runtime/zhihu_articles_history_2026-01-01_to_2026-04-05 \
  /path/to/ObsidianVault \
  .
```

历史笔记会保留：

```yaml
interaction_action: "赞同了回答"
interaction_time: 2026-03-20T10:17:57.235000+00:00
interaction_date: 2026-03-20
tags: [zhihu, 编程与开发, 赞同了回答]
```

历史列表中断时重新运行同一条命令即可续跑；加 `--fresh` 可忽略现有 checkpoint 重建。写入 Obsidian 时会扫描已有笔记的 `url` 并按 URL 更新，避免重复导入。

### 用户专栏流程（他的专栏）

适用于 `https://www.zhihu.com/people/<slug>/columns`：先列出专栏，再按栏抓文章。多专栏是列表，栏下文章是层级；可用 **`--column 专栏名`** 只爬其中一个。不写条数时走配置 `column.max_columns` / `column.items_per_column`。

```bash
# 列出并抓取（受配置默认上限）
python scripts/zhihu.py columns https://www.zhihu.com/people/<slug>/columns

# 只爬指定专栏名，每栏 2 篇
python scripts/zhihu.py columns https://www.zhihu.com/people/<slug>/columns --column 远东轶事 --per-column 2

# 仅列专栏、不抓文章
python scripts/zhihu.py columns https://www.zhihu.com/people/<slug>/columns --list-only

# 正文与图片
python scripts/zhihu.py batch zhihu-fetch-workspace/zhihu_column_<id>.json
```

输出：`zhihu_columns_{slug}.json`（层级）+ `zhihu_column_{id}.json`（单栏，可交给 batch）。加 `--since-last` 只补尚未抓过的文章。

### 个人页文章 / 回答

专栏只是作者产出的一部分。跟读某个作者时，裸主页默认跑跟读包；也可以只用 `/posts` 与 `/answers`。文章与专栏按 URL 去重后再抓。默认上限 `people.max_articles` / `people.max_answers`。

```bash
python scripts/zhihu.py route https://www.zhihu.com/people/<slug>
python scripts/zhihu.py follow https://www.zhihu.com/people/<slug> --no-since-last
python scripts/zhihu.py route https://www.zhihu.com/people/<slug>/posts
python scripts/zhihu.py route https://www.zhihu.com/people/<slug>/answers
python scripts/zhihu.py posts https://www.zhihu.com/people/<slug> --kind both --since-last --min-voteup 50 --days 30
python scripts/zhihu.py batch zhihu-fetch-workspace/zhihu_posts_<slug>.json
```

输出：`zhihu_posts_{slug}.json`、`zhihu_answers_{slug}.json`（可交给 batch）。

### 问题页回答

`https://www.zhihu.com/question/{id}`（不含 `/answer/`）拉默认排序回答列表，上限 `question.max_answers`。

```bash
python scripts/zhihu.py route https://www.zhihu.com/question/<id> --max-items 2
python scripts/zhihu.py batch zhihu-fetch-workspace/zhihu_question_<id>.json
```

---

## 路径与输出约定

### 批量抓取命令格式

```bash
python scripts/zhihu.py batch <列表文件> [输出目录] [图片目录]
```

| 参数 | 说明 |
|------|------|
| **列表文件** | `zhihu.py collection` 产出的 JSON |
| **输出目录** | 可选；省略时默认为 **`{workspace}/zhihu_articles_{collectionId}/`**（`collectionId` 由列表文件名推导） |
| **图片目录** | 可选；省略时默认为 **`{输出目录}/images/`** |

### 目录结构示例

```
zhihu_articles_{collectionId}/
├── _progress.json          # 断点续传
├── images/                 # 默认图片目录
│   └── ...
├── 0001_文章标题.md
└── ...
```

### 单篇文章格式要点

- YAML frontmatter：`title`、`author`、`source`、`url`、`voteup`、`images` 等
- 正文为 Markdown；图片引用指向本地 **`images/`** 下文件名（或脚本生成的相对路径）

示例结构：

```markdown
---
title: "文章标题"
author: "作者"
source: zhihu
url: "https://..."
voteup: 123
images: 5
---

# 文章标题

> 作者: xxx | 原文: [知乎链接](https://...)

正文...
```

### 持久化文件（默认 workspace）

未设置 **`ZHIHU_WORKSPACE`** 时，`{workspace}` 为技能根目录下的 **`zhihu-fetch-workspace/`**。

| 用途 | 路径 |
|------|------|
| Cookie | `{workspace}/zhihu_cookies.json` |
| URL 增量索引 | `{workspace}/zhihu_url_index.json` |
| 当次 run 摘要 | `{workspace}/zhihu_run_summary.json` |
| Playwright 用户数据 | `{workspace}/chrome_user_data/` |
| 默认文章目录 | `{workspace}/zhihu_articles_{collectionId}/` |
| 默认图片目录 | `{文章输出目录}/images/` |

---

## Obsidian 写入要点

- **原文镜像**：`python scripts/zhihu.py obsidian` 写入 **`{Vault}/知乎收藏/{分类}/{标题}.md`**，行为与旧版相同（分类、图片、删除工作区源 md）。**不要**把镜像改成笔记、不要覆盖已有镜像来当笔记。
- **笔记板块**：`python scripts/zhihu.py notes [Vault]` 扫描「知乎收藏」，在 Vault **并列根目录**写入 **`{Vault}/知乎笔记/{分类}/`**，并维护 `知乎笔记/作者/`、`知乎笔记/问题/` 索引。不删除、不改写镜像。已有笔记默认跳过；Agent 可再润色摘要。
- **Vault**：① **命令行参数**；② 环境变量 **`OBSIDIAN_VAULT`**；③ 常见目录扫描。
- **分类**：优先对齐已有 **`知乎收藏/`** 子目录；否则按内容关键词；无法归类则 **「未分类」**。

---

## 已知问题与对策

| # | 现象 / 原因 | 处理 |
|---|-------------|------|
| 1 | **Cookie 失效**：标题「安全验证」、`/account/unhuman` | **自动恢复**：脚本内置 3 次重试（激进保活：访问文章页+模拟阅读）；仍失败则 **`python scripts/zhihu.py relogin`** |
| 2 | **收藏夹 API 分页**：带 `include` 时列表可能被截断 | **`zhihu.py collection`** 已内置 API ↔ DOM 切换；必要时减少 `include` 或走浏览器分页 |
| 3 | **反爬**：Headless 被识别 | Stealth、UA、间隔；必要时 **`zhihu.py interactive`** |
| 4 | **API 正文不完整**：`include` 只给摘要 | 批量与单篇流程中已优先 **页面 DOM** 拉全文 |
| 5 | **图片下载失败** | 正文仍保留原 URL；排查网络、Referer、过期链接 |
| 6 | **Windows 控制台 GBK** | 脚本已 **`sys.stdout.reconfigure(encoding='utf-8')`** |
| 7 | **批量中断** | 直接再次运行 **`python scripts/zhihu.py batch`**，依赖 **`_progress.json`** |
| 8 | **失败项累积** | 散发失败自动记录到 `_progress.json`（含 url/reason/title/timestamp）；连续失败 ≥5 次中断并丢弃缓存；用 **`--retry-failed`** 参数可重试 |

### Cookie 保活机制

脚本内置多层 Cookie 保活策略：

1. **主动 TTL 检测**（每篇文章）：解析 z_c0 的 `expires` 字段，剩余 < 30 分钟时自动触发激进刷新
2. **常规保活**（每 5-8 篇）：访问知乎列表页 + 模拟滚动
3. **激进保活**（每 ~20 篇）：访问实际文章页 + 模拟阅读（停留 2-5 秒 + 滚动）
4. **被动检测**：每次访问文章时检查是否被重定向到 `/account/unhuman` 或 `/signin`
5. **自动恢复**：检测到失效时，自动尝试 3 次激进保活恢复
6. **Cookie 备份**：每次保活后自动从浏览器提取最新 Cookie 保存到文件（扩展格式含 expires）
7. **安全退出**：脚本结束前保存最新 Cookie + 当前进度

### 失败处理策略

脚本采用**两级失败处理**，区分「文章本身问题」和「环境问题」：

| 场景 | 行为 | 说明 |
|------|------|------|
| 散发失败（中间有成功） | 记录到 `_progress.json` 的 `failed` 字段 | 视为文章本身问题（已删除/不可访问），后续跳过 |
| 连续失败 ≥ 5 次 | 中断抓取，**丢弃**缓存的失败记录 | 视为环境问题（Cookie/网络），下次重试仍可跑 |

**工作原理：**
- 失败先缓存在内存中，不立即写入进度文件
- 下一条成功时，将缓存的失败记录批量写入进度文件（确认是文章问题）
- 连续失败达到阈值（5 次）时，中断抓取，丢弃缓存（保留重试机会）

**相关常量：**
- `CONSECUTIVE_FAIL_THRESHOLD = 5`：连续失败阈值
- `CONSECUTIVE_FAIL_INTERRUPT = True`：是否在连续失败时中断

**重试模式：**
```bash
python scripts/zhihu.py batch <列表文件> [输出目录] [图片目录] --retry-failed
```
此模式会清空 `failed` 列表，只重试之前记录为失败的文章。

---

## 故障排查流程

```
正文全空？
  → Cookie（含 z_c0）→ 是否跳转验证页 → python scripts/zhihu.py relogin

图片失败？
  → URL/网络/Referer → Markdown 中仍可保留链接

批量中途停止？
  → 确认 _progress.json → 原命令重跑
```

---

## Agent 自用工作流检查清单

```
□ 已确认 scripts 依赖与 playwright chromium 可用；必要时提示用户设置 ZHIHU_WORKSPACE
□ 用户丢了链接：先 python scripts/zhihu.py route，不要猜错模块；裸个人页默认跟读包（专栏+文章+回答）；单栏目用 --posts / --answers / --columns / --collections / --history
□ 收藏夹：zhihu.py collection；指定夹名用 --collection；增量 --since-last；赞数/时间过滤 --min-voteup / --days / --since；再 batch
□ 专栏 / 文章 / 回答 / 问题页：columns、posts、question；文章按 URL 去重；内容更新会 refresh；默认受配置上限，全量才 --all
□ 正文入口有 Cookie 就带上；专栏 403 优先登录而非换抓取器
□ 批量输出路径：知悉默认 {workspace}/zhihu_articles_* 与 images/ 子目录；第三个参数仅在自定义图片目录时需要
□ 回复用户前读 zhihu_run_summary.json（成功/跳过/403/需登录）；失败清单可用 python scripts/zhihu.py failures
□ Obsidian 原文：`zhihu.py obsidian` → `{Vault}/知乎收藏/`；笔记：`zhihu.py notes` → `{Vault}/知乎笔记/`（并列，不改镜像）
□ 遇验证页或全文为空：优先 Cookie/重登录，而非重复盲目加大并发
□ 用户仅需单篇或调试：选用 python scripts/zhihu.py fetch（文章/回答），避免不必要批量
```
