#!/usr/bin/env python3
"""
fetch_trending.py — 从 GitHub Trending 抓取仓库
=================================================

数据源：https://github.com/trending
策略：
  - 按语言分别抓取 daily trending（python, javascript, typescript, go, rust, shell, unknown）
  - 合并去重 + 按 stars_today 排序
  - 提取字段：repo (owner/name), description, language, stars_total, stars_today, forks, url, primary_topic
  - 缓存到 data/trending_<YYYY-MM-DD>.json（同一日复用，可加 --force 强制刷新）

依赖：requests（轻量，零额外三方即可；如未装用 stdlib urllib）
"""

from __future__ import annotations
import argparse
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    requests = None  # type: ignore
    import urllib.request
    import urllib.error

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# 默认语言：开发者关注度最高的 5 种 + unknown（全语言兜底）
DEFAULT_LANGUAGES = ["python", "javascript", "typescript", "go", "rust", "shell", "unknown"]

GITHUB_TRENDING = "https://github.com/trending/{lang}?since={since}"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


# ----------------------- HTTP -----------------------

def _fetch(url: str, timeout: int = 30) -> str:
    if requests is not None:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
        r.raise_for_status()
        return r.text

    # stdlib fallback
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


# ----------------------- 解析 -----------------------

# 一个 article 块
ARTICLE_RE = re.compile(r'<article class="Box-row">(.*?)</article>', re.DOTALL)

# 仓库名 href  -- 形如 href="/owner/repo"
HREF_RE = re.compile(r'href="/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)"\s+data-view-component="true"\s+class="Link"')

# 描述：col-9 color-fg-muted my-1 ... </p>
DESC_RE = re.compile(
    r'<p class="col-9 color-fg-muted my-1[^"]*">\s*(.*?)\s*</p>',
    re.DOTALL,
)

# 语言
LANG_RE = re.compile(r'<span itemprop="programmingLanguage">([^<]+)</span>')

# 仓库 star: 形如 "  34,620"（在 Link--muted 链接后的 svg star 后）
# 用更稳定的 'stargazers' href 后抓
STARS_TOTAL_RE = re.compile(
    r'href="/[^"]+/stargazers"[^>]*>.*?\s([\d,]+)\s*</a>',
    re.DOTALL,
)
FORKS_RE = re.compile(
    r'href="/[^"]+/forks"[^>]*>.*?\s([\d,]+)\s*</a>',
    re.DOTALL,
)

# stars_today: ' <n> stars today'
STARS_TODAY_RE = re.compile(r'([\d,]+)\s+stars\s+(today|this\s+week|yesterday|this\s+month)')


def _clean(text: str) -> str:
    """去掉残留 HTML 实体/标签"""
    text = re.sub(r"<[^>]+>", "", text)
    text = (
        text.replace("&quot;", '"')
        .replace("&amp;", "&")
        .replace("&#39;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&nbsp;", " ")
    )
    return text.strip()


def _num(s: str) -> int:
    return int(s.replace(",", "").strip()) if s else 0


def parse_trending_html(html: str, source_language: str) -> list[dict[str, Any]]:
    """从单页 trending HTML 解析仓库列表"""
    repos: list[dict[str, Any]] = []
    seen: set[str] = set()

    for article in ARTICLE_RE.findall(html):
        # 1) 仓库 owner/name —— 用第一个匹配的 href
        m = HREF_RE.search(article)
        if not m:
            continue
        owner, name = m.group(1), m.group(2)
        repo_key = f"{owner}/{name}"
        if repo_key in seen:
            continue
        seen.add(repo_key)

        # 2) 描述
        desc = ""
        if dm := DESC_RE.search(article):
            desc = _clean(dm.group(1))
            if not desc:
                desc = "(no description)"

        # 3) 语言（页面筛选语言 → 兜底从 article 抽出）
        language = source_language if source_language != "unknown" else ""
        if lm := LANG_RE.search(article):
            language = _clean(lm.group(1))

        # 4) stars_total / forks
        stars_total = 0
        forks = 0
        if sm := STARS_TOTAL_RE.search(article):
            stars_total = _num(sm.group(1))
        if fm := FORKS_RE.search(article):
            forks = _num(fm.group(1))

        # 5) stars_today
        stars_today = 0
        if tm := STARS_TODAY_RE.search(article):
            stars_today = _num(tm.group(1))

        repos.append({
            "repo": repo_key,
            "owner": owner,
            "name": name,
            "description": desc,
            "language": language,
            "stars_total": stars_total,
            "stars_today": stars_today,
            "forks": forks,
            "url": f"https://github.com/{owner}/{name}",
            "source_language": source_language,
        })

    return repos


