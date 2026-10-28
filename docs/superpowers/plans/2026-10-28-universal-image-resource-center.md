# 通用图片资产中心 (Universal Image Resource Center) 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `admin/image-resources` 从“即梦单一专属表”重构升级为“全局自适应图片资产中心”，统一接管所有平台（ChatGPT、即梦、Veo 及未来任意新模型）的生成图、角色图与参考图，实现新平台接入零代码改动自适应展示。

**Architecture:** 
1. 建立通用的 `image_assets` 数据表，核心由标准字段（`url`, `provider`, `category`, `task_id`）与动态载荷 `meta_json` 组成，完全解耦各平台的特有参数；
2. 历史数据与现有本地 `data/generated_images/` 资产自动兼容迁移落库；
3. 在任务完成与本地文件上传处建立统一的资产注册钩子（`register_image_asset`）；
4. 后端提供动态聚合过滤器接口 `GET /api/admin/image-resources/filters`，前端据此自适应渲染过滤胶囊与相册卡片流，消除任何硬编码。

**Tech Stack:** Python (FastAPI, SQLite, aiosqlite), Vanilla JavaScript (ES Module, Bootstrap 5).

**Spec:** `docs/superpowers/plans/2026-10-28-universal-image-resource-center.md`

## Global Constraints

- 严禁引入任何新的第三方重量级依赖，保持轻量与高效（符合 Ponytail 原则）。
- 严格保证向下兼容：原本依赖 `dreamina_subject_images` 的即梦人物一致性引用逻辑保持完全正常运作。
- 保证所有未来新增模型（如 Midjourney、Flux、可灵）只需在存图时传入动态 `provider` 和 `meta_json`，图库页面无需修改任何前端代码即可自适应显示。
- 列表支持分页（默认 30 条/页），采用卡片画廊相册布局，图片加载失败时显示友好占位符。

## Review Focus

1. **历史数据迁移平滑度**：迁移现有 `dreamina_subject_images` 与已下载的 `data/generated_images/*.png` 时，不能丢弃已有元数据或重复插入。
2. **`meta_json` 动态渲染鲁棒性**：前端解析任意复杂 JSON 时，必须安全容错，不能因字段缺失或格式异常导致页面卡死。
3. **删除操作安全性**：删除资产记录时，需校验是否属于本地可写目录，防止任意路径删除风险。
4. **长文本提示词截断与展示**：超长提示词（prompt）在相册卡片上限制 2 行省略号展示，在详情弹窗中支持完整展开查看。
5. **并发访问与分页效率**：`image_assets` 表在 `provider`, `category`, `task_id`, `created_at` 上建立索引，保证大量资产下毫秒级响应。

---

### Task 1: 建立通用资产数据表与迁移层

**Files:**
- Modify: `src/core/database.py:70-130, 6600-6680`
- Create: `tests/test_image_assets_db.py`

**Interfaces:**
- Consumes: `aiosqlite` connection from `Database._write_conn` and `_read_conn`
- Produces: 
  - `Database.create_image_asset(provider, category, name, url, task_id, width, height, size_bytes, mime, meta_json)`
  - `Database.list_image_assets(provider, category, q, limit, offset) -> (total, items)`
  - `Database.get_image_asset_filters() -> dict`
  - `Database.delete_image_asset(asset_id) -> bool`

- [ ] **Step 1: Write failing test for image_assets database operations**

```python
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
    assert found["meta_json"]["model"] == "gpt-image-2"

    # 3. Dynamic filters
    filters = await db.get_image_asset_filters()
    assert "gpt" in [f["name"] for f in filters.get("providers", [])]

    # 4. Delete asset
    ok = await db.delete_image_asset(asset_id)
    assert ok is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_image_assets_db.py -v`
Expected: FAIL with `AttributeError: 'Database' object has no attribute 'create_image_asset'`

- [ ] **Step 3: Implement `image_assets` table and DB methods in `src/core/database.py`**

