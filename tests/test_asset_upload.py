import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app

@pytest.mark.asyncio
async def test_internal_asset_upload_and_serve():
    test_data_url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/internal/assets/upload", json={
            "data_url": test_data_url,
            "task_id": "test_task_123",
            "prefix": "gpt_workflow/image"
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "url" in data
        assert data["url"].startswith("/static/generated_images/")
        assert data["mime"] == "image/png"
        
        # Verify static file serving
        get_resp = await client.get(data["url"])
        assert get_resp.status_code == 200
        assert "image/png" in get_resp.headers.get("content-type", "")
        assert len(get_resp.content) > 0


def test_r2_config_fallback_to_local():
    from src.services.gpt_task_executor import _gpt_extension_r2_upload_config
    cfg = _gpt_extension_r2_upload_config({"gpt_image2_model": "gpt-image2-1k"})
    assert cfg["enabled"] is True
    assert cfg["provider"] in ("cloudflare_r2", "local_backend")
    if cfg["provider"] == "local_backend":
        assert "/api/internal/assets/upload" in cfg["endpoint"]
        assert "/static/generated_images" in cfg["public_base_url"]
