# 🎬 video-auto-pipeline

> AI 短视频自动化流水线 — 零成本生成 B 站短视频

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## ✨ v0.2.0 新增：每日 Trending 自动选题

过去你只能手动填 `content.json`；现在可以**从 GitHub Trending 自动选当天最火的仓库 → 按场景分类 → LLM 写脚本 → 自动出视频**：

```
GitHub Trending (daily)
  ↓
[1] scripts/fetch_trending.py   抓仓库（按语言筛选 + 去重）
  ↓
[2] scripts/classify_scene.py   按 9 大应用场景分类（纯规则）
  ↓
[3] scripts/generate_story.py   GLM-5.1 生成 6 段视频文案 → content.json
  ↓
[4] pipeline.py (原有)           Pollinations 生图 + edge-tts 配音 + ffmpeg 合成
  ↓
📹 output_final.mp4 + upload_meta.json
```

一行命令搞定：

```bash
python3 scripts/run_daily.py
```

## 🎬 视频流水线（路线 A 零成本）

把一个 `content.json`（含 narration + image_prompt + subtitle）自动变成可发布的短视频：

```
content.json (手工/LLM 生成)
  ↓
[1] Pollinations 逐段生成配图 (免费, flux 模型)
  ↓
[2] edge-tts 生成中文旁白 (14 种中文音色, 免费)
  ↓
[3] ffmpeg 合成片段 (图片 + 音频, Ken Burns 推镜效果)
  ↓
[4] ffmpeg 拼接 + 烧录 SRT 字幕
  ↓
📹 output_final.mp4 — 可直接上传 B 站
```

## 🚀 路线对比

| 路线 | 成本 | 视频质量 | 一致性 | 适用场景 |
|------|------|----------|--------|----------|
| **A 零成本** (本仓库) | ¥0 | 中 (静态图+推镜) | ✅ 高 | 科普/资讯/口播 |
| B 高质量 | ¥? | 高 (AI 视频片段) | ✅ 高 | 剧情/特效 |
| C 骨骼动画 | ¥0 | 中 (程序化动作) | ✅ 完美 | 游戏/二次元 |

## 📦 依赖

- Python 3.10+
- `ffmpeg` + `ffprobe`
- `edge-tts` (`pip install edge-tts`)
- 网络可访问 `image.pollinations.ai`
- (可选) `GLM_API_KEY` 环境变量 — 用于 v0.2 的 LLM 自动选题
- (可选) `requests` — 若未安装则自动 fallback 到 urllib（`scripts/fetch_trending.py`）

## 🚀 快速开始

### 路径 A：每日 Trending 自动跑

```bash
# 一键：抓 trending + 分类 + LLM 文案 + 合成视频
python3 scripts/run_daily.py

# 只跑选题部分，不出视频（快）
python3 scripts/run_daily.py --skip-video

# 强制重抓 trending（忽略缓存）
python3 scripts/run_daily.py --force

# 视频中讲 Top 5 仓库（更细）
python3 scripts/run_daily.py --top 5
```

### 路径 B：手工 / 自定义主题

```bash
# 1. 改示例
cp content.example.json content.json
# 编辑 title / segments / 等

# 2. 跑流水线
python3 pipeline.py
```

### 路径 C：分步执行

```bash
python3 scripts/fetch_trending.py           # 抓 trending
python3 scripts/classify_scene.py           # 按场景分类
python3 scripts/generate_story.py --top 3   # LLM 生成 content.json
python3 pipeline.py                         # 合成视频
```

## 📂 目录结构

```
video-auto-pipeline/
├── pipeline.py                    # 视频合成主程序（路线 A）
├── content.example.json           # 文案格式示例
├── scripts/
│   ├── fetch_trending.py          # 抓 GitHub Trending（按场景分类前的步骤 1）
│   ├── classify_scene.py          # 按 9 大场景分组分类（步骤 2）
│   ├── generate_story.py          # LLM 生成 6 段视频文案（步骤 3）
│   └── run_daily.py               # 一键串联，每日流水线
├── data/
│   └── trending_<date>.json       # Trending 原始数据（每日缓存）
│   └── trending_<date>_classified.json  # 分类后的结果
├── docs/
│   └── SCENE_CATEGORIES.md        # 场景分类规则详解
└── output_*.mp4, upload_meta.json
```

