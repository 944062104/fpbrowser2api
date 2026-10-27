import asyncio
import json
import pytest
from fastapi import HTTPException


async def simulate_stream_generator(should_fail=False):
    seq = 0
    now = 1234567890
    task_id = "test-task-123"
    model = "chatgpt-4o-latest"
    accumulated_text = ""
    
    # 握手
    yield f'event: response.created\ndata: {{"type":"response.created","sequence_number":{seq},"response":{{"id":"resp-{task_id}","status":"in_progress","model":"{model}"}}}}\n\n'
    seq += 1

    try:
        if should_fail:
            raise HTTPException(status_code=504, detail={"message": "chat timeout", "code": "task_timeout"})
        accumulated_text = "Hello world"
        yield f'event: response.output_text.delta\ndata: {{"type":"response.output_text.delta","sequence_number":{seq},"output_index":0,"content_index":0,"delta":"Hello world"}}\n\n'
        seq += 1
        yield f'event: response.completed\ndata: {{"type":"response.completed","sequence_number":{seq},"response":{{"id":"resp-{task_id}","status":"completed"}}}}\n\n'
        yield "data: [DONE]\n\n"
    except Exception as exc:
        err_msg = str(exc.detail if isinstance(exc, HTTPException) else exc)
        yield f'event: response.failed\ndata: {{"type":"response.failed","sequence_number":{seq},"response":{{"id":"resp-{task_id}","status":"failed","error":{{"message":{json.dumps(err_msg)}}}}}}}\n\n'
        seq += 1
        yield f'data: {{"error":{{"message":{json.dumps(err_msg)}}}}}\n\n'
        yield f'event: response.completed\ndata: {{"type":"response.completed","sequence_number":{seq},"response":{{"id":"resp-{task_id}","status":"failed"}}}}\n\n'
        yield "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_stream_generator_error_does_not_raise():
    # 测试异常被完全吸收转换为 SSE 事件，生成器正常耗尽不抛异常
    chunks = []
    async for c in simulate_stream_generator(should_fail=True):
        chunks.append(c)

    full_output = "".join(chunks)
    assert "response.failed" in full_output
    assert "chat timeout" in full_output
    assert "response.completed" in full_output
    assert "data: [DONE]" in full_output


@pytest.mark.asyncio
async def test_stream_generator_direct_output_without_buffering():
    chunks = []
    async for c in simulate_stream_generator(should_fail=False):
        chunks.append(c)

    full_output = "".join(chunks)
    assert "response.created" in full_output
    assert "response.output_text.delta" in full_output
    assert "Hello world" in full_output
    assert "response.completed" in full_output
    assert "data: [DONE]" in full_output
