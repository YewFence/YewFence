#!/usr/bin/env python3
"""下载 profile README 图标到 assets/icons/。

可重复运行：所有图标源均为官方仓库 raw 地址，重跑即更新到最新版本。
处理方式三类：
- PLAIN: 原样下载（彩色图标）
- SINGLE: 单色图标改造为 auto SVG（浅色模式黑 / 深色模式白）
- MERGE: 两个主题变体合并为单文件 auto SVG

下载/改造后需再运行 normalize_icons.py 统一视觉尺寸。
"""

from __future__ import annotations

import pathlib
import re
import urllib.request

OUT = pathlib.Path(__file__).resolve().parent.parent / "assets" / "icons"
OUT.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "Mozilla/5.0 (YewFence profile icons fetcher)"}

DV = "https://raw.githubusercontent.com/devicons/devicon/master/icons"
LOBE = "https://raw.githubusercontent.com/lobehub/lobe-icons/master/packages/static-svg/icons"

# 原样下载：目标文件名 -> 源 URL
PLAIN: dict[str, str] = {
    # devicon（original 彩色变体，GitHub master 分支）
    "python.svg": f"{DV}/python/python-original.svg",
    "vue.svg": f"{DV}/vuejs/vuejs-original.svg",
    "vite.svg": f"{DV}/vite/vite-original.svg",
    "react.svg": f"{DV}/react/react-original.svg",
    "nodejs.svg": f"{DV}/nodejs/nodejs-original.svg",
    "git.svg": f"{DV}/git/git-original.svg",
    "docker.svg": f"{DV}/docker/docker-original.svg",
    "debian.svg": f"{DV}/debian/debian-original.svg",
    "nginx.svg": f"{DV}/nginx/nginx-original.svg",
    "pnpm.svg": f"{DV}/pnpm/pnpm-original.svg",
    "sqlite.svg": f"{DV}/sqlite/sqlite-original.svg",
    "go.svg": f"{DV}/go/go-original.svg",
    "fedora.svg": f"{DV}/fedora/fedora-original.svg",
    "traefik.svg": f"{DV}/traefikproxy/traefikproxy-original.svg",
    "neovim.svg": f"{DV}/neovim/neovim-original.svg",
    "openapi.svg": f"{DV}/openapi/openapi-original.svg",
    "postgresql.svg": f"{DV}/postgresql/postgresql-original.svg",
    "cloudflare.svg": f"{DV}/cloudflare/cloudflare-original.svg",
    "grafana.svg": f"{DV}/grafana/grafana-original.svg",
    "zsh.svg": f"{DV}/zsh/zsh-original.svg",
    "forgejo.svg": f"{DV}/forgejo/forgejo-original.svg",
    "tmux.svg": f"{DV}/tmux/tmux-original.svg",
    # lobe-icons（AI 组，color 变体）
    "claude.svg": f"{LOBE}/claude-color.svg",
    "deepseek.svg": f"{LOBE}/deepseek-color.svg",
    "zhipu.svg": f"{LOBE}/zhipu-color.svg",
    "codex.svg": f"{LOBE}/codex-color.svg",
    "tavily.svg": f"{LOBE}/tavily-color.svg",
    # 官方仓库
    "uv.svg": "https://raw.githubusercontent.com/astral-sh/uv/main/docs/assets/logo-letter.svg",
    "jj.svg": "https://raw.githubusercontent.com/jj-vcs/jj/main/docs/images/jj-logo.svg",
    "rclone.svg": "https://raw.githubusercontent.com/rclone/rclone/master/graphics/logo/svg/logo_symbol_color.svg",
    "context7.svg": "https://raw.githubusercontent.com/upstash/context7/master/public/context7-icon-green.svg",
    "pi.svg": "https://pi.dev/logo-auto.svg",
}

# 位图图标：下载后保持纵横比缩放到指定高度（需要 Pillow，缺失则原样保存）
RASTER: dict[str, tuple[str, int]] = {
    "zellij.png": (
        "https://raw.githubusercontent.com/zellij-org/zellij/main/assets/logo.png",
        128,
    ),
}

# 需要随主题反转的前景 fill 正则：黑系 / 白色
FG_DARK = r"(?:black|#000000|#000|#141414|#010101|currentColor)"
FG_LIGHT = r"(?:white|#ffffff|#fff)"

# 黑色主体的单色图标 -> 改造 auto（浅黑深白）。
# 仅用于官方未提供深色变体、且标志本身单色的情况：有官方双变体的走 MERGE（如 rust）。
SINGLE: dict[str, str] = {
    "markdown.svg": f"{DV}/markdown/markdown-original.svg",
    "flask.svg": f"{DV}/flask/flask-original.svg",
    "openai.svg": f"{LOBE}/openai.svg",
    "zed.svg": "https://raw.githubusercontent.com/zed-industries/zed/main/assets/images/zed_logo.svg",
    "tailscale.svg": "https://raw.githubusercontent.com/tailscale/tailscale/main/client/web/src/assets/icons/tailscale-icon.svg",
}

