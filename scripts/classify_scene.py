#!/usr/bin/env python3
"""
classify_scene.py — 把 trending 仓库按"应用场景"分类
====================================================

用户决策（2026-07-04）：按场景分类替代 t1/t2，按"开发者/观众视角"分类，覆盖主流使用场景。
本脚本是**纯规则**，不需要 LLM。

九大场景：

  🎨 SCENE_FRONTEND       前端开发            React / Vue / Svelte / Next / Tailwind / 组件库 / UI 框架
  ⚙️  SCENE_BACKEND        后端 / API          FastAPI / Django / 数据库 / Auth / 微服务 / gRPC
  🤖 SCENE_AI_AGENT        AI Agent / LLM      Claude / GPT / LLM / MCP / RAG / Agent / Skills / Prompt
  🎬 SCENE_VIDEO_MEDIA     视频 / 多媒体生成    ComfyUI / Pollinations / ASCII video / 音频 / TTS / 动画
  🛠️  SCENE_DEVOPS          DevOps / 效率       CI/CD / Docker / K8s / 监控 / IaC / GitHub Actions / 测试
  📱 SCENE_MOBILE          移动端              iOS / Android / ReactNative / Flutter / Swift / Kotlin
  🎮 SCENE_GAME            游戏开发            Unity / UE / Godot / 游戏引擎 / 独立游戏
  📚 SCENE_LEARNING        学习资源            教程 / 书籍 / 课程 / 公开课 / cheatsheet / roadmap
  🧪 SCENE_QA              测试 / 质量         E2E / Playwright / 性能 / Lint / 静态分析 / e2e
  📦 SCENE_OTHER           其他                兜底分类
"""

from __future__ import annotations
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"


# -------------------- 场景定义 --------------------

SCENES = {
    "frontend":    "🎨 前端开发",
    "backend":     "⚙️  后端/API",
    "ai_agent":    "🤖 AI Agent/LLM",
    "devops":      "🛠️  DevOps/效率",
    "video_media": "🎬 视频/多媒体生成",
    "mobile":      "📱 移动端",
    "game":        "🎮 游戏开发",
    "learning":    "📚 学习资源",
    "qa":          "🧪 测试/质量",
    "other":       "📦 其他",
}

# 关键词规则 —— 按"主要功能"分类
# 设计思路：
#   1. 每个仓库计算每个场景的得分（关键词命中数 × 权重 + 语言命中）
#   2. AI Agent 用"显式 AI 关键词"做强信号；后端/DevOps/前端用语言作为基础判定
#   3. 平局时按 SCENE_PRIORITY 决定先后
#
# 这些关键词经过 117 个仓库实测调优（trending_2026-07-04.json）

SCENE_PRIORITY = {
    "ai_agent":    100,  # 显式 AI 项目
    "qa":           85,
    "video_media":  80,
    "game":         75,
    "mobile":       70,
    "devops":       60,
    "learning":     55,
    "frontend":     50,
    "backend":      40,
}

