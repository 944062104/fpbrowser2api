import asyncio
import json
import urllib.request
import urllib.parse
from playwright.async_api import async_playwright

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

auth_url = "https://auth.openai.com/oauth/authorize?client_id=app_EMoamEEZ73f0CkXaXp7hrann&code_challenge=Za1SgAQ2DDBp2txGwndjOZ5XTMoMDgIAAiUB5sPJODE&code_challenge_method=S256&codex_cli_simplified_flow=true&id_token_add_organizations=true&redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback&response_type=code&scope=openid+profile+email+offline_access&state=899154ddb1b259d6da5559ae7eaf8a3eeda9224761fccd140a9fe1945c98ebfe"
wid = "2"
target_email = "23-wormier.slowest@icloud.com"

async def run():
    url = "http://127.0.0.1:9000/api/launchBrowser"
    req = urllib.request.Request(url, data=json.dumps({"id": wid}).encode(), headers={"Content-Type": "application/json"})
    res = json.loads(urllib.request.urlopen(req).read().decode())
    port = res["data"]["port"]
    print(f"[*] Worker {wid} (ChatGPT-Worker-01) 已启动，端口: {port}")

    captured_url = None

    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = b.contexts[0]
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        async def on_route(route):
            nonlocal captured_url
            u = route.request.url
            if "localhost:1455" in u or "auth/callback" in u:
                print(f"\n[🎉 成功拦截重定向回调]: {u}\n")
                captured_url = u
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", on_route)

        print("[*] 正在导航至 Sub2API 授权地址...")
        try:
            await page.goto(auth_url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            print("[*] 导航提示 (若为拦截回调则属正常):", e)

        for i in range(30):
            if captured_url or ("code=" in page.url):
                if not captured_url:
                    captured_url = page.url
                break
            cur_url = page.url
            print(f"[{i:2d}s] 当前页面 URL: {cur_url[:80]}")

            # 1. 如果在 choose-an-account 页面，点击账号卡片
            if "choose-an-account" in cur_url:
                try:
                    # 查找包含 email 或账号名称的元素
                    acc_btn = await page.query_selector(f"button:has-text('{target_email}'), [role='button']:has-text('{target_email}'), div:has-text('{target_email}'), button")
                    if acc_btn and await acc_btn.is_visible():
                        print(f"  -> 点击选择账号卡片...")
                        await acc_btn.click()
                        await asyncio.sleep(2)
                except Exception as e:
                    print(f"  [!] 选择账号出错: {e}")

            if "add-phone" in cur_url:
                try:
                    txt = await page.inner_text("body")
                    print("\n[!] 到达 add-phone 页面内容:\n", txt)
                    # 看看是否有 Skip / 稍后 / 跳过
                    skip_btn = await page.query_selector("button:has-text('Skip'), button:has-text('Later'), button:has-text('跳过'), a:has-text('Skip')")
                    if skip_btn:
                        print("  -> 找到跳过按钮，点击跳过...")
                        await skip_btn.click()
                    break
                except Exception as e:
                    print("  [!] 读取 add-phone 失败:", e)
                    break

            # 2. 检查是否有授权按钮
            for btn_text in ["Authorize", "Allow", "Continue", "授权", "允许", "确认", "Consent"]:
                try:
                    btn = await page.query_selector(f"button:has-text('{btn_text}')")
                    if btn and await btn.is_visible():
                        print(f"  -> 点击授权按钮: {btn_text}")
                        await btn.click()
                        break
                except Exception:
                    pass

            await asyncio.sleep(1)

        cdp = await b.new_browser_cdp_session()
        await cdp.send("Browser.close")

    urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:9000/api/stopBrowser", data=json.dumps({"id": wid}).encode(), headers={"Content-Type": "application/json"}))
    
    print("\n" + "=" * 70)
    if captured_url:
        parsed = urllib.parse.urlparse(captured_url)
        qs = urllib.parse.parse_qs(parsed.query)
        code = qs.get("code", [""])[0]
        state = qs.get("state", [""])[0]
        print(f"✅ 成功获取 Code!")
        print(f"Code: {code}")
        print(f"完整重定向 URL: {captured_url}")
    else:
        print("❌ 未捕获到重定向 URL，请查看页面状态。")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(run())
