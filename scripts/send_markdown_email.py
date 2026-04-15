#!/usr/bin/env python3
"""Send a Markdown file as an email body via SMTP."""

from __future__ import annotations

import argparse
import html
import mimetypes
import os
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from pathlib import Path
from typing import Iterable


REQUIRED_ENV_VARS = ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD")
VALID_SECURITY = {"auto", "ssl", "starttls", "plain"}


@dataclass
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    from_name: str
    security: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a Markdown file as an email body via SMTP.",
    )
    parser.add_argument("markdown_path", help="Path to the Markdown file.")
    parser.add_argument("recipient", help="Recipient email address.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and print derived metadata without sending email.",
    )
    return parser.parse_args()


def read_config() -> SmtpConfig:
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        raise SystemExit(
            "Missing required environment variables: " + ", ".join(missing)
        )

    port_raw = os.environ["SMTP_PORT"]
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise SystemExit(f"SMTP_PORT must be an integer, got: {port_raw!r}") from exc

    security = os.environ.get("SMTP_SECURITY", "auto").lower()
    if security not in VALID_SECURITY:
        raise SystemExit(
            "SMTP_SECURITY must be one of: " + ", ".join(sorted(VALID_SECURITY))
        )

    return SmtpConfig(
        host=os.environ["SMTP_HOST"],
        port=port,
        user=os.environ["SMTP_USER"],
        password=os.environ["SMTP_PASSWORD"],
        from_name=os.environ.get("SMTP_FROM_NAME", ""),
        security=resolve_security(security, port),
    )


def resolve_security(security: str, port: int) -> str:
    if security != "auto":
        return security
    if port == 465:
        return "ssl"
    if port == 587:
        return "starttls"
    return "plain"


def validate_email(value: str, label: str) -> str:
    _, address = parseaddr(value)
    if not address or "@" not in address:
        raise SystemExit(f"Invalid {label} email address: {value!r}")
    return address


def load_markdown(path_str: str) -> tuple[Path, str]:
    path = Path(path_str).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"Markdown file not found: {path}")
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"Markdown file must be UTF-8 encoded: {path}") from exc
    return path, content


def derive_subject(path: Path, markdown_text: str) -> str:
    lines = markdown_text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        heading = re.match(r"^#{1,6}\s+(.+?)\s*$", stripped)
        if heading:
            return cleanup_subject(heading.group(1))
        if index + 1 < len(lines):
            underline = lines[index + 1].strip()
            if underline and set(underline) <= {"=", "-"}:
                return cleanup_subject(stripped)
        break
    return cleanup_subject(path.stem)


def cleanup_subject(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.replace("`", "")).strip()
    return cleaned or "Markdown Email"


def markdown_to_html(markdown_text: str) -> str:
    try:
        import markdown as markdown_lib  # type: ignore

        body = markdown_lib.markdown(
            markdown_text,
            extensions=["fenced_code", "tables", "nl2br"],
        )
        return wrap_html(body)
    except ImportError:
        return wrap_html(simple_markdown_to_html(markdown_text))


def wrap_html(body: str) -> str:
    return (
        "<html><body "
        "style=\"font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        "line-height:1.6;color:#1f2328;max-width:720px;margin:0 auto;padding:24px;\">"
        f"{body}</body></html>"
    )


def simple_markdown_to_html(markdown_text: str) -> str:
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
                    "<pre><code>"
                    + html.escape("\n".join(code_lines))
                    + "</code></pre>"
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

        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", stripped)
        if heading:
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{format_inline(heading.group(2))}</h{level}>")
            i += 1
            continue

        if (
            i + 1 < len(lines)
            and lines[i + 1].strip()
            and set(lines[i + 1].strip()) <= {"=", "-"}
        ):
            level = 1 if "=" in lines[i + 1] else 2
            blocks.append(f"<h{level}>{format_inline(stripped)}</h{level}>")
            i += 2
            continue

        if re.match(r"^[-*+]\s+", stripped):
            items, i = consume_list(lines, i, ordered=False)
            blocks.append("<ul>" + "".join(items) + "</ul>")
            continue

        if re.match(r"^\d+\.\s+", stripped):
            items, i = consume_list(lines, i, ordered=True)
            blocks.append("<ol>" + "".join(items) + "</ol>")
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
        blocks.append("<p>" + format_inline(" ".join(paragraph)) + "</p>")

    if in_code_block and code_lines:
        blocks.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")

    return "\n".join(blocks)


