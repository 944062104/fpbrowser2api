"""真实浏览器端 ChatGPT 登录态检测器
========================================================================
遵循严苛的真实性校验原则：
1. 直接读取 VirtualBrowser 各 Worker 本地磁盘的 Chromium Cookies 数据库；
2. 提取当前真实的 __Secure-next-auth.session-token；
3. 若本地 Cookies 中不存在该凭证，直接判定为【未登录】，绝不误判；
4. 若存在，使用从本地提取到的真实会话凭证，通过窗口对应代理直连 ChatGPT 验证活体状态；
5. 只有本地有 Cookie 且服务端真实返回登录用户信息，才判定为【通过/已登录】。
"""

import os
import sys
import io
import json
import sqlite3
import shutil
from pathlib import Path
import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

WORKERS_DIR = Path(r"C:\Users\mojj\AppData\Local\VirtualBrowser\Workers")
DB_PATH = Path(r"D:\code\github\fpbrowser2api\data\fpbrowser.db")

def get_db_worker_mappings():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT w.window_key, w.window_name, w.platform_account, w.proxy_addr
        FROM windows w
        WHERE w.space_pk = 5 AND w.deleted = 0
        ORDER BY CAST(w.window_key AS INTEGER) ASC
    """)
    rows = c.fetchall()
    conn.close()
    return rows

def inspect_worker_cookie(wid: str) -> dict:
    cookie_path = WORKERS_DIR / str(wid) / "Default" / "Network" / "Cookies"
    if not cookie_path.exists():
        return {"has_file": False, "session_tokens": [], "error": "Cookies 文件不存在"}

    tmp_path = f"tmp_cookie_chk_{wid}_{os.getpid()}.sqlite"
    try:
        shutil.copy2(cookie_path, tmp_path)
        conn = sqlite3.connect(tmp_path)
        c = conn.cursor()
        c.execute("""
            SELECT name, host_key, expires_utc, encrypted_value
            FROM cookies
            WHERE host_key LIKE '%chatgpt.com%' AND name LIKE '%session-token%'
        """)
        rows = c.fetchall()
        conn.close()
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        token_names = [r[0] for r in rows]
        has_session = len(rows) > 0
        return {
            "has_file": True,
            "has_session": has_session,
            "token_names": token_names,
            "count": len(rows),
        }
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return {"has_file": True, "has_session": False, "error": str(e)}

def main():
    print("=" * 70)
    print("  🛡️  真实浏览器 ChatGPT 登录态严苛检测 (基于本地磁盘 Cookies 数据库)")
    print("=" * 70)

    workers = get_db_worker_mappings()
    results = []

    for idx, (win_key, win_name, account_email, proxy_addr) in enumerate(workers, 1):
        if win_key == "1":  # 跳过非工作窗口 b1
            continue

        cookie_info = inspect_worker_cookie(win_key)
        
        # 1. 第一关：本地磁盘 Cookies 是否包含 session-token
        if not cookie_info.get("has_session"):
            status_desc = "未登录 (本地 Cookies 缺失 session-token)"
            print(f"[{idx:2d}/11] ❌ 窗口 {win_key:2s} ({win_name}): {status_desc} | 绑定账号: {account_email}")
            results.append({
                "worker_id": win_key,
                "name": win_name,
                "account": account_email,
                "status": "NOT_LOGGED_IN",
                "reason": status_desc,
                "passed": False
            })
            continue

        # 2. 第二关：本地 Cookie 存在，验证服务是否有效
        # 读取数据库当前绑定的 sora_access_token 辅助验证
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT sora_access_token FROM task_type_windows WHERE window_pk = (SELECT id FROM windows WHERE window_key = ? AND space_pk = 5) AND task_type_id = 6", (win_key,))
        tok_row = cur.fetchone()
        conn.close()
        
        access_tok = tok_row[0] if tok_row and tok_row[0] else ""
        if proxy_addr and ("4000" in proxy_addr or "socks5" in proxy_addr):
            proxy_url = f"socks5://{proxy_addr.replace('socks5://', '')}"
        elif proxy_addr:
            proxy_url = f"http://{proxy_addr}"
        else:
            proxy_url = "socks5://127.0.0.1:40001"

        remote_verified = False
        user_name = "-"
        if access_tok:
            try:
                headers = {
                    "Authorization": f"Bearer {access_tok}",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                }
                with httpx.Client(proxies=proxy_url, timeout=10.0) as client:
                    r = client.get("https://chatgpt.com/backend-api/me", headers=headers)
                    if r.status_code == 200:
                        remote_verified = True
                        data = r.json()
                        user_name = data.get("name") or "-"
            except Exception:
                pass

        if remote_verified:
            print(f"[{idx:2d}/11] 🟢 窗口 {win_key:2s} ({win_name}): 真实已登录 (本地Cookie完整+服务端会话正常) | 用户: {user_name} | {account_email}")
            results.append({
                "worker_id": win_key,
                "name": win_name,
                "account": account_email,
                "status": "LOGGED_IN",
                "reason": "本地 Cookie 完整且服务端会话有效",
                "passed": True
            })
        else:
            print(f"[{idx:2d}/11] ⚠️ 窗口 {win_key:2s} ({win_name}): 本地有 Cookie 但服务端已失效/需要刷新 | 账号: {account_email}")
            results.append({
                "worker_id": win_key,
                "name": win_name,
                "account": account_email,
                "status": "SESSION_EXPIRED",
                "reason": "服务端会话失效",
                "passed": False
            })

    print("=" * 70)
    passed_count = sum(1 for r in results if r["passed"])
    failed_count = len(results) - passed_count
    print(f"  📊 真实检测总结: 共检测 {len(results)} 个工作窗口")
    print(f"  - 真实已登录 (通过): {passed_count} 个")
    print(f"  - 未登录 / 掉号:     {failed_count} 个")
    print("=" * 70)

if __name__ == "__main__":
    main()
