# FPBrowser2API Agent Guide

## 1. 项目定位与核心原则
- **定位**：基于真实指纹浏览器（VirtualBrowser/RoxyBrowser）的 AI 自动化与 OpenAI 兼容网关服务。
- **核心准则**：坚持走真机指纹浏览器与页面上下文自动化，拒绝纯协议逆向（避免对抗 Cloudflare Turnstile / WASM PoW），复用真实 Chromium 登录态与环境。

## 2. 运行架构与端口服务
服务采用三位一体协同常驻模式：
1. **SSH WARP 代理桥** (`127.0.0.1:40001~40005`)：从 VPS 映射 5 个独立 US 原生出口，50 个指纹窗口（Worker 2 ~ 51）均分承载（每端口 10 窗口），防关联风控。
2. **VirtualBrowser API** (`http://127.0.0.1:9000`)：底层 Chromium 指纹浏览器内核管理与 CDP 控制服务。
3. **FPBrowser2API 网关** (`http://127.0.0.1:8000`)：对外提供标准 OpenAI `/v1/chat/completions` 与 `/v1/models`。
   - 默认 API Key：`mirrmart_sora2_880315`

## 3. 服务启停规范
- **一键启动**：`python start_services.py` 或双击 `start_all_services.bat`（自动按顺序拉起 40001~40005、9000、8000）。
- **一键停止**：`python stop_services.py` 或双击 `stop_all_services.bat`（跨平台安全优雅终止全部相关子进程）。

## 4. 账号与数据存储
- 主数据库路径：`data/fpbrowser.db`（SQLite）。
- `windows` 表管理指纹窗口与代理映射；`platform_accounts` 管理账号凭据；`task_type_windows` 维护任务绑定与 Access Token。
- 维护工具：`check_real_browser_login.py`（直读 Chromium Cookies 库校验真机活体登录态）。

## 5. 账号池自动化 Skill
- 路径：`skills/chatgpt-account-pool/`
- 工具：`python skills/chatgpt-account-pool/scripts/account_pool.py <账号文件>`
- 能力：支持发货格式 A (TOTP 2FA) 与格式 B (微软 Outlook OAuth 接码) 双模自适应解析、环境创建、代理均衡、自动接码登录、Cookies 刷盘落盘与号池挂载；带 `--check` 一键巡检。