## 🏷️ 场景分类

按"开发者/观众视角"分 9 大应用场景：

| 场景 | Key | 图标 |
|---|---|---|
| 前端开发 | `frontend` | 🎨 |
| 后端 / API | `backend` | ⚙️ |
| AI Agent / LLM | `ai_agent` | 🤖 |
| DevOps / 效率 | `devops` | 🛠️ |
| 视频 / 多媒体生成 | `video_media` | 🎬 |
| 移动端 | `mobile` | 📱 |
| 游戏开发 | `game` | 🎮 |
| 学习资源 | `learning` | 📚 |
| 测试 / 质量 | `qa` | 🧪 |
| 其他 | `other` | 📦 |

详见 [`docs/SCENE_CATEGORIES.md`](docs/SCENE_CATEGORIES.md)。

## ⚙️ 配置项

### pipeline.py（视频合成）

```python
VOICE = "zh-CN-XiaoyiNeural"   # edge-tts 音色
IMG_MODEL = "flux"             # Pollinations 模型
IMG_W, IMG_H = 1024, 576       # 16:9 图片尺寸
```

中文 TTS 推荐音色：

- `zh-CN-XiaoyiNeural` — 温柔知性女声 (默认)
- `zh-CN-YunxiNeural` — 阳光少年男声
- `zh-CN-YunjianNeural` — 稳重新闻男声
- `zh-CN-XiaoxiaoNeural` — 甜美女声
- `zh-CN-liaoning-XiaobeiNeural` — 东北话女声 (趣味)

### generate_story.py（LLM 文案）

环境变量：

| 变量 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `GLM_API_KEY` | ✅ | — | Z.AI / 智谱的 API key（GLM Coding Plan） |
| `VIDEO_STORY_MODEL` | ❌ | `glm-5.1` | 想换模型覆盖即可 |

CLI 参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--top N` | 3 | 视频要讲的 Top N 仓库 |
| `--per-scene N` | 1 | 每个场景最多选 N 个（保证多样性） |
| `--max-tokens N` | 4000 | GLM 推理模型需要大值（reasoning_tokens 占空间） |
| `--model NAME` | glm-5.1 | 覆盖默认模型 |

> 💡 **GLM 推理模型坑**：max_tokens 太小时 reasoning_tokens 会占满空间，导致 content 为空。默认值 4000 经过实测验证可正常工作。

## 🪛 常见坑

### Pollinations 限速 (HTTP 429)

- 匿名用户每 IP 仅 1 并发
- 单帧约 30-85s，建议帧间 sleep ≥ 5s
- 429 响应后等 60-90s 再重试

### Pollinations 临时故障 (HTTP 500)

- 偶发 fetch failed，请稍后重试
- pipeline.py 已自动重试 3 次

### GLM 返回空 content

- 必须设 `max_tokens >= 2000`（推理模型占空间）
- generate_story.py 已自动重试 1 次

### ffmpeg 路径含特殊字符

`subtitles` filter 在路径含 `:` 或 `'` 时会失败。
当前已用 `srt_escaped` 处理，但 Windows 路径 `C:\` 仍可能出问题。

## 🗺️ Roadmap

- [x] v0.1.0 路线 A：零成本静态图流水线
- [x] **v0.2.0 每日 Trending 自动选题**（含场景分类）
- [ ] v0.3.0 B 站自动上传（biliup 集成）
- [ ] v0.4.0 YouTube Shorts / TikTok 竖屏模板
- [ ] v0.5.0 BGM 背景音乐 + 字幕样式可定制
- [ ] 路线 B：可灵/Seedance AI 视频片段
- [ ] 路线 C：单图+骨骼动画 (ArtPipe)
- [ ] Web UI (Gradio / Streamlit)
- [ ] 多语言支持 (英/日/韩)

## 📜 License

MIT
