#!/usr/bin/env python3
"""Fetch WakaTime stats and inject them into a README between marker comments.

Requires a WakaTime API key: https://wakatime.com/api-key
Pass via --api-key or the WAKATIME_API_KEY environment variable.

Labels are localized per README: zh-CN filenames get Chinese labels.

Local usage:
  export WAKATIME_API_KEY=$(gum input)
  mise run waka
"""

import argparse
import base64
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request

WAKATIME_API = "https://wakatime.com/api/v1/users/current/stats/last_7_days"
START_MARKER = "<!--START_SECTION:waka-->"
END_MARKER = "<!--END_SECTION:waka-->"

BAR_LENGTH = 25
BLOCK_FILLED = "█"
BLOCK_EMPTY = "░"

LABELS = {
    "en": {
        "total": "**🕐 Total Coding Time**",
        "languages": "**💻 Programming Languages**",
        "editors": "**🛠️ Editors & Agents**",
        "operating_systems": "**💻 Operating Systems**",
    },
    "zh-CN": {
        "total": "**🕐 总编码时长**",
        "languages": "**💻 编程语言**",
        "editors": "**🛠️ 编辑器 & 智能体**",
        "operating_systems": "**💻 操作系统**",
    },
}

NAME_OVERRIDES = {
    "Other": {"en": "Other", "zh-CN": "其他"},
    "Unknown Editor": {"en": "Unknown", "zh-CN": "未知"},
}


def format_duration(seconds: float, locale: str) -> str:
    total_minutes = int(seconds) // 60
    hours, minutes = divmod(total_minutes, 60)
    if locale == "zh-CN":
        if hours == 0:
            return f"{minutes} 分钟"
        return f"{hours} 小时 {minutes} 分钟"
    if hours == 0:
        return f"{minutes} mins"
    hour_unit = "hr" if hours == 1 else "hrs"
    return f"{hours} {hour_unit} {minutes} mins"


def generate_bar(percent: float) -> str:
    filled = int(BAR_LENGTH * percent / 100)
    return BLOCK_FILLED * filled + BLOCK_EMPTY * (BAR_LENGTH - filled)


def display_width(text: str) -> int:
    """Count CJK characters as two columns so bar columns stay aligned."""
    return sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in text)


def truncate(name: str, width: int) -> str:
    """Truncate long names so the bar columns stay aligned."""
    if display_width(name) <= width:
        return name
    kept = []
    used = 0
    for char in name:
        char_width = 2 if unicodedata.east_asian_width(char) in "WF" else 1
        if used + char_width > width - 1:
            break
        kept.append(char)
        used += char_width
    return "".join(kept) + "…"


def format_list(items: list[dict], name_width: int, top: int, locale: str, show_time: bool) -> str:
    lines = []
    for item in items[:top]:
        name = truncate(item["name"], name_width)
        bar = generate_bar(item["percent"])
        suffix = f"  {format_duration(item['total_seconds'], locale)}" if show_time else ""
        padding = " " * max(0, name_width - display_width(name))
        lines.append(f"{name}{padding} {bar} {item['percent']:>5.2f}%{suffix}")
    return "\n".join(lines)


def localize_names(items: list[dict], locale: str) -> list[dict]:
    """Rename aggregate entries like Other or Unknown Editor per locale."""
    return [
        dict(item, name=NAME_OVERRIDES.get(item["name"], {}).get(locale, item["name"]))
        for item in items
    ]


def locale_for(path: str) -> str:
    return "zh-CN" if "zh-CN" in os.path.basename(path) else "en"


def fetch_stats(api_key: str) -> dict:
    encoded = base64.b64encode(f"{api_key}:".encode()).decode()
    request = urllib.request.Request(
        WAKATIME_API,
        headers={"Authorization": f"Basic {encoded}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())["data"]
    except urllib.error.HTTPError as e:
        print(f"WakaTime API returned HTTP {e.code}: {e.read().decode()}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Failed to reach WakaTime API: {e.reason}", file=sys.stderr)
        sys.exit(1)


def render(stats: dict, locale: str) -> str:
    labels = LABELS[locale]
    parts = []

    total_seconds = stats.get("total_seconds_including_other_language", 0)
    parts.append(f"{labels['total']}: {format_duration(total_seconds, locale)}\n")

    if stats.get("languages"):
        body = format_list(localize_names(stats["languages"], locale), name_width=15, top=5, locale=locale, show_time=True)
        parts.append(f"{labels['languages']}:\n```text\n{body}\n```\n")

    if stats.get("editors"):
        body = format_list(localize_names(stats["editors"], locale), name_width=15, top=3, locale=locale, show_time=False)
        parts.append(f"{labels['editors']}:\n```text\n{body}\n```\n")

    if stats.get("operating_systems"):
        body = format_list(localize_names(stats["operating_systems"], locale), name_width=15, top=3, locale=locale, show_time=False)
        parts.append(f"{labels['operating_systems']}:\n```text\n{body}\n```\n")

    return "\n".join(parts)


def update_readme(path: str, content: str) -> bool:
    with open(path, "r", encoding="utf-8") as f:
        original = f.read()

    pattern = re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER)
    replacement = f"{START_MARKER}\n{content}\n{END_MARKER}"
    updated = re.sub(pattern, replacement, original, flags=re.DOTALL)

    if updated == original:
        print(f"{path}: no changes")
        return False

    with open(path, "w", encoding="utf-8") as f:
        f.write(updated)
    print(f"{path}: updated")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "readmes",
        nargs="+",
        help="README files to update",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("WAKATIME_API_KEY"),
        help="WakaTime API key (default: $WAKATIME_API_KEY)",
    )
    args = parser.parse_args()

    if not args.api_key:
        print("WakaTime API key is required (--api-key or WAKATIME_API_KEY)", file=sys.stderr)
        sys.exit(1)

    stats = fetch_stats(args.api_key)

    changed = False
    for path in args.readmes:
        changed |= update_readme(path, render(stats, locale_for(path)))

    sys.exit(0 if changed else 0)


if __name__ == "__main__":
    main()
