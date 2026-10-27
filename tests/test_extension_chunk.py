import pytest
import asyncio
from src.services.browser_extension_bridge import ExtensionClient, _handle_client_message

@pytest.mark.asyncio
async def test_extension_client_chunk_callback():
    """测试当收到 task.chunk 消息时，触发绑定的 chunk_cb 回调"""
    received_deltas = []
    
    async def mock_chunk_cb(delta: str):
        received_deltas.append(delta)
        
    client = ExtensionClient(
        client_id="test_client",
        websocket=None, # 测试时无需真实 WS
        space_id="default",
        window_key="3",
    )
    # 模拟设置 chunk_cbs 字典
    client.chunk_cbs = {"task-123": mock_chunk_cb}
    
    # 模拟收到第一段 chunk
    await _handle_client_message(client, {
        "type": "task.chunk",
        "task_id": "task-123",
        "delta": "Hello ",
    })
    
    # 模拟收到第二段 chunk
    await _handle_client_message(client, {
        "type": "task.chunk",
        "task_id": "task-123",
        "delta": "World!",
    })
    
    assert received_deltas == ["Hello ", "World!"]
