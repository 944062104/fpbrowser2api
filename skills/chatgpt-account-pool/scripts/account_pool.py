"""ChatGPT 账号池统一自动化工具 (Universal ChatGPT Account Pool Manager)
========================================================================
单文件搞定：
1. 双格式自适应解析 (TOTP 2FA / 微软 Outlook OAuth 接码)
2. 指纹浏览器环境创建与代理轮询均分 (40001~40005)
3. 数据库一键挂载 (windows, platform_accounts, task_type_windows)
4. 自动化网页登录、动态接码与 CDP Browser.close 会话持久化落盘
5. 账号池一键状态巡检 (--check)
"""

import argparse
import asyncio
import base64
import hashlib
import hmac
import json
import re
import sqlite3
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

VB_BASE = "http://127.0.0.1:9000"
DB_PATH = Path(r"D:\code\github\fpbrowser2api\data\fpbrowser.db")
MS_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"})
)


def http_post(url: str, data: dict = None, timeout: int = 30) -> dict:
    h = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(data or {}).encode("utf-8"), headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ==========================================
# 1. 账号解析与 TOTP 计算 (纯标准库)
# ==========================================
@dataclass
class Account:
    email: str
    password: str
    auth_type: str  # 'totp' | 'outlook_oauth' | 'password_only'
    totp_secret: Optional[str] = None
    ms_client_id: Optional[str] = None
    ms_refresh_token: Optional[str] = None
    access_token: Optional[str] = None

    def get_totp_code(self) -> str:
        clean = re.sub(r"\s+", "", self.totp_secret or "").upper()
        if len(clean) % 8:
            clean += "=" * (8 - len(clean) % 8)
        key = base64.b32decode(clean, casefold=True)
        msg = struct.pack(">Q", int(time.time() // 30))
        h = hmac.new(key, msg, hashlib.sha1).digest()
        o = h[-1] & 0x0F
        code = struct.unpack(">I", h[o : o + 4])[0] & 0x7FFFFFFF
        return str(code % 1000000).zfill(6)


def parse_accounts(sources: List[str]) -> List[Account]:
    results: List[Account] = []
    seen = set()
    raw_texts = []

    for src in sources:
        if src == "-":
            raw_texts.append(sys.stdin.read())
        elif Path(src).exists():
            raw_texts.append(Path(src).read_text(encoding="utf-8", errors="ignore"))
        else:
            # 直接传入的文本行
            raw_texts.append(src)

    for text in raw_texts:
        for line in text.splitlines():
            line = line.strip()
            if not line or any(k in line for k in ["教程", "售后", "不会用"]):
                continue
            # 支持常用分隔符：----、制表符、竖线
            parts = [x.strip() for x in re.split(r"----|\t|\|", line) if x.strip()]
            if len(parts) < 2 or "@" not in parts[0]:
                continue
            em, pw = parts[0], parts[1]
            if em.lower() in seen:
                continue
            seen.add(em.lower())

            if len(parts) >= 4 and ("-" in parts[2] or "M." in parts[3] or len(parts[3]) > 30):
                results.append(Account(em, pw, "outlook_oauth", ms_client_id=parts[2], ms_refresh_token=parts[3], access_token=parts[4] if len(parts) > 4 else None))
            elif len(parts) >= 3 and re.match(r"^[A-Z2-7]{16,64}$", re.sub(r"[\s=]+", "", parts[2]).upper()):
                results.append(Account(em, pw, "totp", totp_secret=re.sub(r"[\s=]+", "", parts[2]).upper()))
            else:
                results.append(Account(em, pw, "password_only"))
    return results


# ==========================================
# 2. 微软 Outlook OAuth 接码
# ==========================================
def get_ms_token(cid: str, rtok: str) -> str:
    data = urllib.parse.urlencode({"client_id": cid, "grant_type": "refresh_token", "refresh_token": rtok}).encode()
    req = urllib.request.Request("https://login.live.com/oauth20_token.srf", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with MS_OPENER.open(req, timeout=15) as r:
        return json.loads(r.read().decode())["access_token"]


def get_latest_mail(token: str) -> Optional[dict]:
    req = urllib.request.Request("https://outlook.office.com/api/v2.0/me/messages?$top=1", headers={"Authorization": f"Bearer {token}"})
    with MS_OPENER.open(req, timeout=15) as r:
        val = json.loads(r.read().decode()).get("value", [])
        return val[0] if val else None


def wait_mail_code(cid: str, rtok: str, baseline_id: str = None, timeout: int = 50) -> str:
    token = get_ms_token(cid, rtok)
    start = time.time()
    while time.time() - start < timeout:
        try:
            m = get_latest_mail(token)
            if m and (not baseline_id or m.get("Id") != baseline_id):
                subj = str(m.get("Subject") or "")
                body = str(m.get("BodyPreview") or "") + " " + str(m.get("Body", {}).get("Content") or "")
                if any(k in subj or k in body for k in ["ChatGPT", "OpenAI", "验证码", "verification code"]):
                    codes = re.findall(r"\b\d{6}\b", body)
                    if codes:
                        return codes[0]
        except Exception:
            try:
                token = get_ms_token(cid, rtok)
            except Exception:
                pass
        time.sleep(2)
    raise TimeoutError("未能及时收到最新的 ChatGPT 验证码邮件")


# ==========================================
# 3. 自动化登录与 Cookies 落盘
# ==========================================
async def login_worker(worker_id: int, acc: Account, vb_base: str = VB_BASE) -> bool:
    from playwright.async_api import async_playwright
    print(f"\n[*] Worker {worker_id:<2} [{acc.auth_type}] -> {acc.email}")

    res = http_post(f"{vb_base}/api/launchBrowser", {"id": worker_id, "url": "https://chatgpt.com/"})
    port = res["data"]["debuggingPort"]

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # 检查是否已有会话
        cookies = await ctx.cookies("https://chatgpt.com")
        if any("session-token" in c.get("name", "") for c in cookies):
            print(f"  [+] Worker {worker_id} 已有登录态，跳过！")
            cdp = await browser.new_browser_cdp_session()
            await cdp.send("Browser.close")
            return True

        base_id = None
        if acc.auth_type == "outlook_oauth" and acc.ms_client_id and acc.ms_refresh_token:
            try:
                m = get_latest_mail(get_ms_token(acc.ms_client_id, acc.ms_refresh_token))
                base_id = m.get("Id") if m else None
            except Exception:
                pass

        # 页面登录与邮箱提交
        code_input = await page.query_selector("input[name='code'], input#code, input[inputmode='numeric']")
        if not code_input:
            if "chatgpt.com" not in page.url or "auth" not in page.url:
                await page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=50000)
                await asyncio.sleep(2)
                btn = await page.wait_for_selector("button:has-text('登录'), button:has-text('Log in'), [data-testid='login-button']", timeout=20000)
                await btn.click()
                await asyncio.sleep(2)

            email_inp = await page.wait_for_selector("input[type='email'], input#email-input, input[name='email']", timeout=25000)
            await email_inp.fill(acc.email)
            await asyncio.sleep(1)

            cont_btn = await page.query_selector("button:has-text('继续'), button:has-text('Continue'), button[type='submit']")
            if cont_btn and await cont_btn.is_visible():
                await cont_btn.click()
            else:
                await email_inp.press("Enter")

            try:
                await page.wait_for_url(lambda u: "auth.openai.com" in u or "email-verification" in u or "password" in u, timeout=45000)
            except Exception:
                pass

            pwd_inp = await page.query_selector("input[type='password'], input[name='password']")
            if pwd_inp and await pwd_inp.is_visible():
                await pwd_inp.fill(acc.password)
                await asyncio.sleep(1)
                p_btn = await page.query_selector("button:has-text('继续'), button:has-text('Continue'), button[type='submit']")
                if p_btn:
                    await p_btn.click()
                else:
                    await pwd_inp.press("Enter")
                await asyncio.sleep(3)

            code_input = await page.wait_for_selector("input[name='code'], input#code, input[inputmode='numeric']", timeout=45000)

        # 获取验证码
        code = acc.get_totp_code() if acc.auth_type == "totp" else wait_mail_code(acc.ms_client_id, acc.ms_refresh_token, base_id)
        print(f"  -> 输入验证码: {code}")

        # 键盘模拟按键输入 (触发 React Aria 状态)
        await code_input.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.3)
        await page.keyboard.type(code, delay=100)
        await asyncio.sleep(1)

        val_btn = await page.wait_for_selector("button[value='validate'], button[data-dd-action-name='Continue'], button[type='submit']", timeout=15000)
        await val_btn.click()

        # 等待主页跳转
        success = False
        for _ in range(45):
            await asyncio.sleep(1)
            if "chatgpt.com" in page.url and "auth" not in page.url and "login" not in page.url:
                success = True
                break
        if not success:
            raise RuntimeError(f"等待主页超时: {page.url}")

        print(f"  [SUCCESS] 🎉 Worker {worker_id} 登录成功！")
        cdp = await browser.new_browser_cdp_session()
        await cdp.send("Browser.close")
        await asyncio.sleep(2)
        return True


# ==========================================
# 4. 数据库同步与环境分配
# ==========================================
def sync_to_db(accounts: List[Account], start_id: int, space_pk: int = 5):
    if not DB_PATH.exists():
        return
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    tt_ids = [r[0] for r in c.execute("SELECT id FROM task_types WHERE code IN ('gpt_workflow', 'gpt_chat')").fetchall()]

    for i, acc in enumerate(accounts):
        w_id = start_id + i
        acc_id = i + 1

        c.execute("UPDATE windows SET platform_account = ? WHERE space_pk = ? AND (window_remark = ? OR window_key = ?)", (acc.email, space_pk, acc.email, str(w_id)))
        w_row = c.execute("SELECT id FROM windows WHERE space_pk = ? AND (window_key = ? OR window_sort_num = ? OR id = ?)", (space_pk, str(w_id), w_id, w_id)).fetchone()
        win_pk = w_row[0] if w_row else w_id

        efa = acc.totp_secret if acc.auth_type == "totp" else ""
        rmk = f"{acc.ms_client_id}----{acc.ms_refresh_token}" if acc.auth_type == "outlook_oauth" else ""
        raw = json.dumps({"email": acc.email, "auth_type": acc.auth_type, "totp": acc.totp_secret, "cid": acc.ms_client_id, "rtok": acc.ms_refresh_token})

        pa = c.execute("SELECT id FROM platform_accounts WHERE space_pk = ? AND account_id = ?", (space_pk, acc_id)).fetchone()
        if pa:
            c.execute("UPDATE platform_accounts SET platform_username = ?, platform_password = ?, platform_efa = ?, platform_remarks = ?, raw_json = ?, updated_at = datetime('now','localtime') WHERE id = ?", (acc.email, acc.password, efa, rmk, raw, pa[0]))
        else:
            c.execute("INSERT INTO platform_accounts (space_pk, account_id, platform_url, platform_username, platform_password, platform_efa, platform_remarks, raw_json, created_at, updated_at) VALUES (?, ?, 'https://chatgpt.com', ?, ?, ?, ?, ?, datetime('now','localtime'), datetime('now','localtime'))", (space_pk, acc_id, acc.email, acc.password, efa, rmk, raw))

        for tid in tt_ids:
            tw = c.execute("SELECT id FROM task_type_windows WHERE task_type_id = ? AND window_pk = ?", (tid, win_pk)).fetchone()
            if tw:
                c.execute("UPDATE task_type_windows SET enabled = 1, remaining_quota = 999, consecutive_errors = 0, updated_at = datetime('now','localtime') WHERE id = ?", (tw[0],))
            else:
                c.execute("INSERT INTO task_type_windows (task_type_id, window_pk, inflight_slots, total_errors, consecutive_errors, daily_quota, remaining_quota, enabled, created_at, updated_at) VALUES (?, ?, 0, 0, 0, 999, 999, 1, datetime('now','localtime'), datetime('now','localtime'))", (tid, win_pk))

    conn.commit()
    conn.close()
    print("  [+] FPBrowser 数据库同步与路由挂载完成！")


# ==========================================
# 5. 巡检模式 (--check)
# ==========================================
def run_check():
    print("=" * 65)
    print("🔍 ChatGPT 账号池状态一览")
    print("=" * 65)
    # VirtualBrowser
    try:
        data = json.loads(urllib.request.urlopen(f"{VB_BASE}/api/getBrowserList", timeout=5).read()).get("data", [])
        print(f"[1] VirtualBrowser 环境: {len(data)} 个 (ID: {min(b['id'] for b in data)} ~ {max(b['id'] for b in data)})")
    except Exception as e:
        print(f"[1] VirtualBrowser: 离线 ({e})")

    # Proxies
    print("[2] 本地免密 SOCKS5 出口:")
    for p in [40001, 40002, 40003, 40004, 40005]:
        res = subprocess.run(["curl.exe", "-s", "-x", f"socks5h://127.0.0.1:{p}", "https://api.ipify.org", "--max-time", "6"], capture_output=True, text=True)
        print(f"    - :{p} -> {res.stdout.strip() if res.stdout else '超时/未连接'}")

    # Database
    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        w_cnt = c.execute("SELECT COUNT(*) FROM windows WHERE space_pk = 5").fetchone()[0]
        acc_cnt = c.execute("SELECT COUNT(*) FROM platform_accounts WHERE space_pk = 5").fetchone()[0]
        routes = c.execute("SELECT tt.name, COUNT(*) FROM task_type_windows ttw JOIN task_types tt ON tt.id = ttw.task_type_id WHERE ttw.enabled = 1 GROUP BY tt.name").fetchall()
        print(f"[3] 数据库挂载 (Space 5): {w_cnt} 窗口 | {acc_cnt} 凭据")
        for r_name, cnt in routes:
            print(f"    - 路由 {r_name:<16}: {cnt} 个就绪窗口")
        conn.close()
    print("=" * 65)


# ==========================================
# 6. 主执行流
# ==========================================
async def main():
    parser = argparse.ArgumentParser(description="ChatGPT 账号池统一自动化工具")
    parser.add_argument("files", nargs="*", help="发货文本路径 (支持多个)")
    parser.add_argument("--start-id", type=int, default=12, help="起始 Worker ID (默认 12)")
    parser.add_argument("--proxy-ports", type=str, default="40001,40002,40003,40004,40005", help="代理端口列表")
    parser.add_argument("--no-login", action="store_true", help="仅建环境与同步数据库，不登录")
    parser.add_argument("--check", action="store_true", help="执行健康状态巡检")
    args = parser.parse_args()

    if args.check:
        run_check()
        return

    if not args.files:
        parser.print_help()
        return

    accs = parse_accounts(args.files)
    print(f"[*] 成功解析 {len(accs)} 个账号 (TOTP: {sum(1 for a in accs if a.auth_type == 'totp')}, OAuth: {sum(1 for a in accs if a.auth_type == 'outlook_oauth')})")

    # 创建/绑定环境
    try:
        vb_browsers = {b["id"]: b for b in json.loads(urllib.request.urlopen(f"{VB_BASE}/api/getBrowserList", timeout=10).read()).get("data", [])}
    except Exception:
        vb_browsers = {}

    ports = [int(p) for p in args.proxy_ports.split(",")]
    for i, a in enumerate(accs):
        wid = args.start_id + i
        if wid not in vb_browsers:
            http_post(f"{VB_BASE}/api/addBrowser", {
                "name": f"ChatGPT-Worker-{wid}",
                "group": ["ChatGPT-Farm"],
                "remark": a.email,
                "homepage": {"mode": 1, "value": "https://chatgpt.com/"},
                "proxy": {"mode": 1, "value": f"127.0.0.1:{ports[i % len(ports)]}", "protocol": "SOCKS5", "host": "127.0.0.1", "port": str(ports[i % len(ports)]), "user": "", "pass": "", "API": ""},
            })

    sync_to_db(accs, args.start_id)

    if not args.no_login:
        for i, a in enumerate(accs):
            wid = args.start_id + i
            for _ in range(2):
                try:
                    if await login_worker(wid, a):
                        break
                except Exception as e:
                    print(f"  [-] Worker {wid} 失败: {e}")
                    try:
                        http_post(f"{VB_BASE}/api/stopBrowser", {"id": wid})
                    except Exception:
                        pass
                await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
