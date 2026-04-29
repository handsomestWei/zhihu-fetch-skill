<div align="center">

# 知乎抓取.skill

> 从知乎**收藏夹列表**到**批量正文与图片**，再到 **Obsidian 自动分类入库**：API / Playwright 多级降级、Cookie 持久化与保活、断点续传。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Playwright-Chromium-45ba4b.svg)](https://playwright.dev/)
[![AgentSkills](https://img.shields.io/badge/AgentSkills-Standard-green)](https://agentskills.io)

<br>

收藏夹里上千篇文章想**归档成 Markdown**？<br>
需要**配图本地化**、中断后能**接着抓**？<br>
希望落库到 Obsidian，并**按主题自动分类**？<br>
Cookie 经常失效，想要**持久化上下文 + 保活**？

**本 Skill 按 AgentSkills 约定编排全流程，入口见根目录 [`SKILL.md`](SKILL.md)，脚本集中在 `scripts/`。**

[功能特性](#功能特性) · [安装](#安装) · [使用](#使用) · [项目结构](#项目结构) · [运行效果](#运行效果) · [参考文档](#参考文档)

</div>

---

## 功能特性

| 能力 | 说明 |
|------|------|
| 收藏夹列表 | `fetch_zhihu_collection.py` 优先 API，失败降级 Playwright DOM；输出 JSON 列表 |
| 批量抓取 | `fetch_zhihu_batch.py`：正文 Markdown、图片默认写入 `{输出目录}/images/`、`_progress.json` 断点续传 |
| Cookie | 持久化浏览器上下文 + 定时保活；失效时用 `zhihu_relogin.py` 手动登录 |
| 单篇 / 调试 | `fetch_zhihu.py`、`fetch_zhihu_api.py`、`fetch_zhihu_stealth.py`、`fetch_zhihu_interactive.py` 等多路径 |
| Obsidian | `write_to_obsidian.py`：Vault 检测、按内容与已有「知乎收藏」结构智能分类、同步图片 |

**依赖**：见 [`scripts/requirements.txt`](scripts/requirements.txt)，并需 `playwright install chromium`。

---

## 安装

### Claude Code / Cursor

将本仓库放到宿主约定的 skills 路径（与 [`SKILL.md`](SKILL.md) 同级为 skill 根目录），重启后在规则或技能列表中确认已加载。

```bash
# 示例：克隆到项目的 skills 目录
mkdir -p .cursor/skills
git clone https://github.com/handsomestWei/zhihu-fetch-skill.git .cursor/skills/zhihu-fetch-skill
```

### 依赖

```bash
cd scripts
pip install -r requirements.txt
playwright install chromium
```

---

## 使用

在 Agent 中用自然语言描述即可，例如：知乎文章、收藏夹、批量抓取、写入 Obsidian、Cookie 失效。

典型三步（路径请按本机 `{workspace}` 调整，详见 [`SKILL.md`](SKILL.md)）：

```bash
# 1. 收藏夹 → JSON 列表
python scripts/fetch_zhihu_collection.py <收藏夹URL或ID>

# 2. 批量抓取正文与图片
python scripts/fetch_zhihu_batch.py <列表.json>

# 3. 写入 Obsidian Vault（可选 Vault 路径）
python scripts/write_to_obsidian.py <文章目录> [Vault路径]
```

Cookie 异常时：

```bash
python scripts/zhihu_relogin.py
```

---

## 项目结构

本仓库遵循 [AgentSkills](https://agentskills.io)，根目录即一个 skill：

```
zhihu-fetch-skill/
├── SKILL.md                 # 技能入口：触发条件、命令与路径约定
├── README.md                # 本说明
├── LICENSE
├── .gitignore
├── docs/                    # 文档配图（运行效果截图）
│   ├── openclaw-run.jpg
│   └── obs.jpg
└── scripts/
    ├── requirements.txt
    ├── fetch_zhihu_collection.py
    ├── fetch_zhihu_batch.py
    ├── fetch_zhihu.py
    ├── fetch_zhihu_api.py
    ├── fetch_zhihu_stealth.py
    ├── fetch_zhihu_interactive.py
    ├── write_to_obsidian.py
    ├── zhihu_login.py
    ├── zhihu_login_save.py
    └── zhihu_relogin.py
```

默认文章与图片目录等行为以 [`SKILL.md`](SKILL.md)「批量抓取详解」「文件路径」为准。

---

## 运行效果

**在 OpenClaw 对话中执行批量抓取**（工具输出中可见进度、剩余篇数、图片数量与 Cookie 保活提示）

![OpenClaw 聊天：批量抓取进度与 Cookie 保活](./docs/openclaw-run.jpg)

**写入 Obsidian 后的 Vault 结构**（「知乎收藏」下主题分类与关系图谱）

![Obsidian：知乎收藏分类与关系图谱](./docs/obs.jpg)

---

## 参考文档

- [技能入口与完整命令说明](SKILL.md)（依赖、脚本表、故障排查）
- [脚本依赖清单](scripts/requirements.txt)

---

<div align="center">

MIT License © [handsomestWei](https://github.com/handsomestWei/)

</div>
