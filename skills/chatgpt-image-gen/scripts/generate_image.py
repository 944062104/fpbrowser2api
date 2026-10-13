"""ChatGPT 泛用自动化绘图执行器 (Universal ChatGPT Image Generator)
========================================================================
支持双通道模式，满足不同环境与架构需求：

【通道 A：FPBrowser2API 统一调度模式】(--mode fpb)
- 面向多账号池化并发调度；
- 对接兼容 NewAPI / OpenAI 规范的 `/v1/videos` 或 `/v1/tasks` 接口；
- 配合持久化指纹环境与浏览器扩展自动执行。

【通道 B：浏览器 CDP 直连免服务模式】(--mode cdp)
- 零额外后端依赖，适配任意指纹浏览器 (VirtualBrowser / AdsPower / 比特等) 或本地 Chrome；
- 通过 Chromium DevTools Protocol (CDP) 注入并安全下载原图与存证截图。
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from prompt_optimizer import optimize_prompt
except ImportError:
    from .prompt_optimizer import optimize_prompt

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None


def http_post(url: str, data: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=json.dumps(data or {}).encode("utf-8"), headers=h)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get(url: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def fetch_image_via_cdp(port: int, image_url: str, save_path: Path) -> int:
    """在已鉴权的浏览器上下文中下载 ChatGPT 内部图片以规避 403 权限拦截。"""
    if not async_playwright:
        raise RuntimeError("需要安装 playwright 以通过 CDP 下载图片: pip install playwright")

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        b64 = await page.evaluate("""async (url) => {
            const resp = await fetch(url);
            const blob = await resp.blob();
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onloadend = () => resolve(reader.result.split(',')[1]);
                reader.onerror = reject;
                reader.readAsDataURL(blob);
            });
        }""", image_url)

        data = base64.b64decode(b64)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(data)
        return len(data)


# -------------------- 模式 A: FPBrowser2API --------------------
def run_via_fpbrowser2api(
    prompt: str,
    output_path: Path,
    api_base: str = "http://127.0.0.1:8000",
    api_key: str = "mirrmart_sora2_880315",
    aspect_ratio: str = "16:9",
    resolution: str = "1k",
    poll_timeout_seconds: int = 300,
    vb_api_base: str = "http://127.0.0.1:9000",
) -> Path:
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": f"gpt-image2-{resolution}",
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
    }

    print(f"[*] [FPB 模式] 向 {api_base}/v1/videos 提交生图任务...")
    res = http_post(f"{api_base}/v1/videos", payload, headers)
    task_id = res.get("id") or res.get("task_id")
    if not task_id:
        raise RuntimeError(f"创建任务失败: {res}")
    print(f"[+] 任务成功入队: Task ID = {task_id}")

    start_time = time.time()
    result_data = None
    while time.time() - start_time < poll_timeout_seconds:
        time.sleep(4)
        elapsed = int(time.time() - start_time)
        try:
            status_data = http_get(f"{api_base}/v1/tasks/{task_id}", headers)
            st = status_data.get("status")
            progress = status_data.get("progress", 0)
            print(f"  -> [{elapsed}s] 状态: {st} | 进度: {progress}%")

            if st == "completed":
                result_data = status_data.get("result") or {}
                break
            elif st == "failed":
                err = status_data.get("error_message") or "未知错误"
                raise RuntimeError(f"FPBrowser2API 任务执行失败: {err}")
        except Exception as e:
            if "任务执行失败" in str(e):
                raise
            print(f"  -> 轮询等待中: {e}")

    if not result_data:
        raise TimeoutError("生图任务在规定时间内未完成")

    # 获取结果 URL
    image_url = result_data.get("image_url") or result_data.get("share_url")
    if not image_url and result_data.get("urls"):
        image_url = result_data["urls"][0]
    if not image_url:
        raise RuntimeError("未在任务结果中找到图片地址")

    print(f"[+] 获取到生成图片下载链接: {image_url[:80]}...")

    # 取回图片二进制文件
    # 优先检测活跃的 VirtualBrowser CDP 端口来完成已鉴权会话下载
    try:
        running_info = http_get(f"{vb_api_base}/api/getBrowserRunningList")
        workers = running_info.get("data", [])
        if workers:
            port = workers[0].get("debuggingPort") or workers[0].get("port") or 9222
            print(f"[*] 借助 Worker (端口 {port}) 会话上下文高速取回原图...")
            size = asyncio.run(fetch_image_via_cdp(port, image_url, output_path))
            print(f"[SUCCESS] 高清图片已保存: {output_path.resolve()} (大小: {size / 1024:.1f} KB)")
            return output_path
    except Exception as e:
        print(f"[!] CDP 鉴权下载提示: {e}，尝试本地直连下载...")

    # 直连下载兜底
    req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw_bytes = r.read()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(raw_bytes)
    print(f"[SUCCESS] 图片已保存: {output_path.resolve()}")
    return output_path


# -------------------- 模式 B: CDP 独立直连模式 --------------------
async def run_via_cdp(
    prompt: str,
    output_path: Path,
    port: int = 9222,
    screenshot_path: Optional[Path] = None,
) -> Path:
    if not async_playwright:
        raise RuntimeError("需要安装 playwright: pip install playwright")

    print(f"[*] [CDP 模式] 连接本地调试端口 http://127.0.0.1:{port}...")
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        print("[*] 正在导航至 ChatGPT...")
        await page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(2)

        # 定位输入框
        prompt_sel = None
        for sel in ["#prompt-textarea", "div#prompt-textarea", "div[contenteditable='true']", "textarea"]:
            try:
                await page.wait_for_selector(sel, timeout=10000)
                prompt_sel = sel
                break
            except Exception:
                continue

        if not prompt_sel:
            raise RuntimeError("未能定位到 ChatGPT 输入框，请确认浏览器处于登录状态")

        print("[*] 正在输入提示词并提交任务...")
        await page.click(prompt_sel)
        await asyncio.sleep(0.5)
        await page.keyboard.type(prompt, delay=25)
        await asyncio.sleep(1)

        # 发送
        sent = False
        for b_sel in ["button[data-testid='send-button']", "button[aria-label*='Send' i]", "button[aria-label*='发送']"]:
            btn = await page.query_selector(b_sel)
            if btn and await btn.is_enabled():
                await btn.click()
                sent = True
                break
        if not sent:
            await page.keyboard.press("Enter")

        print("[*] 等待 ChatGPT 绘图生成中 (约 20-50 秒)...")
        img_src = None
        for _ in range(40):
            await asyncio.sleep(3)
            imgs = await page.query_selector_all("div[data-message-author-role='assistant'] img, img[src*='oaiusercontent']")
            if imgs:
                for im in reversed(imgs):
                    src = await im.get_attribute("src")
                    if src and ("oaiusercontent" in src or "blob:" in src or "http" in src):
                        img_src = src
                        break
            stop_btn = await page.query_selector("button[data-testid='stop-button']")
            if img_src and not stop_btn:
                break

        if not img_src:
            raise RuntimeError("图片生成超时或由于配额限制未能出图")

        print(f"[+] 提取到图片: {img_src[:80]}...")
        # 页面上下文下载
        b64 = await page.evaluate("""async (url) => {
            const resp = await fetch(url);
            const blob = await resp.blob();
            return new Promise((resolve) => {
                const reader = new FileReader();
                reader.onloadend = () => resolve(reader.result.split(',')[1]);
                reader.readAsDataURL(blob);
            });
        }""", img_src)

        data = base64.b64decode(b64)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(data)
        print(f"[SUCCESS] 高清图片已保存: {output_path.resolve()} (大小: {len(data) / 1024:.1f} KB)")

        if screenshot_path:
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(screenshot_path))
            print(f"[+] 对话截图已保存: {screenshot_path.resolve()}")

        return output_path


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="ChatGPT 泛用自动化绘图执行工具")
    parser.add_argument("prompt", type=str, help="生图提示词 (支持简短中文/英文描述)")
    parser.add_argument("-m", "--mode", choices=["fpb", "cdp"], default="fpb", help="执行模式: fpb(默认调度池模式) 或 cdp(浏览器直连模式)")
    parser.add_argument("-o", "--output", type=str, default="output/generated_image.png", help="输出图片保存路径")
    parser.add_argument("-s", "--style", type=str, default="concept_art", help="风格: realistic, concept_art, cyberpunk, anime, oil_painting, product")
    parser.add_argument("-r", "--ratio", type=str, default="16:9", help="画幅比例: 16:9, 1:1, 9:16, 4:3, 3:4")
    parser.add_argument("--res", type=str, default="1k", choices=["1k", "2k", "4k"], help="分辨率层级: 1k, 2k, 4k")
    parser.add_argument("--raw-prompt", action="store_true", help="是否直接使用原始提示词（跳过自动结构化扩写与防反问优化）")
    parser.add_argument("--port", type=int, default=9222, help="CDP 模式下的浏览器端口 (默认 9222)")
    parser.add_argument("--fpb-url", type=str, default="http://127.0.0.1:8000", help="FPBrowser2API 服务地址")
    parser.add_argument("--api-key", type=str, default="mirrmart_sora2_880315", help="FPBrowser2API 访问秘钥")

    args = parser.parse_args()

    final_prompt = args.prompt if args.raw_prompt else optimize_prompt(
        args.prompt, style=args.style, aspect_ratio=args.ratio, resolution=args.res
    )
    print("=" * 70)
    print(f"[*] 最终执行提示词:\n    {final_prompt}")
    print("=" * 70)

    out_file = Path(args.output)

    if args.mode == "fpb":
        run_via_fpbrowser2api(
            prompt=final_prompt,
            output_path=out_file,
            api_base=args.fpb_url,
            api_key=args.api_key,
            aspect_ratio=args.ratio,
            resolution=args.res,
        )
    else:
        shot_file = out_file.with_name(f"{out_file.stem}_conversation.png")
        asyncio.run(
            run_via_cdp(
                prompt=final_prompt,
                output_path=out_file,
                port=args.port,
                screenshot_path=shot_file,
            )
        )


if __name__ == "__main__":
    main()
