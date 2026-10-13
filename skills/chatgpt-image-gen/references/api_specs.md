# ChatGPT 生图接口与规格规范 (API Specs)

本规范整理了 FPBrowser2API 与 VirtualBrowser 联动实现 ChatGPT 图像生成的核心接口定义与数据结构。

---

## 1. 任务创建接口：`POST /v1/videos`

兼容 NewAPI 异步视频/图片任务通道标准，直接适配主流 AI 聚合网关。

### 请求头
- `Authorization`: `Bearer <API_KEY>` (默认: `mirrmart_sora2_880315`)
- `Content-Type`: `application/json`

### 请求体 (JSON)
| 参数名 | 类型 | 是否必需 | 说明 |
|---|---|---|---|
| `model` | string | 是 | 填写 `gpt-image2-1k` / `gpt-image2-2k` / `gpt-image2-4k` |
| `prompt` | string | 是 | 生图提示词（建议使用优化后的结构化防反问 Prompt） |
| `aspect_ratio` | string | 否 | 画幅比例：`16:9`、`1:1`、`9:16`、`4:3`、`3:4`（默认 `16:9`） |
| `duration` | int | 否 | 图像任务传 `1` 或省略 |

### 响应示例
```json
{
  "id": "646a2d661241444da427e9e1d2efc926",
  "task_id": "646a2d661241444da427e9e1d2efc926",
  "object": "video",
  "status": "queued",
  "progress": 0,
  "model": "gpt-image2-1k",
  "aspect_ratio": "16:9"
}
```

---

## 2. 任务状态查询接口：`GET /v1/tasks/{task_id}`

### 请求头
- `Authorization`: `Bearer <API_KEY>`

### 响应体 (JSON)
```json
{
  "task_id": "646a2d661241444da427e9e1d2efc926",
  "status": "completed",
  "progress": 100,
  "result": {
    "type": "gpt_workflow_image",
    "workflow_kind": "image",
    "conversation_id": "6acea3c7-...",
    "urls": [
      "https://chatgpt.com/backend-api/estuary/content?id=file_...&sig=..."
    ],
    "image_url": "https://chatgpt.com/backend-api/estuary/content?id=file_...&sig=...",
    "model": "gpt-image2-1k",
    "resolution": "1k",
    "aspect_ratio": "16:9",
    "size": "1344x768"
  },
  "error_message": null
}
```

---

## 3. 分辨率与画幅映射对照表

| 规格代码 | 比例 `1:1` | 比例 `16:9` | 比例 `9:16` | 比例 `4:3` | 比例 `3:4` |
|---|---|---|---|---|---|
| `gpt-image2-1k` | 1024×1024 | 1344×768 | 768×1344 | 1152×864 | 864×1152 |
| `gpt-image2-2k` | 1248×1248 | 1664×928 | 928×1664 | 1440×1088 | 1088×1440 |
| `gpt-image2-4k` | 2480×2480 | 3312×1872 | 1872×3312 | 2880×2160 | 2160×2880 |
