"""Sub2API 凭据提取与 RT 生成工具 (Token & RT Extractor)
======================================================
支持两套工作流：
1. [快速模式] 一键从 10 个 Worker 窗口中提取当前有效的 Access Token (AT) 及 Session Token，
   生成可直接复制给 Sub2API 批量导入的文本。
2. [OAuth RT 模式] 自动化配合 Sub2API 的「手动授权」流程：
   调起对应账号的指纹浏览器，自动打开 Sub2API 的授权 URL，自动同意并捕获回调 code，
   直接换取包含永久自动刷新能力的 Refresh Token (RT) 或 auth.json。
"""

import asyncio
import json
import os
import shutil
import sqlite3
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

WORKERS_DIR = Path(r"C:\Users\mojj\AppData\Local\VirtualBrowser\Workers")
DB_PATH = Path(r"D:\code\github\fpbrowser2api\data\fpbrowser.db")
OUTPUT_DIR = Path(r"D:\code\github\fpbrowser2api\data\sub2api_export")


def launch_vb_browser(worker_id: str | int) -> int:
    url = "http://127.0.0.1:9000/api/launchBrowser"
    data = json.dumps({"id": str(worker_id)}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        res = json.loads(resp.read().decode("utf-8"))
    if not res.get("success"):
        raise RuntimeError(f"启动环境 {worker_id} 失败: {res.get('msg')}")
    return res["data"]["debuggingPort"]


def stop_vb_browser(worker_id: str | int):
    try:
        url = "http://127.0.0.1:9000/api/stopBrowser"
        data = json.dumps({"id": str(worker_id)}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            pass
    except Exception:
        pass


def get_workers():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT w.window_key, w.window_name, pa.platform_username, w.proxy_addr
        FROM windows w
        JOIN platform_accounts pa ON w.platform_account_id = pa.id
        WHERE w.space_pk = 5 AND w.window_key != '1'
        ORDER BY CAST(w.window_key AS INTEGER) ASC
    """)
    rows = c.fetchall()
    conn.close()
    return rows


async def extract_all_access_tokens():
    """提取全部 10 个账号的最新 accessToken"""
    print("\n" + "=" * 70)
    print("  🚀 开始批量提取 10 个 Worker 浏览器的 Access Token (AT)...")
    print("=" * 70)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    workers = get_workers()
    tokens = []

    for idx, (wid, wname, email, proxy) in enumerate(workers, 1):
        print(f"\n[{idx:2d}/{len(workers)}] 正在提取 窗口 {wid:2s} ({wname}) | 账号: {email}...")
        try:
            port = launch_vb_browser(wid)
            async with async_playwright() as p:
                b = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
                ctx = b.contexts[0]
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()

                # 通过页面直接获取当前有效的 Session
                session_resp = await page.evaluate('''async () => {
                    try {
                        const r = await fetch('https://chatgpt.com/api/auth/session');
                        return await r.json();
                    } catch(e) {
                        return null;
                    }
                }''')

                token = session_resp.get("accessToken") if session_resp else None
                user_info = session_resp.get("user") or {}

                if token:
                    print(f"   ✅ 成功获取 AT! 有效期至: {session_resp.get('expires', '未知')}")
                    tokens.append({
                        "worker_id": wid,
                        "worker_name": wname,
                        "email": email,
                        "proxy": proxy,
                        "access_token": token,
                        "user": user_info
                    })
                else:
                    print(f"   ⚠️ 未能直接读取到 accessToken")

                cdp = await b.new_browser_cdp_session()
                await cdp.send("Browser.close")
        except Exception as e:
            print(f"   ❌ 提取异常: {e}")
        finally:
            stop_vb_browser(wid)

    # 保存结果
    txt_file = OUTPUT_DIR / "access_tokens_only.txt"
    json_file = OUTPUT_DIR / "sub2api_at_export.json"

    with open(txt_file, "w", encoding="utf-8") as f:
        for item in tokens:
            f.write(item["access_token"] + "\n")

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(tokens, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    print("  🎉 提取完成！")
    print(f"  - 成功数量: {len(tokens)} / {len(workers)}")
    print(f"  - 纯 AT 文本 (每行一个，可直接复制): {txt_file}")
    print(f"  - 详细 JSON 文件:                    {json_file}")
    print("=" * 70)
    return tokens


async def run_oauth_flow_in_worker(wid: str, auth_url: str):
    """在指定 Worker 浏览器中打开 Sub2API 授权链接并自动获取回调结果"""
    print(f"\n[*] 正在拉起 Worker {wid} 浏览器执行 OAuth 授权...")
    port = launch_vb_browser(wid)
    captured_code = None
    captured_callback = None

    try:
        async with async_playwright() as p:
            b = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            ctx = b.contexts[0]
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

            def handle_route(route):
                nonlocal captured_code, captured_callback
                url = route.request.url
                if "code=" in url:
                    captured_callback = url
                    parsed = urllib.parse.urlparse(url)
                    qs = urllib.parse.parse_qs(parsed.query)
                    if "code" in qs:
                        captured_code = qs["code"][0]
                        print(f"\n[🎉 成功捕获 Auth Code]: {captured_code}")
                route.continue_()

            await page.route("**/*", handle_route)

            print(f"[*] 导航至授权页面: {auth_url[:60]}...")
            try:
                await page.goto(auth_url, wait_until="commit", timeout=45000)
            except Exception:
                pass

            # 检查是否有“Continue / 授权 / 允许”按钮并尝试辅助点击
            await asyncio.sleep(3)
            for _ in range(30):
                if captured_code:
                    break
                # 尝试查找确认/授权按钮
                try:
                    btn = await page.query_selector("button:has-text('Allow'), button:has-text('Continue'), button:has-text('允许'), button:has-text('授权')")
                    if btn and await btn.is_visible():
                        print("  -> 检测到授权确认按钮，自动点击...")
                        await btn.click()
                except Exception:
                    pass
                await asyncio.sleep(1)

            cdp = await b.new_browser_cdp_session()
            await cdp.send("Browser.close")
    finally:
        stop_vb_browser(wid)

    return captured_code, captured_callback


def main():
    print("=" * 70)
    print("  🔑 Sub2API 凭证提取与授权工具")
    print("  1. 批量提取当前 10 个已登录窗口的 Access Token (纯 AT 列表)")
    print("  2. 在指定 Worker 浏览器中执行 Sub2API「手动授权」链接 (自动拦截 code)")
    print("=" * 70)

    if len(sys.argv) > 1 and sys.argv[1] == "at":
        asyncio.run(extract_all_access_tokens())
    elif len(sys.argv) > 2 and sys.argv[1] == "oauth":
        wid = sys.argv[2]
        auth_url = sys.argv[3] if len(sys.argv) > 3 else input("请输入 Sub2API 生成的授权 URL: ").strip()
        code, cb = asyncio.run(run_oauth_flow_in_worker(wid, auth_url))
        print(f"\n结果: Code={code}")
        print(f"完整回调 URL: {cb}")
    else:
        # 默认模式：交互式菜单
        choice = input("请选择操作 [1 提取AT / 2 辅助手动授权] (默认 1): ").strip() or "1"
        if choice == "1":
            asyncio.run(extract_all_access_tokens())
        elif choice == "2":
            wid = input("请输入目标窗口 ID (例如 2): ").strip()
            auth_url = input("请输入 Sub2API 给出的授权链接: ").strip()
            code, cb = asyncio.run(run_oauth_flow_in_worker(wid, auth_url))
            print(f"\n结果: Code={code}")
            print(f"完整回调 URL: {cb}")


if __name__ == "__main__":
    main()