# 白色主体的图标 -> 改造 auto（反转白色 fill，其余彩色路径保留）。
# kimi 官方反色版即"K 随主题反转、蓝点不变"，与此处处理一致。
SINGLE_WHITE: dict[str, str] = {
    "kimi.svg": f"{LOBE}/kimi-color.svg",
}

# 双变体合并：(浅色背景用源, 深色背景用源)
MERGE: dict[str, tuple[str, str]] = {
    "github.svg": (
        "https://raw.githubusercontent.com/xandemon/developer-icons/main/icons/github-dark.svg",
        "https://raw.githubusercontent.com/xandemon/developer-icons/main/icons/github-light.svg",
    ),
    "mise.svg": (
        "https://raw.githubusercontent.com/jdx/mise/main/docs/public/logo-light.svg",
        "https://raw.githubusercontent.com/jdx/mise/main/docs/public/logo-dark.svg",
    ),
    "opentofu.svg": (
        "https://raw.githubusercontent.com/opentofu/brand-artifacts/main/symbol-only/transparent/SVG/on-light.svg",
        "https://raw.githubusercontent.com/opentofu/brand-artifacts/main/symbol-only/transparent/SVG/on-dark.svg",
    ),
    # rust 官方 artwork：浅色用单路径版（完整版含 mask，部分渲染器不支持），深色用白色描边版
    "rust.svg": (
        "https://raw.githubusercontent.com/rust-lang/rust-artwork/main/logo/rust-logo-single-path.svg",
        "https://raw.githubusercontent.com/rust-lang/rust-artwork/main/logo/rust-logo-white-outline.svg",
    ),
}

# 来源许可（生成 NOTICE.md 用）
LICENSES: dict[str, str] = {
    "devicons/devicon": "MIT",
    "lobehub/lobe-icons": "MIT",
    "xandemon/developer-icons": "MIT",
    "astral-sh/uv": "Apache-2.0",
    "jj-vcs/jj": "Apache-2.0",
    "zellij-org/zellij": "MIT",
    "rclone/rclone": "MIT",
    "opentofu/brand-artifacts": "见仓库 LICENSE",
    "jdx/mise": "MIT",
    "zed-industries/zed": "GPL-3.0（代码）；logo 为商标",
    "tailscale/tailscale": "BSD-3-Clause（代码）；logo 为商标",
    "upstash/context7": "MIT",
    "pi.dev": "商标",
    "rust-lang/rust-artwork": "CC-BY-4.0；logo 为 Rust Foundation 商标",
}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def is_svg(name: str) -> bool:
    return name.endswith(".svg")


def to_auto_single(svg: bytes, fg: str = FG_DARK) -> bytes:
    """单色 SVG 注入主题媒体查询：浅色模式黑、深色模式白。

    fg 指定要随主题反转的前景 fill 正则（默认黑系；白色主体图标用 FG_LIGHT）。
    """
    text = svg.decode("utf-8")
    style = (
        "<style>"
        ":root{--icon-fg:#000}"
        "path:not([fill]),rect:not([fill]),circle:not([fill]),ellipse:not([fill]),polygon:not([fill]){fill:var(--icon-fg)}"
        "@media (prefers-color-scheme: dark){:root{--icon-fg:#fff}}"
        "</style>"
    )
    # 删除黑系 presentation attribute（让 CSS 变量接管），
    # 同时把内联 style 里的黑系 fill 替换为变量。
    text = re.sub(rf'\sfill="{fg}"', "", text)
    text = re.sub(rf"fill:\s*{fg}(?=[;\"])", "fill:var(--icon-fg)", text)
    if "<style>" not in text:
        text = re.sub(r"(<svg[^>]*>)", rf"\1{style}", text, count=1)
    else:
        text = re.sub(r"(<style>)", rf"\1{style_content(style)}", text, count=1)
    return text.encode("utf-8")


def style_content(style_tag: str) -> str:
    return style_tag[len("<style>") : -len("</style>")]


def viewbox(svg_text: str) -> tuple[float, float, float, float] | None:
    m = re.search(r'viewBox="([-\d. ]+)"', svg_text)
    if not m:
        return None
    parts = [float(x) for x in m.group(1).split()]
    return tuple(parts)  # type: ignore[return-value]


def inner_content(svg_text: str) -> str:
    """去掉 <svg ...> 与 </svg> 外壳后的内容。"""
    m = re.search(r"<svg[^>]*>", svg_text)
    assert m, "SVG 根标签缺失"
    body = svg_text[m.end() :]
    body = body.rsplit("</svg>", 1)[0]
    return body


