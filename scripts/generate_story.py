#!/usr/bin/env python3
"""
generate_story.py — 从"按场景分类的 trending 仓库"生成视频文案
================================================================

输入：data/trending_<date>_classified.json（来自 classify_scene.py）
输出：content.json（pipeline.py 直接消费的格式）

流程：
  1. 读分类结果 → 按场景选 Top 仓库（默认每个场景 Top 1 → 凑齐 Top N 个视频中要讲的仓库）
  2. 拼 prompt 描述仓库，让 LLM 写一段故事化脚本
  3. LLM 返回标准 content.json 格式

LLM：默认 GLM-5.1（zai Coding Plan），自动 fallback 到 glm-5.2
   - base_url: https://open.bigmodel.cn/api/coding/paas/v4
   - api_key: env GLM_API_KEY
   - max_tokens 必须够大（GLM 推理模型 reasoning_tokens 占空间），默认 4000
"""

from __future__ import annotations
import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"

# GLM Coding Plan (Z.AI)
GLM_BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
GLM_API_KEY_ENV = "GLM_API_KEY"
DEFAULT_MODEL = os.environ.get("VIDEO_STORY_MODEL", "glm-5.1")
DEFAULT_MAX_TOKENS = 4000  # 必须留足空间给 reasoning_tokens（GLM 推理模型的特性）
DEFAULT_TEMPERATURE = 0.8


# ----------------------- LLM 调用 -----------------------

def call_glm(prompt: str, system: str = "",
             model: str = DEFAULT_MODEL, max_tokens: int = DEFAULT_MAX_TOKENS,
             temperature: float = DEFAULT_TEMPERATURE,
             timeout: int = 120) -> tuple[str, dict[str, Any]]:
    """调用 GLM / Z.AI，返回 (content_text, usage_dict). 失败抛 RuntimeError。"""
    api_key = os.environ.get(GLM_API_KEY_ENV)
    if not api_key:
        raise RuntimeError(f"环境变量 {GLM_API_KEY_ENV} 未设置")

    url = f"{GLM_BASE_URL}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            *([{"role": "system", "content": system}] if system else []),
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GLM HTTP {e.code}: {body[:500]}") from e
    except Exception as e:
        raise RuntimeError(f"GLM 调用失败: {e}") from e

    msg = data["choices"][0]["message"]
    content = msg.get("content", "") or ""
    return content, data.get("usage", {})


def call_glm_with_retry(prompt: str, system: str = "",
                        model: str = DEFAULT_MODEL, max_tokens: int = DEFAULT_MAX_TOKENS,
                        temperature: float = DEFAULT_TEMPERATURE,
                        max_retries: int = 2) -> str:
    """调用 GLM 并对"空 content"自动重试（GLM 推理模型常见问题）"""
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            content, usage = call_glm(prompt, system, model, max_tokens, temperature)
            if content.strip():
                # 顺便打印用量
                if usage:
                    print(f"  📊 usage: prompt={usage.get('prompt_tokens','?')} "
                          f"completion={usage.get('completion_tokens','?')} "
                          f"reasoning={usage.get('completion_tokens_details',{}).get('reasoning_tokens','?')}")
                return content
            else:
                print(f"  ⚠️  GLM 返回空 content（attempt {attempt+1}/{max_retries+1}），重试...")
                last_err = "empty content"
                time.sleep(2)
        except RuntimeError as e:
            last_err = str(e)
            print(f"  ⚠️  GLM 调用异常: {e}")
            time.sleep(2)
    raise RuntimeError(f"GLM 多次重试仍失败: {last_err}")


def _extract_json(text: str) -> dict[str, Any]:
    """从 LLM 输出提取 JSON（处理 ```json ... ``` 包裹、文中夹杂对话）"""
    text = text.strip()

    # 1) 整段就是 JSON
    if text.startswith("{"):
        return json.loads(text)

    # 2) ```json ... ```
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1))

    # 3) 抓第一个完整的 {...} 块
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    start = None
                    continue

    raise ValueError(f"无法从 LLM 输出提取 JSON:\n{text[:1000]}")


