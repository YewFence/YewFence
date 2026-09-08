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

运行：./scripts/normalize_icons.py（或 uv run scripts/normalize_icons.py）
注意：fetch_icons.py 重跑会还原官方原始文件，之后需要重新运行本脚本。
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
    new_vb = f'viewBox="{nx:.2f} {ny:.2f} {side:.2f} {side:.2f}"'

    if vb_m:
        new_tag = tag[: vb_m.start()] + new_vb + tag[vb_m.end() :]
    else:
        new_tag = tag[:-1].rstrip() + f" {new_vb}>"  # 插到 <svg ...> 末尾
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


def main() -> None:
    for path in sorted(ICONS.iterdir()):
        if path.suffix == ".svg":
            print(f"{path.name:16} {normalize_svg(path)}")
        elif path.suffix == ".png":
            print(f"{path.name:16} {normalize_png(path)}")


if __name__ == "__main__":
    main()