SCENE_RULES: dict[str, dict[str, Any]] = {
    # === AI Agent / LLM（仅"显式 AI"关键词才计入）===
    # 因为 2025-2026 几乎所有项目都自称 "AI-powered"，所以要收紧
    "ai_agent": {
        "priority": SCENE_PRIORITY["ai_agent"],
        "weight_per_match": 5,  # 单个匹配权重高
        "keywords": [
            r"\bclaude\s*code\b", r"\bclaude[\-_]?skill", r"\bmcp\b",
            r"\bmodel\s*context\s*protocol\b", r"\blangchain\b", r"\blanggraph\b",
            r"\brag\b", r"\bvecto(r|ry)\s*(store|db|database)\b",
            r"\bembedding(s)?\b", r"\bprompt\s*engineer", r"\bfine[\s_-]*tune",
            r"\bopenai\b", r"\banthropic\b", r"\bgemini\b", r"\bclaude\s*api\b",
            r"\bgpt[\-_]?\d", r"\bllm\b", r"\bagent(ic|s)?\s*(framework|skills?|platform|orchestrat|workflow|system)",
            r"\bcoding\s*agent\b", r"\bagentic\b", r"\bskills?\s*framework\b",
            r"\bcopilot\s*cli\b", r"\bcursor\b",
            r"\bopencode(?:\s+cli)?\b", r"\bcodex\s*cli\b",
            r"\bhugging\s*face\b", r"\btransformers?\s*library\b",
            # 宽松：明显的"agent 项目"—— 名字/描述里有"agent"且不是前端
            r"\bgui\s*agent\b", r"\bin[\s_-]*page\s*agent\b", r"\bterminal\s*agent\b",
            r"\btrading\s*agent\b", r"\bvibe[\s_-]*trading\b",
            r"\bagentic\s*coding\b", r"\bai[\s_-]*powered\s*agents?\b",
            r"\bagent\s*multiplexer\b", r"\bskills?\s+(for|from)\s+real\b",
            r"\bcoding\s*assistant\s*skill\b", r"\bai\s*knowledge\s*management\b",
            # AI 工具/项目命名模式
            r"\bagency[\s_-]*agents?\b", r"\bskills?\s+for\s+real\s+engineers?\b",
            r"\b\d+\s+specialized\s+skills?\b",
            r"\borchestrate\s+your\b", r"\bai\s*agency\b", r"\bspecialized\s+agents?\b",
        ],
        "langs": [],
    },

    # === 视频/多媒体生成 ===
    "video_media": {
        "priority": SCENE_PRIORITY["video_media"],
        "weight_per_match": 4,
        "keywords": [
            r"\bvideo\s*(generator|creation|editing|edito)r?\b",
            r"\banimat(e|ion)\s*tool\b",
            r"\bcomfyui\b", r"\bpollinations?\b",
            r"\bsora\b", r"\bveo\b", r"\bkling\b", r"\brunway\b",
            r"\bascii[\s_-]*video\b", r"\bascii[\s_-]*art\s*tool\b",
            r"\bimage[\s_-]*to[\s_-]*video\b", r"\bt2v\b",
            r"\btext[\s_-]*to[\s_-]*(video|speech|music|audio|image)\b",
            r"\btts\b", r"\btext[\s_-]*to[\s_-]*speech\b", r"\bedge[\s_-]*tts\b",
            r"\bmusicgen\b", r"\baudiogen\b", r"\bwhisper\b",
            r"\bsprite\s*sheet\b", r"\bplatformer\b", r"\bgame\s*asset\b", r"\b2d\s*game\b",
            r"\bmeeting\s*(assistant|notes|transcri)\b",  # 通常有音视频处理
            r"\bparakeet\b", r"\bvideo\s*stream(ing)?\b",
        ],
        "langs": [],
    },

    # === 游戏开发 ===
    "game": {
        "priority": SCENE_PRIORITY["game"],
        "weight_per_match": 5,
        "keywords": [
            r"\bunity\s*(engine|game|2d|3d)\b", r"\bunreal\s*engine\b", r"\bgodot\b",
            r"\bindie\s*game\b", r"\brpg\s*game\b", r"\bbullet\s*hell\b",
            r"\bgame\s*engine\b", r"\bgam(eplay|ification)\b",
        ],
        "langs": [],
    },

    # === 移动端 ===
    "mobile": {
        "priority": SCENE_PRIORITY["mobile"],
        "weight_per_match": 4,
        "keywords": [
            r"\bios\s*(app|sdk)\b", r"\bandroid\s*(app|sdk)\b", r"\bswiftui\b", r"\bjetpack\s*compose\b",
            r"\breact[\s_-]*native\b", r"\bflutter\s*(app|framework)\b", r"\bexpo\b",
            r"\bionic\b", r"\bcordova\b", r"\bnative\s*script\b",
        ],
        "langs": ["Swift", "Kotlin", "Dart"],
    },

    # === 测试 / 质量 ===
    "qa": {
        "priority": SCENE_PRIORITY["qa"],
        "weight_per_match": 4,
        "keywords": [
            r"\btesting\s*framework\b", r"\bunit\s*test(s|ing)?\b",
            r"\be2e\s*test", r"\bplaywright\b",
            r"\bselenium\b", r"\bcypress\b",
            r"\blint(ing|er)?\b", r"\bstatic\s*analysis\b",
            r"\bmutation\s*test(ing)?\b",
            r"\bbenchmark\s*(suite|tool)?\b", r"\bperf(ormance)?\s*tool\b",
            r"\bqa\s*tool\b", r"\bcode\s*coverage\b",
            r"\bpenetration\s*test(ing)?\b", r"\bpentest(ing)?\b",
            r"\bvulnerab(ility|le)\s*scan", r"\bfuzz(ing|er)?\b",
            r"\bvulner(ability|able)\b",
        ],
        "langs": [],
    },

    # === DevOps / 效率 ===
    "devops": {
        "priority": SCENE_PRIORITY["devops"],
        "weight_per_match": 3,
        "keywords": [
            r"\bdevops\b", r"\bci[\s_/-]?cd\b", r"\bgithub\s*actions?\b",
            r"\bdocker\b", r"\bkubernetes\b", r"\bk8s\b",
            r"\bterraform\b", r"\bansible\b", r"\bpulumi\b",
            r"\bhelm\b", r"\bnomad\b", r"\bconsul\b", r"\bvault\b",
            r"\bprometheus\b", r"\bgrafana\b", r"\bloki\b",
            r"\bargocd\b", r"\bjenkins\b", r"\bcaddy\b", r"\bnginx\b", r"\btraefik\b",
            r"\bobserv(ability|ation)\b", r"\bmonitoring\b",
            r"\bself[\s_-]*host(ed|ing)\b", r"\bhome[\s_-]*server\b",
            r"\bVPN\b", r"\bwireguard\b", r"\btailscale\b", r"\bheadscale\b",
            r"\bcontainer\s*runtime\b", r"\bcontainerd\b", r"\brunc\b",
            r"\bterraforming\b",
        ],
        "langs": ["HCL", "Dockerfile", "Shell"],
    },

    # === 学习资源 ===
    "learning": {
        "priority": SCENE_PRIORITY["learning"],
        "weight_per_match": 5,
        "keywords": [
            r"\b(course|curriculum|tutorial|textbook|handbook|cheatsheet)\b",
            r"\broadmap\b", r"\blearn(ing)?\s*resources?\b",
            r"\beducation(al)?\s*resources?\b",
            r"\bcourse\s*materials?\b", r"\btextbook\b", r"\bcs\s*\d+\s*course\b",
            r"\bcs\s*\d+\w*\s*(book|course)\b",
            r"\bdeep\s*learning\s*book\b", r"\bml\s*book\b", r"\bsystems?\s*book\b",
            r"\bhow[\s_-]*to\b", r"\blearning\s*path\b",
        ],
        "langs": [],
    },

    # === 前端 ===
    "frontend": {
        "priority": SCENE_PRIORITY["frontend"],
        "weight_per_match": 3,
        "keywords": [
            r"\breact\s*(js|dom|router)\b", r"\bvue\s*\d?\b", r"\bsvelte\b", r"\bsveltekit\b",
            r"\bnext\.?js\b", r"\bnuxt\b", r"\bastro\b", r"\bremix\b",
            r"\btailwind\s*(css)?\b", r"\bdesign\s*system\b",
            r"\bcomponent\s*library\b", r"\bui\s*(library|framework|kit)\b",
            r"\bfrontend\b", r"\bfront[\s_-]*end\b",
            r"\bcss\s*framework\b", r"\bcss\s*in\s*js\b",
            r"\belectron\b(?!.*meeting)", r"\btauri\b",
            r"\bvite\b", r"\bwebpack\b", r"\brollup\b", r"\besbuild\b",
            r"\bchrome\s*extension\b", r"\bbrowser\s*extension\b",
            r"\bruntime\s*for\s*javascript\b", r"\bjs\s*runtime\b",
        ],
        "langs": [],
    },

    # === 后端 / API ===
    "backend": {
        "priority": SCENE_PRIORITY["backend"],
        "weight_per_match": 3,
        "keywords": [
            r"\bfastapi\b", r"\bdjango\b", r"\bflask\b", r"\bexpress\b", r"\bkoa\b",
            r"\bnestjs?\b", r"\bfastify\b",
            r"\bspring\s*boot\b", r"\bgrails\b",
            r"\brest(ful)?\s*api\b", r"\bgraphql\b", r"\bgrpc\b", r"\bwebsocket\b",
            r"\boauth\s*\d", r"\bjwt\b", r"\bsso\b", r"\bauth0\b",
            r"\bpostgres(ql)?\b", r"\bmysql\b", r"\bsqlite\b",
            r"\bmongodb\b", r"\bredis\b", r"\bkafka\b", r"\brabbitmq\b",
            r"\bmigration\s*tool", r"\bschema\s*migration", r"\bsqlx\b",
            r"\bmicro[\s_-]*service", r"\bserver[\s_-]*less\b",
            r"\bbackend\b", r"\bback[\s_-]*end\b",
            r"\bcli\s*tool\b", r"\bcommand[\s_-]*line\s*tool\b",
            r"\bdesktop\s*app(?!.*meeting)", r"\bweb\s*app\s*framework\b",
            r"\borm\b",
        ],
        "langs": ["Go", "Rust", "Java", "Ruby", "PHP", "Elixir"],
    },
}


