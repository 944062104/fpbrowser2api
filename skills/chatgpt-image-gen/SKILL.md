---
name: chatgpt-image-gen
description: "Universal ChatGPT automated image generation skill. Use when the user wants to generate images using ChatGPT / GPT-4o (DALL-E 3 / gpt-image-2), optimize image prompts to avoid conversational clarification, schedule batch generation across browser pools via FPBrowser2API, or directly automate image generation and high-resolution retrieval via browser CDP. Keywords: chatgpt生图, gpt画图, dalle, chatgpt画画, 文本生图, text-to-image, gpt-image-2, AI绘画, 柴犬生图, 指纹浏览器生图."
---

# ChatGPT 自动化生图 Skill (Universal ChatGPT Image Generation)

基于实战沉淀的 ChatGPT 高保真通用生图工作流。解决三大核心痛点：
1. **防反问死锁**：利用结构化提示词消除 ChatGPT 免费版（GPT-4o）因语义礼貌或模糊产生的“反问意向而不出图”问题；
2. **多账号池化调度**：无缝对接 FPBrowser2API，自动在多个 VirtualBrowser / 指纹 Worker 间分发任务、自动复用与轮转会话；
3. **安全提取与落盘**：突破 OpenAI Estuary 403 权限隔离，在已鉴权会话上下文中稳定取回 1080P/2K/4K 级 2.6MB+ 无损原图。

---

## 快速使用 (Quick Start)

### 1. 命令行快速生图 (一键运行)

#### 模式 A：通过 FPBrowser2API 调度池（推荐，支持多账号与排队）
```bash
# 简短提示词自动扩写 + 16:9 比例 + 自动下载原图
python skills/chatgpt-image-gen/scripts/generate_image.py "一只在未来天台喝热咖啡的柴犬宇航员" --ratio 16:9 -o output/shiba.png

# 指定风格（realistic: 电影写实, cyberpunk: 赛博朋克, anime: 二次元, concept_art: 概念艺术）
python skills/chatgpt-image-gen/scripts/generate_image.py "雨夜霓虹街道的机械武士" --style cyberpunk -o output/samurai.png
```

#### 模式 B：CDP 直连模式（无需启动后台 API，直连任意已开启调试端口的浏览器）
```bash
# 连接本地 9222 端口已登录 ChatGPT 的浏览器并完成生图与取回
python skills/chatgpt-image-gen/scripts/generate_image.py "赛博朋克猫咪飞行员" --mode cdp --port 9222 -o output/cat.png
```

---

### 2. 提示词结构化优化工具 (Prompt Optimizer)

如果需要自行获取并调试“防 ChatGPT 追问”的专业绘图提示词：

```bash
python skills/chatgpt-image-gen/scripts/prompt_optimizer.py "悬浮在云海中的天空之城" -s concept_art -r 16:9
```

**输出示例**：
> `立即生成图片：悬浮在云海中的天空之城，极致细节的概念艺术插画，电影级广角宏大构图，史诗级光影氛围，柔和光晕，精细笔触与微光粒子，8k Octane Render 质感。画面宽高比设置为 16:9，画质规格为 1k。请直接调用画图工具立即生成图片，不要输出任何询问文字、选项或确认反问。`

---

## 核心架构与两种模式

```text
[ 用户 / AI Agent ]
       │
       ├─── (模式 A：调度池模式) ───> [ FPBrowser2API (:8000) ]
       │                                     │
       │                                     ├─ 负载均衡调度已登录 Worker
       │                                     ├─ 扩展 WebSocket 长连接交互
       │                                     ▼
       │                            [ VirtualBrowser / Chromium ]
       │                                     │
       └─── (模式 B：CDP直连模式) ───────────┴─> Playwright CDP (:9222)
                                             │
                                             ├─ 注入防反问 Prompt
                                             ├─ 等待 DALL-E / GPT-4o 图像渲染
                                             └─ 页面会话提取 2.6MB+ 无损 PNG
```

---

## 核心经验与避坑清单

在开放给他人使用或部署生产时，必须遵循以下规则（详见 [排坑指南](references/troubleshooting.md)）：

1. **防反问黄金公式**：
   - 前置动词：`立即生成图片：...`
   - 画面描述：`主体 + 细节材质 + 环境光影 + 构图`
   - 终止后缀：`请直接调用画图工具立即生成图片，不要输出任何询问文字、选项或确认反问。`
2. **SQLite WAL 刷盘与持久化登录**：
   - 绑定 ChatGPT 账号后，**严禁使用 taskkill 或急停接口强制杀死 Chromium**。
   - 必须先通过 CDP `await browser.close()`，等待 3-5 秒缓冲，确保 SQLite WAL 完整写入 Cookies，避免冷重启后登录失效。
3. **403 权限下载防御**：
   - 生成的图片地址 `chatgpt.com/backend-api/estuary/content` 外部直接请求必报 403。
   - 必须在对应已鉴权的浏览器标签页中，通过 JavaScript `fetch()` 转为 Blob/Base64 取回。
4. **FPBrowser2API 额度配置**：
   - 数据库 `task_type_windows` 表中对应环境的 `remaining_quota` 需维持在 `999`，否则调度引擎会判定无额度而持续处于 `queued`。

---

## 接口参数参考 (API Reference)

详情请参阅 [接口规范文档](references/api_specs.md)。

- **任务接口**：`POST http://127.0.0.1:8000/v1/videos`
- **支持模型**：
  - `gpt-image2-1k`：默认输出（16:9 对应 1344×768，1:1 对应 1024×1024）
  - `gpt-image2-2k`：高分辨率模式（16:9 对应 1664×928）
  - `gpt-image2-4k`：超清模式（16:9 对应 3312×1872）
