---
name: chatgpt-account-pool
description: "Universal ChatGPT account pool manager. Auto-detects dual account formats (TOTP 2FA vs Outlook OAuth), creates VirtualBrowser environments, balances SOCKS5/HTTP proxies, runs automated web login with email code extraction, flushes session cookies via CDP Browser.close, and mounts scheduling routes into FPBrowser2API. Keywords: chatgpt账号配置, 批量上号, 微软邮箱接码, TOTP 2FA, 账号池管理, 指纹浏览器上号, outlook验证码, account pool, batch login."
---

# ChatGPT 账号池自动化管理与统一接入 Skill

单文件搞定 ChatGPT 多格式发货账号的自适应解析、环境创建、代理绑定、自动接码登录、Cookies 刷盘与调度号池挂载。

---

## 📋 支持的发货格式

| 格式类型 | 行格式规范 | 认证方式 |
| :--- | :--- | :--- |
| **格式 A (TOTP 2FA)** | `邮箱----密码----TOTP密钥` | 纯 Python 标准库实时计算 RFC 6238 6 位动态码 |
| **格式 B (微软接码)** | `邮箱----密码----Client ID----Refresh Token----[AT]` | 微软官方 OAuth 2.0 API 毫秒级静默拉取邮件验证码 |

> 脚本会逐行自适应判断格式、自动过滤客服/售后说明行并完成全局去重。

---

## 🚀 常用命令

### 1. 批量导入并全自动接码登录入池
```bash
python skills/chatgpt-account-pool/scripts/account_pool.py \
  "d:/Personal/Downloads/FF261016165710.txt" \
  "d:/Personal/Downloads/FF261019842540.txt" \
  --start-id 12 \
  --proxy-ports 40001,40002,40003,40004,40005
```

### 2. 仅建环境与同步数据库 (不启动浏览器登录)
```bash
python skills/chatgpt-account-pool/scripts/account_pool.py \
  "d:/Personal/Downloads/FF261019842540.txt" \
  --no-login
```

### 3. 一键账号池健康巡检
```bash
python skills/chatgpt-account-pool/scripts/account_pool.py --check
```
