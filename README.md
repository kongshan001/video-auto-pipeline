# 🎬 video-auto-pipeline

> AI 短视频自动化流水线 — 零成本生成 B 站竖屏短视频

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## ✨ 功能

把一个"主题"自动变成一条可发布的短视频，全流程无需人工：

```
主题输入
  ↓
[1] LLM 生成文案 (含 narration + image_prompt + subtitle)
  ↓
[2] Pollinations 逐段生成配图 (免费, flux 模型)
  ↓
[3] edge-tts 生成中文旁白 (14 种中文音色, 免费)
  ↓
[4] ffmpeg 合成片段 (图片 + 音频, Ken Burns 推镜效果)
  ↓
[5] ffmpeg 拼接 + 烧录 SRT 字幕
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

## 🔧 使用方法

### 1. 准备文案

复制示例，按需求修改：

```bash
cp content.example.json content.json
```

`content.json` 结构：

```json
{
  "title": "猫咪的五种超能力",
  "tags": ["猫咪", "冷知识", "科普"],
  "desc": "你以为猫咪只会卖萌？",
  "segments": [
    {
      "id": 1,
      "narration": "旁白文本...",
      "image_prompt": "English prompt for image generation",
      "subtitle": "显示在屏幕上的字幕"
    }
  ]
}
```

### 2. 运行流水线

```bash
python3 pipeline.py
```

输出文件：

- `images/seg{01-99}.png` — 各段配图
- `audio/seg{01-99}.mp3` — 各段旁白
- `clips/seg{01-99}.mp4` — 各段视频片段
- `subs/subtitles.srt` — SRT 字幕
- `output_final.mp4` — **最终成片**
- `upload_meta.json` — B 站上传元数据

### 3. (可选) 上传 B 站

```bash
biliup upload -t 投稿 -f upload_meta.json
# 或手动填 title/desc/tags 里的内容
```

## ⚙️ 配置项

在 `pipeline.py` 顶部修改：

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

## 🪛 常见坑

### Pollinations 限速 (HTTP 429)

- 匿名用户每 IP 仅 1 并发
- 单帧约 30-85s，建议帧间 sleep ≥ 5s
- 429 响应后等 60-90s 再重试

### ffmpeg 路径含特殊字符

`subtitles` filter 在路径含 `:` 或 `'` 时会失败。
当前已用 `srt_escaped` 处理，但 Windows 路径 `C:\` 仍可能出问题。

### Pollinations 内容审核

会偶发拒绝 NSFW/血腥/真人脸请求。解决方案：

1. 改用更安全的 prompt
2. 用 placeholder image 占位
3. 接入其他生图服务 (Midjourney/Stable Diffusion)

## 🗺️ Roadmap

- [x] 路线 A：零成本静态图流水线
- [ ] 路线 B：可灵/Seedance AI 视频片段
- [ ] 路线 C：单图+骨骼动画 (ArtPipe)
- [ ] YouTube Shorts / TikTok 竖屏模板
- [ ] 自动上传 (biliup / YouTube API)
- [ ] Web UI (Gradio / Streamlit)
- [ ] 字幕样式可定制 (字体/颜色/位置)
- [ ] BGM 背景音乐自动添加
- [ ] 多语言支持 (英/日/韩)

## 📝 开发日志

见 [`docs/CHANGELOG.md`](docs/CHANGELOG.md)。

## 📜 License

MIT