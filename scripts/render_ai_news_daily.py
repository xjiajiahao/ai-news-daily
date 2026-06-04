#!/usr/bin/env python3
"""Render a normalized AI daily report JSON into Markdown and WeChat HTML."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from markdown_utils import markdown_to_wechat_html

SECTION_ALIASES = {
    "模型 / 研究": "模型 / 研究",
    "model_research": "模型 / 研究",
    "AI 产品 / Agent": "AI 产品 / Agent",
    "ai_product_agent": "AI 产品 / Agent",
    "开源项目": "开源项目",
    "open_source": "开源项目",
    "基础设施 / 硬件 / 安全": "基础设施 / 硬件 / 安全",
    "infra_hardware_security": "基础设施 / 硬件 / 安全",
}

SECTION_ORDER = [
    "模型 / 研究",
    "AI 产品 / Agent",
    "开源项目",
    "基础设施 / 硬件 / 安全",
]

TOP_ITEM_ALIASES = ("top_items", "top10", "top_10")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render an AI daily report JSON file into Markdown and WeChat HTML."
    )
    parser.add_argument("json_path", help="Path to the normalized report JSON file.")
    parser.add_argument(
        "--markdown-output",
        help="Write rendered Markdown to this path. If omitted, prints Markdown to stdout.",
    )
    parser.add_argument(
        "--wechat-html-output",
        help="Optional path for rendered WeChat HTML output.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the JSON structure without rendering files.",
    )
    return parser.parse_args()


def load_json(path_str: str) -> tuple[Path, dict[str, Any]]:
    path = Path(path_str).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"JSON file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Top-level JSON must be an object: {path}")
    return path, data


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise SystemExit(f"{label} must be a string")
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        raise SystemExit(f"{label} must not be empty")
    return cleaned


def optional_string(value: Any, label: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise SystemExit(f"{label} must be a string when present")
    return " ".join(value.strip().split())


def normalize_links(value: Any, label: str) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list) or not value:
        raise SystemExit(f"{label} must be a non-empty list")

    normalized: list[dict[str, str]] = []
    for index, item in enumerate(value, start=1):
        item_label = f"{label}[{index}]"
        if isinstance(item, str):
            url = require_url(item, item_label)
            normalized.append({"label": "", "url": url})
            continue
        if not isinstance(item, dict):
            raise SystemExit(f"{item_label} must be a string or object")
        url = require_url(item.get("url"), f"{item_label}.url")
        link_label = optional_string(item.get("label"), f"{item_label}.label")
        normalized.append({"label": link_label, "url": url})
    return normalized


def require_url(value: Any, label: str) -> str:
    url = require_string(value, label)
    if not (url.startswith("http://") or url.startswith("https://")):
        raise SystemExit(f"{label} must start with http:// or https://")
    return url


def resolve_top_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    for key in TOP_ITEM_ALIASES:
        if key in data:
            value = data[key]
            if not isinstance(value, list):
                raise SystemExit(f"{key} must be a list")
            return value
    raise SystemExit("Missing top_items list")


def normalize_report(data: dict[str, Any]) -> dict[str, Any]:
    title = optional_string(data.get("title"), "title")
    date_value = optional_string(data.get("date"), "date")
    growth_label = optional_string(
        data.get("open_source_growth_label"),
        "open_source_growth_label",
    ) or "今日增长"
    if not title:
        if not date_value:
            raise SystemExit("Either title or date must be provided")
        title = f"AI每日简报 - {date_value}"

    top_items = [
        normalize_item(
            item,
            f"top_items[{index}]",
            open_source=False,
            single_link_only=True,
        )
        for index, item in enumerate(resolve_top_items(data), start=1)
    ]
    if not top_items:
        raise SystemExit("top_items must not be empty")

    raw_sections = data.get("sections")
    if not isinstance(raw_sections, dict):
        raise SystemExit("sections must be an object")

    sections: dict[str, list[dict[str, Any]]] = {}
    for key, value in raw_sections.items():
        if key not in SECTION_ALIASES:
            raise SystemExit(f"Unsupported section key: {key}")
        section_name = SECTION_ALIASES[key]
        if not isinstance(value, list):
            raise SystemExit(f"Section {section_name} must be a list")
        sections[section_name] = [
            normalize_item(
                item,
                f"sections.{section_name}[{index}]",
                open_source=section_name == "开源项目",
            )
            for index, item in enumerate(value, start=1)
        ]

    for section_name in SECTION_ORDER:
        sections.setdefault(section_name, [])

    return {
        "title": title,
        "date": date_value,
        "open_source_growth_label": growth_label,
        "top_items": top_items,
        "sections": sections,
    }


def normalize_item(
    item: Any,
    label: str,
    open_source: bool,
    single_link_only: bool = False,
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise SystemExit(f"{label} must be an object")

    title = require_string(item.get("title"), f"{label}.title")
    summary = optional_string(item.get("summary"), f"{label}.summary")
    links = normalize_links(item.get("links"), f"{label}.links")

    if not links:
        fallback_url = item.get("url")
        if fallback_url is not None:
            links = [{"label": "", "url": require_url(fallback_url, f"{label}.url")}]
    if not links:
        raise SystemExit(f"{label} requires at least one link")
    if single_link_only:
        links = links[:1]

    normalized = {
        "title": title,
        "summary": summary,
        "links": links,
    }

    if open_source:
        normalized["stars"] = normalize_stat(item.get("stars"), f"{label}.stars")
        normalized["today_stars"] = normalize_stat(
            item.get("today_stars"),
            f"{label}.today_stars",
        )

    return normalized


def normalize_stat(value: Any, label: str) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            return cleaned
    raise SystemExit(f"{label} must be an integer or non-empty string when present")


def render_markdown(report: dict[str, Any]) -> str:
    lines = [f"# {report['title']}", "", "## Top 10 最热 / 最前沿消息", ""]

    for index, item in enumerate(report["top_items"], start=1):
        lines.append(f"{index}. **{item['title']}**")
        if item["summary"]:
            lines.append(f"   {item['summary']}")
        lines.extend(render_links(item["links"], indent="   "))
        lines.append("")

    lines.extend(["## 更多新闻", ""])

    for section_name in SECTION_ORDER:
        lines.append(f"### {section_name}")
        section_items = report["sections"][section_name]
        if not section_items:
            lines.append("- 暂无")
            lines.append("")
            continue
        for item in section_items:
            first_line = f"- **{item['title']}**"
            if section_name == "开源项目":
                stats: list[str] = []
                if item["stars"]:
                    stats.append(f"Stars: {item['stars']}")
                if item["today_stars"]:
                    stats.append(
                        f"{report['open_source_growth_label']}: {item['today_stars']}"
                    )
                if stats:
                    first_line += " - " + " | ".join(stats)
            lines.append(first_line)
            if item["summary"]:
                if section_name == "开源项目":
                    lines.append("")
                lines.append(f"  {item['summary']}")
            lines.extend(render_links(item["links"], indent="  "))
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_links(links: list[dict[str, str]], indent: str) -> list[str]:
    rendered: list[str] = []
    for link in links:
        if link["label"]:
            rendered.append(f"{indent}链接（{link['label']}）: {link['url']}")
        else:
            rendered.append(f"{indent}链接: {link['url']}")
    return rendered


def write_text(path_str: str, content: str) -> Path:
    path = Path(path_str).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def main() -> int:
    args = parse_args()
    input_path, raw_data = load_json(args.json_path)
    report = normalize_report(raw_data)

    if args.validate_only:
        print(f"Validated report JSON: {input_path}")
        return 0

    markdown_text = render_markdown(report)

    if args.markdown_output:
        markdown_path = write_text(args.markdown_output, markdown_text)
        print(f"Rendered Markdown: {markdown_path}")
    else:
        print(markdown_text, end="")

    if args.wechat_html_output:
        html_path = write_text(
            args.wechat_html_output,
            markdown_to_wechat_html(markdown_text) + "\n",
        )
        print(f"Rendered WeChat HTML: {html_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