def consume_list(lines: list[str], start: int, ordered: bool) -> tuple[list[str], int]:
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

        items.append("<li>" + render_list_item(item_lines) + "</li>")

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


def render_list_item(lines: list[str]) -> str:
    chunks: list[str] = []
    paragraph: list[str] = []

    for line in lines:
        if not line:
            if paragraph:
                chunks.append("<p>" + format_inline(" ".join(paragraph)) + "</p>")
                paragraph = []
            continue
        paragraph.append(line)

    if paragraph:
        chunks.append("<p>" + format_inline(" ".join(paragraph)) + "</p>")

    if len(chunks) == 1 and chunks[0].startswith("<p>") and chunks[0].endswith("</p>"):
        return chunks[0][3:-4]
    return "".join(chunks)


def format_inline(text: str) -> str:
    escaped = html.escape(text)
    replacements: Iterable[tuple[str, str]] = (
        (r"\*\*(.+?)\*\*", r"<strong>\1</strong>"),
        (r"__(.+?)__", r"<strong>\1</strong>"),
        (r"\*(.+?)\*", r"<em>\1</em>"),
        (r"_(.+?)_", r"<em>\1</em>"),
        (r"`(.+?)`", r"<code>\1</code>"),
        (r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>'),
    )
    for pattern, replacement in replacements:
        escaped = re.sub(pattern, replacement, escaped)
    return escaped


def build_message(
    config: SmtpConfig,
    markdown_path: Path,
    recipient: str,
    subject: str,
    markdown_text: str,
) -> EmailMessage:
    message = EmailMessage()
    from_display = (
        formataddr((config.from_name, config.user)) if config.from_name else config.user
    )
    message["From"] = from_display
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(markdown_text)
    message.add_alternative(markdown_to_html(markdown_text), subtype="html")
    content_type, _ = mimetypes.guess_type(markdown_path.name)
    if content_type:
        maintype, subtype = content_type.split("/", 1)
    else:
        maintype, subtype = "text", "markdown"
    message.add_attachment(
        markdown_path.read_bytes(),
        maintype=maintype,
        subtype=subtype,
        filename=markdown_path.name,
    )
    return message


def send_message(config: SmtpConfig, message: EmailMessage) -> None:
    if config.security == "ssl":
        with smtplib.SMTP_SSL(
            config.host,
            config.port,
            context=ssl.create_default_context(),
        ) as server:
            server.login(config.user, config.password)
            server.send_message(message)
        return

    with smtplib.SMTP(config.host, config.port) as server:
        server.ehlo()
        if config.security == "starttls":
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        server.login(config.user, config.password)
        server.send_message(message)


def main() -> None:
    args = parse_args()
    config = read_config()
    sender = validate_email(config.user, "SMTP_USER")
    recipient = validate_email(args.recipient, "recipient")
    path, markdown_text = load_markdown(args.markdown_path)
    subject = derive_subject(path, markdown_text)
    message = build_message(config, path, recipient, subject, markdown_text)

    if args.dry_run:
        print(f"markdown_path={path}")
        print(f"subject={subject}")
        print(f"from={sender}")
        print(f"to={recipient}")
        print(f"security={config.security}")
        print(f"html_part_bytes={len(message.get_payload()[1].as_bytes())}")
        print(f"attachment={path.name}")
        print(f"attachment_bytes={path.stat().st_size}")
        return

    send_message(config, message)
    print(f"Sent {path.name} to {recipient} with subject: {subject}")


if __name__ == "__main__":
    main()