# ----------------------- 主流程 -----------------------

def fetch_all(since: str = "daily", languages: list[str] | None = None,
              force: bool = False, today: datetime.date | None = None) -> tuple[Path, list[dict[str, Any]]]:
    """返回 (cache_path, repos)。缓存命中时也返回缓存里的 repos。"""
    today = today or datetime.date.today()
    cache_path = DATA_DIR / f"trending_{today.isoformat()}.json"

    if cache_path.exists() and not force:
        print(f"📦 命中缓存: {cache_path.name}（用 --force 重抓）")
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return cache_path, data.get("repos", [])

    languages = languages or DEFAULT_LANGUAGES
    all_repos: list[dict[str, Any]] = []
    dedup: dict[str, dict[str, Any]] = {}  # repo_key → repo，stars_today 最大的保留

    for lang in languages:
        url = GITHUB_TRENDING.format(lang=lang, since=since)
        print(f"🔎 抓取 {lang:11s} ... ", end="", flush=True)
        try:
            html = _fetch(url, timeout=30)
        except Exception as e:
            print(f"❌ 失败 ({e.__class__.__name__}: {e})")
            continue
        repos = parse_trending_html(html, source_language=lang)
        print(f"✅ {len(repos)} 个仓库")

        for r in repos:
            existing = dedup.get(r["repo"])
            # 同一仓库可能在多个语言榜单出现（如 C++/C 互现）
            if existing is None or r["stars_today"] > existing["stars_today"]:
                dedup[r["repo"]] = r

        time.sleep(0.5)  # 礼貌延迟

    all_repos = list(dedup.values())
    # 排序：stars_today 优先，再按 stars_total
    all_repos.sort(key=lambda x: (x["stars_today"], x["stars_total"]), reverse=True)

    # 写缓存
    payload = {
        "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "since": since,
        "languages": languages,
        "count": len(all_repos),
        "repos": all_repos,
    }
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n💾 缓存写入: {cache_path}")
    print(f"📊 去重后共 {len(all_repos)} 个仓库")

    return cache_path, all_repos  # ← 返回 (cache_path, repos)


# ----------------------- CLI -----------------------

def main():
    p = argparse.ArgumentParser(
        description="从 GitHub Trending 抓取仓库（按场景分类前的预处理）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例:
  python scripts/fetch_trending.py                 # 默认多语言 daily trending
  python scripts/fetch_trending.py --lang python javascript --since weekly
  python scripts/fetch_trending.py --force        # 强制重抓
""",
    )
    p.add_argument("--since", default="daily", choices=["daily", "weekly", "monthly"],
                   help="Trending 时间范围（默认 daily）")
    p.add_argument("--lang", nargs="+", default=None, metavar="LANG",
                   help="要抓的语言列表（默认五种主流 + unknown 兜底）")
    p.add_argument("--force", action="store_true", help="忽略缓存强制重抓")
    p.add_argument("--top", type=int, default=0,
                   help="只打印前 N 个仓库（不传=全部；缓存仍写入完整列表）")
    args = p.parse_args()

    _, repos = fetch_all(since=args.since, languages=args.lang, force=args.force)

    # 打印预览
    preview = repos[: args.top] if args.top > 0 else repos
    print(f"\n{'='*80}\n预览（共 {len(preview)} / {len(repos)}）\n{'='*80}")
    for i, r in enumerate(preview, 1):
        print(f"  {i:>2}. [{r['language'] or '?':10s}] ⭐+{r['stars_today']:<5}  {r['repo']}")
        if r["description"]:
            print(f"       └─ {r['description'][:90]}{'...' if len(r['description'])>90 else ''}")

    if not repos:
        print("⚠️  没有抓到任何仓库，请检查网络", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
