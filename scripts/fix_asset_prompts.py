import asyncio
import json
import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DB_PATH = Path(r"D:\code\github\fpbrowser2api\data\fpbrowser.db")

def fix():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Build index of all tasks
    cur = conn.execute("SELECT id, task_id, prompt, image_path, result_json, created_at FROM tasks")
    all_tasks = cur.fetchall()

    by_task_id = {}
    by_image_filename = {}
    for t in all_tasks:
        tid = str(t["task_id"] or "").strip()
        if tid:
            by_task_id[tid] = t
        ipath = str(t["image_path"] or "").strip()
        if ipath:
            fname = Path(ipath).name
            by_image_filename[fname] = t

    # Query all assets
    cur = conn.execute("SELECT id, url, name, meta_json, task_id FROM image_assets")
    assets = cur.fetchall()

    print(f"Checking {len(assets)} image assets...")
    fixed_count = 0
    for a in assets:
        aid = a["id"]
        url = a["url"]
        filename = Path(url).name

        # Exact match
        matched = by_image_filename.get(filename)
        if not matched:
            stem_clean = Path(filename).stem.split("_")[0]
            matched = by_task_id.get(stem_clean) or by_task_id.get(Path(filename).stem)

        if matched:
            real_task_id = matched["task_id"]
            p_raw = matched["prompt"] or ""
            actual_prompt = ""
            model = ""
            try:
                p_obj = json.loads(p_raw)
                actual_prompt = p_obj.get("prompt") or p_obj.get("text") or p_raw
                model = p_obj.get("model", "")
            except Exception:
                actual_prompt = p_raw

            new_name = actual_prompt[:35] if actual_prompt else f"生图_{real_task_id[:8]}"
            
            # Update meta_json
            meta = {}
            if a["meta_json"]:
                try:
                    meta = json.loads(a["meta_json"])
                except Exception:
                    pass
            meta["prompt"] = actual_prompt
            meta["filename"] = filename
            if model:
                meta["model"] = model
            meta["matched_task_pk"] = matched["id"]
            meta["task_id"] = real_task_id

            meta_str = json.dumps(meta, ensure_ascii=False)

            conn.execute(
                "UPDATE image_assets SET name = ?, task_id = ?, meta_json = ? WHERE id = ?",
                (new_name, real_task_id, meta_str, aid)
            )
            fixed_count += 1
            print(f"✓ Fixed Asset #{aid} ({filename}):")
            print(f"   Name: {new_name}")
            print(f"   Task ID: {real_task_id}")
            print(f"   Prompt: {actual_prompt[:60]}...")

    conn.commit()
    conn.close()
    print(f"\nDone! Successfully fixed {fixed_count} assets.")


if __name__ == "__main__":
    fix()
