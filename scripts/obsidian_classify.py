#!/usr/bin/env python3
"""Obsidian「知乎收藏」智能分类：扫描已有目录 + 模板启发式。"""

import os

# 预定义模板（参考用，不强制；已有 Vault 分类优先）
ZHIHU_TEMPLATE_RULES = {
    "AI与人工智能": [
        "ai", "人工智能", "gpt", "chatgpt", "大模型", "llm", "深度学习",
        "机器学习", "openai", "claude", "gemini", "aigc", "agent",
    ],
    "编程与开发": [
        "python", "java", "javascript", "typescript", "编程", "代码",
        "开发", "框架", "api", "数据库", "docker", "git", "前端", "后端",
    ],
    "创业与商业": [
        "创业", "商业", "融资", "投资", "startup", "产品", "运营",
        "市场", "营销", "一人公司", "独立开发", "副业",
    ],
    "效率与工具": ["效率", "工具", "自动化", "工作流", "笔记", "obsidian", "notion"],
    "职场与成长": ["职场", "工作", "面试", "职业", "成长", "学习", "认知"],
    "科技与互联网": ["科技", "互联网", "芯片", "区块链", "web3", "自动驾驶"],
    "产品与设计": ["产品", "设计", "ui", "ux", "交互", "用户体验", "figma"],
    "生活杂谈": ["生活", "健康", "旅行", "电影", "读书", "随笔", "思考"],
}

# 非文章分类的固定子目录
ZHIHU_RESERVED_DIRS = frozenset({"images"})


def detect_existing_categories(vault_path):
    """
    扫描 Obsidian Vault 中已有的分类目录。
    返回: {'zhihu': {分类名: 文章数}, 'vault': {一级目录: 文章数}}
    """
    categories = {}
    zhihu_dir = os.path.join(vault_path, "知乎收藏")

    if os.path.exists(zhihu_dir):
        for item in os.listdir(zhihu_dir):
            if item in ZHIHU_RESERVED_DIRS or item.startswith("."):
                continue
            item_path = os.path.join(zhihu_dir, item)
            if os.path.isdir(item_path):
                article_count = len(
                    [f for f in os.listdir(item_path) if f.endswith(".md")]
                )
                categories[item] = article_count

    vault_categories = {}
    for item in os.listdir(vault_path):
        item_path = os.path.join(vault_path, item)
        if os.path.isdir(item_path) and not item.startswith("."):
            article_count = len(
                [f for f in os.listdir(item_path) if f.endswith(".md")]
            )
            vault_categories[item] = article_count

    return {"zhihu": categories, "vault": vault_categories}


def analyze_content_categories(_article_files, existing_categories):
    """
    结合 Vault 已有「知乎收藏」子目录与模板，生成分类规则。
    _article_files: 待导入文章路径（预留扩展；当前主要依赖 existing_categories）。
    """

    existing_keywords = {}
    for cat_name in existing_categories.get("zhihu", {}):
        existing_keywords[cat_name] = cat_name.lower()

    template_rules = dict(ZHIHU_TEMPLATE_RULES)
    zhihu_count = len(existing_categories.get("zhihu", {}))

    if zhihu_count >= 3:
        print(f"检测到已有 {zhihu_count} 个分类，优先匹配已有分类")
        return existing_keywords, template_rules

    print(f"已有分类较少（{zhihu_count} 个），使用智能分类")
    return {}, template_rules


def classify_article(title, content_preview, existing_keywords, template_rules):
    """优先匹配已有分类名，其次模板关键词，再次标题特征，否则「未分类」。"""
    text = (title + " " + content_preview).lower()

    if existing_keywords:
        for cat_name, keyword in existing_keywords.items():
            if keyword in text:
                return cat_name

    scores = {}
    for category, keywords in template_rules.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[category] = score

    if scores:
        return max(scores, key=scores.get)

    if any(w in title for w in ["?", "？", "如何", "怎么", "为什么", "是什么"]):
        return "问答与思考"

    return "未分类"
