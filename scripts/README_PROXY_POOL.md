# AI 号池独立 IP 分配与代理池管理工具

本目录提供了为指纹浏览器环境（如 `ChatGPT-Worker-01` ~ `10`）分配**完全独立海外 IP**的自动化方案，有效防止多账号串 IP 风控。

---

## 方案 1：从 Clash / Mihomo 订阅一键自动分配（推荐）

如果你有现成的机场或代理订阅链接，可以通过 `setup_sub_proxies.py` 一键自动完成：
1. 自动从订阅中筛选最适合 AI / ChatGPT 的 10 个海外专线或家宽节点；
2. 自动在本地开启 10 个独立的转发端口（`127.0.0.1:7891` ~ `7900`）；
3. 自动测试各端口的连通性与真实公网出口 IP；
4. 自动调用 VirtualBrowser API 将 10 个独立端口回写到对应 Worker 中（**原有登录态不丢失**）。

### 运行方式：
```bash
python scripts/setup_sub_proxies.py -u "https://your-subscribe-url/subscribe/..." --test-ip
```

---

## 方案 2：从文本文件批量导入已有代理 IP

如果你手头已有购买的独立代理列表（如 SOCKS5、HTTP、静态住宅代理）：

1. 新建 `proxies.txt`，参考 `scripts/proxies.example.txt` 填入每行一个代理：
   ```text
   127.0.0.1:7890
   127.0.0.1:7891
   198.51.100.1:8080:username:password
   socks5://user:pass@198.51.100.2:1080
   ```
2. 运行批量更新命令：
   ```bash
   python scripts/update_worker_proxies.py -f proxies.txt
   ```
   脚本会按顺序自动为 `ChatGPT-Worker-01` ~ `10` 绑定对应代理。