# ----------------------- 内容选择 -----------------------

def select_featured_repos(classified: dict[str, Any],
                          top_per_scene: int = 1,
                          top_total: int = 3) -> list[tuple[dict[str, Any], str]]:
    """从分类结果里选出要讲的仓库。

    策略：先按 stars_today 全局排序，但优先从不同场景选，避免重复。
    返回 [(repo_dict, scene_key), ...]。
    """
    groups = classified.get("groups", {})
    all_repos: list[tuple[dict[str, Any], str]] = []
    seen: set[str] = set()
    # 把每个场景的前 N 个拿出来
    for scene_key, items in groups.items():
        items_sorted = sorted(items, key=lambda x: x.get("stars_today", 0), reverse=True)
        for r in items_sorted[:top_per_scene]:
            if r["repo"] not in seen:
                seen.add(r["repo"])
                all_repos.append((r, scene_key))

    # 按 stars_today 排序
    all_repos.sort(key=lambda x: x[0].get("stars_today", 0), reverse=True)
    return all_repos[:top_total]  # ← 修复：返回 (repo, scene) tuples


def build_repo_briefs(repos: list[tuple[dict[str, Any], str]],
                      scenes_labels: dict[str, str]) -> str:
    """构造给 LLM 看的仓库摘要"""
    lines = []
    for i, (r, scene_key) in enumerate(repos, 1):
        scene_label = scenes_labels.get(scene_key, scene_key)
        lines.append(
            f"### {i}. {r['repo']}  ({scene_label})\n"
            f"- **描述**: {r.get('description', '(无描述)')}\n"
            f"- **语言**: {r.get('language', '?') or '?'}\n"
            f"- **今日 star**: ⭐+{r.get('stars_today', 0):,}\n"
            f"- **总 star**: {r.get('stars_total', 0):,}\n"
            f"- **URL**: {r.get('url', '')}\n"
        )
    return "\n".join(lines)


# ----------------------- Prompt 构造 -----------------------

SYSTEM_PROMPT = """你是"今日 GitHub 热门速报"的短视频文案编辑。

风格要求：
- 语言：中文口语化、有节奏感、像真人讲解
- 让人看了就想点收藏
- 每段（segment）必须有字幕（subtitle），简短有力 8-15 字
- 每段配图 prompt 用英文（16:9, photorealistic, high detail）
- 严格按下方 JSON Schema 输出，不要任何解释/前言/后记

JSON Schema（必须严格遵守）：
{
  "title": "视频标题 25 字以内，有冲击力",
  "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"],
  "desc": "150 字以内的视频简介，B 站/抖音风格，1-2 句话讲亮点",
  "segments": [
    {
      "id": 1,
      "narration": "中文旁白 60-120 字，要口语、有节奏、有信息密度",
      "image_prompt": "English prompt for image gen, 16:9, photorealistic",
      "subtitle": "中文短标题 8-15 字"
    }
  ]
}

段数：恰好 6 段。
结构：
  1. hook（抓住眼球，30 字内点题）
  2-3. 项目 1 详解
  4-5. 项目 2 详解（如有）
  6. CTA（结尾互动，问观众"你最想试哪个"）

每次只把"最重要、最值得讲"的 1-2 个项目展开，其他在 desc/标题里带过。
"""

USER_PROMPT_TEMPLATE = """# 今日 Trending Top 仓库（共 {n} 个）

{repo_briefs}

# 任务

写一段 6 段的"今日 Trending 速报"视频脚本：
- 标题要能让人 1 秒就知道今天有什么值得关注
- 第 1 段 hook，要直接说"今天这几样东西突然火起来了"
- 主要展开 1-2 个最值得讲的项目（按 ⭐+ 排序最高的）
- 其他项目在标题或简介里提到即可
- 最后一段一定要互动：让观众评论他们最想试哪个

严格按 JSON Schema 输出，不要任何 markdown ```json``` 包裹外的废话。
"""


