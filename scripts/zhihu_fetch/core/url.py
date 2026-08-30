#!/usr/bin/env python3
"""Classify Zhihu URLs into existing fetch pipelines."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class ZhihuTarget:
    kind: str
    url: str
    slug: str = ""
    collection_id: str = ""
    column_id: str = ""
    article_id: str = ""
    answer_id: str = ""
    question_id: str = ""

    def people_url(self):
        return f"https://www.zhihu.com/people/{self.slug}" if self.slug else ""


def _digits(text):
    return "".join(ch for ch in text if ch.isdigit())


def classify_zhihu_url(raw):
    text = (raw or "").strip()
    if not text:
        return ZhihuTarget(kind="unknown", url="")

    if text.startswith("http://") or text.startswith("https://"):
        parsed = urlparse(text)
        host = (parsed.netloc or "").lower()
        parts = [p for p in parsed.path.split("/") if p]
        url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".split("?")[0]

        if "zhuanlan.zhihu.com" in host:
            if len(parts) >= 2 and parts[0] == "p" and parts[1].isdigit():
                return ZhihuTarget(kind="article", url=url, article_id=parts[1])
            if parts and parts[0] not in {"p", "api"}:
                return ZhihuTarget(kind="column", url=url, column_id=parts[0])
            return ZhihuTarget(kind="unknown", url=url)

        if "zhihu.com" not in host:
            return ZhihuTarget(kind="unknown", url=url)

        if "collection" in parts:
            idx = parts.index("collection")
            cid = parts[idx + 1] if idx + 1 < len(parts) else ""
            return ZhihuTarget(kind="collection", url=url, collection_id=_digits(cid) or cid)

        if "column" in parts:
            idx = parts.index("column")
            token = parts[idx + 1] if idx + 1 < len(parts) else ""
            return ZhihuTarget(kind="column", url=url, column_id=token)

        if "answer" in parts:
            idx = parts.index("answer")
            aid = parts[idx + 1] if idx + 1 < len(parts) else ""
            qid = ""
            if "question" in parts:
                qidx = parts.index("question")
                if qidx + 1 < len(parts):
                    qid = parts[qidx + 1]
            return ZhihuTarget(
                kind="answer",
                url=url,
                answer_id=_digits(aid) or aid,
                question_id=_digits(qid) or qid,
            )

        if "question" in parts:
            idx = parts.index("question")
            qid = parts[idx + 1] if idx + 1 < len(parts) else ""
            return ZhihuTarget(
                kind="question",
                url=url,
                question_id=_digits(qid) or qid,
            )

        if len(parts) >= 2 and parts[0] == "p" and parts[1].isdigit():
            return ZhihuTarget(
                kind="article",
                url=f"https://zhuanlan.zhihu.com/p/{parts[1]}",
                article_id=parts[1],
            )

        if "people" in parts:
            idx = parts.index("people")
            slug = parts[idx + 1] if idx + 1 < len(parts) else ""
            tab = parts[idx + 2] if idx + 2 < len(parts) else ""
            kind = {
                "columns": "columns",
                "collections": "collections",
                "posts": "posts",
                "answers": "answers",
                "activities": "history",
            }.get(tab, "people")
            return ZhihuTarget(kind=kind, url=url, slug=slug)

        return ZhihuTarget(kind="unknown", url=url)

    if text.isdigit():
        return ZhihuTarget(kind="unknown", url=text)

    return ZhihuTarget(kind="people", url=f"https://www.zhihu.com/people/{text}", slug=text)