def _matches(text: str, patterns: list[str]) -> list[str]:
    return [p for p in patterns if re.search(p, text, re.IGNORECASE)]


def classify(repo: dict[str, Any]) -> tuple[str, list[str]]:
    """
    把一个仓库分到一个场景。
    决策：
      1. 每个场景计算 score = matches × weight + lang_hit
      2. 排序：score 高的胜出；同分用 SCENE_PRIORITY 高的胜出
    """
    text = " ".join([
        repo.get("repo", ""),
        repo.get("name", ""),
        repo.get("description", ""),
    ]).lower()

    language = repo.get("language", "")

    scores: list[tuple[str, int, int, list[str]]] = []  # (scene, score, priority, reasons)

    for scene, rules in SCENE_RULES.items():
        weight = rules.get("weight_per_match", 3)
        matches = _matches(text, rules["keywords"])
        score = len(matches) * weight
        reasons = [f"kw: {p[:40]}" for p in matches[:3]]

        # 语言加成（语言命中 +1，仅在该语言确实是该场景的代表时）
        if language in rules.get("langs", []):
            score += 2
            reasons.append(f"lang: {language}")

        if score > 0:
            scores.append((scene, score, rules["priority"], reasons))

    if not scores:
        return "other", ["no rule matched"]

    # 排序：score 高优先 → 同分 priority 高优先
    scores.sort(key=lambda x: (x[1], x[2]), reverse=True)
    winner = scores[0]
    return winner[0], winner[3]  # ← bug 修复：用 score 而非先看 priority


