# 方案二：代码生成与对话模块化重构实施计划 (Code Completion Modular Refactor)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 VirtualBrowser ChatGPT Web 代理全面重构为轻量解耦、专为代码补全/生成与对话设计的纯流式服务，彻底清理不可行的 Tool Calling 仿真与拦截延迟代码，按职责分层模块化。

**Architecture:** 
1. 建立独立请求解构与适配层 (`src/services/chat_adapter.py`)，统一规范解析并清洗 OpenAI Chat Completions 与 Responses API 的复杂入参（`messages`、`input`、`instructions`），剥离多余的本地环境仿真污染。
2. 彻底精简路由层 (`src/api/routes.py`)，移除所有复杂脆弱的工具标记匹配、流式块拦截缓冲与伪造 Tool Call 逻辑，恢复高吞吐、零延迟的双通道（Chat Completion + Responses API）SSE 实时直出。
3. 强化执行器 (`src/services/gpt_chat_executor.py`) 的防沙箱指令与 Markdown 代码块规范，严格禁止模型调用 Web 内置 Python 代码解释器生成虚假 `sandbox:/mnt/data/` 下载链接，确保完整代码内联输出。

**Tech Stack:** Python 3.12+, FastAPI, Uvicorn, asyncio, Pytest

**Spec:** 方案二：纯代码补全与生成架构设计，基于未绑手机号池的高可用重构规范。

## Global Constraints
- 遵循 YAGNI 与 Ponytail 原则：杜绝臆造的多余抽象，彻底清理已验证不可行的代码与测试。
- 保证对外接口与 OpenAI `/v1/chat/completions` 及 OpenAI Responses API 双向协议兼容。
- 保证流式响应 (SSE) 零等待缓冲，首字延迟 (TTFT) 直连浏览器扩展推送，严禁在后端做跨 chunk 正则截留等待。
- 严格禁止在回复中引导模型生成任何 `sandbox:/mnt/data/` 虚假下载链接。

## Review Focus
1. 复杂的嵌套 `input` 结构（如 Responses API 的 `[{type: "message", content: [{type: "input_text", text: "..."}]}]`）：需正确提取出用户实际 Prompt。
2. 含有超大历史消息的 `messages` 列表：需要提取合理的对话上下文与最新用户需求，避免超出浏览器网页版输入框负荷。
3. 流式 SSE 模式下网络抖动与完成通知：确保发送完毕时正常发送 `[DONE]` 与 `response.completed` 事件，不留悬挂连接。
4. 客户端传参带有 `tools` 字段时：静默忽略或在 Prompt 中规范降级为纯文本代码输出指引，不再尝试伪造终端仿真工具拦截。
5. 针对代码/HTML/脚本生成的请求：确保自动附加“输出完整 Markdown 代码块”引导，防止网页端触发 Python 数据分析沙箱。

---

### Task 1: 独立请求解构与消息适配模块 (`chat_adapter.py`)

**Files:**
- Create: `D:\code\github\fpbrowser2api\src\services\chat_adapter.py`
- Test: `D:\code\github\fpbrowser2api\tests\test_chat_adapter.py`

**Interfaces:**
- Consumes: `body: Dict[str, Any]` (来自 `/v1/chat/completions` 或 `/v1/responses` 的原始请求体)
- Produces: 
  - `extract_prompt_and_system(body: Dict[str, Any]) -> str`: 提取规范化后的纯文本 Prompt，包含上下文与指令。
  - `clean_chat_reply(text: str) -> str`: 清洗 Unicode 引用标记、PUA 乱码，并将 Canvas/Artifacts `<CodeBlock>` 规范化转换为 Markdown ` ``` `。
  - `build_completion_payload(model: str, content: str, task_id: str, conversation_id: str = "") -> Dict[str, Any]`: 构建标准非流式响应。

- [ ] **Step 1: 编写失败的单元测试**

在 `tests/test_chat_adapter.py` 中编写测试：
```python
import pytest
from src.services.chat_adapter import (
    extract_prompt_and_system,
    clean_chat_reply,
    build_completion_payload,
)

def test_extract_from_chat_completions_messages():
    body = {
        "messages": [
            {"role": "system", "content": "You are a coding assistant."},
            {"role": "user", "content": "Write a python fibonacci function."}
        ]
    }
    prompt = extract_prompt_and_system(body)
    assert "[System]: You are a coding assistant." in prompt
    assert "[User]: Write a python fibonacci function." in prompt

