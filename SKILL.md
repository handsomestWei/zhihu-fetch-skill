---
name: zhihu-fetcher
description: "知乎收藏夹与文章内容抓取：API/Playwright 多级降级、Cookie 持久化与保活、批量正文与图片、断点续传、可选写入 Obsidian。| Zhihu collection scraping, batch article fetch, Obsidian export."
version: "1.1.0"
user-invocable: true
argument-hint: "[可选：收藏夹 URL 或 ID、单篇链接、输出目录、Vault 路径]"
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, WebFetch
---

# 知乎数据抓取

从知乎获取**收藏夹文章列表**与**正文 Markdown**（含图片本地化），支持写入 **Obsidian** 知识库。命令与路径约定见下文；可视化说明见仓库根目录 [`README.md`](README.md)。

---

## 环境与约定

- **语言**：默认与用户语种一致。
- **技能根目录**：下文 `${CLAUDE_SKILL_DIR}` 表示本 skill 仓库根目录（部分宿主 UI 中写作 **`{baseDir}`**，含义相同）。脚本均在 **`scripts/`** 下。
- **工作区目录**：脚本默认将 Cookie、浏览器用户数据、默认文章输出等放在 **`OPENCLAW_WORKSPACE`** 环境变量指定的目录；未设置时为 **`~/.openclaw/workspace/`**。
- **依赖**：在 **`scripts/`** 下执行 **`pip install -r requirements.txt`**，并 **`playwright install chromium`**。

### 登录与可选页面验证

- **`zhihu_login.py`**：打开浏览器等待登录，默认以检测到 **`z_c0`** 为成功条件即可结束（不要求额外跳转）。
- **可选二次校验**：若用户希望登录后再确认「某一内需登录页」是否可访问（如某收藏夹页、专栏后台、关注动态等），属**可选项**，不设则不执行：
  - **环境变量** **`ZHIHU_VERIFY_URL`**：值为完整 **`http://` 或 `https://`** URL；
  - **或**命令行第一个参数传入同一完整 URL：`python "${CLAUDE_SKILL_DIR}/scripts/zhihu_login.py" "https://www.zhihu.com/..."`。
  - 脚本会访问该 URL，若正文仍出现知乎通用提示「请登录后查看」，则提示可能未登录完成；否则认为当前会话可访问该页。**不限定于收藏夹**，任意知乎链接均可（只要登录态相关）。
- **`zhihu_relogin.py`**：Cookie 失效、需重新登录并写回 **`zhihu_cookies.json`** 时使用（会打开浏览器）。

---

## 触发条件

在用户使用以下任一方式时启用本技能：

- 明确提及：知乎、Zhihu、专栏、收藏夹、文章抓取、批量下载、Cookie、验证码、Obsidian、知识库同步等
- 粘贴 **zhihu.com** / **zhuanlan.zhihu.com** 链接并希望获取正文或列表
- 需要 **断点续传**、**图片落盘**、**反爬 / Stealth** 相关协助

---

## 工具与脚本路由

按任务选用能力；具体工具名以当前 Agent 环境为准。

### 常见任务与建议方式

| 任务 | 建议方式 |
|------|----------|
| 获取收藏夹 JSON 列表 | **`Bash`** → `python "${CLAUDE_SKILL_DIR}/scripts/fetch_zhihu_collection.py" <收藏夹URL或ID>`；优先 API，失败降级 Playwright DOM |
| 批量抓取正文与图片 | **`Bash`** → `python "${CLAUDE_SKILL_DIR}/scripts/fetch_zhihu_batch.py" <列表.json> [输出目录] [图片目录]`；默认输出目录见「路径约定」 |
| 写入 Obsidian Vault | **`Bash`** → `python "${CLAUDE_SKILL_DIR}/scripts/write_to_obsidian.py" <文章目录> [Vault路径]`；Vault：命令行优先，否则环境变量 **`OBSIDIAN_VAULT`**；会先找 `<文章目录>/images`，否则兼容同级 **`zhihu_images`** |
| Cookie 失效需人工登录 | **`Bash`** → `python "${CLAUDE_SKILL_DIR}/scripts/zhihu_relogin.py"`（会打开浏览器窗口） |
| 首次登录辅助（可选验证页） | **`Bash`** → `zhihu_login.py`；可选 **`ZHIHU_VERIFY_URL`** 或首个参数传入完整 http(s) 链接，见「登录与可选页面验证」 |
| 单篇快速验证 | **`Bash`** → `fetch_zhihu_api.py` / `fetch_zhihu_stealth.py` / `fetch_zhihu_interactive.py` / 汇总 **`fetch_zhihu.py`**（自动多策略），按场景选用 |
| 读本地已抓取 Markdown、排查 `_progress.json` | **`Read`** / **`Grep`** |

---

## 脚本一览

