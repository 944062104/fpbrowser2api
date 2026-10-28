import sys
from pathlib import Path
import pytest
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.main import app
from src.core.database import Database
from src.core.paths import GENERATED_IMAGES_DIR
import src.api.admin as admin_module


@pytest.mark.asyncio
async def test_admin_image_resources_endpoints():
    db = Database()
    admin_module.db = db
    admin_module.active_admin_tokens["mock_token"] = "admin"

    async def _mock_page_access(token, page_key):
        return None

    admin_module._ensure_page_access = _mock_page_access

    # Create dummy local file on disk
    GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    dummy_file = GENERATED_IMAGES_DIR / "test_del_physical_001.png"
    dummy_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRdummydata")
    assert dummy_file.exists()

    # Insert test image asset pointing to the dummy file
    asset_id = await db.create_image_asset(
        provider="gpt",
        category="generated",
        name="测试图片001",
        url="/static/generated_images/test_del_physical_001.png",
        task_id="task_test_api_001",
        meta_json={"prompt": "A cute cat"},
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": "Bearer mock_token"}

        # 1. Fetch filters
        filter_resp = await client.get("/api/admin/image-resources/filters", headers=headers)
        assert filter_resp.status_code == 200
        filter_data = filter_resp.json()
        assert "providers" in filter_data
        assert "categories" in filter_data
        assert any(p["provider"] == "gpt" for p in filter_data["providers"])

        # 2. List resources with provider filter
        list_resp = await client.get("/api/admin/image-resources?provider=gpt&limit=20", headers=headers)
        assert list_resp.status_code == 200
        list_data = list_resp.json()
        assert list_data.get("success") is True
        assert list_data.get("total") >= 1
        items = list_data.get("items", [])
        assert any(x["id"] == asset_id for x in items)

        # 3. Delete resource (both DB and physical disk file)
        del_resp = await client.delete(f"/api/admin/image-resources/{asset_id}", headers=headers)
        assert del_resp.status_code == 200
        del_data = del_resp.json()
        assert del_data.get("success") is True
        assert del_data.get("deleted") is True
        assert del_data.get("file_deleted") is True
        assert not dummy_file.exists(), "Local disk file must be physically deleted"


@pytest.mark.asyncio
async def test_admin_image_resources_upload():
    db = Database()
    admin_module.db = db
    admin_module.active_admin_tokens["mock_token"] = "admin"

    async def _mock_page_access(token, page_key):
        return None

    admin_module._ensure_page_access = _mock_page_access

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": "Bearer mock_token"}
        files = {
            "file": ("test_upload.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRmockdata", "image/png"),
        }
        data = {
            "provider": "custom",
            "category": "manual",
            "name": "手动上传图片",
        }
        upload_resp = await client.post(
            "/api/admin/image-resources/upload",
            headers=headers,
            data=data,
            files=files,
        )
        assert upload_resp.status_code == 200
        res = upload_resp.json()
        assert res.get("success") is True
        assert res["item"]["provider"] == "custom"
        assert res["item"]["name"] == "手动上传图片"
        assert res["item"]["url"].startswith("/static/generated_images/")

        # Clean up uploaded file physically
        uploaded_id = res["item"]["id"]
        del_r = await client.delete(f"/api/admin/image-resources/{uploaded_id}", headers=headers)
        assert del_r.status_code == 200
        assert del_r.json().get("file_deleted") is True
