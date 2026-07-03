#!/usr/bin/env python3
"""
AI视频自动化流水线 - 路线A（零成本）
主题 → AI文案 → Pollinations生图 → edge-tts配音 → ffmpeg合成 → MP4输出
"""

import json
import os
import subprocess
import time
import sys
import urllib.parse
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(BASE_DIR, "images")
AUDIO_DIR = os.path.join(BASE_DIR, "audio")
CLIPS_DIR = os.path.join(BASE_DIR, "clips")
SUBS_DIR = os.path.join(BASE_DIR, "subs")
OUTPUT_DIR = BASE_DIR

# edge-tts 中文女声（温柔知性）
VOICE = "zh-CN-XiaoyiNeural"
# Pollinations模型
IMG_MODEL = "flux"
# 图片尺寸（16:9）
IMG_W, IMG_H = 1024, 576


def load_content(path="content.json"):
    with open(os.path.join(BASE_DIR, path), "r") as f:
        return json.load(f)


def step1_generate_images(segments):
    """Step1: Pollinations逐段生成配图"""
    print(f"\n🎨 Step1: 生成 {len(segments)} 张配图...")
    for seg in segments:
        idx = seg["id"]
        prompt = seg["image_prompt"]
        out_path = os.path.join(IMG_DIR, f"seg{idx:02d}.png")

        if os.path.exists(out_path) and os.path.getsize(out_path) > 10000:
            print(f"  ✅ seg{idx:02d} 已存在，跳过")
            continue

        encoded = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width={IMG_W}&height={IMG_H}&model={IMG_MODEL}&nologo=true&seed={idx*42+7}"

        print(f"  🖼️  seg{idx:02d}: {prompt[:50]}...")
        for attempt in range(3):
            try:
                r = subprocess.run(
                    ["curl", "-s", "-o", out_path, "-w", "%{http_code}", url],
                    capture_output=True, text=True, timeout=120
                )
                code = r.stdout.strip()
                if code == "200" and os.path.exists(out_path) and os.path.getsize(out_path) > 5000:
                    print(f"  ✅ seg{idx:02d} 完成 ({code})")
                    break
                else:
                    print(f"  ⚠️  seg{idx:02d} 尝试{attempt+1}失败 (HTTP {code}, size={os.path.getsize(out_path) if os.path.exists(out_path) else 0})")
                    if attempt < 2:
                        wait = 30 * (attempt + 1)
                        print(f"     等待{wait}s...")
                        time.sleep(wait)
            except subprocess.TimeoutExpired:
                print(f"  ⚠️  seg{idx:02d} 超时，重试...")
                time.sleep(30)

        # 帧间隔，避免429
        if idx < len(segments):
            time.sleep(8)

    print("🎨 配图生成完成!\n")


def step2_generate_audio(segments):
    """Step2: edge-tts旁白转语音"""
    print(f"\n🎙️ Step2: 生成 {len(segments)} 段语音...")
    for seg in segments:
        idx = seg["id"]
        text = seg["narration"]
        out_path = os.path.join(AUDIO_DIR, f"seg{idx:02d}.mp3")

        if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            print(f"  ✅ seg{idx:02d} 音频已存在，跳过")
            continue

        print(f"  🔊 seg{idx:02d}: {text[:40]}...")
        try:
            r = subprocess.run(
                ["edge-tts", "--voice", VOICE, "--text", text, "--write-media", out_path],
                capture_output=True, text=True, timeout=60
            )
            if r.returncode == 0:
                print(f"  ✅ seg{idx:02d} 音频完成")
            else:
                print(f"  ❌ seg{idx:02d} 失败: {r.stderr[:100]}")
        except Exception as e:
            print(f"  ❌ seg{idx:02d} 异常: {e}")

    print("🎙️ 语音生成完成!\n")


def step2b_generate_subtitles(segments):
    """Step2b: 生成SRT字幕（基于音频时长）"""
    print("\n📝 Step2b: 生成SRT字幕...")
    srt_path = os.path.join(SUBS_DIR, "subtitles.srt")
    srt_entries = []
    current_time = 0.0

    for seg in segments:
        idx = seg["id"]
        audio_path = os.path.join(AUDIO_DIR, f"seg{idx:02d}.mp3")
        if not os.path.exists(audio_path):
            continue

        # 获取音频时长
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True, timeout=10
        )
        duration = float(r.stdout.strip())

        start_time = current_time
        end_time = current_time + duration
        current_time = end_time

        # SRT格式
        start_str = _srt_time(start_time)
        end_str = _srt_time(end_time)
        subtitle_text = seg["subtitle"]

        srt_entries.append(f"{idx}\n{start_str} --> {end_str}\n{subtitle_text}\n")

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_entries))

    print(f"  ✅ 字幕保存到 {srt_path}")
    print("📝 字幕生成完成!\n")


