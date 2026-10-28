import json
import sqlite3
import os
from pathlib import Path

worker_ports = {
    '2': 40001,
    '3': 40001,
    '4': 40002,
    '5': 40002,
    '6': 40003,
    '7': 40003,
    '8': 40004,
    '9': 40004,
    '10': 40005,
    '11': 40005
}

vdat_path = Path(r"C:\Users\mojj\AppData\Local\VirtualBrowser\User Data\virtual.dat")
with open(vdat_path, "r", encoding="utf-8") as f:
    master_v = json.load(f)

users = master_v.get("users", [])
for u in users:
    str_id = str(u.get("id")).strip()
    if str_id in worker_ports:
        port = worker_ports[str_id]
        name = u.get("name")
        u["proxy"] = {
            "mode": 1,
            "value": f"127.0.0.1:{port}",
            "protocol": "SOCKS5",
            "host": "127.0.0.1",
            "port": str(port),
            "user": "",
            "pass": "",
            "API": ""
        }
        print(f"Updated Master virtual.dat: id={str_id} ({name}) -> 127.0.0.1:{port}")

# Save master virtual.dat
with open(vdat_path, "w", encoding="utf-8") as f:
    json.dump(master_v, f, ensure_ascii=False, indent=2)

# Sync worker virtual.dat
workers_dir = Path(r"C:\Users\mojj\AppData\Local\VirtualBrowser\User Data\workers")
for wid, port in worker_ports.items():
    wdir = workers_dir / wid
    if wdir.exists():
        wv = wdir / "virtual.dat"
        with open(wv, "w", encoding="utf-8") as f:
            json.dump(master_v, f, ensure_ascii=False, indent=2)
        print(f"Synced worker {wid} virtual.dat")

# Update fpbrowser.db
db_path = r"D:\code\github\fpbrowser2api\data\fpbrowser.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()
for wid, port in worker_ports.items():
    cur.execute("UPDATE windows SET proxy_addr = ? WHERE window_key = ?", (f"127.0.0.1:{port}", wid))
conn.commit()
conn.close()
print("Successfully updated fpbrowser.db windows proxy_addr!")
