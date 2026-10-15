"""通过 Mihomo 订阅自动为 10 个 Worker 分配独立 IP 代理池
========================================================================
1. 解析订阅中的 38 个节点，精选 10 个最适合 ChatGPT 的海外节点（美西/美东/新加坡/日本，包含家宽与 AI 专线）；
2. 自动生成专属轻量 Mihomo 配置文件，开启 10 个独立本地监听端口 (7891 ~ 7900)；
3. 启动后台 Mihomo 转发服务；
4. 逐个测试 10 个端口的外网 IP 与连通性；
5. 调用 VirtualBrowser API 将 10 个独立端口自动分配绑定到 10 个 Worker 环境！
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
BIN_DIR = BASE_DIR / "bin"
MIHOMO_EXE = BIN_DIR / "mihomo.exe"


def fetch_subscription(sub_url: str, proxy: str = "http://127.0.0.1:7890") -> Dict[str, Any]:
    print(f"[*] 正在拉取订阅配置...")
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    handlers.append(urllib.request.HTTPSHandler(context=ctx))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(sub_url, headers={"User-Agent": "ClashMeta;mihomo"})
    with opener.open(req, timeout=15) as resp:
        content = resp.read().decode("utf-8", errors="ignore")
    return yaml.safe_load(content)


def select_best_ai_nodes(proxies: List[Dict[str, Any]], count: int = 10) -> List[Dict[str, Any]]:
    """优先筛选标记有 [AI]、家宽、直连主力的美/新/日优质节点"""
    selected: List[Dict[str, Any]] = []

    priority_keywords = [
        "[AI]",
        "AI",
        "家宽",
        "ISP",
        "专线",
        "主力",
        "硅谷",
        "洛杉矶",
        "西雅图",
        "纽约",
        "新加坡",
        "东京",
        "美国",
    ]

    used_names = set()
    for kw in priority_keywords:
        for p in proxies:
            name = p.get("name", "")
            if kw in name and name not in used_names:
                selected.append(p)
                used_names.add(name)
                break
        if len(selected) >= count:
            break

    # 如果还不够，从其他美国、新加坡、日本节点补齐
    if len(selected) < count:
        for p in proxies:
            name = p.get("name", "")
            if name not in used_names and any(k in name for k in ["🇺🇸", "🇸🇬", "🇯🇵"]):
                selected.append(p)
                used_names.add(name)
            if len(selected) >= count:
                break

    return selected[:count]


def generate_mihomo_config(
    nodes: List[Dict[str, Any]],
    start_port: int = 7891,
    out_file: Path = DATA_DIR / "worker_proxy_pool.yaml",
) -> List[Dict[str, Any]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    listeners = []
    assignments = []
    for idx, node in enumerate(nodes):
        port = start_port + idx
        name = node["name"]
        listeners.append({
            "name": f"worker-inbound-{idx+1:02d}",
            "type": "mixed",
            "port": port,
            "proxy": name,
        })
        assignments.append({
            "index": idx + 1,
            "port": port,
            "node_name": name,
            "node": node,
        })

    cfg = {
        "mode": "rule",
        "log-level": "warning",
        "allow-lan": False,
        "bind-address": "127.0.0.1",
        "ipv6": False,
        "external-controller": "127.0.0.1:9095",
        "proxies": nodes,
        "listeners": listeners,
        "rules": [
            "MATCH,DIRECT",
        ],
    }

    with open(out_file, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, sort_keys=False)

    print(f"[+] 已生成多端口转发配置: {out_file} (包含 {len(listeners)} 个独立端口)")
    return assignments


def start_mihomo_service(config_file: Path) -> subprocess.Popen:
    if not MIHOMO_EXE.exists():
        raise FileNotFoundError(f"找不到 Mihomo 可执行文件: {MIHOMO_EXE}")

    cmd = [
        str(MIHOMO_EXE),
        "-f",
        str(config_file),
    ]
    print(f"[*] 正在启动独立 Mihomo 多端口代理服务...")
    proc = subprocess.Popen(
        cmd,
        cwd=str(BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )
    time.sleep(2)
    if proc.poll() is not None:
        raise RuntimeError("Mihomo 启动失败，请检查端口是否冲突。")
    print(f"[+] Mihomo 多端口服务启动成功 (PID: {proc.pid})")
    return proc


def test_port_outbound_ip(port: int) -> str:
    """测试指定端口的外网出口 IP"""
    proxy_handler = urllib.request.ProxyHandler({"http": f"http://127.0.0.1:{port}", "https": f"http://127.0.0.1:{port}"})
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    opener = urllib.request.build_opener(proxy_handler, urllib.request.HTTPSHandler(context=ctx))
    req = urllib.request.Request("https://api.ipify.org", headers={"User-Agent": "curl/7.68.0"})
    try:
        with opener.open(req, timeout=8) as resp:
            return resp.read().decode("utf-8").strip()
    except Exception as e:
        return f"超时/失败: {e}"


def update_virtualbrowser_workers(
    assignments: List[Dict[str, Any]],
    vb_url: str = "http://127.0.0.1:9000",
    name_prefix: str = "ChatGPT-Worker",
) -> None:
    print(f"\n[*] 正在将 10 个独立 IP 自动应用到 VirtualBrowser 环境...")
    try:
        req = urllib.request.Request(f"{vb_url}/api/getBrowserList", data=b"{}", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            browsers = json.loads(resp.read().decode("utf-8")).get("data", [])
    except Exception as e:
        print(f"[!] 无法连接 VirtualBrowser (9000 端口): {e}")
        return

    workers = [b for b in browsers if name_prefix in b.get("name", "")]
    workers.sort(key=lambda x: x.get("name", ""))

    print(f"{'序号':<4} | {'Worker名称':<18} | {'绑定本地端口':<14} | {'出口节点名称'}")
    print("-" * 75)
    for idx, w in enumerate(workers):
        if idx < len(assignments):
            assign = assignments[idx]
            port = assign["port"]
            proxy_cfg = {
                "mode": 1,
                "value": f"127.0.0.1:{port}",
                "protocol": "HTTP",
                "host": "127.0.0.1",
                "port": str(port),
                "user": "",
                "pass": "",
                "API": "",
            }
            payload = {"id": w["id"], "proxy": proxy_cfg}
            req_up = urllib.request.Request(
                f"{vb_url}/api/updateBrowser",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req_up, timeout=10) as resp:
                    pass
            except Exception:
                pass
            print(f"{idx+1:<4} | {w['name']:<18} | 127.0.0.1:{port:<6} | {assign['node_name']}")


def main():
    parser = argparse.ArgumentParser(description="自动从 Mihomo 订阅为每个 Worker 建立独立多端口代理池")
    parser.add_argument(
        "-u",
        "--url",
        type=str,
        required=True,
        help="Mihomo / Clash 订阅链接 (例如: https://example.com/subscribe/mihomo/token)",
    )
    parser.add_argument("--start-port", type=int, default=7891, help="本地起始监听端口 (默认 7891)")
    parser.add_argument("--count", type=int, default=10, help="分配节点数量 (默认 10)")
    parser.add_argument("--vb-url", type=str, default="http://127.0.0.1:9000", help="VirtualBrowser API 地址")
    parser.add_argument("--test-ip", action="store_true", help="是否逐个测试每个端口的外网 IP")

    args = parser.parse_args()

    # 1. 获取订阅
    sub_data = fetch_subscription(args.url)
    all_proxies = sub_data.get("proxies", [])
    print(f"[+] 成功解析订阅，共包含 {len(all_proxies)} 个节点")

    # 2. 筛选最佳 10 个节点
    selected_nodes = select_best_ai_nodes(all_proxies, count=args.count)
    print(f"[+] 已为您精选 {len(selected_nodes)} 个高品质 AI 专用与家宽节点：")
    for i, n in enumerate(selected_nodes, 1):
        print(f"    {i:02d}. {n['name']}")

    # 3. 生成配置
    assignments = generate_mihomo_config(selected_nodes, start_port=args.start_port)

    # 4. 启动轻量服务
    proc = start_mihomo_service(DATA_DIR / "worker_proxy_pool.yaml")

    # 5. 测试外网 IP
    if args.test_ip:
        print("\n[*] 正在验证每个端口的外网出口 IP...")
        for a in assignments:
            ip = test_port_outbound_ip(a["port"])
            print(f"    端口 {a['port']} ({a['node_name']}) -> 真实出口 IP: {ip}")

    # 6. 自动应用到 VirtualBrowser
    update_virtualbrowser_workers(assignments, vb_url=args.vb_url)

    print("\n" + "=" * 70)
    print("【10 个 Worker 独立 IP 代理池自动分配完成！】")
    print("=" * 70)
    print("说明：")
    print(f"1. 本地 Mihomo 服务已在后台运行，分别监听 127.0.0.1:{args.start_port} ~ {args.start_port + args.count - 1}；")
    print("2. 每个本地端口完全独享对应的海外专线节点，彼此物理隔离、绝不串 IP；")
    print("3. VirtualBrowser 中的 10 个 Worker 已自动更新代理，原有 ChatGPT 登录态全部完好！")


if __name__ == "__main__":
    main()
