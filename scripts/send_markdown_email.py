#!/usr/bin/env python3
"""Send a Markdown file as an email body via SMTP."""

from __future__ import annotations

import argparse
import mimetypes
import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from pathlib import Path
from typing import Iterable

from markdown_utils import derive_title, load_markdown, markdown_to_html, wrap_html_document


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
    parser.add_argument(
        "recipients",
        nargs="+",
        help="One or more recipient email addresses.",
    )
    parser.add_argument(
        "--cc",
        action="append",
        nargs="+",
        default=[],
        help="One or more CC email addresses. Repeatable.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and print derived metadata without sending email.",
    )
    parser.add_argument(
        "--attach",
        action="append",
        default=[],
        help="Optional extra attachment paths. Repeatable.",
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


def flatten_addresses(values: Iterable[Iterable[str]]) -> list[str]:
    flattened: list[str] = []
    for group in values:
        flattened.extend(group)
    return flattened


def validate_emails(values: Iterable[str], label: str) -> list[str]:
    validated: list[str] = []
    for value in values:
        validated.append(validate_email(value, label))
    return validated


def build_message(
    config: SmtpConfig,
    markdown_path: Path,
    recipients: list[str],
    cc_recipients: list[str],
    subject: str,
    markdown_text: str,
    extra_attachments: list[Path],
) -> EmailMessage:
    message = EmailMessage()
    from_display = (
        formataddr((config.from_name, config.user)) if config.from_name else config.user
    )
    message["From"] = from_display
    message["To"] = ", ".join(recipients)
    if cc_recipients:
        message["Cc"] = ", ".join(cc_recipients)
    message["Subject"] = subject
    message.set_content(markdown_text)
    message.add_alternative(
        wrap_html_document(markdown_to_html(markdown_text)),
        subtype="html",
    )
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
    for attachment_path in extra_attachments:
        content_type, _ = mimetypes.guess_type(attachment_path.name)
        if content_type:
            maintype, subtype = content_type.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"
        message.add_attachment(
            attachment_path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=attachment_path.name,
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
    recipients = validate_emails(args.recipients, "recipient")
    cc_recipients = validate_emails(flatten_addresses(args.cc), "cc recipient")
    path, markdown_text = load_markdown(args.markdown_path)
    extra_attachments = [Path(raw).expanduser().resolve() for raw in args.attach]
    missing_attachments = [str(item) for item in extra_attachments if not item.is_file()]
    if missing_attachments:
        raise SystemExit(
            "Attachment file(s) not found: " + ", ".join(missing_attachments)
        )
    subject = derive_title(path, markdown_text, fallback="Markdown Email")
    message = build_message(
        config,
        path,
        recipients,
        cc_recipients,
        subject,
        markdown_text,
        extra_attachments,
    )

    if args.dry_run:
        print(f"markdown_path={path}")
        print(f"subject={subject}")
        print(f"from={sender}")
        print(f"to={', '.join(recipients)}")
        if cc_recipients:
            print(f"cc={', '.join(cc_recipients)}")
        print(f"security={config.security}")
        print(f"html_part_bytes={len(message.get_payload()[1].as_bytes())}")
        print(f"attachment={path.name}")
        print(f"attachment_bytes={path.stat().st_size}")
        for attachment_path in extra_attachments:
            print(f"extra_attachment={attachment_path.name}")
            print(f"extra_attachment_bytes={attachment_path.stat().st_size}")
        return

    send_message(config, message)
    delivered_to = recipients + cc_recipients
    print(f"Sent {path.name} to {', '.join(delivered_to)} with subject: {subject}")


if __name__ == "__main__":
    main()
