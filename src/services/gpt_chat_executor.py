"""GPT/ChatGPT 纯对话专属执行器 (Chat Executor)。

与生图 (Image/Video) 执行器彻底解耦：
- 仅处理纯文本对话、多轮会话以及后续的实时 SSE Token 增量推送
- 杜绝引入图片尺寸、参考图上传、生图重试轮询或生视频逻辑
- 针对代码生成强化 Markdown 代码块输出指引，严禁触发 Web 内置沙箱下载链接
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, Optional

from .browser_extension_interaction import submit_extension_task
from .chat_adapter import clean_chat_reply, extract_prompt_and_system
from .gpt_task_executor import (
    DEFAULT_GPT_TARGET,
    _gpt_target_url,
    ensure_extension_connected_via_window,
)
from .task_executor_types import ProgressCB
from .veo_workflow_executor import get_or_create_veo_session

logger = logging.getLogger("fpbrowser2api")


def _safe_trim(s: Any, max_len: int = 100) -> str:
    raw = str(s or "")
    return raw[:max_len] + ("..." if len(raw) > max_len else "")


_clean_chat_text = clean_chat_reply


def _prepare_chat_prompt(payload: Dict[str, Any]) -> str:
    """提取规范化 Prompt 并针对代码生成注入防沙箱规范指引。"""
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        prompt = extract_prompt_and_system(payload)
    if not prompt:
        return ""

    lp = prompt.lower()
    code_triggers = ("svg", "矢量", "html", "htm", "css", "javascript", "python", "script", "代码", "文件", "file", "code", "写一个", "实现")
    if any(k in lp for k in code_triggers) and "严禁在后台沙箱创建虚拟文件" not in prompt and "严禁生成任何 sandbox:" not in prompt:
        prompt = (
            f"{prompt}\n\n"
            "【输出规范】：请直接在回复正文中以标准 Markdown 对应语言代码块形式输出完整代码。"
            "严禁调用你内置的 Python 数据分析代码解释器或沙箱环境，严禁生成任何 sandbox:/ 虚假下载链接！"
        )
    return prompt


async def gpt_chat_workflow(
    payload: Dict[str, Any],
    progress_cb: ProgressCB,
    *,
    browser_vendor: str,
    browser_base_url: str,
    browser_access_key: Optional[str] = None,
    space_id: Optional[str] = None,
    window_key: Optional[str] = None,
    default_target_url: Optional[str] = None,
    target_url: Optional[str] = None,
    access_token: Optional[str] = None,
    access_expires: Optional[str] = None,
    task_id: Optional[str] = None,
    window_pk: Optional[int] = None,
) -> Dict[str, Any]:
    """专属 ChatGPT 对话工作流执行器。"""
    prompt = _prepare_chat_prompt(payload)
    if not prompt:
        raise ValueError("prompt 不能为空")

    target = _gpt_target_url(payload.get("target_url") or default_target_url or target_url or DEFAULT_GPT_TARGET)
    sess = get_or_create_veo_session(
        vendor=browser_vendor,
        base_url=browser_base_url,
        access_key=browser_access_key,
        space_id=space_id,
        window_key=window_key,
    )

    await progress_cb(2, {"stage": "init", "workflow_kind": "chat", "prompt": _safe_trim(prompt, 100)})

    # 确保扩展连接并处于活跃状态
    await ensure_extension_connected_via_window(
        sess=sess,
        target_url=target,
        space_id=space_id,
        window_key=window_key,
        wait_seconds=float(payload.get("connect_timeout") or 10.0),
    )

    ext_payload = {
        "action": "submit_task",
        "workflow_kind": "chat",
        "target_url": target,
        "prompt": prompt,
        "model": payload.get("model") or "auto",
        "web_model": payload.get("web_model") or "auto",
        "conversation_id": payload.get("conversation_id"),
        "task_id": task_id,
    }

    await progress_cb(10, {"stage": "generating", "workflow_kind": "chat"})

    max_wait = float(payload.get("max_wait_seconds") or 180.0)
    chunk_cb = payload.get("chunk_cb")
    result = await submit_extension_task(
        space_id=space_id,
        window_key=window_key,
        provider="gpt",
        payload=ext_payload,
        progress_cb=progress_cb,
        chunk_cb=chunk_cb,
        timeout_seconds=max_wait,
    )

    # 规范化清洗输出格式
    raw_text = str((result or {}).get("text") or (result or {}).get("content") or "").strip()
    text = clean_chat_reply(raw_text)
    cid = str((result or {}).get("conversation_id") or "")
    msg_id = str((result or {}).get("message_id") or "")

    await progress_cb(100, {"stage": "completed", "workflow_kind": "chat"})
    return {
        "workflow_kind": "chat",
        "text": text,
        "content": text,
        "conversation_id": cid,
        "message_id": msg_id,
        "raw": result,
    }
