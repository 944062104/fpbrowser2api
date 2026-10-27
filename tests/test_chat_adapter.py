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


def test_extract_from_chat_completions_single_user_message():
    body = {
        "messages": [
            {"role": "user", "content": "Simple prompt"}
        ]
    }
    prompt = extract_prompt_and_system(body)
    assert prompt == "Simple prompt"


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
    raw = 'Here is code:\ue200cite turn0search0\ue201\n<CodeBlock language="python">\nprint("hello")\n</CodeBlock>'
    cleaned = clean_chat_reply(raw)
    assert "cite" not in cleaned
    assert "turn0search0" not in cleaned
    assert '```python\nprint("hello")\n```' in cleaned


def test_build_completion_payload():
    resp = build_completion_payload("gpt-4o", 'print("hello")', "task-123", "conv-456")
    assert resp["model"] == "gpt-4o"
    assert resp["choices"][0]["message"]["content"] == 'print("hello")'
    assert resp["conversation_id"] == "conv-456"
    assert resp["output"][0]["content"][0]["text"] == 'print("hello")'