In `src/core/database.py`:
- In `init_db()` and `check_and_migrate_db()`, create table:
  ```sql
  CREATE TABLE IF NOT EXISTS image_assets (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      task_id TEXT,
      provider TEXT NOT NULL DEFAULT 'unknown',
      category TEXT NOT NULL DEFAULT 'generated',
      name TEXT NOT NULL,
      url TEXT NOT NULL,
      width INTEGER DEFAULT 0,
      height INTEGER DEFAULT 0,
      size_bytes INTEGER DEFAULT 0,
      mime TEXT,
      meta_json TEXT,
      created_at TIMESTAMP DEFAULT (datetime('now','localtime')),
      updated_at TIMESTAMP DEFAULT (datetime('now','localtime'))
  );
  CREATE INDEX IF NOT EXISTS idx_image_assets_provider ON image_assets(provider);
  CREATE INDEX IF NOT EXISTS idx_image_assets_category ON image_assets(category);
  CREATE INDEX IF NOT EXISTS idx_image_assets_task_id ON image_assets(task_id);
  ```
- Implement `create_image_asset`, `list_image_assets`, `get_image_asset_filters`, `delete_image_asset`.
- In `check_and_migrate_db()`, check existing local images in `data/generated_images/` and completed tasks with `image_path`, auto-registering them into `image_assets` if not exists.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_image_assets_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/database.py tests/test_image_assets_db.py
git commit -m "feat(db): add universal image_assets schema, migration and queries"
```

---

### Task 2: 通用资产收集与自动登记

**Files:**
- Modify: `src/api/routes.py:1260-1320`
- Modify: `src/services/task_service.py:2160-2180`
- Create: `tests/test_asset_auto_register.py`

**Interfaces:**
- Consumes: `Database.create_image_asset` from Task 1
- Produces: Automatic creation of `image_assets` rows on task finish and file upload

- [ ] **Step 1: Write failing test for asset auto-registration**

```python
import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app
from src.core.database import Database

@pytest.mark.asyncio
async def test_upload_auto_registers_in_image_assets():
    transport = ASGITransport(app=app)
    db = Database()
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/internal/assets/upload", json={
            "data_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            "task_id": "auto_reg_test_task",
            "prefix": "gpt_workflow/image"
        })
        assert resp.status_code == 200
        total, items = await db.list_image_assets(provider="gpt", limit=10)
        found = next((x for x in items if x["task_id"] == "auto_reg_test_task"), None)
        assert found is not None
        assert found["url"].startswith("/static/generated_images/")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_asset_auto_register.py -v`
Expected: FAIL because `found is None` (upload didn't register into `image_assets`)

- [ ] **Step 3: Hook asset registration into `upload_internal_asset` and `task_service`**

- In `src/api/routes.py` `upload_internal_asset`:
  Call `await db.create_image_asset(provider="gpt", category="generated", name=f"GPT生图_{task_id_clean}", url=local_url, task_id=task_id_clean, size_bytes=len(raw_bytes), mime=mime_type, meta_json={"source": "extension_upload"})`.
- In `src/services/task_service.py` at task completion (line ~2170):
  If result contains images (e.g. `result.urls` or `image_path`), ensure asset is registered with provider derived from `picked.create_task_handler` (e.g. `gpt`, `dreamina`, `veo`).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_asset_auto_register.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/routes.py src/services/task_service.py tests/test_asset_auto_register.py
git commit -m "feat: auto-register image assets on task completion and asset upload"
```

---

### Task 3: 后端统一资产管理 API

**Files:**
- Modify: `src/api/admin.py:7044-7085`
- Create: `tests/test_admin_image_resources_api.py`

**Interfaces:**
- Consumes: `image_assets` methods from Task 1
- Produces: 
  - `GET /api/admin/image-resources` (with `provider`, `category`, `q`, `limit`, `offset`)
  - `GET /api/admin/image-resources/filters`
  - `DELETE /api/admin/image-resources/{id}`
  - `POST /api/admin/image-resources/upload`

- [ ] **Step 1: Write failing test for admin image resources API**