def fit_transform(src_vb: tuple[float, float, float, float], dst_vb: tuple[float, float, float, float]) -> str:
    """把 src viewBox 的内容等比缩放到 dst viewBox 内并居中。"""
    sx, sy, sw, sh = src_vb
    dx, dy, dw, dh = dst_vb
    scale = min(dw / sw, dh / sh)
    tx = dx + (dw - sw * scale) / 2 - sx * scale
    ty = dy + (dh - sh * scale) / 2 - sy * scale
    return f"translate({tx:.4f} {ty:.4f}) scale({scale:.4f})"


def merge_auto(light: bytes, dark: bytes) -> bytes:
    """两个主题变体合并成单文件 auto SVG。"""
    light_text = light.decode("utf-8")
    dark_text = dark.decode("utf-8")
    outer_vb = viewbox(light_text) or (0, 0, 100, 100)
    dark_vb = viewbox(dark_text)

    light_body = inner_content(light_text)
    dark_body = inner_content(dark_text)
    if dark_vb and dark_vb != outer_vb:
        dark_body = f'<g transform="{fit_transform(dark_vb, outer_vb)}">{dark_body}</g>'

    css = (
        "<style>"
        ".dark{display:none}"
        "@media (prefers-color-scheme: dark){.light{display:none}.dark{display:inline}}"
        "</style>"
    )
    vb = " ".join(f"{v:g}" for v in outer_vb)
    result = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}">'
        f"{css}"
        f'<g class="light">{light_body}</g>'
        f'<g class="dark">{dark_body}</g>'
        "</svg>"
    )
    return result.encode("utf-8")


def fill_summary(svg: bytes) -> list[str]:
    """统计 SVG 里的 fill 值，用于抽查黑系图标。"""
    text = svg.decode("utf-8", errors="replace")
    fills = re.findall(r'fill="([^"]+)"', text) + re.findall(r"fill:([^;]+)", text)
    counts: dict[str, int] = {}
    for f in fills:
        f = f.strip()
        counts[f] = counts.get(f, 0) + 1
    return [f"{k}×{v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])[:6]]


def shrink_png(data: bytes, target_h: int) -> bytes:
    """保持纵横比缩放到指定高度；Pillow 不可用时原样返回。"""
    try:
        from PIL import Image
        import io
    except ImportError:
        print("  [warn] Pillow 不可用，跳过缩放（uvx --with pillow python scripts/fetch_icons.py）")
        return data
    img = Image.open(io.BytesIO(data))
    w, h = img.size
    target_w = max(1, round(w * target_h / h))
    img = img.convert("RGBA").resize((target_w, target_h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def main() -> None:
    manifest: dict[str, str] = {}
    for name, url in PLAIN.items():
        data = fetch(url)
        (OUT / name).write_bytes(data)
        manifest[name] = url
        note = ""
        if is_svg(name):
            note = f" | fill: {fill_summary(data)}"
        print(f"[plain] {name}{note}")
    for name, url in SINGLE.items():
        data = to_auto_single(fetch(url))
        (OUT / name).write_bytes(data)
        manifest[name] = url
        print(f"[auto ] {name} <- {url}")
    for name, url in SINGLE_WHITE.items():
        data = to_auto_single(fetch(url), FG_LIGHT)
        (OUT / name).write_bytes(data)
        manifest[name] = url
        print(f"[auto ] {name} <- {url}")
    for name, (light_url, dark_url) in MERGE.items():
        data = merge_auto(fetch(light_url), fetch(dark_url))
        (OUT / name).write_bytes(data)
        manifest[name] = f"{light_url} + {dark_url}"
        print(f"[merge] {name} <- {light_url}")
    for name, (url, target_h) in RASTER.items():
        data = shrink_png(fetch(url), target_h)
        (OUT / name).write_bytes(data)
        manifest[name] = url
        print(f"[png  ] {name} <- {url}")
    (OUT / "sources.tsv").write_text(
        "\n".join(f"{k}\t{v}" for k, v in manifest.items()) + "\n", encoding="utf-8"
    )
    # NOTICE.md
    lines = [
        "# Icon Sources & Licenses",
        "",
        "The icons in this directory are used in the YewFence GitHub profile README. "
        "All logos are trademarks of their respective owners.",
        "Files are fetched and processed (theme-aware auto variants / dual-variant merging / "
        "raster resizing) by `scripts/fetch_icons.py` from the public sources listed below. "
        "Re-run the script to update them.",
        "",
        "| File | Source | License |",
        "| --- | --- | --- |",
    ]
    for name, url in sorted(manifest.items()):
        repo = ""
        for key in LICENSES:
            if key.split("/")[-1] in url or key in url:
                repo = key
                break
        if not repo:
            repo = url.split("//")[1].split("/")[0] or url
        lines.append(f"| {name} | {url} | {LICENSES.get(repo, 'see source repo')} |")
    (OUT / "NOTICE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n共 {len(manifest)} 个图标 -> {OUT}")


if __name__ == "__main__":
    main()
