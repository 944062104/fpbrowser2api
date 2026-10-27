import asyncio
import time
import pytest


async def simulate_heartbeat_generator(duration=1.2, heartbeat_interval=0.4):
    last_yield = time.monotonic()
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        await asyncio.sleep(0.1)
        now = time.monotonic()
        if now - last_yield >= heartbeat_interval:
            yield ": ping\n\n"
            last_yield = now
    yield "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_stream_heartbeat():
    events = []
    async for item in simulate_heartbeat_generator(duration=1.0, heartbeat_interval=0.3):
        events.append(item)
    
    pings = [e for e in events if e == ": ping\n\n"]
    assert len(pings) >= 2
    assert events[-1] == "data: [DONE]\n\n"
