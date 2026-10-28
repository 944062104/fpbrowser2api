import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.main import app
from src.core.database import Database
from src.services.task_service import TaskService


@pytest.mark.asyncio
async def test_upload_auto_registers_in_image_assets():
    transport = ASGITransport(app=app)
    db = Database()
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/internal/assets/upload",
            json={
                "data_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                "task_id": "auto_reg_test_task_001",
                "prefix": "gpt_workflow/image",
            },
        )
        assert resp.status_code == 200
        total, items = await db.list_image_assets(provider="gpt", limit=10)
        found = next((x for x in items if x.get("task_id") == "auto_reg_test_task_001"), None)
        assert found is not None
        assert found["url"].startswith("/static/generated_images/")
        assert found["provider"] == "gpt"


@pytest.mark.asyncio
async def test_task_service_registers_image_asset():
    db = Database()
    ts = TaskService(db)

    fake_picked = MagicMock()
    fake_picked.create_task_handler = "gpt_workflow"

    task_id = "test_task_completion_002"
    result = {
        "status": "completed",
        "urls": ["/static/generated_images/test_gen_002.png"],
    }

    await ts._maybe_register_task_image_assets(
        task_id=task_id,
        picked=fake_picked,
        result=result,
        payload={"prompt": "A cat in space"},
    )

    total, items = await db.list_image_assets(provider="gpt", limit=10)
    found = next((x for x in items if x.get("task_id") == task_id), None)
    assert found is not None
    assert found["url"] == "/static/generated_images/test_gen_002.png"
    assert found["provider"] == "gpt"
