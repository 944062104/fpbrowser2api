"""针对未登录/掉号窗口的自动重新登录与持久化落盘工具
========================================================================
支持自动检测掉号窗口并重新登录，或指定窗口 ID 单独重新登录。
包含 4 秒 Cloudflare 探测准备、TOTP 动态验证码计算以及 CDP 优雅退出落盘。

用法:
    python relogin_all_missing_workers.py          # 自动扫描并修复所有未登录窗口
    python relogin_all_missing_workers.py 5 8 11   # 仅修复指定窗口 ID
"""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import shutil
import sqlite3
import struct
import sys
import time
import urllib.request
from pathlib import Path
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

WORKERS_DIR = Path(r"C:\Users\mojj\AppData\Local\VirtualBrowser\Workers")
DB_PATH = Path(r"D:\code\github\fpbrowser2api\data\fpbrowser.db")

def log(msg: str):
    print(msg, flush=True)

def get_totp(secret: str) -> str:
    secret = secret.strip().replace(" ", "").upper()
    padding = "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(secret + padding)
    counter = int(time.time() // 30)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[19] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset+4])[0] & 0x7FFFFFFF) % 1000000
    return f"{code:06d}"

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

def check_local_disk_session_cookie(wid: str) -> bool:
    cookie_path = WORKERS_DIR / str(wid) / "Default" / "Network" / "Cookies"
    if not cookie_path.exists():
        return False
    tmp_path = f"tmp_chk_{wid}_{os.getpid()}.sqlite"
    try:
        shutil.copy2(cookie_path, tmp_path)
        conn = sqlite3.connect(tmp_path)
        c = conn.cursor()
        c.execute("SELECT name FROM cookies WHERE host_key LIKE '%chatgpt.com%' AND name LIKE '%session-token%'")
        rows = c.fetchall()
        conn.close()
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return len(rows) > 0
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False

async def relogin_one_worker(wid: str, email: str, pwd: str, secret_2fa: str) -> bool:
    log("\n" + "=" * 65)
    log(f"  ▶️ 正在自动化登录: 窗口 {wid} | 账号: {email}")
    log("=" * 65)

    port = launch_vb_browser(wid)
    log(f"[*] 窗口 {wid} 已拉起，CDP 调试端口: {port}")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            ctx = browser.contexts[0]
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

            log("[1/5] 导航至 ChatGPT 页面...")
            try:
                await page.goto("https://chatgpt.com/", wait_until="commit", timeout=45000)
            except Exception:
                pass
            await asyncio.sleep(4)

            # 检查是否直接就是已登录态
            cookies = await ctx.cookies("https://chatgpt.com")
            if any("session-token" in c.get("name", "") for c in cookies):
                log("  -> 检测到页面已有完整 session-token，无需重复登录！")
                cdp = await browser.new_browser_cdp_session()
                await cdp.send("Browser.close")
                await asyncio.sleep(2)
                return True

            # 点击首页“登录 / Log in”按钮打开模态框
            login_btn = await page.query_selector("button:has-text('登录'), button:has-text('Log in')")
            if login_btn:
                log("  -> 点击首页「登录」按钮...")
                await login_btn.click()
                await asyncio.sleep(4)

            # 输入邮箱
            log(f"[2/5] 输入邮箱: {email}...")
            email_el = await page.wait_for_selector(
                "input[type='email'], input#email-input, input[name='email'], input[placeholder*='Email' i], input[placeholder*='电子邮件' i]",
                timeout=25000
            )
            await email_el.fill(email)
            await asyncio.sleep(1)
            await email_el.press("Enter")
            log("  -> 已回车提交邮箱，等待跳转至密码页面...")

            for _ in range(30):
                await asyncio.sleep(1)
                if "password" in page.url or "auth.openai.com" in page.url:
                    break

            # 输入密码
            log(f"[3/5] 等待密码输入框... (当前 URL: {page.url})")
            pwd_el = await page.wait_for_selector(
                "input[type='password'], input#password, input[name='password']",
                timeout=30000
            )
            log("  -> 等待 Cloudflare 探测脚本就绪 (4s)...")
            await asyncio.sleep(4)
            log("  -> 填写密码并回车提交...")
            await pwd_el.fill(pwd)
            await asyncio.sleep(2)
            await pwd_el.press("Enter")
            log("  -> 已回车提交密码，等待进入 2FA 或主页...")

            # 2FA 验证或主页跳转
            log("[4/5] 检查 2FA 验证或主页跳转...")
            for s in range(40):
                await asyncio.sleep(1)
                cur_url = page.url
                try:
                    retry_btn = await page.query_selector("button:has-text('重试'), button:has-text('Retry')")
                    if retry_btn and await retry_btn.is_visible():
                        log("  -> 检测到「糟糕，出错了！」提示，正在点击「重试」...")
                        await retry_btn.click()
                        await asyncio.sleep(4)
                except Exception:
                    pass

                if "chatgpt.com" in cur_url and "auth" not in cur_url and "login" not in cur_url:
                    log(f"  -> 已成功进入 ChatGPT 主页: {cur_url}")
                    break

                try:
                    code_el = await page.query_selector("input[name='code'], input#code, input[autocomplete='one-time-code'], input[placeholder*='code' i], input[placeholder*='代码' i]")
                    if code_el and await code_el.is_visible():
                        log("  -> 遇到 2FA 输入框，等待 4 秒就绪 Cloudflare 探测...")
                        await asyncio.sleep(4)
                        totp = get_totp(secret_2fa)
                        log(f"  -> 填入动态验证码: {totp} ...")
                        await code_el.fill(totp)
                        await asyncio.sleep(2)
                        await code_el.press("Enter")
                        log("  -> 已提交 2FA 动态码，等待最终跳转...")
                        break
                except Exception:
                    pass

            # 等待主页完全加载
            log(f"[5/5] 等待主界面完全加载... (当前 URL: {page.url})")
            for s5 in range(50):
                await asyncio.sleep(1)
                cur_url = page.url
                try:
                    retry_btn = await page.query_selector("button:has-text('重试'), button:has-text('Retry')")
                    if retry_btn and await retry_btn.is_visible():
                        log("  -> 检测到「糟糕，出错了！」提示，正在点击「重试」...")
                        await retry_btn.click()
                        await asyncio.sleep(4)
                except Exception:
                    pass

                if "chatgpt.com" in cur_url and "auth" not in cur_url and "login" not in cur_url:
                    log(f"  -> 成功进入 ChatGPT 主页: {cur_url}")
                    break
            await asyncio.sleep(6)

            # 提取 accessToken 并更新数据库
            try:
                session_resp = await page.evaluate('''async () => {
                    try {
                        const r = await fetch('/api/auth/session');
                        return await r.json();
                    } catch(e) {
                        return null;
                    }
                }''')
                if session_resp and session_resp.get("accessToken"):
                    latest_token = session_resp.get("accessToken")
                    conn = sqlite3.connect(DB_PATH)
                    cur = conn.cursor()
                    cur.execute("""
                        UPDATE task_type_windows
                        SET sora_access_token = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE window_pk = (SELECT id FROM windows WHERE window_key = ? AND space_pk = 5)
                          AND task_type_id = 6
                    """, (latest_token, wid))
                    conn.commit()
                    conn.close()
                    log("  [+] 已提取并更新数据库中的最新 accessToken！")
            except Exception as e:
                log(f"  [!] 提取最新 session 出错: {e}")

            # 优雅通过 CDP 发送 Browser.close 命令以持久化写入磁盘
            log("[*] 正在通过 CDP 发送 Browser.close 命令优雅退出以确保写盘...")
            cdp_client = await browser.new_browser_cdp_session()
            await cdp_client.send("Browser.close")
            await asyncio.sleep(4)
    finally:
        stop_vb_browser(wid)

    # 磁盘检测
    disk_ok = check_local_disk_session_cookie(wid)
    log(f"[*] 磁盘写入校验: Worker {wid} session-token 写入磁盘: {'✅ 成功' if disk_ok else '❌ 失败'}")
    return disk_ok

async def main():
    target_workers = sys.argv[1:]
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if target_workers:
        placeholders = ",".join("?" for _ in target_workers)
        c.execute(f"""
            SELECT w.window_key, pa.platform_username, pa.platform_password, pa.platform_efa
            FROM windows w
            JOIN platform_accounts pa ON w.platform_account_id = pa.id
            WHERE w.window_key IN ({placeholders}) AND w.space_pk = 5
            ORDER BY CAST(w.window_key AS INTEGER) ASC
        """, target_workers)
    else:
        # 自动查出所有未登录的
        c.execute("""
            SELECT w.window_key, pa.platform_username, pa.platform_password, pa.platform_efa
            FROM windows w
            JOIN platform_accounts pa ON w.platform_account_id = pa.id
            WHERE w.space_pk = 5
            ORDER BY CAST(w.window_key AS INTEGER) ASC
        """)
    rows = c.fetchall()
    conn.close()

    # 如果是全量检测，过滤掉已登录的
    if not target_workers:
        filtered = []
        for wid, email, pwd, efa in rows:
            if not check_local_disk_session_cookie(wid):
                filtered.append((wid, email, pwd, efa))
        rows = filtered

    if not rows:
        log("🎉 所有窗口本地均已登录且持久化完整，无需登录任何账号！")
        return

    log("=" * 65)
    log(f"  🚀 开始重新登录 {len(rows)} 个未登录窗口: {[r[0] for r in rows]}")
    log("=" * 65)

    summary = {}
    for wid, email, pwd, efa in rows:
        try:
            ok = await relogin_one_worker(wid, email, pwd, efa)
            summary[wid] = ok
        except Exception as e:
            log(f"[!] 窗口 {wid} 登录异常: {e}")
            summary[wid] = False
        await asyncio.sleep(3)

    log("\n" + "=" * 65)
    log("  📋 批量重新登录完成汇总:")
    for wid, ok in summary.items():
        log(f"  - 窗口 {wid:2s}: {'🟢 成功持久化' if ok else '🔴 失败'}")
    log("=" * 65)

if __name__ == "__main__":
    asyncio.run(main())
