#!/usr/bin/env python3
"""Fetch WakaTime stats and inject them into a README between marker comments.

Requires a WakaTime API key: https://wakatime.com/api-key
Pass via --api-key or the WAKATIME_API_KEY environment variable.

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
import urllib.error
import urllib.request

WAKATIME_API = "https://wakatime.com/api/v1/users/current/stats/last_7_days"
START_MARKER = "<!--START_SECTION:waka-->"
END_MARKER = "<!--END_SECTION:waka-->"

BAR_LENGTH = 25
BLOCK_FILLED = "█"
BLOCK_EMPTY = "░"


def format_duration(seconds: float) -> str:
    total_minutes = int(seconds) // 60
    hours, minutes = divmod(total_minutes, 60)
    if hours == 0:
        return f"{minutes} mins"
    return f"{hours} hrs {minutes} mins"


def generate_bar(percent: float) -> str:
    filled = int(BAR_LENGTH * percent / 100)
    return BLOCK_FILLED * filled + BLOCK_EMPTY * (BAR_LENGTH - filled)


def truncate(name: str, width: int) -> str:
    """Truncate long names so the bar columns stay aligned."""
    if len(name) <= width:
        return name
    return name[: width - 1] + "…"


def format_list(items: list[dict], name_width: int, top: int, show_time: bool) -> str:
    lines = []
    for item in items[:top]:
        name = truncate(item["name"], name_width)
        bar = generate_bar(item["percent"])
        suffix = f"  {item['text']}" if show_time else ""
        lines.append(f"{name:<{name_width}} {bar} {item['percent']:>5.2f}%{suffix}")
    return "\n".join(lines)


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


def render(stats: dict) -> str:
    parts = []

    total_seconds = stats.get("total_seconds_including_other_language", 0)
    parts.append(f"**🕐 Total Coding Time**: {format_duration(total_seconds)}\n")

    if stats.get("languages"):
        body = format_list(stats["languages"], name_width=15, top=5, show_time=True)
        parts.append(f"**💻 Programming Languages**:\n```text\n{body}\n```\n")

    if stats.get("editors"):
        body = format_list(stats["editors"], name_width=15, top=3, show_time=False)
        parts.append(f"**🛠️ Editors**:\n```text\n{body}\n```\n")

    if stats.get("operating_systems"):
        body = format_list(stats["operating_systems"], name_width=15, top=3, show_time=False)
        parts.append(f"**💻 Operating Systems**:\n```text\n{body}\n```\n")

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
    content = render(stats)

    changed = False
    for path in args.readmes:
        changed |= update_readme(path, content)

    sys.exit(0 if changed else 0)


if __name__ == "__main__":
    main()
