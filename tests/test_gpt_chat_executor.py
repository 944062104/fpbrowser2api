import pytest
import asyncio
from src.services.task_handler_registry import get_create_task_handler, CREATE_TASK_HANDLERS
from src.services.gpt_chat_executor import _prepare_chat_prompt


def test_gpt_chat_handler_registered():
    """验证 gpt_chat 已在 CREATE_TASK_HANDLERS 中正确注册"""
    assert "gpt_chat" in CREATE_TASK_HANDLERS
    label, handler = CREATE_TASK_HANDLERS["gpt_chat"]
    assert "对话" in label or "Chat" in label
    assert callable(handler)
    assert get_create_task_handler("gpt_chat") == handler


def test_gpt_chat_executor_imports():
    """验证 gpt_chat_executor 模块导出及基础签名正确"""
    from src.services.gpt_chat_executor import gpt_chat_workflow
    assert callable(gpt_chat_workflow)


def test_prepare_chat_prompt_anti_sandbox_codeblock():
    payload = {"prompt": "写一个 python 快速排序脚本"}
    prompt = _prepare_chat_prompt(payload)
    assert "Markdown 对应语言代码块" in prompt
    assert "严禁调用你内置的 Python 数据分析" in prompt or "严禁生成任何 sandbox:/" in prompt
    assert "exec_command" not in prompt
    assert "tool_call" not in prompt


def test_prepare_chat_prompt_normal_chat():
    payload = {"prompt": "你好，请问今天天气怎么样？"}
    prompt = _prepare_chat_prompt(payload)
    assert prompt == "你好，请问今天天气怎么样？"
    assert "sandbox" not in prompt


@pytest.mark.asyncio
async def test_gpt_chat_workflow_validation():
    """验证 prompt 为空时的参数校验"""
    from src.services.gpt_chat_executor import gpt_chat_workflow
    
    events = []
    async def mock_progress(pct, meta):
        events.append((pct, meta))
        
    with pytest.raises(ValueError, match="prompt 不能为空"):
        await gpt_chat_workflow(
            payload={"prompt": ""},
            progress_cb=mock_progress,
            browser_vendor="roxy",
            browser_base_url="http://127.0.0.1:9000",
            browser_access_key="",
            space_id="default",
            window_key="3",
        )


def test_gpt_chat_workflow_signature():
    """验证 gpt_chat_workflow 支持 headless 和 pure_mode 参数"""
    import inspect
    from src.services.gpt_chat_executor import gpt_chat_workflow
    sig = inspect.signature(gpt_chat_workflow)
    assert "headless" in sig.parameters
    assert "pure_mode" in sig.parameters
