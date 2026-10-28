import asyncio
import json
import os
import re
import sys
from pathlib import Path

# Add project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.core.database import Database
from src.core.paths import GENERATED_IMAGES_DIR


async def sync():
    db = Database()
    print("Connecting to database...")

    # 1. First, scan dreamina_subject_images if exists
    async with db._read_conn() as conn:
        try:
            cur = await conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dreamina_subject_images'")
            if await cur.fetchone():
                cur = await conn.execute("SELECT id, uid, subject_id, data_id, name, image_uri, width, height, created_at FROM dreamina_subject_images")
                rows = await cur.fetchall()
                print(f"Found {len(rows)} legacy dreamina subject images.")
                for r in rows:
                    uri = r[5]
                    await db.create_image_asset(
                        provider="dreamina",
                        category="subject",
                        name=r[4] or f"即梦角色_{r[2]}",
                        url=uri,
                        width=r[6] or 0,
                        height=r[7] or 0,
                        meta_json={"uid": r[1], "subject_id": r[2], "data_id": r[3], "source": "dreamina_subject_images"},
                    )
        except Exception as e:
            print(f"Sync dreamina_subject_images skipped: {e}")

    # 2. Match generated image files with tasks
    files = list(GENERATED_IMAGES_DIR.glob("*.*"))
    print(f"Found {len(files)} files in generated_images directory.")

    async with db._read_conn() as conn:
        conn.row_factory = __import__("aiosqlite").Row
        cur = await conn.execute("SELECT id, task_id, prompt, result_json, image_path, created_at FROM tasks")
        all_tasks = [dict(r) for r in await cur.fetchall()]

    by_task_id = {}
    by_image_filename = {}
    for t in all_tasks:
        tid = str(t.get("task_id") or "").strip()
        if tid:
            by_task_id[tid] = t
        ipath = str(t.get("image_path") or "").strip()
        if ipath:
            fname = Path(ipath).name
            by_image_filename[fname] = t

    registered_count = 0
    for f in sorted(files, key=lambda x: x.stat().st_mtime):
        filename = f.name
        # Skip small test dummy files if needed
        if f.stat().st_size < 100 and "test" in filename:
            continue

        local_url = f"/static/generated_images/{filename}"

        # Match candidate 1: exact image_path filename
        matched_task = by_image_filename.get(filename)
        # Match candidate 2: exact task_id (or stem before _)
        if not matched_task:
            stem_clean = f.stem.split("_")[0]
            matched_task = by_task_id.get(stem_clean) or by_task_id.get(f.stem)

        provider = "gpt"
        prompt = ""
        task_id = None
        model = ""
        if matched_task:
            task_id = str(matched_task.get("task_id") or matched_task.get("id"))
            p_raw = matched_task.get("prompt") or ""
            try:
                p_obj = json.loads(p_raw)
                prompt = p_obj.get("prompt") or p_obj.get("text") or p_raw
                model = p_obj.get("model", "")
            except Exception:
                prompt = p_raw

            if "dreamina" in str(matched_task.get("result_json") or ""):
                provider = "dreamina"

        name = prompt[:35] if prompt else f"生图_{task_id or f.stem[:12]}"

        meta = {
            "filename": filename,
            "source": "local_generated_images",
            "prompt": prompt,
        }
        if model:
            meta["model"] = model

        aid = await db.create_image_asset(
            provider=provider,
            category="generated",
            name=name,
            url=local_url,
            task_id=task_id,
            size_bytes=f.stat().st_size,
            mime="image/png" if f.suffix == ".png" else "image/jpeg",
            meta_json=meta,
        )
        if aid:
            registered_count += 1
            print(f"Registered asset #{aid}: {name} ({local_url}) -> {provider}")

    # 3. Check filters
    filters = await db.get_image_asset_filters()
    print("\n--- Current Image Asset Summary ---")
    print(f"Total: {filters.get('total')}")
    print(f"Providers: {filters.get('providers')}")
    print(f"Categories: {filters.get('categories')}")


if __name__ == "__main__":
    asyncio.run(sync())
