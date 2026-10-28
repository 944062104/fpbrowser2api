# GPT 生图结果本地持久化与前端图片预览改造计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 解决 ChatGPT 生图外链 403 防盗链与后台纯文本无图片渲染的问题，实现生图结果自动本地落盘托管并在任务列表与测试页中直观预览图片。

**Architecture:** 
1. 浏览器插件在任务完成时，利用指纹浏览器页面上下文通过 `pageDownloadAssetAsDataUrl` 截获图片数据；
2. 当系统未配置 Cloudflare R2 / OSS 时，自动降级为 `local_backend` 本地持久化模式，将图片上传至后端 `POST /api/internal/assets/upload` 保存于本地 `data/generated_images/`；
3. 后端静态挂载 `/static/generated_images` 并将本地访问 URL 回写至 `tasks.image_path` 与 `result_json`；
4. 前端 `static/tasks.html`（列表缩略图 + 弹窗大图预览）与 `static/test.html`（测试结果图片画廊）全面支持渲染图片。

**Tech Stack:** Python (FastAPI, SQLite, aiosqlite), Vanilla JavaScript (ES Module, Bootstrap 5), Chrome Extension Manifest V3.

**Spec:** `docs/superpowers/plans/2026-10-28-gpt-image-preview-and-caching.md`

## Global Constraints

- 严禁引入任何不必要的重量级第三方依赖，遵循 Ponytail 原则（轻量、复用已有模式、保持最小修改量）。
- 保持向后兼容：当配置了 Cloudflare R2 时，继续优先使用 R2 云存储；未配置时无缝透明降级为本地持久化。
- 本地静态资源统一保存在 `data/generated_images/`，通过 FastAPI 静态目录服务向前端暴露。
- 保证无鉴权环境（例如普通浏览器打开管理后台）可稳定加载已生成的图片，彻底消除 403 Forbidden。

## Review Focus

1. **未配置 R2/OSS 时的降级保护**：未填写 R2 配置时，必须透明回退到本地存储，不可抛出 R2 缺少凭据的错误。
2. **大图传输安全性**：本地上传接口需校验 base64 头部格式与大小限制（单图不超过 20MB），防止恶意请求导致内存溢出。
3. **并发写盘与同名覆盖防范**：图片文件名采用 `task_id_index_timestamp.png` 结构，确保全局唯一性。
4. **历史任务容错**：对于老旧任务 `result_json` 仍为已失效 `estuary/content` 链接的，前端应提供友好降级提示（例如“外链已失效”），不能破坏页面渲染或卡死。
5. **UI 性能与布局适配**：列表页缩略图限制 36x36 尺寸并采用 object-fit: cover，防止宽比例图片撑破表格排版。

---

### Task 1: 后端本地资源上传与静态托管接口

**Files:**
- Modify: `src/core/paths.py:40-52`
- Modify: `src/main.py:260-275`
- Modify: `src/api/routes.py:1200-1280`
- Create: `tests/test_asset_upload.py`

**Interfaces:**
- Consumes: `DATA_DIR` from `src.core.paths`, `Database` from `src.core.database`
- Produces: `POST /api/internal/assets/upload` endpoint returning `{"url": str, "file_path": str, "size": int}`

- [ ] **Step 1: Write the failing test for asset upload and static serve**

```python
import pytest
from httpx import AsyncClient
from src.main import app

@pytest.mark.asyncio
async def test_internal_asset_upload_and_serve():
    test_data_url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    async with AsyncClient(app=app, base_url="http://test") as client:
        resp = await client.post("/api/internal/assets/upload", json={
            "data_url": test_data_url,
            "task_id": "test_task_123",
            "prefix": "gpt_workflow/image"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "url" in data
        assert data["url"].startswith("/static/generated_images/")
        
        # Verify static file serving
        get_resp = await client.get(data["url"])
        assert get_resp.status_code == 200
        assert get_resp.headers["content-type"] == "image/png"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_asset_upload.py -v`
Expected: FAIL with 404 Not Found on `/api/internal/assets/upload`

- [ ] **Step 3: Define `GENERATED_IMAGES_DIR` and mount static path**

In `src/core/paths.py`:
- Add `GENERATED_IMAGES_DIR = DATA_DIR / "generated_images"`
- In `ensure_runtime_dirs()`, ensure `GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)`.

In `src/main.py`:
- Mount `/static/generated_images` pointing to `GENERATED_IMAGES_DIR`.