# -------------------- 主流程 --------------------

def classify_file(path: Path) -> dict[str, list[dict[str, Any]]]:
    """从 trending_<date>.json 读，按场景分组输出"""
    data = json.loads(path.read_text(encoding="utf-8"))
    repos = data.get("repos", [])

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    stats = Counter()

    for r in repos:
        scene, reasons = classify(r)
        r_out = dict(r)
        r_out["scene"] = scene
        r_out["scene_reasons"] = reasons
        grouped[scene].append(r_out)
        stats[scene] += 1

    return dict(grouped)


def main():
    p = argparse.ArgumentParser(
        description="按场景分类 trending 仓库（不依赖 LLM，纯规则）",
    )
    p.add_argument("--date", default=None,
                   help="trending JSON 日期（YYYY-MM-DD），默认取最新")
    p.add_argument("--top", type=int, default=5,
                   help="每场景最多打印 N 个仓库（默认 5）")
    args = p.parse_args()

    # 找原始 trending 文件（跳过 *_classified.json）
    if args.date:
        path = DATA_DIR / f"trending_{args.date}.json"
    else:
        files = sorted(DATA_DIR.glob("trending_*.json"))
        files = [f for f in files if "_classified" not in f.stem]
        if not files:
            print("❌ 没有 trending 数据，请先运行 fetch_trending.py", file=sys.stderr)
            sys.exit(1)
        path = files[-1]  # ← 取原始而非分类版

    if not path.exists():
        print(f"❌ 文件不存在: {path}", file=sys.stderr)
        sys.exit(1)

    print(f"📂 读取: {path.name}\n")
    grouped = classify_file(path)

    total = sum(len(v) for v in grouped.values())
    print(f"{'='*80}\n📊 场景分类分布 (共 {total} 个仓库)\n{'='*80}")
    for scene_key in SCENES:
        items = grouped.get(scene_key, [])
        if items:
            print(f"  {SCENES[scene_key]:24s}  {len(items):>3} 个")

    print(f"\n{'='*80}\n🔥 每场景 Top {args.top}\n{'='*80}")
    for scene_key, label in SCENES.items():
        items = grouped.get(scene_key, [])
        if not items:
            continue
        items_sorted = sorted(items, key=lambda x: x["stars_today"], reverse=True)
        print(f"\n{label}  ({len(items)} 个)")
        print("-" * 70)
        for i, r in enumerate(items_sorted[: args.top], 1):
            print(f"  {i:>2}. ⭐+{r['stars_today']:<5} [{r['language'] or '?':10s}] {r['repo']}")
            if r["description"]:
                print(f"       └─ {r['description'][:90]}{'...' if len(r['description'])>90 else ''}")

    # 写一份 sidecar 缓存（带 scene 字段），后续步骤可直接消费
    out_path = path.with_name(path.stem + "_classified.json")
    payload = {
        "source": path.name,
        "classified_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "scenes": SCENES,
        "groups": grouped,
        "total": total,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n💾 分类结果缓存: {out_path.name}")


if __name__ == "__main__":
    main()
