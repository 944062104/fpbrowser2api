"""ChatGPT 绘图提示词结构化优化工具 (Prompt Optimizer)
========================================================================
核心作用：
1. 解决 ChatGPT (尤其是免费版 GPT-4o) 面对模糊或礼貌性提问时“反问确认而不生图”的痛点；
2. 自动补充画质、光影、构图、材质细节，输出具有极高成片率的高清 Prompt；
3. 严格添加防反问安全后缀，强制 ChatGPT 立即调用画图工具。
"""

from __future__ import annotations

import argparse
import sys
from typing import Dict

STYLES: Dict[str, Dict[str, str]] = {
    "realistic": {
        "name": "写实摄影 / 电影质感",
        "keywords": "电影级写实摄影风格，8k高分辨率，真实物理光学渲染，哈苏中画幅镜头质感，丰富表面纹理，浅景深，自然丁达尔光线，真实色彩还原",
    },
    "concept_art": {
        "name": "概念艺术 / 奇幻插画",
        "keywords": "极致细节的概念艺术插画，电影级广角宏大构图，史诗级光影氛围，柔和光晕，精细笔触与微光粒子，8k Octane Render 质感",
    },
    "cyberpunk": {
        "name": "赛博朋克 / 未来科技",
        "keywords": "未来赛博朋克美学，高科技机械细节，霓虹青粉交错光辉，雨夜湿漉地面倒影，全息投影与半透明全息界面，高对比度电影光影",
    },
    "anime": {
        "name": "精致日系动漫 / 动画剧照",
        "keywords": "高精细日式新海诚动画电影风格，细腻光影，清透天空与飘逸云彩，明亮通透的色彩，精致人物/场景线条，唯美情绪氛围",
    },
    "oil_painting": {
        "name": "古典油画 / 艺术大师",
        "keywords": "古典大师油画质感，厚重丰富笔触，伦勃朗式戏剧性明暗对比光，丰富层次与油画画布纹理，高雅复古艺术色调",
    },
    "product": {
        "name": "商业产品 / 极简静物",
        "keywords": "顶级商业广告摄影，高端极简影棚布光，极净纯色渐变背景，精湛材质高光反射，超高质感静物特写，无杂乱元素",
    },
}

ANTI_CLARIFICATION_SUFFIX = "请直接调用画图工具立即生成图片，不要输出任何询问文字、选项或确认反问。"


def optimize_prompt(
    raw_prompt: str,
    style: str = "concept_art",
    aspect_ratio: str = "16:9",
    resolution: str = "1k",
) -> str:
    cleaned = raw_prompt.strip().rstrip("。！？.!?")
    if not cleaned:
        raise ValueError("输入提示词不能为空")

    style_cfg = STYLES.get(style, STYLES["concept_art"])
    style_keywords = style_cfg["keywords"]

    # 规范化前缀
    prefix = "立即生成图片："

    optimized = f"{prefix}{cleaned}，{style_keywords}。画面宽高比设置为 {aspect_ratio}，画质规格为 {resolution}。{ANTI_CLARIFICATION_SUFFIX}"
    return optimized


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="ChatGPT 绘图提示词结构化优化工具")
    parser.add_argument("prompt", type=str, help="用户原始提示词需求")
    parser.add_argument("-s", "--style", type=str, default="concept_art", choices=list(STYLES.keys()), help="画面风格")
    parser.add_argument("-r", "--ratio", type=str, default="16:9", help="宽高比 (如 16:9, 1:1, 9:16)")
    parser.add_argument("--res", type=str, default="1k", choices=["1k", "2k", "4k"], help="分辨率层级")

    args = parser.parse_args()
    result = optimize_prompt(args.prompt, style=args.style, aspect_ratio=args.ratio, resolution=args.res)
    print(result)


if __name__ == "__main__":
    main()
