import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from src.core.database import Database

@pytest.mark.asyncio
async def test_image_assets_crud():
    db = Database()
    await db.init_db()

    # 1. Create asset
    asset_id = await db.create_image_asset(
        provider="gpt",
        category="generated",
        name="测试中国美女",
        url="/static/generated_images/test_1.png",
        task_id="task_test_999",
        width=1024,
        height=1024,
        meta_json={"model": "gpt-image-2", "ratio": "1:1"}
    )
    assert asset_id > 0

    # 2. List assets
    total, items = await db.list_image_assets(provider="gpt", limit=10, offset=0)
    assert total >= 1
    found = next((x for x in items if x["id"] == asset_id), None)
    assert found is not None
    assert found["name"] == "测试中国美女"
    assert isinstance(found["meta_json"], dict)
    assert found["meta_json"]["model"] == "gpt-image-2"

    # 3. Dynamic filters
    filters = await db.get_image_asset_filters()
    assert "providers" in filters
    assert "categories" in filters
    provider_names = [p["name"] for p in filters["providers"]]
    assert "gpt" in provider_names

    # 4. Search query
    t_search, s_items = await db.list_image_assets(q="中国美女", limit=10)
    assert t_search >= 1
    assert any(x["id"] == asset_id for x in s_items)

    # 5. Delete asset
    ok = await db.delete_image_asset(asset_id)
    assert ok is True
    
    # 6. Verify deleted
    total_after, items_after = await db.list_image_assets(limit=100)
    assert not any(x["id"] == asset_id for x in items_after)