def _srt_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def step3_compose_clips(segments):
    """Step3: ffmpeg合成每段（图片+音频→视频片段）"""
    print(f"\n🎬 Step3: 合成 {len(segments)} 个视频片段...")
    for seg in segments:
        idx = seg["id"]
        img_path = os.path.join(IMG_DIR, f"seg{idx:02d}.png")
        audio_path = os.path.join(AUDIO_DIR, f"seg{idx:02d}.mp3")
        clip_path = os.path.join(CLIPS_DIR, f"seg{idx:02d}.mp4")

        if not os.path.exists(img_path) or not os.path.exists(audio_path):
            print(f"  ⚠️ seg{idx:02d} 缺少图片或音频，跳过")
            continue

        if os.path.exists(clip_path) and os.path.getsize(clip_path) > 10000:
            print(f"  ✅ seg{idx:02d} 片段已存在，跳过")
            continue

        print(f"  🎞️ seg{idx:02d} 合成中...")
        # Ken Burns效果：缓慢放大 + 淡入淡出
        filter_complex = (
            f"[0:v]scale=1920:1080,zoompan=z='min(zoom+0.0008,1.08)':"
            f"d=250:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=25,"
            f"fade=t=in:st=0:d=0.8,fade=t=out:st=9:d=1[v]"
        )

        r = subprocess.run(
            ["ffmpeg", "-y", "-loop", "1", "-i", img_path, "-i", audio_path,
             "-vf", f"scale=1920:1080,zoompan=z='min(zoom+0.0008,1.08)':d=250:s=1920x1080:fps=25,fade=t=in:st=0:d=0.8",
             "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "192k",
             "-pix_fmt", "yuv420p", "-shortest", "-movflags", "+faststart",
             clip_path],
            capture_output=True, text=True, timeout=120
        )
        if r.returncode == 0:
            size_mb = os.path.getsize(clip_path) / 1024 / 1024
            print(f"  ✅ seg{idx:02d} 完成 ({size_mb:.1f}MB)")
        else:
            # 简化方案：无zoompan
            print(f"  ⚠️ seg{idx:02d} zoompan失败，使用简单合成...")
            r2 = subprocess.run(
                ["ffmpeg", "-y", "-loop", "1", "-i", img_path, "-i", audio_path,
                 "-vf", "scale=1920:1080,fade=t=in:st=0:d=0.8,fade=t=out:st=9:d=1",
                 "-c:v", "libx264", "-tune", "stillimage", "-c:a", "aac", "-b:a", "192k",
                 "-pix_fmt", "yuv420p", "-shortest", "-movflags", "+faststart",
                 clip_path],
                capture_output=True, text=True, timeout=120
            )
            if r2.returncode == 0:
                size_mb = os.path.getsize(clip_path) / 1024 / 1024
                print(f"  ✅ seg{idx:02d} 完成-简化版 ({size_mb:.1f}MB)")
            else:
                print(f"  ❌ seg{idx:02d} 失败: {r2.stderr[-200:]}")

    print("🎬 片段合成完成!\n")


def step4_merge_video(segments):
    """Step4: 拼接所有片段 + 添加字幕 → 最终MP4"""
    print("\n🔧 Step4: 拼接最终视频...")

    # 生成concat文件
    concat_path = os.path.join(CLIPS_DIR, "concat.txt")
    clip_files = []
    for seg in segments:
        clip_path = os.path.join(CLIPS_DIR, f"seg{seg['id']:02d}.mp4")
        if os.path.exists(clip_path):
            clip_files.append(clip_path)

    if not clip_files:
        print("  ❌ 没有可用的视频片段!")
        return None

    with open(concat_path, "w") as f:
        for cp in clip_files:
            f.write(f"file '{cp}'\n")

    # 拼接
    merged_path = os.path.join(OUTPUT_DIR, "output_merged.mp4")
    r = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_path,
         "-c", "copy", merged_path],
        capture_output=True, text=True, timeout=120
    )
    if r.returncode != 0:
        print(f"  ❌ 拼接失败: {r.stderr[-200:]}")
        return None

    # 烧录字幕（如果有的话）
    srt_path = os.path.join(SUBS_DIR, "subtitles.srt")
    final_path = os.path.join(OUTPUT_DIR, "output_final.mp4")

    if os.path.exists(srt_path):
        print("  📝 烧录字幕...")
        # subtitles filter需要转义路径中的特殊字符
        srt_escaped = srt_path.replace(":", "\\:").replace("'", "\\'")
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", merged_path,
             "-vf", f"subtitles='{srt_escaped}':force_style='FontName=Noto Sans CJK SC,FontSize=22,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,Outline=2'",
             "-c:v", "libx264", "-preset", "fast", "-crf", "23",
             "-c:a", "copy", "-movflags", "+faststart",
             final_path],
            capture_output=True, text=True, timeout=300
        )
        if r.returncode != 0:
            print(f"  ⚠️ 字幕烧录失败，使用无字幕版本")
            final_path = merged_path
        else:
            # 删除中间文件
            os.remove(merged_path)
    else:
        final_path = merged_path

    size_mb = os.path.getsize(final_path) / 1024 / 1024
    print(f"  ✅ 最终视频: {final_path} ({size_mb:.1f}MB)")
    print(f"  📹 片段数: {len(clip_files)}/{len(segments)}")

    return final_path


def run_pipeline():
    """运行完整流水线"""
    print("=" * 60)
    print("🚀 AI视频自动化流水线 - 路线A（零成本）")
    print("=" * 60)

    content = load_content()
    segments = content["segments"]

    print(f"📋 主题: {content['title']}")
    print(f"📋 段落: {len(segments)} 段")
    print(f"📋 标签: {', '.join(content['tags'])}")

    t0 = time.time()

    step1_generate_images(segments)
    step2_generate_audio(segments)
    step2b_generate_subtitles(segments)
    step3_compose_clips(segments)
    final = step4_merge_video(segments)

    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    if final:
        print(f"🎉 流水线完成! 耗时 {elapsed:.0f}s")
        print(f"📹 输出: {final}")
        # 保存元数据供上传用
        meta = {
            "video_path": final,
            "title": content["title"],
            "desc": content["desc"],
            "tags": content["tags"],
            "segments": len(segments),
            "elapsed_seconds": int(elapsed)
        }
        with open(os.path.join(OUTPUT_DIR, "upload_meta.json"), "w") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print("📋 上传元数据已保存到 upload_meta.json")
    else:
        print("❌ 流水线失败，请检查日志")
    print("=" * 60)


if __name__ == "__main__":
    run_pipeline()
