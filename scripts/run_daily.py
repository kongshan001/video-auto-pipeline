#!/usr/bin/env python3
"""
run_daily.py — 一键运行每日 Trending 视频生成全流程
=====================================================

串联四个步骤：
  1. fetch_trending.py  抓 GitHub Trending（按多个语言，每日缓存）
  2. classify_scene.py  按 9 大场景分组
  3. generate_story.py  LLM (GLM-5.1) 生成今日 6 段视频文案
  4. pipeline.py        Pollinations 生图 + edge-tts 配音 + ffmpeg 合成 → MP4

典型用法：
  python3 scripts/run_daily.py                      # 默认：生成今日 Top 3 视频
  python3 scripts/run_daily.py --top 5 --skip-video # 只生成 content.json 不跑视频
  python3 scripts/run_daily.py --force              # 强制重新抓 Trending
  python3 scripts/run_daily.py --skip-classify      # 已分类，跳过分步
"""

from __future__ import annotations
import argparse
import datetime
import os
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BASE_DIR / "scripts"


def _run(cmd: list[str], cwd: Path | None = None) -> int:
    """运行子进程，实时打印输出。返回 exit code。"""
    print(f"\n$ {' '.join(cmd)}\n")
    result = subprocess.run(
        cmd,
        cwd=str(cwd or BASE_DIR),
        env=os.environ.copy(),
    )
    return result.returncode


def main():
    p = argparse.ArgumentParser(
        description="每日 GitHub Trending → 视频 自动化流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
完整流程：
  1. 抓 Trending  2. 分类  3. LLM 生成文案  4. 合成视频

跳过某步（用 --skip-*）可单独复用上一步结果。

示例：
  # 默认：抓→分类→生成文案→合成视频
  python3 scripts/run_daily.py
  # 强制重新抓
  python3 scripts/run_daily.py --force
  # 只生文案不合成视频
  python3 scripts/run_daily.py --skip-video
  # 视频 top 5
  python3 scripts/run_daily.py --top 5
""",
    )
    p.add_argument("--since", default="daily", choices=["daily", "weekly", "monthly"])
    p.add_argument("--lang", nargs="+", default=None,
                   help="Trending 抓的语言列表（默认 5 种主流 + unknown 兜底）")
    p.add_argument("--top", type=int, default=3,
                   help="视频中要讲的 Top N 仓库（默认 3）")
    p.add_argument("--per-scene", type=int, default=1,
                   help="每个场景最多选 N 个仓库（保证多样性）")
    p.add_argument("--force", action="store_true",
                   help="忽略缓存强制重新抓 Trending")
    p.add_argument("--skip-fetch", action="store_true",
                   help="跳过抓取（用今天的缓存）")
    p.add_argument("--skip-classify", action="store_true",
                   help="跳过分步（用今天的分类）")
    p.add_argument("--skip-story", action="store_true",
                   help="跳过文案生成（用现有 content.json）")
    p.add_argument("--skip-video", action="store_true",
                   help="跳过视频合成（只产 content.json）")
    p.add_argument("--max-tokens", type=int, default=4500,
                   help="GLM max_tokens（默认 4500）")
    p.add_argument("--model", default=None,
                   help="指定 LLM 模型（默认 glm-5.1）")
    args = p.parse_args()

    started = time.time()
    today = datetime.date.today().isoformat()
    print("=" * 80)
    print(f"🚀 每日 Trending 视频流水线 — {today}")
    print("=" * 80)

    # ---- Step 1: 抓 Trending ----
    if not args.skip_fetch:
        cmd = ["python3", "scripts/fetch_trending.py", "--since", args.since]
        if args.lang:
            cmd += ["--lang"] + args.lang
        if args.force:
            cmd.append("--force")
        rc = _run(cmd)
        if rc != 0:
            print(f"❌ 抓取失败 (exit {rc})", file=sys.stderr)
            sys.exit(rc)
    else:
        print("\n⏭️  跳过抓取（--skip-fetch）")

    # ---- Step 2: 分类 ----
    if not args.skip_classify:
        rc = _run(["python3", "scripts/classify_scene.py", "--top", "5"])
        if rc != 0:
            print(f"❌ 分类失败 (exit {rc})", file=sys.stderr)
            sys.exit(rc)
    else:
        print("\n⏭️  跳过分类（--skip-classify）")

    # ---- Step 3: 生成文案 ----
    if not args.skip_story:
        cmd = ["python3", "scripts/generate_story.py",
               "--top", str(args.top),
               "--per-scene", str(args.per_scene),
               "--max-tokens", str(args.max_tokens)]
        if args.model:
            cmd += ["--model", args.model]
        rc = _run(cmd)
        if rc != 0:
            print(f"❌ 文案生成失败 (exit {rc})", file=sys.stderr)
            sys.exit(rc)
    else:
        print("\n⏭️  跳过文案生成（--skip-story）")

    # ---- Step 4: 合成视频 ----
    if not args.skip_video:
        rc = _run(["python3", "pipeline.py"])
        if rc != 0:
            print(f"❌ 视频合成失败 (exit {rc})", file=sys.stderr)
            sys.exit(rc)
    else:
        print("\n⏭️  跳过视频合成（--skip-video）")

    # ---- 完成 ----
    elapsed = time.time() - started
    print("\n" + "=" * 80)
    print(f"🎉 全部完成！总耗时 {elapsed:.0f}s")
    print("=" * 80)

    print("\n📁 产出文件：")
    # 找最新的 trending 文件
    for pattern, label in [
        (f"data/trending_{today}.json", "Trending 原始数据"),
        (f"data/trending_{today}_classified.json", "按场景分类结果"),
        ("content.json", "今日视频文案（LLM 生成）"),
        ("upload_meta.json", "上传元数据"),
        ("output_final.mp4", "🎬 最终视频"),
    ]:
        path = BASE_DIR / pattern
        if path.exists():
            size = path.stat().st_size
            sz = f"{size/1024/1024:.1f}MB" if size > 1024*1024 else f"{size/1024:.0f}KB"
            print(f"   ✅ {label:30s} {sz:>8s}  {path.relative_to(BASE_DIR)}")
        else:
            print(f"   ⚪ {label:30s} {'(未生成)':>8s}  {pattern}")
    print("\n💡 下一步：python3 scripts/upload_bilibili.py (B 站上传, 未实现)")


if __name__ == "__main__":
    main()
