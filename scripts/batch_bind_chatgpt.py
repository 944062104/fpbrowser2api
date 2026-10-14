"""ChatGPT 自动化多账号绑定与持久化登录工具
========================================================================
支持从发货格式文件（邮箱----密码----2fa）批量读取账号，自动对接 VirtualBrowser
完成环境创建、自动化网页登录、TOTP 2FA 验证、Session Cookie 磁盘持久化固化，
并同步绑定至 FPBrowser2API 任务调度池。

使用方法:
    python scripts/batch_bind_chatgpt.py -f accounts.txt
    python scripts/batch_bind_chatgpt.py -f accounts.txt --proxy 127.0.0.1:7890 --sync-fpb
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import pyotp
except ImportError:
    print("[Error] 请先安装 pyotp: pip install pyotp")
    sys.exit(1)

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("[Error] 请先安装 playwright: pip install playwright && playwright install chromium")
    sys.exit(1)


# -------------------- HTTP 请求辅助 --------------------
def http_post(url: str, data: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=json.dumps(data or {}).encode("utf-8"), headers=h)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get(url: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


# -------------------- 账号解析 --------------------
class AccountItem:
    def __init__(self, email: str, pwd: str, secret_2fa: str):
        self.email = email.strip()
        self.pwd = pwd.strip()
        self.secret_2fa = secret_2fa.strip()

    def __repr__(self) -> str:
        return f"<Account {self.email}>"


def parse_accounts_file(file_path: Path) -> List[AccountItem]:
    if not file_path.exists():
        raise FileNotFoundError(f"找不到账号文件: {file_path}")

    accounts: List[AccountItem] = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("----")
            if len(parts) >= 3:
                accounts.append(AccountItem(parts[0], parts[1], parts[2]))
            elif len(parts) == 2:
                # 兼容无 2FA 场景
                accounts.append(AccountItem(parts[0], parts[1], ""))
    return accounts


# -------------------- VirtualBrowser 管理 --------------------
class VirtualBrowserManager:
    def __init__(self, base_url: str = "http://127.0.0.1:9000"):
        self.base_url = base_url.rstrip("/")

    def get_browser_list(self) -> List[Dict[str, Any]]:
        res = http_post(f"{self.base_url}/api/getBrowserList", {})
        return res.get("data", [])

    def ensure_worker(
        self,
        name: str,
        email: str,
        proxy_host: str = "127.0.0.1",
        proxy_port: str = "7890",
        proxy_proto: str = "HTTP",
    ) -> int:
        browsers = self.get_browser_list()
        # 1. 先按 remark (email) 或 name 查找已有
        for b in browsers:
            if b.get("remark") == email or b.get("name") == name:
                wid = b.get("id")
                # 更新名称与备注保证统一
                http_post(
                    f"{self.base_url}/api/updateBrowser",
                    {"id": wid, "name": name, "remark": email},
                )
                return wid

        # 2. 不存在则创建新环境
        cur_proxy = {
            "mode": 1 if proxy_host and proxy_port else 0,
            "value": f"{proxy_host}:{proxy_port}" if proxy_host and proxy_port else "",
            "protocol": proxy_proto,
            "host": proxy_host or "",
            "port": proxy_port or "",
            "user": "",
            "pass": "",
            "API": "",
        }
        payload = {
            "name": name,
            "group": ["默认分组"],
            "homepage": {"mode": 1, "value": "https://chatgpt.com"},
            "proxy": cur_proxy,
            "remark": email,
        }
        res = http_post(f"{self.base_url}/api/addBrowser", payload)
        if not res.get("success"):
            raise RuntimeError(f"创建 VirtualBrowser 环境失败: {res.get('msg')}")
        return res["data"]["id"]

    def launch_browser(self, worker_id: int) -> int:
        res = http_post(f"{self.base_url}/api/launchBrowser", {"id": worker_id})
        if not res.get("success"):
            raise RuntimeError(f"启动环境 ID={worker_id} 失败: {res.get('msg')}")
        return res["data"]["debuggingPort"]

    def stop_browser(self, worker_id: int) -> None:
        try:
            http_post(f"{self.base_url}/api/stopBrowser", {"id": worker_id})
        except Exception:
            pass


# -------------------- 自动化登录流程 --------------------
async def perform_chatgpt_login(
    port: int,
    account: AccountItem,
    worker_id: int,
    screenshot_dir: Optional[Path] = None,
) -> bool:
    """自动化登录单账号，并在确认登录后优雅注销 CDP 连接以刷盘。"""
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0]

        # 清除任何历史残留的冲突 Cookie
        await ctx.clear_cookies()

        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        print(f"  [1/6] 导航至 ChatGPT 登录页...")
        await page.goto("https://chatgpt.com/auth/login", wait_until="commit", timeout=45000)
        await asyncio.sleep(4)

        # 1. 输入邮箱
        print(f"  [2/6] 输入邮箱: {account.email}...")
        email_input = await page.wait_for_selector(
            "input[type='email'], input[name='email'], input[placeholder*='Email' i]",
            timeout=25000,
        )
        await email_input.fill(account.email)
        await asyncio.sleep(1)

        submit_btn = await page.wait_for_selector("button[type='submit'], button.btn-primary", timeout=5000)
        await submit_btn.click()

        # 2. 等待密码框
        print(f"  [3/6] 输入密码...")
        pwd_input = await page.wait_for_selector(
            "input[type='password'], input[name='password'], #password",
            timeout=25000,
        )
        await pwd_input.fill(account.pwd)
        await asyncio.sleep(1)

        submit_pwd = await page.wait_for_selector("button[type='submit'], button.btn-primary", timeout=5000)
        await submit_pwd.click()

        # 3. 处理 2FA 验证码
        if account.secret_2fa:
            print(f"  [4/6] 等待 2FA 验证码输入框...")
            code_input = None
            for _ in range(25):
                await asyncio.sleep(1)
                cur_u = page.url
                if "chatgpt.com" in cur_u and "auth" not in cur_u and "mfa" not in cur_u:
                    print(f"  -> 已直接跳转至主页，跳过 2FA")
                    break
                try:
                    el = await page.query_selector("input[name='code'], input[autocomplete='one-time-code']")
                    if el and await el.is_visible():
                        code_input = el
                        break
                except Exception:
                    pass

            if code_input:
                totp = pyotp.TOTP(account.secret_2fa.strip()).now()
                print(f"  -> 计算并填入 TOTP 2FA: {totp}...")
                await code_input.fill(totp)
                await asyncio.sleep(1)
                submit_2fa = await page.wait_for_selector("button[type='submit'], button.btn-primary", timeout=5000)
                await submit_2fa.click()

        # 4. 等待跳转至 ChatGPT 主页
        print(f"  [5/6] 等待主页加载与会话就绪...")
        for _ in range(15):
            await asyncio.sleep(1)
            if "chatgpt.com" in page.url and "auth" not in page.url:
                break
        await asyncio.sleep(8)

        # 5. 校验 Session Token
        cookies = await ctx.cookies("https://chatgpt.com")
        has_session = any("session-token" in c.get("name", "") for c in cookies)
        print(f"  -> 主页就绪: URL={page.url}, 包含 Session Token: {has_session}")

        # 截图存证
        if screenshot_dir:
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            shot_file = screenshot_dir / f"worker_{worker_id}_verified.png"
            await page.screenshot(path=str(shot_file))
            print(f"  -> 登录成功截图已保存: {shot_file}")

        # 6. 优雅关闭 CDP，触发 SQLite WAL Checkpoint
        print(f"  [6/6] 优雅注销 CDP 连接，等待 5 秒完成磁盘 WAL 写入...")
        await browser.close()
        await asyncio.sleep(5)
        return has_session


# -------------------- FPBrowser2API 同步 --------------------
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "fpbrowser.db"


def sync_to_fpbrowser2api(
    fpb_url: str = "http://127.0.0.1:8000",
    db_path: Path | str = DEFAULT_DB_PATH,
    space_pk: int = 5,
    task_type_id: int = 6,
) -> None:
    print("\n" + "=" * 65)
    print("[*] 正在同步环境与任务池至 FPBrowser2API...")
    print("=" * 65)
    try:
        login_res = http_post(f"{fpb_url}/api/admin/login", {"username": "admin", "password": "admin"})
        token = login_res.get("token")
        headers = {"Authorization": f"Bearer {token}"}
        sync_res = http_post(f"{fpb_url}/api/admin/spaces/{space_pk}/sync-windows", {}, headers=headers)
        print(f"  [+] FPBrowser2API 窗口同步成功: {sync_res.get('message')}")
    except Exception as e:
        print(f"  [!] 调用 FPBrowser2API 接口提示: {e}")

    # 本地数据库检查与任务池绑定
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT id, window_key, window_name FROM windows WHERE space_pk = ?", (space_pk,))
        windows = cur.fetchall()
        for win_pk, w_key, w_name in windows:
            cur.execute(
                "SELECT id FROM task_type_windows WHERE task_type_id = ? AND window_pk = ?",
                (task_type_id, win_pk),
            )
            ttw = cur.fetchone()
            if not ttw:
                cur.execute(
                    "INSERT INTO task_type_windows (task_type_id, window_pk, enabled, deleted) VALUES (?, ?, 1, 0)",
                    (task_type_id, win_pk),
                )
            else:
                cur.execute("UPDATE task_type_windows SET enabled = 1, deleted = 0 WHERE id = ?", (ttw[0],))
        conn.commit()
        conn.close()
        print(f"  [+] 已更新本地数据库任务池绑定 (task_type_id={task_type_id})")


# -------------------- 主入口 --------------------
async def main_async(args: argparse.Namespace) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    account_file = Path(args.file)
    print("=" * 70)
    print(f"[*] 读取账号文件: {account_file.resolve()}")
    accounts = parse_accounts_file(account_file)
    print(f"[*] 解析到 {len(accounts)} 个账号")
    print(f"[*] VirtualBrowser API 地址: {args.vb_url}")
    print(f"[*] 统一代理设置: {args.proxy or '(直连)'}")
    print("=" * 70)

    vb = VirtualBrowserManager(args.vb_url)
    p_host, p_port = ("", "")
    if args.proxy and ":" in args.proxy:
        p_host, p_port = args.proxy.split(":", 1)

    screenshot_dir = Path(args.screenshot_dir) if args.screenshot_dir else None

    results = []
    for idx, acc in enumerate(accounts, start=args.start_index):
        w_name = f"{args.prefix}-{idx:02d}"
        print(f"\n>>>>> [{idx}/{len(accounts) + args.start_index - 1}] 处理账号: {acc.email} -> {w_name} <<<<<")

        try:
            # 1. 确保环境存在
            wid = vb.ensure_worker(
                name=w_name,
                email=acc.email,
                proxy_host=p_host,
                proxy_port=p_port,
            )
            print(f"  -> VirtualBrowser 环境 ID: {wid}")

            # 2. 启动浏览器
            port = vb.launch_browser(wid)
            print(f"  -> 浏览器已启动，调试端口: {port}")
            await asyncio.sleep(2)

            # 3. 执行自动化登录
            success = await perform_chatgpt_login(
                port=port,
                account=acc,
                worker_id=wid,
                screenshot_dir=screenshot_dir,
            )
            results.append({"name": w_name, "id": wid, "email": acc.email, "success": success})
        except Exception as e:
            print(f"  [!] 绑定失败: {e}")
            results.append({"name": w_name, "id": "-", "email": acc.email, "success": False, "error": str(e)})
        finally:
            if "wid" in locals():
                vb.stop_browser(wid)
                await asyncio.sleep(2)

    # 汇总
    print("\n" + "=" * 70)
    print("【批量账号绑定结果汇总】")
    print("=" * 70)
    print(f"{'序号':<6} | {'环境名称':<18} | {'VB ID':<6} | {'账号邮箱':<32} | {'状态'}")
    print("-" * 70)
    for i, r in enumerate(results, 1):
        st = "成功已固化" if r["success"] else "失败"
        print(f"{i:<6} | {r['name']:<18} | {r.get('id', '-'):<6} | {r['email']:<32} | {st}")
    print("=" * 70)

    # 同步至 FPBrowser2API
    if args.sync_fpb:
        sync_to_fpbrowser2api(
            fpb_url=args.fpb_url,
            space_pk=args.space_pk,
            task_type_id=args.task_type_id,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="ChatGPT 自动化多账号绑定与持久化登录工具")
    parser.add_argument("-f", "--file", type=str, default="scripts/accounts.example.txt", help="账号发货文本文件路径")
    parser.add_argument("-p", "--prefix", type=str, default="ChatGPT-Worker", help="环境名称前缀 (默认: ChatGPT-Worker)")
    parser.add_argument("--start-index", type=int, default=1, help="命名起始序号 (默认: 1)")
    parser.add_argument("--vb-url", type=str, default="http://127.0.0.1:9000", help="VirtualBrowser API 地址")
    parser.add_argument("--proxy", type=str, default="127.0.0.1:7890", help="代理配置 host:port (留空为直连)")
    parser.add_argument("--screenshot-dir", type=str, default="scratch/bind_screenshots", help="验证截图保存目录")
    parser.add_argument("--sync-fpb", action="store_true", help="是否自动同步至 FPBrowser2API 任务调度池")
    parser.add_argument("--fpb-url", type=str, default="http://127.0.0.1:8000", help="FPBrowser2API 地址")
    parser.add_argument("--space-pk", type=int, default=5, help="FPBrowser2API 空间主键 (默认: 5)")
    parser.add_argument("--task-type-id", type=int, default=6, help="GPT 任务类型 ID (默认: 6)")

    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
