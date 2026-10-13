# ChatGPT 自动化绘图实战排坑与避坑指南 (Troubleshooting & Best Practices)

在通过自动化、指纹浏览器（VirtualBrowser / AdsPower 等）及调度网关（FPBrowser2API）调度 ChatGPT 进行图像生成时，沉淀出的核心避坑经验如下：

---

### 1. 登录态丢失与冷重启失效（SQLite WAL 事务刷盘机制）

- **现象**：脚本自动登录 ChatGPT、甚至成功进入主页后，重启浏览器环境查看，依然显示“未登录”状态。
- **根本原因**：
  Chromium 内核使用 SQLite WAL（Write-Ahead Logging）模式存储 Cookies、Local Storage 与 Session Tokens。如果在页面操作完毕后立即使用 `taskkill /F` 或调用客户端急停接口（`/api/stopBrowser`），Chromium 进程会被强杀，内存中的 WAL 日志未及时 Checkpoint 提交到磁盘数据库文件。
- **解决方案**：
  1. 自动化登录或会话就绪后，**严禁立即强杀进程**；
  2. 必须先通过 CDP 协议调用 `await browser.close()` 发送标准注销信号；
  3. 保留 **3~5 秒等待缓冲**，确保 SQLite 事务完整落盘后，再执行环境关闭或退出。

---

### 2. ChatGPT 免费版（GPT-4o）“反问确认而不生图”死锁

- **现象**：任务提交后，调度器超时或报错 `GPT image: ... 你想要哪种风格？更偏写实还是概念插画？`，ChatGPT 并未直接调用 DALL-E / gpt-image-2 插件。
- **根本原因**：
  如果提示词过于礼貌或含有提问色彩（如“请帮我画一张...”、“你觉得如何？”、“帮我设计...”），ChatGPT 免费版的大语言模型会将请求识别为“多轮对话咨询”，主动输出文本征询用户意向，而自动化调度器需要直接获取生成的图像流（`image gen` / `file_id`）。
- **解决方案**：
  - **前置强制动词**：使用 `立即生成图片：...` 或 `Generate image directly: ...`；
  - **后置防反问安全后缀**：在提示词末尾统一附加：
    `请直接调用画图工具生成图片，无需回复任何多余文字或询问确认。`
  - 使用内置优化器：`python scripts/prompt_optimizer.py "你的想法"`。

---

### 3. 图片下载 403 Forbidden 权限拦截

- **现象**：从 ChatGPT 接口或 HTML 提取到图片地址（如 `https://chatgpt.com/backend-api/estuary/content?id=file_...`），外部直接使用 `curl`、`urllib.request` 或 `requests.get` 下载报 `403 Forbidden`。
- **根本原因**：
  OpenAI 的 Estuary 内容服务要求携带当前浏览器上下文的完整登录态 Cookies、会话 Token 与正确的 Referer / Cloudflare 安全标记，非授权直连被严格拦截。
- **解决方案**：
  - **页面上下文注入下载（CDP 评估）**：
    在已连接的 Playwright CDP 页面中通过 `page.evaluate()` 执行 `fetch(url)`，将二进制数据转为 Base64，由 Python 端解码保存到本地文件；
  - **扩展转存**：通过 `browser_extension` 内部直接提取或对接 Cloudflare R2 / S3 图床。

---

### 4. 任务调度池卡在 `queued` 状态无法分发

- **现象**：向 FPBrowser2API 提交生图任务后，任务状态始终为 `queued`（进度 0%），没有分配到任何窗口运行。
- **根本原因**：
  1. **额度限制**：数据库 `task_type_windows` 表中的 `remaining_quota` 字段默认为 0，调度引擎在挑选窗口时判定 `remaining_quota < 2`，认为环境额度耗尽；
  2. **空白环境污染**：默认空白环境（如 `b1`）未登录 ChatGPT，却被启用了 `task_type_id=6`，导致任务分配失败。
- **解决方案**：
  - 将各已登录 Worker 的 `remaining_quota` 设为 `999`：
    ```sql
    UPDATE task_type_windows SET remaining_quota = 999, consecutive_errors = 0, error_cooldown_until = NULL WHERE task_type_id = 6;
    ```
  - 将未登录或测试空白环境置为 `enabled = 0`。

---

### 5. VirtualBrowser 插件自动化加载

- **现象**：浏览器启动后未加载 `browser_extension`，无法与 FPBrowser2API 建立 WebSocket 长连接。
- **解决方案**：
  - VirtualBrowser 支持通过本地 API 安装扩展：
    ```bash
    curl -X POST http://127.0.0.1:9000/api/addCrx \
      -H "Content-Type: application/json" \
      -d '{"name": "fpbrowser_extension", "path": "E:\\path\\to\\browser_extension"}'
    ```
  - VirtualBrowser 启动各环境时会自动注入 `--load-extension`。