In `src/api/routes.py`:
- Implement `POST /api/internal/assets/upload` accepting `{ data_url: str, task_id: Optional[str], prefix: Optional[str] }`.
- Decode base64 bytes, write to `GENERATED_IMAGES_DIR`, and return local URL.
- If `task_id` is supplied and exists in `tasks`, update `tasks.image_path = local_url`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_asset_upload.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/paths.py src/main.py src/api/routes.py tests/test_asset_upload.py
git commit -m "feat: add local asset upload and static serve endpoints"
```

---

### Task 2: 浏览器插件本地转存与配置下发

**Files:**
- Modify: `src/services/gpt_task_executor.py:286-327`
- Modify: `browser_extension/providers/common.js:316-360`
- Modify: `browser_extension/providers/gpt_provider.js:1865-1885`

**Interfaces:**
- Consumes: `POST /api/internal/assets/upload` from Task 1
- Produces: `uploadDataUrlListToR2` handles `provider === "local_backend"`

- [ ] **Step 1: Write verification script for `_gpt_extension_r2_upload_config` fallback**

```python
def test_r2_config_fallback_to_local():
    from src.services.gpt_task_executor import _gpt_extension_r2_upload_config
    cfg = _gpt_extension_r2_upload_config({"gpt_image2_model": "gpt-image2-1k"})
    assert cfg["enabled"] is True
    assert cfg["provider"] in ("cloudflare_r2", "local_backend")
    if cfg["provider"] == "local_backend":
        assert "/api/internal/assets/upload" in cfg["endpoint"]
```

- [ ] **Step 2: Update `_gpt_extension_r2_upload_config` in `src/services/gpt_task_executor.py`**

- If `r2_cfg.enabled` is false or credentials are missing:
  - Generate a local fallback upload configuration:
    ```python
    return {
        "enabled": True,
        "provider": "local_backend",
        "endpoint": f"http://{extension_base_url}/api/internal/assets/upload",
        "public_base_url": f"http://{extension_base_url}/static/generated_images",
        "object_key_prefix": f"gpt_workflow/image/gpt-image-2/{resolution}",
        "required": False,
    }
    ```

- [ ] **Step 3: Update `browser_extension/providers/common.js` to handle `local_backend`**

In `uploadDataUrlListToR2`:
- Check `cfg.provider`:
  - If `cfg.provider === "local_backend"`:
    - Post `{ data_url: value, task_id: options.taskId, prefix: cfg.object_key_prefix }` to `cfg.endpoint`.
    - Retrieve returned `{ url }` and populate `out.push(res.url)`.
    - Record progress via `options.runtime.progress`.

- [ ] **Step 4: Verify in `browser_extension/providers/gpt_provider.js`**

- Ensure `runImage2Workflow` passes `p._bridge_task_id || p.task_id` into `uploadPageAccessibleAssetsToR2` so the backend can link the image to the task row immediately.

- [ ] **Step 5: Commit**

```bash
git add src/services/gpt_task_executor.py browser_extension/providers/common.js browser_extension/providers/gpt_provider.js
git commit -m "feat: enable extension local asset upload fallback when R2 is disabled"
```

---

### Task 3: 任务列表前端缩略图展示与结果大图弹窗

**Files:**
- Modify: `static/tasks.html:444-470, 715-748`

**Interfaces:**
- Consumes: Task data from `GET /api/admin/tasks`, local image URLs from Task 1/2
- Produces: Thumbnail in `媒体` column + rich image card in `resultModal`

- [ ] **Step 1: Add image helper functions in `static/tasks.html`**

```javascript
function extractImageUrlsFromItem(item) {
  const urls = [];
  if (item?.image_path && typeof item.image_path === "string") {
    urls.push(item.image_path.trim());
  }
  const rj = item?.result_json;
  if (rj) {
    try {
      const obj = typeof rj === "object" ? rj : JSON.parse(rj);
      if (obj.urls && Array.isArray(obj.urls)) urls.push(...obj.urls);
      if (obj.image_url) urls.push(obj.image_url);
      if (obj.result_urls && Array.isArray(obj.result_urls)) urls.push(...obj.result_urls);
    } catch (_) {}
  }
  return Array.from(new Set(urls.filter(Boolean)));
}
```

- [ ] **Step 2: Update table row rendering in `render()`**

In `render()` under `static/tasks.html`:
- For the `媒体` cell:
  - If `imgUrls.length > 0`:
    Render a 36x36 rounded thumbnail with `object-fit: cover`, clickable to open full-size preview, alongside the label badge.
  - If no image: keep the original badge (e.g. `对话` / `视频` / `图片`).

- [ ] **Step 3: Update `openResultModal(taskId)`**

- Look up task by `taskId`, extract all image URLs via `extractImageUrlsFromItem(item)`.
- If images exist:
  - Render an image preview card at the top of the modal with thumbnail/large view, direct download link, and open-in-new-tab button.
  - If the URL is an internal ChatGPT estuary URL (without local mirror), display an alert badge noting: "注意：该链接为 ChatGPT 临时凭证链接，如遇 403 建议刷新或右键保存".
- Render the syntax-formatted JSON in the `<pre>` below the image card.

- [ ] **Step 4: Manual browser verification**

- Open `http://127.0.0.1:8000/admin/tasks`.
- Inspect the task list table and verify:
  1. The table header and layout remain intact without breaking.
  2. Clicking "查看" in the `result` column opens the modal with the image preview if available.
  3. Clicking thumbnail opens full-size preview.