def build_prompt(repos: list[tuple[dict[str, Any], str]],
                 scenes_labels: dict[str, str]) -> tuple[str, str]:
    briefs = build_repo_briefs(repos, scenes_labels)
    return SYSTEM_PROMPT, USER_PROMPT_TEMPLATE.format(n=len(repos), repo_briefs=briefs)


# ----------------------- 主流程 -----------------------

def main():
    p = argparse.ArgumentParser(
        description="从已分类的 trending 仓库生成视频文案 (content.json)",
    )
    p.add_argument("--date", default=None,
                   help="trending JSON 日期（YYYY-MM-DD），默认取最新")
    p.add_argument("--top", type=int, default=3,
                   help="本次视频要讲的 Top N 仓库（默认 3）")
    p.add_argument("--per-scene", type=int, default=1,
                   help="每个场景最多选几个仓库（保证多样性，默认 1）")
    p.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                   help=f"LLM max_tokens（默认 {DEFAULT_MAX_TOKENS}，GLM 推理模型需要大值）")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"模型名（默认 {DEFAULT_MODEL}）")
    p.add_argument("--out", default=None,
                   help="输出 content.json 路径（默认写到根 content.json）")
    args = p.parse_args()

    # 1) 读分类结果
    if args.date:
        path = DATA_DIR / f"trending_{args.date}_classified.json"
    else:
        files = sorted(DATA_DIR.glob("trending_*_classified.json"))
        if not files:
            print("❌ 没有分类数据，请先运行 fetch_trending + classify_scene", file=sys.stderr)
            sys.exit(1)
        path = files[-1]

    if not path.exists():
        print(f"❌ 文件不存在: {path}", file=sys.stderr)
        sys.exit(1)

    print(f"📂 读取: {path.name}")
    classified = json.loads(path.read_text(encoding="utf-8"))
    scenes_labels = classified.get("scenes", {})

    # 2) 选仓库
    selected = select_featured_repos(classified,
                                      top_per_scene=args.per_scene,
                                      top_total=args.top)
    if not selected:
        print("❌ 没有任何仓库可选", file=sys.stderr)
        sys.exit(1)

    print(f"\n🎯 选中 {len(selected)} 个仓库：")
    for r, scene_key in selected:
        print(f"   - {r['repo']} ⭐+{r.get('stars_today', 0)} [{scenes_labels.get(scene_key, scene_key)}]")

    # 3) 调 LLM
    system, user = build_prompt(selected, scenes_labels)
    print(f"\n🤖 调用 {args.model} 生成脚本...")
    raw = call_glm_with_retry(user, system=system, model=args.model,
                              max_tokens=args.max_tokens)

    # 4) 解析 JSON
    try:
        content = _extract_json(raw)
    except Exception as e:
        # 把原始输出写到 content_raw.txt 方便 debug
        debug_path = BASE_DIR / "content_raw.txt"
        debug_path.write_text(raw, encoding="utf-8")
        print(f"❌ JSON 解析失败: {e}")
        print(f"原始 LLM 输出已写入 {debug_path}")
        sys.exit(1)

    # 5) 校验 segments 数量（>= 4 段；如果不到 6 段但不严重也接受，仅警告）
    segs = content.get("segments", [])
    if len(segs) < 3:
        print(f"⚠️  segments 只有 {len(segs)} 段，太少")
    elif len(segs) != 6:
        print(f"💡  segments 有 {len(segs)} 段（prompt 要求 6 段）")

    # 6) 强制填上 id（pipeline.py 依赖 id 命名文件）
    for i, seg in enumerate(segs, 1):
        seg.setdefault("id", i)

    # 7) 写到根目录的 content.json
    out_path = Path(args.out) if args.out else BASE_DIR / "content.json"
    out_path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ 文案已保存: {out_path}")
    print(f"   标题: {content.get('title', '?')}")
    print(f"   简介: {content.get('desc', '?')[:80]}")
    print(f"   段落: {len(segs)} 段")
    print(f"   标签: {', '.join(content.get('tags', []))}")
    print("\n▶️  下一步：运行 python3 pipeline.py 合成视频")


if __name__ == "__main__":
    main()
