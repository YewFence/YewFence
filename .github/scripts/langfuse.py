#!/usr/bin/env python3
"""Fetch Langfuse model usage and inject it into README langfuse marker sections.

Requires project API keys from Langfuse Cloud's project settings:
  LANGFUSE_BASE_URL: Cloud base URL, without the API path.
  LANGFUSE_PUBLIC_KEY: Project public API key.
  LANGFUSE_SECRET_KEY: Project secret API key.
Set these as repository Actions secrets for the daily Profile Stats workflow,
or in an untracked mise.local.toml [env] table for local use.

Local usage:
  mise run langfuse

Uses Metrics API v2 to rank exact model names by recorded totalTokens on
GENERATION observations over the rolling last seven days. Displays the top
three with bars and percentages only. Shares use all generation tokens,
including other and unknown models, so they need not add up to 100%.
Labels are localized per README: zh-CN filenames get Chinese labels.
"""

import argparse
import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

START_MARKER = "<!--START_SECTION:langfuse-->"
END_MARKER = "<!--END_SECTION:langfuse-->"
BAR_LENGTH = 25

AI_MODELS_LABELS = {"en": "**🤖 AI Models**", "zh-CN": "**🤖 AI 模型**"}
NO_USAGE_MESSAGES = {"en": "No model usage recorded.", "zh-CN": "暂无模型使用记录。"}


def fetch_metrics(base_url: str, public_key: str, secret_key: str, query: dict) -> list[dict]:
    """Query the project's Metrics API without retrieving trace contents."""
    credentials = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    params = urllib.parse.urlencode({"query": json.dumps(query)})
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/public/v2/metrics?{params}",
        headers={"Authorization": f"Basic {credentials}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["data"]


def fetch_stats(base_url: str, public_key: str, secret_key: str) -> tuple[list[dict], int]:
    """Fetch the top models and an independent total for accurate percentages."""
    now = datetime.now(timezone.utc)
    query = {
        "view": "observations",
        "metrics": [{"measure": "totalTokens", "aggregation": "sum"}],
        "filters": [
            {"column": "type", "operator": "=", "value": "GENERATION", "type": "string"}
        ],
        "fromTimestamp": (now - timedelta(days=7)).isoformat(),
        "toTimestamp": now.isoformat(),
    }
    models = fetch_metrics(base_url, public_key, secret_key, {
        **query,
        "dimensions": [{"field": "providedModelName"}],
        "orderBy": [{"field": "sum_totalTokens", "direction": "desc"}],
        "config": {"row_limit": 3},
    })
    totals = fetch_metrics(base_url, public_key, secret_key, {**query, "dimensions": []})
    total = int(Decimal(str(totals[0]["sum_totalTokens"] or 0))) if totals else 0
    return models, total


def render(models: list[dict], total: int, locale: str) -> str:
    """Render model shares of all generation tokens, including other models."""
    parts = [f"{AI_MODELS_LABELS[locale]}:\n"]
    if total == 0:
        parts.append(f"{NO_USAGE_MESSAGES[locale]}\n")
        return "\n".join(parts)

    rows = []
    for model in models:
        tokens = int(Decimal(str(model["sum_totalTokens"] or 0)))
        if tokens > 0:
            name = " ".join((model["providedModelName"] or "Unknown model").split())
            name = name.replace("`", "")
            rows.append((name, tokens))
    rows.sort(key=lambda row: (-row[1], row[0]))
    width = max((len(name) for name, _ in rows), default=0)
    lines = []
    for name, tokens in rows[:3]:
        percent = tokens / total * 100
        filled = int(BAR_LENGTH * tokens / total)
        bar = "█" * filled + "░" * (BAR_LENGTH - filled)
        lines.append(f"{name:<{width}} {bar} {percent:>6.2f}%")
    parts.append("```text\n" + "\n".join(lines) + "\n```\n")
    return "\n".join(parts)


def updated_readme(path: Path, content: str) -> str:
    """Replace exactly one marked section, preserving the surrounding README."""
    original = path.read_text(encoding="utf-8")
    if original.count(START_MARKER) != 1 or original.count(END_MARKER) != 1:
        raise ValueError(f"{path}: expected exactly one pair of Langfuse markers")
    before, rest = original.split(START_MARKER)
    if END_MARKER not in rest:
        raise ValueError(f"{path}: Langfuse markers are out of order")
    _, after = rest.split(END_MARKER)
    return f"{before}{START_MARKER}\n{content}\n{END_MARKER}{after}"


def locale_for(path: Path) -> str:
    return "zh-CN" if "zh-CN" in path.name else "en"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("readmes", nargs="+", type=Path, help="README files to update")
    parser.add_argument("--base-url", default=os.environ.get("LANGFUSE_BASE_URL"))
    parser.add_argument("--public-key", default=os.environ.get("LANGFUSE_PUBLIC_KEY"))
    parser.set_defaults(secret_key=os.environ.get("LANGFUSE_SECRET_KEY"))
    args = parser.parse_args()
    for name in ("base_url", "public_key", "secret_key"):
        if not getattr(args, name):
            parser.error(f"LANGFUSE_{name.upper()} is required")
    url = urllib.parse.urlsplit(args.base_url)
    if (
        url.scheme not in ("http", "https")
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        parser.error("base URL must be an HTTP(S) address without credentials, query or fragment")

    try:
        models, total = fetch_stats(args.base_url, args.public_key, args.secret_key)
        updates = [
            (path, updated_readme(path, render(models, total, locale_for(path))))
            for path in args.readmes
        ]
        for path, updated in updates:
            if path.read_text(encoding="utf-8") == updated:
                print(f"{path}: no changes")
            else:
                path.write_text(updated, encoding="utf-8")
                print(f"{path}: updated")
    except urllib.error.HTTPError as error:
        print(f"Langfuse API returned HTTP {error.code}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as error:
        print(f"Failed to reach Langfuse API: {error.reason}", file=sys.stderr)
        sys.exit(1)
    except (OSError, ValueError, KeyError, TypeError, InvalidOperation) as error:
        print(f"Failed to update Langfuse stats: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
