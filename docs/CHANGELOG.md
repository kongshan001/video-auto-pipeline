# 开发日志 (CHANGELOG)

本文件记录 video-auto-pipeline 的演进过程：决策、坑、里程碑。

---

## 2026-07-03 · v0.1.0 · 路线 A 零成本流水线首版

**仓库:** https://github.com/kongshan001/video-auto-pipeline

### 🎯 决策

1. **仓库命名**: `video-auto-pipeline`
   - 候选：`ai-video-pipeline` (太通用) / `video-auto-pipeline` (简洁直接) / `hermes-video-factory` (跟 Hermes 品牌挂钩但限制太死)
   - 选定 `video-auto-pipeline`：通用 + 直白，未来可扩展到 B 路线 (AI 视频片段)

2. **路线 A 优先于路线 B**
   - 路线 A 零成本：Pollinations (匿名生图) + edge-tts (免费 TTS) + ffmpeg
   - 路线 B 高质量：可灵/Seedance 视频生成，要 Cookie/付费
   - 决策：先把 A 跑通，验证流程，再考虑 B 升级

3. **不提交生成产物到 Git**
   - 生成的 MP4/PNG/MP3 单文件可达几十 MB，仓库会爆
   - `.gitignore` 排除 `images/ audio/ clips/ subs/ output_*.mp4`
   - 只提交 `pipeline.py` (代码) + `content.example.json` (示例) + 文档

4. **保留 `content.example.json`，不提交真实 `content.json`**
   - 真实内容涉及具体选题 (如"猫咪超能力") 是用户私有资产
   - 示例文件展示结构，用户复制后改名使用

### 🪛 已踩的坑

| 现象 | 根因 | 解决方案 |
|------|------|----------|
| Pollinations HTTP 429 | 匿名用户每 IP 仅 1 并发 | 帧间 sleep ≥ 5s，429 后等 60-90s |
| Pollinations 单帧 30-85s | 模型推理 + 队列 | 串行处理，重试 3 次 |
| urllib 频繁 429 | Python 内置库连接复用差 | 改用 curl 子进程，更稳定 |
| ffmpeg zoompan 复杂 filter 偶尔失败 | filter 语法解析差异 | 加 fallback：无 zoompan 的简化版 |
| 字幕烧录路径含 `:` 报错 | ffmpeg `subtitles=` filter 把 `:` 当协议分隔符 | `srt_escaped = srt_path.replace(":", "\\:")` |
| edge-tts 偶发超时 | 微软服务限速 | 60s 超时，依赖 retry 逻辑 (待补) |

### 📦 技术栈

| 组件 | 版本 | 角色 |
|------|------|------|
| Python | 3.11 | 主控脚本 |
| Pollinations | flux | 文生图 (匿名免费) |
| edge-tts | v7.2.7 | 微软中文 TTS (免费) |
| ffmpeg | 系统 | 视频合成 + 字幕烧录 |
| biliup | v1.1.29 | B 站上传 CLI (可选) |

### 🎬 已验证产出

- 主题：猫咪的五种超能力
- 段落：6 段 (约 60 秒成片)
- 耗时：约 8-12 分钟 (含 Pollinations 限速等待)
- 大小：约 50 MB
- 输出：`output_final.mp4` (本地 `~/ai-video-pipeline/`)

### 🔜 下一步

- [ ] 路线 B：可灵 AI 视频片段生成 (高动效需求场景)
- [ ] 路线 C：ArtPipe 骨骼动画方案 (游戏/二次元)
- [ ] 字幕样式模板化 (字体/颜色/位置可配置)
- [ ] BGM 背景音乐自动添加
- [ ] 自动上传 B 站 (biliup 集成)
- [ ] 抽象出 `pipeline_lib.py` 模块化，便于复用

---

## 备注

- 主开发目录：`/root/ai-video-pipeline/` (本地，未推)
- 仓库目录：`/root/video-auto-pipeline/`
- 远端：https://github.com/kongshan001/video-auto-pipeline