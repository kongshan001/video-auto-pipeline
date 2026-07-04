# 场景分类规则（Scene Categories）

> 2026-07-04 决策：用"开发者/观众视角"的应用场景替代旧的 t1/t2 难度分层。

## 背景

旧分类 `t1/t2` 是**创作者视角**（按难度分层），用户视角不直观，且"什么算 t2"边界模糊。
新分类按"用户能看到、能用上的真实场景"组织，覆盖开发者日常工作的 9 大类别。

## 场景清单

| 场景 | Key | 图标 | 代表项目 | 关键词触发示例 |
|---|---|---|---|---|
| 前端开发 | `frontend` | 🎨 | React, Vue, Svelte, design system, UI kit | `react`, `vue`, `tailwind`, `design system`, `component library` |
| 后端 / API | `backend` | ⚙️ | FastAPI, Django, Postgres, CLI tools | `fastapi`, `postgres`, `cli tool`, `migration tool` |
| AI Agent / LLM | `ai_agent` | 🤖 | Claude Code, LangChain, MCP servers, Agent skills | `claude code`, `mcp`, `langchain`, `rag`, `agent framework` |
| DevOps / 效率 | `devops` | 🛠️ | Docker, Kubernetes, Terraform, self-hosted | `kubernetes`, `docker`, `terraform`, `self-hosted`, `vpn` |
| 视频 / 多媒体生成 | `video_media` | 🎬 | ComfyUI, Sora, TTS, Whisper, PeerTube | `comfyui`, `text-to-video`, `tts`, `whisper` |
| 移动端 | `mobile` | 📱 | React Native, Flutter, iOS, Android | `react native`, `flutter`, `swiftui` |
| 游戏开发 | `game` | 🎮 | Unity, Unreal, Godot, indie game | `unity`, `unreal`, `godot`, `game engine`, `rpg game` |
| 学习资源 | `learning` | 📚 | 教程、书籍、course repo | `course`, `textbook`, `cheatsheet`, `cs course` |
| 测试 / 质量 | `qa` | 🧪 | E2E tools, vulnerability scanners, linters | `playwright`, `linting`, `vulnerability`, `penetration testing` |
| 其他 | `other` | 📦 | 不能归类的兜底 | — |

## 决策规则

每个场景有：
- **`keywords`** — 正则表达式列表（不区分大小写），匹配仓库名 / description / name
- **`weight_per_match`** — 每个匹配贡献的分数
- **`langs`** — 命中这些语言时额外加分（语言命中场景代表性的项目）
- **`priority`** — 平局时优先级

对每个仓库：
1. 对每个场景计算 `score = matches × weight_per_match + (lang 命中 ? 2 : 0)`
2. 排序：分数高的胜出 → 同分 priority 高的胜出
3. 没有命中任何规则 → 归到 `other`

## 为何这样设计

- **不用 LLM** —— 关键词规则，0 成本、0 延迟、可复现
- **关键词经过实测调优** —— 在 117 个 trending 仓库上手动验证过
- **AI Agent 收紧** —— 2025-2026 几乎所有项目都自称"AI-powered"，关键词必须具体（claude code / mcp / langchain），不是宽泛的"agent"
- **平局决胜用 priority** —— 比如某个项目同时命中 frontend 和 ai_agent，agent 的 priority=100 决胜

## 调优指南

如果你看到分类错误（误判/漏判），加一条更精确的关键词：

```python
"ai_agent": {
    ...
    "keywords": [
        ...
        r"\byour\s+new\s+keyword\b",   # ← 加这里
    ],
},
```

调优规则放在 `scripts/classify_scene.py` 的 `SCENE_RULES` 字典里。

## 维护

- **新增场景**：在 `SCENES` 和 `SCENE_RULES` 同时添加
- **删除场景**：移除两个字典的对应项 + 删除所有引用
- **改名字**：改 `SCENES[key]` 显示名即可
