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
        cur = await conn.execute("SELECT id, prompt, result_json, image_path, created_at FROM tasks WHERE status='completed'")
        completed_tasks = {str(r["id"]): dict(r) for r in await cur.fetchall()}

    registered_count = 0
    for f in sorted(files, key=lambda x: x.stat().st_mtime):
        filename = f.name
        # Skip small test dummy files if needed, or register real generated images
        if f.stat().st_size < 100 and "test" in filename:
            continue

        local_url = f"/static/generated_images/{filename}"
        base_name = f.stem

        # Try to find corresponding task
        matched_task = None
        for tid, t in completed_tasks.items():
            if tid in filename or (t.get("image_path") and filename in str(t["image_path"])):
                matched_task = t
                break
            # Check if filename is in result_json
            rj = str(t.get("result_json") or "")
            if filename in rj:
                matched_task = t
                break

        provider = "gpt"
        prompt = ""
        task_id = None
        if matched_task:
            task_id = str(matched_task["id"])
            prompt = matched_task.get("prompt") or ""
            if "dreamina" in str(matched_task.get("result_json") or ""):
                provider = "dreamina"

        name = f"生图_{task_id or base_name[:12]}"
        if prompt:
            name = prompt[:24]

        meta = {
            "filename": filename,
            "source": "local_generated_images",
            "prompt": prompt,
        }

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
