# ChatGPT 对话流式安全边界与格式优化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 VirtualBrowser 对话接口构建完备的安全边界（解决 `error decoding response body` 与重试风暴），并自动将 ChatGPT Canvas 私有 `<CodeBlock>` 协议转换为标准 Markdown 代码块。

**Architecture:** 
1. 在文本清洗层增加专用转换器，将 ChatGPT Web 端专有的 `<CodeBlock language="..." editable>` 映射为通用 Markdown ````lang ... ````。
2. 在流式 API (`StreamingResponse`) 中引入安全异常隔离层，拦截下游一切 `HTTPException` / 超时，优雅输出 SSE 规范的失败与终止帧，杜绝 TCP reset。
3. 增加 SSE 注释心跳机制（5s 空闲定时推送 `:\n\n`），防止代理/客户端空闲断连。
4. 优化对话超时与快速失败策略，避免双端重试滚雪球。

**Tech Stack:** Python 3.10+, FastAPI, Starlette StreamingResponse, pytest, asyncio.

**Spec:** 用户反馈问题（9分钟累积重试、`error decoding response body`、`<CodeBlock language="html" editable>` 标签外露排版混乱）。

## Global Constraints
- 严格遵循 `ponytail` 原则：最少文件、最少代码、拒绝过度抽象。
- 绝不破坏现有生图 (`gpt-image-2` / `gpt_workflow`) 逻辑。
- 保持与 OpenAI Responses API 及 Chat Completions 协议 100% 规范兼容。

## Review Focus
1. 包含多个 `<CodeBlock>` 或混合代码与文字时，转换不能误伤普通 HTML 或已有的 Markdown 代码块。
2. 流式传输中途底层发生 504 超时时，不能直接向外抛 HTTPException，必须输出合法的 `response.failed` 与 `[DONE]` 并正常 200 完结。
3. ChatGPT 网页在长达 30 秒的“深度思考”无增量输出期间，心跳包必须定期推送且不能破坏前端 JSON 解析。
4. 异常发生时，已注册的内存队列 `unregister_task_chunk_queue` 必须得到释放，避免内存泄漏。

---

### Task 1: ChatGPT Canvas `<CodeBlock>` 专有标签转标准 Markdown

**Files:**
- Modify: `src/api/routes.py:396-410`
- Modify: `src/services/gpt_chat_executor.py:130-144`
- Test: `tests/test_codeblock_transform.py`

**Interfaces:**
- Produces: `_convert_codeblocks_to_markdown(text: str) -> str`
- 规则：
  - `<CodeBlock language="(\w+)"[^>]*>\s*` -> ````$1\n````
  - `\s*</CodeBlock>` -> ````\n```\n````

- [ ] **Step 1: 编写单元测试**
  测试包含 `<CodeBlock language="html" editable>` 的输入能够正确转换为 ````html ... ````。

- [ ] **Step 2: 运行测试验证失败**
  `pytest tests/test_codeblock_transform.py`

- [ ] **Step 3: 实现 `_convert_codeblocks_to_markdown` 并集成至文本清洗链路**
  在 `routes.py` 和 `gpt_chat_executor.py` 中应用。

- [ ] **Step 4: 运行测试验证通过**
  `pytest tests/test_codeblock_transform.py`

---

### Task 2: 流式异常安全隔离层（SSE Exception Guard）与优雅收尾

**Files:**
- Modify: `src/api/routes.py:1156-1212`
- Test: `tests/test_stream_safety_guard.py`

**Interfaces:**
- Consumes: `_wait_for_task_final(task_id, timeout_sec=90.0)`
- 行为：
  在 `real_stream_generator` 中将等待与事件生成包裹在完整的 `try...except Exception as exc:` 中。
  当捕获到 `HTTPException(504)` 或底层错误时：
  1. 记录错误日志，不再向上抛出。
  2. 依次 yield:
     - `event: response.failed\ndata: {"type":"response.failed", ...}\n\n`
     - `data: {"error":{"message":"..."}}\n\n`
     - `event: response.completed\ndata: {"type":"response.completed", ...}\n\n`
     - `data: [DONE]\n\n`
  3. 客户端平滑读取到错误并关闭连接，不再报 `error decoding response body`，彻底打断重试风暴。

- [ ] **Step 1: 编写单元测试模拟流式中断**
  测试当 `waiter_task` 抛出 HTTPException 时，生成器依然能产生合法 SSE 错误事件且正常退出。

- [ ] **Step 2: 运行测试验证**

- [ ] **Step 3: 在 `routes.py` 的 `real_stream_generator` 中实现异常防御与事件转换**

- [ ] **Step 4: 运行测试验证通过**

---

### Task 3: 长连接空闲心跳保活（SSE Keep-alive ping）

**Files:**
- Modify: `src/api/routes.py:1170-1185`
- Test: `tests/test_stream_heartbeat.py`

**Interfaces:**
- 行为：
  在增量轮询循环 `while not waiter_task.done() ...` 中：
  记录 `last_yield_time = time.monotonic()`。
  若超过 4.0 秒没有新 chunk，则 yield `:\n\n`（SSE 标准注释心跳包，客户端忽略且不计入文本，但刷新 TCP 传输活跃度）。

- [ ] **Step 1: 编写单元测试**
  测试空闲 5 秒能捕获到 `:\n\n` 心跳包。

- [ ] **Step 2: 在 `real_stream_generator` 中加入心跳逻辑**

- [ ] **Step 3: 运行测试验证通过**

---

### Task 4: 整体端到端回归验证与服务热重载

**Files:**
- System: 重启 `task-8492`（fpbrowser2api 服务）
- Manual Test: 在 CC Switch 或 curl 端点中复测带有代码/SVG 的请求，确认排版格式完全正常，无报错重连。

- [ ] **Step 1: 运行所有相关自动化测试**
  `pytest tests/test_codeblock_transform.py tests/test_stream_safety_guard.py tests/test_stream_heartbeat.py`

- [ ] **Step 2: 重启后台服务 `fpbrowser2api`**

- [ ] **Step 3: 验证端点正常响应**
