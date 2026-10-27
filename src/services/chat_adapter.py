"""Chat & Responses API 请求解构适配与响应标准化模块。

负责：
1. 规范化提取各种客户端格式（Chat Completions messages, Responses API input, instructions）为干净的纯文本 Prompt。
2. 剥离 ChatGPT 网页端私有 Unicode 标记与清洗 Canvas / Artifacts <CodeBlock> 为标准 Markdown。
3. 构建统一、符合 OpenAI 与 Responses 规范的结构化出参。
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional


def _extract_content_text(content: Any) -> str:
    """提取 message.content 或 input_item.content 中的纯文本内容。"""
    if not content:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item.strip())
            elif isinstance(item, dict):
                # 支持 {"type": "text", "text": "..."} 或 {"type": "input_text", "text": "..."}
                t = str(item.get("text") or item.get("input_text") or item.get("output") or "").strip()
                if t:
                    parts.append(t)
        return " ".join(parts).strip()
    return str(content).strip()


def extract_prompt_and_system(body: Dict[str, Any]) -> str:
    """从 OpenAI 兼容请求体中提取规范化的对话文本与系统指令。"""
    if not isinstance(body, dict):
        return ""

    prompt = ""
    messages = body.get("messages")
    conversation_id = str(body.get("conversation_id") or "").strip()

    # 1. 尝试从 messages 提取
    if isinstance(messages, list) and messages:
        if conversation_id:
            # 多轮延续模式：优先取最后一个 user 角色作为当轮输入
            for m in reversed(messages):
                if isinstance(m, dict) and str(m.get("role") or "").lower() == "user":
                    prompt = _extract_content_text(m.get("content") or m.get("output"))
                    if prompt:
                        break
        if not prompt:
            if len(messages) == 1 and str(messages[0].get("role") or "").lower() == "user":
                prompt = _extract_content_text(messages[0].get("content") or messages[0].get("output"))
            else:
                lines = []
                for m in messages:
                    if not isinstance(m, dict):
                        continue
                    role = str(m.get("role") or "user").capitalize()
                    c_text = _extract_content_text(m.get("content") or m.get("output"))
                    if c_text:
                        lines.append(f"[{role}]: {c_text}")
                prompt = "\n\n".join(lines).strip()

    # 2. 尝试从 input 提取 (OpenAI Responses API)
    elif body.get("input"):
        raw_in = body.get("input")
        if isinstance(raw_in, str):
            prompt = raw_in.strip()
        elif isinstance(raw_in, list):
            parts = []
            for item in raw_in:
                if isinstance(item, str):
                    parts.append(item.strip())
                elif isinstance(item, dict):
                    c = item.get("content")
                    if c:
                        t = _extract_content_text(c)
                        if t:
                            parts.append(t)
                    elif item.get("text"):
                        parts.append(str(item.get("text")).strip())
                    elif item.get("output"):
                        parts.append(str(item.get("output")).strip())
            prompt = "\n\n".join(parts).strip()

    # 3. 尝试从 prompt 提取
    elif body.get("prompt"):
        prompt = str(body.get("prompt")).strip()

    # 4. 附加 instructions (System Instructions)
    instructions = str(body.get("instructions") or "").strip()
    if instructions:
        prompt = f"[System Instructions]: {instructions}\n\n{prompt}" if prompt else instructions

    return prompt.strip()


def clean_chat_reply(text: str) -> str:
    """清理 ChatGPT 网页版私有标记与 Canvas 标签，转换为标准 Markdown。"""
    if not text:
        return ""

    # Strip ChatGPT private Unicode citation markers: \ue200cite...\ue201 or PUA blocks
    s = re.sub(r"[\ue200-\ue206][^\ue200-\ue206\n]*[\ue200-\ue206]?", "", text)
    # Strip orphaned turnXsearchY tokens
    s = re.sub(r"(?:turn\d+search\d+)+", "", s, flags=re.IGNORECASE)
    # Strip raw ■cite tokens
    s = re.sub(r"■cite[^\s\n]*", "", s)
    # Strip source citations like 【1†source】
    s = re.sub(r"【\d+†(?:source|来源)】", "", s)
    # Strip any remaining Private Use Area characters
    s = re.sub(r"[\ue000-\uf8ff]", "", s)

    # Convert ChatGPT Canvas / Artifacts <CodeBlock language="xxx" ...> to standard markdown ```xxx
    def _repl_codeblock_open(m: re.Match) -> str:
        lang = (m.group(1) or "").strip()
        return f"```{lang}\n" if lang else "```\n"

    s = re.sub(r'<CodeBlock(?:\s+language="([^"]*)")?[^>]*>\s*', _repl_codeblock_open, s, flags=re.IGNORECASE)
    s = re.sub(r'\s*</CodeBlock>', "\n```", s, flags=re.IGNORECASE)
    return s.strip()


def build_completion_payload(
    model: str,
    content: str,
    task_id: str,
    conversation_id: str = "",
    prompt_tokens: int = 1,
    completion_tokens: int = 1,
) -> Dict[str, Any]:
    """构建兼容 Chat Completions 与 Responses API 的统一非流式响应。"""
    now = int(time.time())
    total_tokens = prompt_tokens + completion_tokens

    resp: Dict[str, Any] = {
        "id": f"chatcmpl-{task_id}",
        "object": "chat.completion",
        "created": now,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "output": [
            {
                "id": f"msg-{task_id}",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": content}],
            }
        ],
        "output_text": content,
        "status": "completed",
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
    }
    if conversation_id:
        resp["conversation_id"] = conversation_id

    return resp