- [ ] **Step 5: Commit**

```bash
git add static/tasks.html
git commit -m "feat(ui): add image thumbnails and preview modal to admin tasks"
```

---

### Task 4: 测试页面前端渲染生图结果

**Files:**
- Modify: `static/test.html:130-140, 290-305`

**Interfaces:**
- Consumes: Task poll output from `GET /v1/tasks/{task_id}`
- Produces: Live image rendering in `#result` container on `test.html`

- [ ] **Step 1: Add image preview container to `static/test.html`**

In `static/test.html` right next to `<pre id="result">`:
- Add `<div id="resultImageGallery" class="d-flex flex-wrap gap-2 mt-2"></div>`.

- [ ] **Step 2: Update `renderTask(d)` in `static/test.html`**

```javascript
const galleryEl = document.getElementById("resultImageGallery");
if (galleryEl) {
  galleryEl.innerHTML = "";
  const resultObj = d?.result || {};
  const urls = [];
  if (resultObj.image_url) urls.push(resultObj.image_url);
  if (Array.isArray(resultObj.urls)) urls.push(...resultObj.urls);
  if (Array.isArray(resultObj.result_urls)) urls.push(...resultObj.result_urls);
  const uniqueUrls = Array.from(new Set(urls.filter(Boolean)));
  
  if (uniqueUrls.length > 0) {
    galleryEl.innerHTML = uniqueUrls.map(u => `
      <div class="border rounded p-1 bg-white shadow-sm" style="max-width: 320px;">
        <a href="${escapeHtml(u)}" target="_blank" rel="noreferrer">
          <img src="${escapeHtml(u)}" class="img-fluid rounded" style="max-height: 240px; object-fit: contain;" alt="Result Image" />
        </a>
        <div class="mt-1 d-flex justify-content-between align-items-center">
          <a href="${escapeHtml(u)}" target="_blank" class="btn btn-sm btn-outline-primary btn-compact">新窗口查看大图</a>
        </div>
      </div>
    `).join("");
  }
}
```

- [ ] **Step 3: Verify in browser**

- Open `http://127.0.0.1:8000/admin/test`.
- Query an existing completed image task ID (e.g. `cb94d9c259e04797af7bf123726929e1`).
- Verify the image gallery renders without breaking.

- [ ] **Step 4: Commit**

```bash
git add static/test.html
git commit -m "feat(ui): add image preview gallery to admin test page"
```

---

### Task 5: 全流程端到端联调与回归验证

- [ ] **Step 1: 重启并热载后端服务**
- [ ] **Step 2: 在 `admin/test` 发起一次新的 `gpt_workflow` 1K 生图任务**
- [ ] **Step 3: 观察任务执行日志与浏览器插件行为**
  - 确认插件成功下载生成的图片为 dataUrl；
  - 确认插件调用 `POST /api/internal/assets/upload` 将图片转存至本地 `data/generated_images/`；
  - 确认数据库任务返回的 `image_url` 指向本地静态链接 `/static/generated_images/...`。
- [ ] **Step 4: 在 `admin/tasks` 与 `admin/test` 验证直接显示图片，确认无 403 报错**
- [ ] **Step 5: 最终回归与代码提交**

```bash
git add .
git commit -m "chore: complete end-to-end gpt image preview and local caching"
```
