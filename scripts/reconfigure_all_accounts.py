import json
import sqlite3
import base64
import sys
import paramiko
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

TXT_PATH = Path(r"d:\Personal\Downloads\FF261019842540 - 副本.txt")
LOCAL_DB = Path(r"D:\code\github\fpbrowser2api\data\fpbrowser.db")

VPS_HOST = "192.129.200.213"
VPS_PORT = 22
VPS_USER = "root"
VPS_PASS = "p6L02UcboJiaK6RQ39"

def decode_jwt_payload(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) >= 2:
            p = parts[1]
            p += "=" * ((4 - len(p) % 4) % 4)
            return json.loads(base64.urlsafe_b64decode(p))
    except Exception:
        pass
    return {}

def parse_accounts():
    with open(TXT_PATH, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    accounts = []
    for i, line in enumerate(lines[:10]):
        parts = line.split("----")
        email = parts[0].strip()
        pwd = parts[1].strip()
        client_id = parts[2].strip()
        rt = parts[3].strip()
        at = parts[4].strip()
        payload = decode_jwt_payload(at)
        user_id = payload.get("https://api.openai.com/auth", {}).get("user_id") or payload.get("sub") or ""
        accounts.append({
            "index": i + 1,
            "worker_name": f"ChatGPT-Worker-{i+1:02d}",
            "email": email,
            "pwd": pwd,
            "ms_client_id": client_id,
            "ms_rt": rt,
            "at": at,
            "user_id": user_id
        })
    return accounts

def update_local_db(accounts):
    print(">>> [1/2] 更新本地 fpbrowser.db ...")
    conn = sqlite3.connect(LOCAL_DB)
    c = conn.cursor()
    for acc in accounts:
        idx = acc["index"]
        window_pk = idx + 1 # window_key 2..11 maps to window_pk 2..11
        pa_id = idx        # platform_accounts id 1..10
        
        # 1. Update platform_accounts
        c.execute("""
            UPDATE platform_accounts 
            SET platform_username = ?, platform_password = ?, platform_remarks = ?, updated_at = datetime('now','localtime')
            WHERE id = ?
        """, (acc["email"], acc["pwd"], f"{acc['ms_client_id']}----{acc['ms_rt']}", pa_id))
        
        # 2. Update task_type_windows (task_type_id = 6 is ChatGPT/Sora)
        c.execute("""
            UPDATE task_type_windows 
            SET sora_access_token = ?, total_errors = 0, consecutive_errors = 0, enabled = 1, updated_at = datetime('now','localtime')
            WHERE window_pk = ? AND task_type_id = 6
        """, (acc["at"], window_pk))
        
        # Also ensure windows table has updated account name
        c.execute("""
            UPDATE windows SET window_name = ? WHERE id = ?
        """, (acc["worker_name"], window_pk))
        
    conn.commit()
    conn.close()
    print("  [✓] 本地 fpbrowser.db 10 个账号更新完毕！")

def update_remote_sub2api(accounts):
    print(">>> [2/2] 更新远程 Sub2API (PostgreSQL) ...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(VPS_HOST, port=VPS_PORT, username=VPS_USER, password=VPS_PASS)
    
    # Build SQL script
    sql_lines = []
    # Proxy IDs: 1..5 map to 16..20, 6..10 map to 16..20
    proxy_map = {1: 16, 2: 17, 3: 18, 4: 19, 5: 20, 6: 16, 7: 17, 8: 18, 9: 19, 10: 20}
    
    for acc in accounts:
        idx = acc["index"]
        pid = proxy_map[idx]
        creds = json.dumps({
            "access_token": acc["at"],
            "refresh_token": acc["ms_rt"],
            "email": acc["email"],
            "client_id": "app_EMoamEEZ73f0CkXaXp7hrann",
            "account_id": acc["user_id"]
        })
        extra = json.dumps({
            "email": acc["email"],
            "import_source": "batch_file",
            "imported_at": "2026-10-19T23:35:00Z"
        })
        
        # Update accounts table
        sql_lines.append(f"""
            UPDATE accounts 
            SET name = '{acc["worker_name"]}',
                credentials = '{creds.replace("'", "''")}'::jsonb,
                extra = '{extra.replace("'", "''")}'::jsonb,
                proxy_id = {pid},
                status = 'active',
                schedulable = true,
                error_message = '',
                rate_multiplier = 1.0,
                updated_at = now()
            WHERE id = {idx};
        """)
        
        # Ensure account_groups binding
        sql_lines.append(f"""
            INSERT INTO account_groups (account_id, group_id, priority, created_at, updated_at)
            VALUES ({idx}, 3, 0, now(), now())
            ON CONFLICT (account_id, group_id) DO NOTHING;
        """)

    full_sql = "\n".join(sql_lines)
    sftp = ssh.open_sftp()
    with sftp.open("/tmp/update_10_accounts.sql", "w") as f:
        f.write(full_sql)
    sftp.close()
    
    cmd = "docker exec -i 1Panel-postgresql-UlLX psql -U sub2api -d sub2api < /tmp/update_10_accounts.sql"
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='ignore')
    err = stderr.read().decode('utf-8', errors='ignore')
    print("  [PSQL OUT]:", out.strip().replace("\n", " "))
    if err.strip():
        print("  [PSQL ERR]:", err.strip())
        
    # Verify in DB
    verify_cmd = "docker exec 1Panel-postgresql-UlLX psql -U sub2api -d sub2api -c 'SELECT id, name, proxy_id, status, schedulable, substr(credentials->>\"access_token\", 1, 25) as at_prefix FROM accounts WHERE id BETWEEN 1 AND 10 ORDER BY id;'"
    stdin, stdout, stderr = ssh.exec_command(verify_cmd)
    print("\n--- 远程 Sub2API 账号最新状态 ---")
    print(stdout.read().decode('utf-8', errors='ignore'))
    
    ssh.close()
    print("  [✓] 远程 Sub2API 10 个账号更新完毕！")

if __name__ == "__main__":
    accs = parse_accounts()
    print(f"成功解析 {len(accs)} 个账号")
    update_local_db(accs)
    update_remote_sub2api(accs)
