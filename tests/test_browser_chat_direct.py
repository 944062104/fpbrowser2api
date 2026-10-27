import asyncio
import json
import time
import urllib.request
import pytest
from playwright.async_api import async_playwright

WORKER_ID = "2"

def launch_worker():
    url = "http://127.0.0.1:9000/api/launchBrowser"
    data = json.dumps({"id": WORKER_ID}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        res = json.loads(resp.read().decode("utf-8"))
    assert res.get("success"), f"Launch failed: {res}"
    return res["data"]["debuggingPort"]

def stop_worker():
    try:
        url = "http://127.0.0.1:9000/api/stopBrowser"
        data = json.dumps({"id": WORKER_ID}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass

@pytest.mark.skip(reason="Manual integration test requiring active window 2 session")
@pytest.mark.asyncio
async def test_direct_conversation_pipeline():
    """TDD 核心验证：
    在已登录的指纹浏览器上下文中，能否免 DOM 输入、免点击，
    直接以底层会话协议触发 ChatGPT 对话并实时流式接收回复？
    """
    port = launch_worker()
    print(f"\n[1] Worker {WORKER_ID} launched on port {port}")

    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            ctx = browser.contexts[0]
            pages = ctx.pages
            page = pages[0] if pages else await ctx.new_page()

            # 确保在 chatgpt.com
            if "chatgpt.com" not in page.url:
                await page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            # 1. 验证登录态
            print("[2] 正在校验浏览器内部 Session...")
            session = await page.evaluate("""async () => {
                const r = await fetch('/api/auth/session');
                if (!r.ok) return null;
                return await r.json();
            }""")
            assert session is not None, "未获取到 Session"
            assert "user" in session, "Session 中无 user 字段"
            email = session.get("user", {}).get("email")
            access_token = session.get("accessToken")
            print(f"  -> 当前登录邮箱: {email}")
            print(f"  -> 获取到 accessToken (len={len(access_token)})")
            assert access_token, "缺失 accessToken"

            # 2. 直接发起对话请求 (免 DOM 输入，直接在页面上下文中注入 fetch)
            print("[3] 正在通过底层会话发起免 DOM 对话测试...")
            test_prompt = "Reply with 'PONYTAIL_DIRECT_TEST_PASS' and nothing else."

            start_t = time.time()
            ttft = None

            # 执行会话调用脚本
            direct_call_script = """async (payload) => {
                const resp = await fetch('/backend-api/conversation', {
                    method: 'POST',
                    headers: {
                        'Authorization': 'Bearer ' + payload.token,
                        'Content-Type': 'application/json',
                        'Accept': 'text/event-stream'
                    },
                    body: JSON.stringify(payload.body)
                });
                if (!resp.ok) {
                    const errText = await resp.text();
                    return { ok: false, status: resp.status, error: errText };
                }

                const reader = resp.body.getReader();
                const decoder = new TextDecoder();
                let fullText = '';
                let firstChunkTime = null;
                const startTime = performance.now();

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    if (firstChunkTime === null) {
                        firstChunkTime = (performance.now() - startTime) / 1000.0;
                    }
                    const chunk = decoder.decode(value, { stream: true });
                    const lines = chunk.split('\\n');
                    for (const line of lines) {
                        if (line.startsWith('data: ') && line !== 'data: [DONE]') {
                            try {
                                const data = JSON.parse(line.slice(6));
                                const parts = data?.message?.content?.parts;
                                if (parts && parts.length > 0 && typeof parts[0] === 'string') {
                                    fullText = parts[0];
                                }
                            } catch(e) {}
                        }
                    }
                }
                return {
                    ok: true,
                    status: resp.status,
                    fullText: fullText,
                    ttft: firstChunkTime,
                    totalDuration: (performance.now() - startTime) / 1000.0
                };
            }"""

            # 构造最小 ChatGPT conversation payload
            import uuid
            msg_id = str(uuid.uuid4())
            parent_id = str(uuid.uuid4())
            req_body = {
                "action": "next",
                "messages": [
                    {
                        "id": msg_id,
                        "author": {"role": "user"},
                        "content": {
                            "content_type": "text",
                            "parts": [test_prompt]
                        },
                        "metadata": {}
                    }
                ],
                "parent_message_id": parent_id,
                "model": "auto",
                "timezone_offset_min": -480,
                "suggestions": [],
                "history_and_training_disabled": False,
                "conversation_mode": {"kind": "primary_assistant"},
                "force_paragen": False,
                "force_paragen_model_slug": "",
                "force_nulligen": False,
                "force_rate_limit": False
            }

            res = await page.evaluate(direct_call_script, {"token": access_token, "body": req_body})
            print(f"[4] 调用结果: ok={res.get('ok')}, status={res.get('status')}")
            print(f"  -> TTFT (首字耗时): {res.get('ttft'):.2f}s")
            print(f"  -> 总耗时: {res.get('totalDuration'):.2f}s")
            print(f"  -> 回复内容: {res.get('fullText')}")

            # 3. 断言验证
            assert res.get("ok") is True, f"请求失败: {res}"
            assert res.get("status") == 200, f"状态码异常: {res.get('status')}"
            assert "PONYTAIL_DIRECT_TEST_PASS" in res.get("fullText", ""), f"回复未包含预期字符串: {res.get('fullText')}"
            assert res.get("ttft") < 4.0, f"首字延迟超标: {res.get('ttft')}s"
            print("\n🎉 [TDD 验证通过] 底层免 DOM 会话与低延迟流式管道完全可行！")

    finally:
        stop_worker()