```python
import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app

@pytest.mark.asyncio
async def test_admin_image_resources_endpoints():
    transport = ASGITransport(app=app)
    # simulate admin login or token
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Fetch filters
        resp = await client.get("/api/admin/image-resources/filters")
        assert resp.status_code == 200
        data = resp.json()
        assert "providers" in data
        assert "categories" in data

        # 2. List resources
        list_resp = await client.get("/api/admin/image-resources?limit=20")
        assert list_resp.status_code == 200
        assert "items" in list_resp.json()
        assert "total" in list_resp.json()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_admin_image_resources_api.py -v`
Expected: FAIL with 404 on `/api/admin/image-resources/filters`

- [ ] **Step 3: Implement admin endpoints in `src/api/admin.py`**

- In `src/api/admin.py`:
  - Update `list_image_resources`: query `image_assets` instead of hardcoded `dreamina_subject_images`.
  - Add `get_image_resource_filters`: return distinct providers and categories with count.
  - Add `delete_image_resource`: delete asset by id.
  - Add `upload_image_resource`: handle multipart upload for manual asset import.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_admin_image_resources_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/admin.py tests/test_admin_image_resources_api.py
git commit -m "feat(api): upgrade /api/admin/image-resources to universal asset endpoints"
```

---

### Task 4: 前端自适应图库重构 (`static/image_resources.html`)

**Files:**
- Modify: `static/image_resources.html`

**Interfaces:**
- Consumes: `/api/admin/image-resources` and `/api/admin/image-resources/filters`
- Produces: Modern, responsive Gallery Card UI with dynamic filter pills and detail modal

- [ ] **Step 1: Re-architect `static/image_resources.html` UI layout**

- Replace the raw Dreamina table with:
  1. **Top Bar**: Search input (`q`), "上传素材" button, "刷新" button.
  2. **Dynamic Filter Bar**:
     - 来源平台胶囊（动态从 `/filters` 接口生成）：`[全部] [ChatGPT (5)] [即梦 (2)] ...`
     - 资产类型胶囊：`[全部] [生成成果] [角色/参考]`
  3. **Gallery Card Grid**:
     - Responsive grid (col-12 col-sm-6 col-md-4 col-lg-3 col-xl-2).
     - Card contains: image with lazy loading, provider badge (e.g. `<span class="badge bg-primary">ChatGPT</span>`), title/prompt snippet, dimensions/size, and hover actions.
     - Hover actions: Quick View (Modal), Open in New Tab, Download, Delete.
  4. **Detail & Metadata Modal**:
     - High-res image preview on left/top.
     - Metadata key-value list on right/bottom: Model, Dimensions, Task ID, Creation Time, and all custom `meta_json` fields formatted.
  5. **Upload Modal**: Simple dropzone/file input to upload a local picture into the asset library.

- [ ] **Step 2: Implement dynamic rendering and filter logic in JavaScript**

- On page load, fetch `/api/admin/image-resources/filters` and render filter pills dynamically.
- Support clicking any provider/category pill to filter without full page reload.
- Handle pagination (prev/next page, page counter).
- Bind image click to open detail modal.

- [ ] **Step 3: Browser visual verification**

- Open `http://127.0.0.1:8000/admin/image-resources`.
- Verify previously recovered GPT images (and any existing Dreamina assets) appear in cards.
- Test filtering by `ChatGPT` / `即梦`.
- Test opening detail modal and downloading.

- [ ] **Step 4: Commit**

```bash
git add static/image_resources.html
git commit -m "feat(ui): redesign admin/image-resources into universal gallery with dynamic filters"
```

---

### Task 5: 历史图片一键迁移与端到端联调

- [ ] **Step 1: Run one-off sync script to ensure all existing `data/generated_images/*.png` and `tasks.image_path` are registered in `image_assets`**
- [ ] **Step 2: Restart `fpbrowser2api` and verify clean server logs**
- [ ] **Step 3: In `admin/test` submit a new `gpt_workflow` task, verify the generated picture appears immediately in `admin/image-resources`**
- [ ] **Step 4: Run all unit and API tests**
- [ ] **Step 5: Final review and commit**
