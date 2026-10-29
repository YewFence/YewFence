#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["cairosvg", "pillow"]
# ///
"""统一 assets/icons/ 图标的视觉尺寸。

问题：图标来自不同项目，viewBox 内边距各不相同，README 里统一 height=48
渲染后视觉大小不一致。

做法：光栅化每个图标，找到非透明内容的包围盒（alpha 通道），
然后把内容居中放进统一的正方形画布：内容最长边占画布的 FRACTION。
- SVG：重写 viewBox（无 viewBox 则补上），文件其余部分不动
- PNG：裁剪内容后重新居中到正方形透明画布

另外会剥掉 SVG 根标签的 width/height 固有尺寸属性：GitHub 渲染时，
有固有尺寸的 SVG 会无视 <img height="48"> 按固有大小显示（1em→16px），
剥掉后所有图标统一由 README 里的 height=48 控制。

幂等性：抗锯齿让内容包围盒在像素边界抖 ±1px，写回 viewBox 后下一轮反推出
略有不同的值，数值会在几个值之间来回跳而永远不收敛。因此每轮计算后都与
现值比一次，差异在 TOLERANCE_PX 像素内就沿用现值；再叠加主循环反复执行
直到内容不再变化，保证重复运行不产生差异。

注意：fetch_icons.py 重跑会还原官方原始文件，之后需要重新运行本脚本
（或直接 `mise run icons` 一次完成两步）。
"""

from __future__ import annotations

import io
import math
import pathlib
import re

import cairosvg
from PIL import Image

ICONS = pathlib.Path(__file__).resolve().parent.parent / "assets" / "icons"

FRACTION = 0.80  # 内容最长边占正方形画布的比例（即四周各留 10% 空白）
RENDER = 1024  # 光栅化分辨率（px），只用于探测内容包围盒
ALPHA_MIN = 12  # alpha 阈值，忽略近乎透明的噪点像素
TOLERANCE_PX = 1.0  # 收敛容差（渲染像素），见 normalize_svg
MAX_ROUNDS = 10  # 归一化迭代上限，见 normalize_all


def alpha_bbox(img: Image.Image) -> tuple[int, int, int, int] | None:
    """非透明内容的包围盒 (left, top, right, bottom)，空图返回 None。"""
    mask = img.getchannel("A").point(lambda v: 255 if v > ALPHA_MIN else 0)
    return mask.getbbox()


def render_svg(path: pathlib.Path) -> Image.Image:
    png = cairosvg.svg2png(
        url=str(path),
        output_width=RENDER,
        background_color="rgba(0,0,0,0)",
    )
    return Image.open(io.BytesIO(png)).convert("RGBA")


def square_viewbox(
    vb: tuple[float, float, float, float], bbox: tuple[int, int, int, int], img: Image.Image
) -> tuple[float, float, float, float]:
    """把像素包围盒映射回 viewBox 坐标，返回以内容为中心的正方形 viewBox。"""
    vx, vy, vw, vh = vb
    sx, sy = vw / img.width, vh / img.height
    x0, y0 = vx + bbox[0] * sx, vy + bbox[1] * sy
    cw, ch = (bbox[2] - bbox[0]) * sx, (bbox[3] - bbox[1]) * sy
    side = max(cw, ch) / FRACTION
    cx, cy = x0 + cw / 2, y0 + ch / 2
    return cx - side / 2, cy - side / 2, side, side


def normalize_svg(path: pathlib.Path) -> str:
    img = render_svg(path)
    bbox = alpha_bbox(img)
    if bbox is None:
        return "跳过（渲染后无内容）"

    text = path.read_text(encoding="utf-8")
    m = re.search(r"<svg\b[^>]*>", text, re.S)
    assert m, f"{path.name}: 找不到 <svg> 标签"
    tag = m.group(0)

    vb_m = re.search(r'viewBox="([^"]+)"', tag)
    if vb_m:
        vb = tuple(float(v) for v in vb_m.group(1).replace(",", " ").split())
        assert len(vb) == 4, f"{path.name}: viewBox 格式异常: {vb_m.group(1)}"
    else:  # 无 viewBox：用 width/height 作为画布（如 jj.svg 的 1024x1024）
        w = float(re.search(r'\bwidth="([\d.]+)', tag).group(1))
        h = float(re.search(r'\bheight="([\d.]+)', tag).group(1))
        vb = (0.0, 0.0, w, h)

    old_fill = (bbox[2] - bbox[0]) / img.width  # 原内容占画布宽度比例
    nx, ny, side, _ = square_viewbox(vb, bbox, img)

    # 收敛判据：抗锯齿让内容包围盒在像素边界 ±1px 间抖动，
    # 写回 viewBox 后下一轮又反推出略有不同的值，于是数值永远收敛不了
    # （实测在几个值之间周期振荡）。差异小于一个渲染像素（换算回 viewBox
    # 单位）时视为抖动噪声，沿用现值，让重复运行不再产生差异。
    if vb_m:
        tol = TOLERANCE_PX * max(vb[2] / img.width, vb[3] / img.height)
        if (
            abs(nx - vb[0]) <= tol
            and abs(ny - vb[1]) <= tol
            and abs(side - vb[2]) <= tol
        ):
            nx, ny, side = vb[0], vb[1], vb[2]

    new_vb = f'viewBox="{nx:.2f} {ny:.2f} {side:.2f} {side:.2f}"'

    if vb_m:
        new_tag = tag[: vb_m.start()] + new_vb + tag[vb_m.end() :]
    else:
        new_tag = tag[:-1].rstrip() + f" {new_vb}>"  # 插到 <svg ...> 末尾
    # 剥掉固有宽高（见模块 docstring）
    new_tag = re.sub(r'\s(?:width|height)="[^"]*"', "", new_tag)
    path.write_text(text.replace(tag, new_tag, 1), encoding="utf-8")
    return f"内容占比 {old_fill:.0%} -> {FRACTION:.0%}，{new_vb}"


def normalize_png(path: pathlib.Path) -> str:
    img = Image.open(path).convert("RGBA")
    bbox = alpha_bbox(img)
    if bbox is None:
        return "跳过（无内容）"
    content = img.crop(bbox)
    side = math.ceil(max(content.size) / FRACTION)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(content, ((side - content.width) // 2, (side - content.height) // 2))
    canvas.save(path)
    return f"内容 {content.width}x{content.height} -> 画布 {side}x{side}"


def normalize_all() -> None:
    """归一化所有图标，迭代到内容不再变化为止。

    单轮归一化未必是不动点：剥除固有宽高会改变下一次光栅化的结果，
    而像素级抖动又会让 viewBox 反复微调。反复执行直到文件内容稳定，
    这样无论上游怎么变，重复运行都得到同一份结果。
    """
    paths = sorted(p for p in ICONS.iterdir() if p.suffix in (".svg", ".png"))
    previous: dict[str, bytes] | None = None
    for round_no in range(1, MAX_ROUNDS + 1):
        for path in paths:
            result = normalize_svg(path) if path.suffix == ".svg" else normalize_png(path)
            if round_no == 1:
                print(f"{path.name:16} {result}")
        current = {p.name: p.read_bytes() for p in paths}
        if current == previous:
            print(f"已收敛（第 {round_no - 1} 轮后内容不再变化）")
            return
        previous = current
    print(f"警告：{MAX_ROUNDS} 轮后仍未收敛")


if __name__ == "__main__":
    normalize_all()
