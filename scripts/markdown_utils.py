#!/usr/bin/env python3
"""Utilities for loading Markdown and rendering lightweight HTML."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Iterable

WECHAT_STYLES = {
    "body": (
        "max-width:677px;margin:0 auto;padding:8px 0;"
        "font-size:15px;line-height:1.8;color:#2c2c2c;"
        "letter-spacing:0.02em;text-align:left;"
    ),
    "h1": (
        "margin:0 0 28px;padding:0 0 18px;"
        "font-size:28px;line-height:1.35;font-weight:700;color:#111827;"
        "text-align:center;border-bottom:2px solid #dbe4f0;"
    ),
    "h2": (
        "margin:32px 0 16px;padding:10px 14px;"
        "font-size:22px;line-height:1.45;font-weight:700;color:#16324f;"
        "background:#eef5ff;border-left:4px solid #3b82f6;border-radius:6px;"
    ),
    "h3": (
        "margin:26px 0 12px;padding:0;"
        "font-size:18px;line-height:1.5;font-weight:700;color:#1f2937;"
    ),
    "p": "margin:12px 0;font-size:15px;line-height:1.85;color:#2c2c2c;",
    "ol": (
        "margin:18px 0;padding-left:1.6em;list-style:decimal;"
        "font-size:15px;line-height:1.85;color:#2c2c2c;"
    ),
    "ul": (
        "margin:16px 0;padding-left:1.4em;list-style:disc;"
        "font-size:15px;line-height:1.85;color:#2c2c2c;"
    ),
    "li": "margin:0 0 18px 0;padding-left:0.1em;",
    "li_p": "margin:0 0 8px 0;font-size:15px;line-height:1.85;color:#2c2c2c;",
    "a": (
        "color:#2755a5;text-decoration:none;"
        "border-bottom:1px solid rgba(39,85,165,0.25);word-break:break-all;"
    ),
    "strong": "font-weight:700;color:#111827;",
    "em": "font-style:italic;color:#374151;",
    "code": (
        "display:inline-block;padding:1px 6px;margin:0 2px;"
        "font-family:Menlo,Consolas,monospace;font-size:0.92em;"
        "color:#b42318;background:#fff1f3;border-radius:4px;"
    ),
    "pre": (
        "margin:18px 0;padding:14px 16px;overflow-x:auto;"
        "background:#0f172a;color:#e5e7eb;border-radius:8px;"
    ),
    "pre_code": (
        "display:block;padding:0;margin:0;background:none;color:inherit;"
        "font-family:Menlo,Consolas,monospace;font-size:13px;line-height:1.7;"
    ),
    "blockquote": (
        "margin:18px 0;padding:10px 14px;color:#475569;"
        "background:#f8fafc;border-left:4px solid #cbd5e1;"
    ),
}


def load_markdown(path_str: str) -> tuple[Path, str]:
    path = Path(path_str).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"Markdown file not found: {path}")
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"Markdown file must be UTF-8 encoded: {path}") from exc
    return path, content


def derive_title(path: Path, markdown_text: str, fallback: str = "Markdown Document") -> str:
    lines = markdown_text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        heading = re.match(r"^#{1,6}\s+(.+?)\s*$", stripped)
        if heading:
            return cleanup_title(heading.group(1), fallback)
        if index + 1 < len(lines):
            underline = lines[index + 1].strip()
            if underline and set(underline) <= {"=", "-"}:
                return cleanup_title(stripped, fallback)
        break
    return cleanup_title(path.stem, fallback)


def cleanup_title(value: str, fallback: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.replace("`", "")).strip()
    return cleaned or fallback


def markdown_to_html(markdown_text: str) -> str:
    try:
        import markdown as markdown_lib  # type: ignore

        return markdown_lib.markdown(
            markdown_text,
            extensions=["fenced_code", "tables", "nl2br"],
        )
    except ImportError:
        return simple_markdown_to_html(markdown_text)


def wrap_html_document(body: str) -> str:
    return (
        "<html><body "
        "style=\"font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        "line-height:1.6;color:#1f2328;max-width:720px;margin:0 auto;padding:24px;\">"
        f"{body}</body></html>"
    )


def markdown_to_wechat_html(markdown_text: str) -> str:
    body = simple_markdown_to_html(markdown_text, wechat_style=True)
    return f'<section style="{WECHAT_STYLES["body"]}">{body}</section>'


def simple_markdown_to_html(markdown_text: str, wechat_style: bool = False) -> str:
    blocks: list[str] = []
    lines = markdown_text.splitlines()
    i = 0
    in_code_block = False
    code_lines: list[str] = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code_block:
                blocks.append(
                    open_tag("pre", wechat_style)
                    + open_tag("code", wechat_style, nested_in="pre")
                    + html.escape("\n".join(code_lines))
                    + close_tag("code")
                    + close_tag("pre")
                )
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        if not stripped:
            i += 1
            continue

        if stripped.startswith(">"):
            quote_lines = [stripped[1:].strip()]
            i += 1
            while i < len(lines):
                next_line = lines[i].strip()
                if not next_line.startswith(">"):
                    break
                quote_lines.append(next_line[1:].strip())
                i += 1
            blocks.append(
                open_tag("blockquote", wechat_style)
                + format_inline(" ".join(part for part in quote_lines if part), wechat_style)
                + close_tag("blockquote")
            )
            continue

        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", stripped)
        if heading:
            level = len(heading.group(1))
            blocks.append(
                open_tag(f"h{level}", wechat_style)
                + format_inline(heading.group(2), wechat_style)
                + close_tag(f"h{level}")
            )
            i += 1
            continue

        if (
            i + 1 < len(lines)
            and lines[i + 1].strip()
            and set(lines[i + 1].strip()) <= {"=", "-"}
        ):
            level = 1 if "=" in lines[i + 1] else 2
            blocks.append(
                open_tag(f"h{level}", wechat_style)
                + format_inline(stripped, wechat_style)
                + close_tag(f"h{level}")
            )
            i += 2
            continue

        if re.match(r"^[-*+]\s+", stripped):
            items, i = consume_list(lines, i, ordered=False, wechat_style=wechat_style)
            blocks.append(open_tag("ul", wechat_style) + "".join(items) + close_tag("ul"))
            continue

        if re.match(r"^\d+\.\s+", stripped):
            items, i = consume_list(lines, i, ordered=True, wechat_style=wechat_style)
            blocks.append(open_tag("ol", wechat_style) + "".join(items) + close_tag("ol"))
            continue

        paragraph: list[str] = [stripped]
        i += 1
        while i < len(lines):
            next_line = lines[i].strip()
            if not next_line:
                break
            if (
                next_line.startswith("```")
                or re.match(r"^(#{1,6})\s+", next_line)
                or re.match(r"^[-*+]\s+", next_line)
                or re.match(r"^\d+\.\s+", next_line)
            ):
                break
            paragraph.append(next_line)
            i += 1
        blocks.append(
            open_tag("p", wechat_style)
            + format_inline(" ".join(paragraph), wechat_style)
            + close_tag("p")
        )

    if in_code_block and code_lines:
        blocks.append(
            open_tag("pre", wechat_style)
            + open_tag("code", wechat_style, nested_in="pre")
            + html.escape("\n".join(code_lines))
            + close_tag("code")
            + close_tag("pre")
        )

    return "\n".join(blocks)


def consume_list(
    lines: list[str],
    start: int,
    ordered: bool,
    wechat_style: bool = False,
) -> tuple[list[str], int]:
    items: list[str] = []
    marker_pattern = r"^\d+\.\s+" if ordered else r"^[-*+]\s+"
    i = start

    while i < len(lines):
        stripped = lines[i].strip()
        if not re.match(marker_pattern, stripped):
            break

        item_lines = [re.sub(marker_pattern, "", stripped)]
        i += 1

        while i < len(lines):
            raw_line = lines[i]
            next_line = raw_line.strip()

            if not next_line:
                if i + 1 < len(lines) and should_continue_list_item(
                    lines, i + 1, ordered
                ):
                    item_lines.append("")
                    i += 1
                    continue
                break

            if starts_block(next_line):
                break

            if raw_line.startswith((" ", "\t")):
                item_lines.append(next_line)
                i += 1
                continue

            if ordered and re.match(r"^\d+\.\s+", next_line):
                break

            if not ordered and re.match(r"^[-*+]\s+", next_line):
                break

            item_lines.append(next_line)
            i += 1

        items.append(
            open_tag("li", wechat_style)
            + render_list_item(item_lines, wechat_style)
            + close_tag("li")
        )

        while i < len(lines) and not lines[i].strip():
            if i + 1 < len(lines) and should_continue_list_item(lines, i + 1, ordered):
                break
            i += 1

    return items, i


def should_continue_list_item(lines: list[str], index: int, ordered: bool) -> bool:
    if index >= len(lines):
        return False
    stripped = lines[index].strip()
    if not stripped:
        return False
    if starts_block(stripped):
        return False
    marker_pattern = r"^\d+\.\s+" if ordered else r"^[-*+]\s+"
    return not re.match(marker_pattern, stripped)


def starts_block(stripped: str) -> bool:
    return bool(
        stripped.startswith("```")
        or re.match(r"^(#{1,6})\s+", stripped)
        or re.match(r"^[-*+]\s+", stripped)
        or re.match(r"^\d+\.\s+", stripped)
    )


def render_list_item(lines: list[str], wechat_style: bool = False) -> str:
    chunks: list[str] = []
    paragraph: list[str] = []

    for line in lines:
        if re.match(r"^(链接|Link)[:：]\s*", line) and paragraph:
            chunks.append(
                open_tag("p", wechat_style, nested_in="li")
                + format_inline(" ".join(paragraph), wechat_style)
                + close_tag("p")
            )
            paragraph = []
        if not line:
            if paragraph:
                chunks.append(
                    open_tag("p", wechat_style, nested_in="li")
                    + format_inline(" ".join(paragraph), wechat_style)
                    + close_tag("p")
                )
                paragraph = []
            continue
        paragraph.append(line)

    if paragraph:
        chunks.append(
            open_tag("p", wechat_style, nested_in="li")
            + format_inline(" ".join(paragraph), wechat_style)
            + close_tag("p")
        )

    if (
        not wechat_style
        and len(chunks) == 1
        and chunks[0].startswith("<p>")
        and chunks[0].endswith("</p>")
    ):
        return chunks[0][3:-4]
    return "".join(chunks)


def format_inline(text: str, wechat_style: bool = False) -> str:
    escaped = html.escape(text)
    placeholders: list[str] = []

    def stash(match: re.Match[str]) -> str:
        placeholders.append(match.group(0))
        return f"@@INLINE_{len(placeholders) - 1}@@"

    escaped = re.sub(r"!\[(.*?)\]\((.+?)\)", stash, escaped)
    escaped = re.sub(r"`(.+?)`", stash, escaped)
    escaped = re.sub(r"\[(.+?)\]\((.+?)\)", stash, escaped)
    escaped = re.sub(r"https?://[^\s<]+", stash, escaped)

    replacements: Iterable[tuple[str, str]] = (
        (r"\*\*(.+?)\*\*", r"<strong>\1</strong>"),
        (r"__(.+?)__", r"<strong>\1</strong>"),
        (r"(?<!\w)\*(.+?)\*(?!\w)", r"<em>\1</em>"),
        (r"(?<!\w)_(.+?)_(?!\w)", r"<em>\1</em>"),
    )
    for pattern, replacement in replacements:
        escaped = re.sub(pattern, replacement, escaped)

    for index, raw in enumerate(placeholders):
        if raw.startswith("!["):
            match = re.match(r"!\[(.*?)\]\((.+?)\)", raw)
            if match:
                alt = html.escape(match.group(1))
                style = (
                    ' style="display:block;max-width:100%;height:auto;margin:18px auto;'
                    'border-radius:8px;"'
                    if wechat_style
                    else ""
                )
                rendered = f'<img src="{match.group(2)}" alt="{alt}"{style} />'
            else:
                rendered = raw
        elif raw.startswith("`") and raw.endswith("`"):
            rendered = open_tag("code", wechat_style) + raw[1:-1] + close_tag("code")
        elif raw.startswith("["):
            match = re.match(r"\[(.+?)\]\((.+?)\)", raw)
            if match:
                rendered = (
                    open_tag("a", wechat_style, href=match.group(2))
                    + match.group(1)
                    + close_tag("a")
                )
            else:
                rendered = raw
        else:
            rendered = open_tag("a", wechat_style, href=raw) + raw + close_tag("a")
        escaped = escaped.replace(f"@@INLINE_{index}@@", rendered)

    if wechat_style:
        escaped = escaped.replace(
            "<strong>",
            f'<strong style="{WECHAT_STYLES["strong"]}">',
        ).replace(
            "<em>",
            f'<em style="{WECHAT_STYLES["em"]}">',
        )

    return escaped


def open_tag(
    tag: str,
    wechat_style: bool,
    nested_in: str = "",
    href: str = "",
) -> str:
    if tag == "a":
        attrs = f' href="{href}"'
        if wechat_style:
            attrs += f' style="{WECHAT_STYLES["a"]}"'
        return f"<a{attrs}>"

    if not wechat_style:
        return f"<{tag}>"

    style_key = "pre_code" if tag == "code" and nested_in == "pre" else tag
    if tag == "p" and nested_in == "li":
        style_key = "li_p"
    if style_key not in WECHAT_STYLES and tag.startswith("h"):
        style_key = "h3"
    return f'<{tag} style="{WECHAT_STYLES[style_key]}">'


def close_tag(tag: str) -> str:
    return f"</{tag}>"