def test_extract_from_responses_api_input():
    body = {
        "instructions": "Be concise.",
        "input": [
            {
                "type": "message",
                "content": [{"type": "input_text", "text": "Create an HTML button"}]
            }
        ]
    }
    prompt = extract_prompt_and_system(body)
    assert "[System Instructions]: Be concise." in prompt
    assert "Create an HTML button" in prompt

def test_clean_chat_reply_codeblock_and_pua():
    raw = 'Here is code:\ue200cite\ue201\n<CodeBlock language="python">\nprint("hello")\n</CodeBlock>'
    cleaned = clean_chat_reply(raw)
    assert "cite" not in cleaned
    assert '```python\nprint("hello")\n```' in cleaned

def test_build_completion_payload():
    resp = build_completion_payload("gpt-4o", "print(1)", "task-123", "conv-456")
    assert resp["model"] == "gpt-4o"
    assert resp["choices"][0]["message"]["content"] == "print(1)"
    assert resp["conversation_id"] == "conv-456"
```

- [ ] **Step 2: 运行测试验证失败**

运行: `pytest tests/test_chat_adapter.py -v`
预期: FAIL with `ModuleNotFoundError: No module named 'src.services.chat_adapter'`

- [ ] **Step 3: 实现 `chat_adapter.py`**

在 `src/services/chat_adapter.py` 中实现：
- `extract_prompt_and_system(body: Dict[str, Any]) -> str`
- `clean_chat_reply(text: str) -> str`
- `build_completion_payload(model: str, content: str, task_id: str, conversation_id: str = "") -> Dict[str, Any]`

- [ ] **Step 4: 运行测试验证通过**

运行: `pytest tests/test_chat_adapter.py -v`
预期: PASS

- [ ] **Step 5: 提交更改**

```bash
git add src/services/chat_adapter.py tests/test_chat_adapter.py
git commit -m "feat: add modular chat_adapter for prompt extraction and clean response building"
```

---

### Task 2: 清理路由层中的工具拦截与延迟缓冲代码 (`src/api/routes.py`)

**Files:**
- Modify: `D:\code\github\fpbrowser2api\src\api\routes.py`
- Test: `D:\code\github\fpbrowser2api\tests\test_stream_safety_guard.py`

**Interfaces:**
- Consumes: `src.services.chat_adapter` 中的 `extract_prompt_and_system`, `clean_chat_reply`, `build_completion_payload`
- Produces: 极简且高吞吐的 `/v1/chat/completions` 与 `/v1/responses` 路由处理，移除所有 `_format_tools_prompt`、`_parse_tool_call_from_text`、`tool_marker_regex` 拦截缓冲。

- [ ] **Step 1: 编写端到端纯流式路由单元测试**

在 `tests/test_stream_safety_guard.py` 中更新或添加对纯流式直出协议的断言，确保 chunk 一旦到达即刻产出 `choices[0].delta` 与 `response.output_text.delta`，无任何拦截或延迟。

- [ ] **Step 2: 运行测试观察现状**

运行: `pytest tests/test_stream_safety_guard.py -v`

- [ ] **Step 3: 重构 `src/api/routes.py`**

1. 导入 `chat_adapter` 中的函数：
   ```python
   from ..services.chat_adapter import (
       extract_prompt_and_system,
       clean_chat_reply,
       build_completion_payload,
   )
   ```
2. 删除 `_format_tools_prompt`、`_parse_tool_call_from_text` 等无用黑魔法函数。
3. 在 `chat_completions` 路由中：
   - 使用 `prompt = extract_prompt_and_system(body)` 替代原先冗长混乱的 80 行提取代码。
   - 彻底删除 `real_stream_generator()` 中的 `tool_marker_regex`、`tool_call_detected` 延迟缓冲逻辑。
   - 恢复最快直接推送：收到 `delta` 立即输出 `chat.completion.chunk` 和 `response.output_text.delta`。
   - 非流式直接调用 `build_completion_payload(...)`。

- [ ] **Step 4: 运行相关测试验证通过**

运行: `pytest tests/test_stream_safety_guard.py -v`
预期: PASS

- [ ] **Step 5: 提交更改**

```bash
git add src/api/routes.py tests/test_stream_safety_guard.py
git commit -m "refactor: simplify routes.py, remove tool call emulation and streaming buffer delays"
```

---

### Task 3: 执行器防沙箱与代码块输出强化 (`src/services/gpt_chat_executor.py`)

**Files:**
- Modify: `D:\code\github\fpbrowser2api\src\services\gpt_chat_executor.py`
- Test: `D:\code\github\fpbrowser2api\tests\test_gpt_chat_executor.py`

**Interfaces:**
- Consumes: `payload: Dict[str, Any]`
- Produces: 注入清晰的纯代码块规范提示词，杜绝触发 ChatGPT 网页端的 Python Interpreter / Sandbox。

- [ ] **Step 1: 编写针对执行器提示词优化的测试**

在 `tests/test_gpt_chat_executor.py` 中断言：
- 当用户要求编写 HTML/Python/代码/文件时，提示词中不会包含任何伪造的终端工具指令；
- 提示词中明确包含“直接输出 markdown 对应语言代码块，严禁调用内置 Python 沙箱或返回 sandbox:/ 链接”。

- [ ] **Step 2: 运行测试验证失败**

运行: `pytest tests/test_gpt_chat_executor.py -v`

- [ ] **Step 3: 修改 `gpt_chat_executor.py`**

1. 移除 `gpt_chat_executor.py` 中旧的 `has_tools` 与 `exec_command` 相关提示词逻辑。
2. 统一代码生成引导逻辑：
   ```python
   code_triggers = ("svg", "html", "css", "js", "javascript", "python", "script", "代码", "文件", "file", "code", "写一个", "实现")
   if any(k in lp for k in code_triggers) and "严禁在后台沙箱创建虚拟文件" not in prompt:
       prompt = f"{prompt}\n\n【输出规范】：请直接在回复正文中以标准 Markdown 对应语言代码块形式输出完整代码。严禁调用你内置的 Python 数据分析代码解释器或沙箱环境，严禁生成任何 sandbox:/ 虚假下载链接！"
   ```
3. 移除重复的 `_clean_chat_text`，直接引用 `chat_adapter.clean_chat_reply`。

- [ ] **Step 4: 运行测试验证通过**

运行: `pytest tests/test_gpt_chat_executor.py -v`
预期: PASS

- [ ] **Step 5: 提交更改**

```bash
git add src/services/gpt_chat_executor.py tests/test_gpt_chat_executor.py
git commit -m "refactor: enforce direct markdown codeblocks and ban sandbox in gpt_chat_executor"
```

---

### Task 4: 清理无用废弃测试与死代码

**Files:**
- Delete: `D:\code\github\fpbrowser2api\tests\test_tool_prompt_injection.py`
- Delete: `D:\code\github\fpbrowser2api\tests\test_stream_tool_calling_synthesis.py`
- Delete: `D:\code\github\fpbrowser2api\tests\test_codex_tool_calling_e2e.py`

**Interfaces:**
- 移除与仿真拦截相关的废弃测试，保持测试套件整洁绿灯。

- [ ] **Step 1: 删除不再需要的仿真测试文件**

删除废弃的 3 个仿真工具调用测试文件。

- [ ] **Step 2: 运行全量测试套件确保全部通过**

运行: `pytest tests/ -v`
预期: 所有活跃测试全部通过（PASS）。

- [ ] **Step 3: 提交更改**

```bash
git add tests/
git commit -m "chore: remove deprecated tool calling simulation test files"
```

---

### Task 5: 重启服务并进行真实代码生成联调验证

**Files:**
- Test: 真实请求 `POST /v1/chat/completions` (stream=True) 生成一个完整 HTML 网页，验证首字延迟 (TTFT)、Markdown 代码块完整性与无白屏。

- [ ] **Step 1: 重启 `fpbrowser2api` 服务**

重启正在运行的 task-9741 后台服务，确保加载最新的模块化代码。

- [ ] **Step 2: 发送流式代码生成请求进行测试**

发送请求："写一个精美的具有渐变背景和点击涟漪效果的 HTML 按钮代码"。
验证：
1. 立即收到 SSE 首字（首字延迟 < 3 秒）。
2. 全文输出为标准的 ````html ... ```` 代码块。
3. 无任何 `<escape>`、`<tool_call>` 乱码，也无 `sandbox:/mnt/data/` 虚假链接。
4. 客户端能够即时渲染并完整显示。

- [ ] **Step 3: 归档记录**

在实施记录中确认方案二重构完成并稳定运行。
