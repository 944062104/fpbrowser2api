"""VirtualBrowser Worker 独立代理批量更新工具
========================================================================
用于为现有的 VirtualBrowser 环境（如 ChatGPT-Worker-01 ~ 10）
按顺序批量配置独立的代理 IP（支持 HTTP / SOCKS5，支持带账号密码）。
修改代理仅更新网络路由，不会清除浏览器已有的 Cookies 和登录态！

使用方式:
    python scripts/update_worker_proxies.py -f proxies.txt
    python scripts/update_worker_proxies.py -f proxies.txt --protocol SOCKS5
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, List


def http_post(url: str, data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(data or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_proxy_line(line: str, default_proto: str = "HTTP") -> Dict[str, Any]:
    """解析单行代理字符串。
    支持格式:
        127.0.0.1:7890
        127.0.0.1:7890:user:pass
        http://user:pass@host:port
        socks5://127.0.0.1:1080
    """
    raw = line.strip()
    proto = default_proto.upper()
    user = ""
    pwd = ""
    host = ""
    port = ""

    if "://" in raw:
        proto_part, rest = raw.split("://", 1)
        proto = proto_part.upper()
        raw = rest

    if "@" in raw:
        auth_part, host_part = raw.split("@", 1)
        if ":" in auth_part:
            user, pwd = auth_part.split(":", 1)
        else:
            user = auth_part
        parts = host_part.split(":")
        host = parts[0]
        port = parts[1] if len(parts) > 1 else ""
    else:
        parts = raw.split(":")
        if len(parts) >= 4:
            host, port, user, pwd = parts[0], parts[1], parts[2], parts[3]
        elif len(parts) >= 2:
            host, port = parts[0], parts[1]
        elif len(parts) == 1:
            host = parts[0]

    return {
        "mode": 1 if host and port else 0,
        "value": f"{host}:{port}" if host and port else "",
        "protocol": proto,
        "host": host,
        "port": port,
        "user": user,
        "pass": pwd,
        "API": "",
    }


def update_worker_proxies(
    proxies_file: Path,
    vb_url: str = "http://127.0.0.1:9000",
    name_prefix: str = "ChatGPT-Worker",
    default_proto: str = "HTTP",
) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if not proxies_file.exists():
        print(f"[!] 找不到代理列表文件: {proxies_file.resolve()}")
        sys.exit(1)

    with open(proxies_file, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]

    if not lines:
        print("[!] 代理文件内容为空")
        sys.exit(1)

    print("=" * 70)
    print(f"[*] 读取到 {len(lines)} 条独立代理配置")
    print(f"[*] VirtualBrowser API 地址: {vb_url}")
    print(f"[*] 目标 Worker 前缀: {name_prefix}")
    print("=" * 70)

    # 获取现有环境
    try:
        res = http_post(f"{vb_url}/api/getBrowserList", {})
        browsers = res.get("data", [])
    except Exception as e:
        print(f"[!] 无法连接到 VirtualBrowser API (端口 9000): {e}")
        print("    请确保 VirtualBrowser 客户端已启动，或者 API 服务正在运行。")
        sys.exit(1)

    # 筛选目标 Worker (如 ChatGPT-Worker-01 ...)
    target_workers = [b for b in browsers if name_prefix in b.get("name", "")]
    # 按名称排序
    target_workers.sort(key=lambda x: x.get("name", ""))

    if not target_workers:
        print(f"[!] 未找到匹配前缀 '{name_prefix}' 的 Worker 环境，将匹配所有环境：")
        target_workers = browsers

    print(f"[*] 找到 {len(target_workers)} 个待配置环境\n")

    print(f"{'序号':<4} | {'环境名称':<18} | {'环境ID':<6} | {'原代理':<20} | {'新分配代理'}")
    print("-" * 75)

    for idx, b in enumerate(target_workers):
        wid = b.get("id")
        wname = b.get("name")
        old_proxy = b.get("proxy", {})
        old_val = old_proxy.get("value") or (f"{old_proxy.get('host')}:{old_proxy.get('port')}" if old_proxy.get("host") else "直连/无")

        if idx < len(lines):
            proxy_cfg = parse_proxy_line(lines[idx], default_proto=default_proto)
            new_val = f"{proxy_cfg['protocol']}://{proxy_cfg['host']}:{proxy_cfg['port']}"
            if proxy_cfg.get("user"):
                new_val += f" (auth: {proxy_cfg['user']})"

            # 更新配置
            payload = {
                "id": wid,
                "proxy": proxy_cfg,
            }
            try:
                up_res = http_post(f"{vb_url}/api/updateBrowser", payload)
                status = "✅ 成功" if up_res.get("success") else f"❌ {up_res.get('msg')}"
            except Exception as e:
                status = f"❌ {e}"
        else:
            new_val = "(超出代理列表长度，保持原样)"
            status = "⚠️ 跳过"

        print(f"{idx+1:<4} | {wname:<18} | {wid:<6} | {old_val:<20} | {new_val} [{status}]")

    print("=" * 75)
    print("[SUCCESS] 批量代理更新完毕！所有现有登录态与 Cookies 保持完好。")


def main():
    parser = argparse.ArgumentParser(description="VirtualBrowser Worker 独立代理批量更新工具")
    parser.add_argument("-f", "--file", type=str, default="proxies.txt", help="独立代理列表文件路径 (每行一条)")
    parser.add_argument("--vb-url", type=str, default="http://127.0.0.1:9000", help="VirtualBrowser API 地址")
    parser.add_argument("-p", "--prefix", type=str, default="ChatGPT-Worker", help="Worker 命名匹配前缀 (默认: ChatGPT-Worker)")
    parser.add_argument("--protocol", type=str, default="HTTP", choices=["HTTP", "SOCKS5"], help="默认代理协议 (HTTP 或 SOCKS5)")

    args = parser.parse_args()
    update_worker_proxies(
        proxies_file=Path(args.file),
        vb_url=args.vb_url,
        name_prefix=args.prefix,
        default_proto=args.protocol,
    )


if __name__ == "__main__":
    main()
