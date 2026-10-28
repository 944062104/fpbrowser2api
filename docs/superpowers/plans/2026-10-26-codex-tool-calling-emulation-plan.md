# Codex 本地文件工具调用 (Tool Calling) 协议映射改造计划 (已全部完成)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让免费指纹浏览器池全面兼容 Codex 的 Tool Calling 协议，使 Codex 能在本地目录真正自动创建、修改和读取物理文件。

**Architecture:** 
1. 请求侧：在 `/v1/responses` 与 `/v1/chat/completions` 中解析客户端的 `tools` 定义，并动态合成为 Tool Calling 协议 Prompt 注入给执行器。
2. 响应侧：在流式生成器 `real_stream_generator` 中构建 Tool Parser 状态机。一旦捕获到模型输出的工具调用块，将其转换为标准的 Responses API `function_call` 事件流。
3. 防撞车机制：强力显式压制 ChatGPT 云端 Python 沙盒惯性，避免其触发官方数据分析限额。

**Tech Stack:** Python 3.10+, FastAPI, SSE Event Framing, pytest.

---

### Task 1: Tools 入参解析与 Tool Calling Prompt 注入器
- [x] **Step 1: 编写单元测试** (`tests/test_tool_prompt_injection.py`)
- [x] **Step 2: 实现 `_format_tools_prompt` 解析并注入系统 Prompt**
- [x] **Step 3: 压制官方 Python 数据分析沙盒并约束 ````tool_call ```` 协议格式**
- [x] **Step 4: 运行测试验证通过 (3/3 passed)**

---

### Task 2: 流式响应中的 `tool_call` 拦截与 Responses API `function_call` 事件合成
- [x] **Step 1: 编写状态机单测** (`tests/test_stream_tool_calling_synthesis.py`)
- [x] **Step 2: 实现 `_parse_tool_call_from_text` 纯函数**
- [x] **Step 3: 流式合成 Responses API `response.output_item.added (function_call)` 与 `response.function_call_arguments.delta` 事件链**
- [x] **Step 4: 兼容标准 Chat Completions `tool_calls` delta 协议**
- [x] **Step 5: 运行测试验证通过 (3/3 passed)**

---

### Task 3: 端到端测试与服务热重载验证
- [x] **Step 1: 编写完整流程模拟测试** (`tests/test_codex_tool_calling_e2e.py`)
- [x] **Step 2: 运行全量 11 个测试验证全部 100% 通过**
- [x] **Step 3: 重启后台服务并验证 8 个指纹窗口秒级就绪**