| 脚本 | 用途 | 典型场景 |
|------|------|----------|
| `fetch_zhihu_collection.py` | **收藏夹列表**，智能版 | 输出 `zhihu_collection_{id}.json` |
| `fetch_zhihu_batch.py` | **批量抓取**，推荐 | 大量文章、图片、`images/`、`_progress.json` |
| `fetch_zhihu.py` | 自动降级抓取 | 单篇、多策略串联 |
| `fetch_zhihu_api.py` | API 直连 | 快速测试 |
| `fetch_zhihu_stealth.py` | Playwright 隐身 | 绕过常见自动化检测 |
| `fetch_zhihu_interactive.py` | 交互式浏览器 | 登录页、验证码 |
| `write_to_obsidian.py` | 写入 Obsidian | 自动检测 Vault、智能分类、`知乎收藏/` |
| `zhihu_relogin.py` | 重新登录 | Cookie 不可用 |
| `zhihu_login.py` | 登录辅助 | 检测 `z_c0`；可选访问 **`ZHIHU_VERIFY_URL`** / 命令行 URL 做页面级验证 |
| `zhihu_login_save.py` | 登录并保存 | 按需配合 Cookie 流程 |

---

## 主流程（推荐执行顺序）

1. **安装依赖**：`scripts/requirements.txt` + Chromium。
2. **`fetch_zhihu_collection.py`** → 得到收藏夹 **JSON 列表**。
3. **`fetch_zhihu_batch.py`** → 生成 **`zhihu_articles_{collectionId}/`**（含 **`_progress.json`**、**`images/`**、编号 **`*.md`**）。
4. （可选）**`write_to_obsidian.py`** → 同步到 **`{Vault}/知乎收藏/{分类}/`**。

中断批量任务时：**重新运行同一条** `fetch_zhihu_batch.py` 命令即可续跑（已完成 URL 记录在 `_progress.json`）。

---

## 路径与输出约定

### 批量抓取命令格式

```bash
python fetch_zhihu_batch.py <列表文件> [输出目录] [图片目录]
```

| 参数 | 说明 |
|------|------|
| **列表文件** | `fetch_zhihu_collection.py` 产出的 JSON |
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

| 用途 | 路径 |
|------|------|
| Cookie | `{workspace}/zhihu_cookies.json` |
| Playwright 用户数据 | `{workspace}/chrome_user_data/` |
| 默认文章目录 | `{workspace}/zhihu_articles_{collectionId}/` |
| 默认图片目录 | `{文章输出目录}/images/` |

---

## Obsidian 写入要点

- **Vault**：① **命令行第二个参数**（优先让用户直接写出 Vault 根路径）；② 未传时使用环境变量 **`OBSIDIAN_VAULT`**（单个路径）；③ 仍无时脚本按常见目录扫描，多个命中时再交互选择。
- **分类**：优先对齐已有 **`知乎收藏/`** 子目录；否则按内容关键词；无法归类则 **「未分类」**。
- **落盘**：**`{Vault}/知乎收藏/{分类}/{文章标题}.md`**；图片同步规则见 **`write_to_obsidian.py`**（目标侧常有集中 **`images`** 目录）。

---

## 已知问题与对策

| # | 现象 / 原因 | 处理 |
|---|-------------|------|
| 1 | **Cookie 失效**：标题「安全验证」、`/account/unhuman` | **自动恢复**：脚本内置 3 次重试（激进保活：访问文章页+模拟阅读）；仍失败则 **`zhihu_relogin.py`** |
| 2 | **收藏夹 API 分页**：带 `include` 时列表可能被截断 | **`fetch_zhihu_collection.py`** 已内置 API ↔ DOM 切换；必要时减少 `include` 或走浏览器分页 |
| 3 | **反爬**：Headless 被识别 | Stealth、UA、间隔；必要时 **`fetch_zhihu_interactive.py`** |
| 4 | **API 正文不完整**：`include` 只给摘要 | 批量与单篇流程中已优先 **页面 DOM** 拉全文 |
| 5 | **图片下载失败** | 正文仍保留原 URL；排查网络、Referer、过期链接 |
| 6 | **Windows 控制台 GBK** | 脚本已 **`sys.stdout.reconfigure(encoding='utf-8')`** |
| 7 | **批量中断** | 直接再次运行 **`fetch_zhihu_batch.py`**，依赖 **`_progress.json`** |
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
python fetch_zhihu_batch.py <列表文件> [输出目录] [图片目录] --retry-failed
```
此模式会清空 `failed` 列表，只重试之前记录为失败的文章。

---

## 故障排查流程

```
正文全空？
  → Cookie（含 z_c0）→ 是否跳转验证页 → zhihu_relogin.py

图片失败？
  → URL/网络/Referer → Markdown 中仍可保留链接

批量中途停止？
  → 确认 _progress.json → 原命令重跑
```

---

## Agent 自用工作流检查清单

```
□ 已确认 scripts 依赖与 playwright chromium 可用；必要时提示用户设置 OPENCLAW_WORKSPACE
□ 收藏夹任务：已运行 fetch_zhihu_collection.py 并得到合法 JSON，再执行 fetch_zhihu_batch.py
□ 批量输出路径：知悉默认 {workspace}/zhihu_articles_* 与 images/ 子目录；第三个参数仅在自定义图片目录时需要
□ Obsidian：`write_to_obsidian.py` 的文章目录含 *.md 与 images/；Vault 优先命令行路径或 **`OBSIDIAN_VAULT`**
□ 遇验证页或全文为空：优先 Cookie/重登录，而非重复盲目加大并发
□ 用户仅需单篇或调试：选用 fetch_zhihu_api / stealth / interactive / fetch_zhihu，避免不必要批量
```
