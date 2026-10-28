import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.core.database import Database


async def clean_names():
    db = Database()
    async with db._write_conn() as conn:
        conn.row_factory = __import__("aiosqlite").Row
        cur = await conn.execute("SELECT id, name, meta_json FROM image_assets")
        rows = await cur.fetchall()
        for r in rows:
            aid = r["id"]
            name = r["name"]
            meta_str = r["meta_json"]
            prompt = ""
            if meta_str:
                try:
                    meta = json.loads(meta_str)
                    raw_p = meta.get("prompt", "")
                    if raw_p.startswith("{") and raw_p.endswith("}"):
                        p_dict = json.loads(raw_p)
                        prompt = p_dict.get("prompt") or p_dict.get("text") or ""
                        meta["prompt"] = prompt
                        if p_dict.get("model"):
                            meta["model"] = p_dict["model"]
                        if p_dict.get("aspect_ratio"):
                            meta["aspect_ratio"] = p_dict["aspect_ratio"]
                    else:
                        prompt = raw_p
                except Exception:
                    pass

            if name.startswith("{") and name.endswith("}"):
                try:
                    p_dict = json.loads(name)
                    name = p_dict.get("prompt") or f"GPT生图_{aid}"
                except Exception:
                    name = f"GPT生图_{aid}"
            elif name.startswith("{"):
                if prompt:
                    name = prompt[:30]
                else:
                    name = f"GPT生图_{aid}"

            new_meta_str = json.dumps(meta, ensure_ascii=False) if meta_str else None
            await conn.execute("UPDATE image_assets SET name = ?, meta_json = ? WHERE id = ?", (name[:50], new_meta_str, aid))
        await conn.commit()
    print("Cleaned asset names and prompts successfully.")


if __name__ == "__main__":
    asyncio.run(clean_names())
