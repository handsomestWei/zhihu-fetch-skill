#!/usr/bin/env python3
"""Skip gone Zhihu resources (deleted posts, dead images) instead of failing the run."""
from __future__ import annotations

import hashlib
import html as html_lib
import os
import urllib.error
import urllib.request

GONE_HTTP = {404, 410, 451}
GONE_REASONS = frozenset({"http_404", "gone", "resource_not_found"})
GONE_HINTS = (
    "没有知识存在的荒原",
    "ResourceNotFoundException",
    "内容不存在",
    "该回答已被删除",
    "该文章已被删除",
)


def is_resource_gone(status=0, text="", error=""):
    try:
        code = int(status or 0)
    except (TypeError, ValueError):
        code = 0
    if code in GONE_HTTP:
        return True
    blob = f"{text or ''} {error or ''}"
    if any(hint in blob for hint in GONE_HINTS):
        return True
    err = str(error or "")
    if "api_failed:404" in err or "api_failed:410" in err:
        return True
    return False


def normalize_image_src(src):
    text = html_lib.unescape((src or "").strip())
    if text.startswith("//"):
        text = "https:" + text
    return text


def image_url_candidates(src):
    src = normalize_image_src(src)
    if not src or src.startswith("data:"):
        return []
    out = [src]
    if "?" in src and "/equation" not in src:
        stripped = src.split("?", 1)[0]
        if stripped not in out:
            out.append(stripped)
    return out


def _image_filename(url):
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    ext = ".jpg"
    lower = url.lower().split("?", 1)[0]
    if ".png" in lower:
        ext = ".png"
    elif ".gif" in lower:
        ext = ".gif"
    elif ".webp" in lower:
        ext = ".webp"
    elif ".svg" in lower:
        ext = ".svg"
    return f"{url_hash}{ext}"


def try_download_image(url, save_dir, cookie_header="", log=True):
    """Download one image. Return (filename_or_None, http_status_or_0)."""
    candidates = image_url_candidates(url)
    if not candidates:
        return None, 0
    last_status = 0
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://zhuanlan.zhihu.com/",
    }
    if cookie_header:
        headers["Cookie"] = cookie_header
    os.makedirs(save_dir, exist_ok=True)
    for candidate in candidates:
        filename = _image_filename(candidate.split("?")[0])
        filepath = os.path.join(save_dir, filename)
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            return filename, 0
        req = urllib.request.Request(candidate, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                data = response.read()
                if not data:
                    last_status = int(getattr(response, "status", 0) or 0) or 404
                    continue
                with open(filepath, "wb") as f:
                    f.write(data)
            return filename, 0
        except urllib.error.HTTPError as exc:
            last_status = exc.code
            if exc.code in GONE_HTTP:
                continue
            last_status = exc.code
        except Exception:
            last_status = last_status or 0
    if log and last_status in GONE_HTTP:
        print(f"  [跳过] 图片 HTTP {last_status}: {url[:100]}")
    return None, last_status
