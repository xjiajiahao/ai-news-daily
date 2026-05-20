#!/usr/bin/env python3
"""Create or publish a WeChat official account article from Markdown."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import uuid
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from markdown_utils import derive_title, load_markdown, markdown_to_wechat_html


TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
DRAFT_ADD_URL = "https://api.weixin.qq.com/cgi-bin/draft/add"
FREEPUBLISH_SUBMIT_URL = "https://api.weixin.qq.com/cgi-bin/freepublish/submit"
UPLOAD_IMAGE_URL = "https://api.weixin.qq.com/cgi-bin/media/uploadimg"
ADD_MATERIAL_URL = "https://api.weixin.qq.com/cgi-bin/material/add_material"
VALID_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}


@dataclass
class WeChatConfig:
    app_id: str
    app_secret: str
    author: str
    digest: str
    content_source_url: str
    thumb_media_id: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a WeChat official account draft from a Markdown file.",
    )
    parser.add_argument("markdown_path", help="Path to the Markdown file.")
    parser.add_argument(
        "--title",
        help="Override article title. Defaults to the first Markdown heading.",
    )
    parser.add_argument(
        "--author",
        help="Article author. Defaults to env WECHAT_AUTHOR.",
    )
    parser.add_argument(
        "--digest",
        help="Article digest. Defaults to env WECHAT_DEFAULT_DIGEST or Markdown intro.",
    )
    parser.add_argument(
        "--content-source-url",
        help="Original article URL. Defaults to env WECHAT_CONTENT_SOURCE_URL.",
    )
    parser.add_argument(
        "--thumb-media-id",
        help="Existing WeChat cover media_id. Overrides env WECHAT_DEFAULT_THUMB_MEDIA_ID.",
    )
    parser.add_argument(
        "--thumb-image",
        help="Upload a local or remote image as cover and use its media_id.",
    )
    parser.add_argument(
        "--open-comment",
        action="store_true",
        help="Enable article comments.",
    )
    parser.add_argument(
        "--fans-only-comment",
        action="store_true",
        help="Only fans can comment. Requires --open-comment.",
    )
    parser.add_argument(
        "--skip-image-upload",
        action="store_true",
        help="Do not rewrite Markdown image URLs through WeChat uploadimg.",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Submit the created draft for publish after draft creation.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print derived metadata and request payload without calling WeChat APIs.",
    )
    parser.add_argument(
        "--payload-output",
        help="Optional path to write the generated draft payload JSON.",
    )
    return parser.parse_args()


def read_config(args: argparse.Namespace) -> WeChatConfig:
    app_id = os.environ.get("WECHAT_APP_ID", "").strip()
    app_secret = os.environ.get("WECHAT_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise SystemExit("Missing WECHAT_APP_ID or WECHAT_APP_SECRET.")

    return WeChatConfig(
        app_id=app_id,
        app_secret=app_secret,
        author=(args.author or os.environ.get("WECHAT_AUTHOR", "")).strip(),
        digest=(args.digest or os.environ.get("WECHAT_DEFAULT_DIGEST", "")).strip(),
        content_source_url=(
            args.content_source_url or os.environ.get("WECHAT_CONTENT_SOURCE_URL", "")
        ).strip(),
        thumb_media_id=(
            args.thumb_media_id or os.environ.get("WECHAT_DEFAULT_THUMB_MEDIA_ID", "")
        ).strip(),
    )


def request_json(
    url: str,
    *,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    data: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    if params:
        query = urllib.parse.urlencode(params)
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{query}"

    request_headers = {"User-Agent": "Mozilla/5.0"}
    if headers:
        request_headers.update(headers)

    body = data
    if json_body is not None:
        body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json; charset=utf-8"

    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"HTTP {exc.code} for {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Network error for {url}: {exc}") from exc


def get_access_token(config: WeChatConfig) -> str:
    payload = request_json(
        TOKEN_URL,
        params={
            "grant_type": "client_credential",
            "appid": config.app_id,
            "secret": config.app_secret,
        },
    )
    if payload.get("access_token"):
        return str(payload["access_token"])
    raise_wechat_error("Failed to get access token", payload)
    raise AssertionError("unreachable")


def raise_wechat_error(prefix: str, payload: Dict[str, Any]) -> None:
    errcode = payload.get("errcode", payload.get("code"))
    errmsg = payload.get("errmsg", payload.get("msg", "unknown error"))
    raise SystemExit(f"{prefix}: errcode={errcode} errmsg={errmsg}")


def summarize_markdown(markdown_text: str) -> str:
    lines: list[str] = []
    for line in markdown_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or stripped.startswith("```"):
            continue
        stripped = re.sub(r"^[-*+]\s+", "", stripped)
        stripped = re.sub(r"^\d+\.\s+", "", stripped)
        if stripped:
            lines.append(stripped)
        if len(" ".join(lines)) >= 120:
            break
    digest = re.sub(r"\s+", " ", " ".join(lines)).strip()
    if len(digest) > 120:
        return digest[:119].rstrip() + "…"
    return digest


def build_multipart_form_data(field_name: str, filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = "----CodexBoundary" + uuid.uuid4().hex
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return body, boundary


def read_binary_from_path_or_url(value: str) -> tuple[bytes, str]:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme in {"http", "https"}:
        request = urllib.request.Request(value, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                content = response.read()
                filename = Path(parsed.path).name or "image"
                return content, filename
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise SystemExit(f"Failed to download image {value}: HTTP {exc.code} {detail}") from exc
        except urllib.error.URLError as exc:
            raise SystemExit(f"Failed to download image {value}: {exc}") from exc

    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"Image file not found: {path}")
    return path.read_bytes(), path.name


def ensure_image_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in VALID_IMAGE_EXTENSIONS:
        return filename
    return filename + ".png"


def upload_content_image(access_token: str, image_ref: str) -> str:
    content, filename = read_binary_from_path_or_url(image_ref)
    body, boundary = build_multipart_form_data("media", ensure_image_filename(filename), content)
    payload = request_json(
        UPLOAD_IMAGE_URL,
        method="POST",
        params={"access_token": access_token},
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    if payload.get("url"):
        return str(payload["url"])
    raise_wechat_error(f"Failed to upload inline image {image_ref}", payload)
    raise AssertionError("unreachable")


def upload_thumb_media(access_token: str, image_ref: str) -> str:
    content, filename = read_binary_from_path_or_url(image_ref)
    body, boundary = build_multipart_form_data("media", ensure_image_filename(filename), content)
    payload = request_json(
        ADD_MATERIAL_URL,
        method="POST",
        params={"access_token": access_token, "type": "image"},
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    if payload.get("media_id"):
        return str(payload["media_id"])
    raise_wechat_error(f"Failed to upload cover image {image_ref}", payload)
    raise AssertionError("unreachable")


def rewrite_inline_images(html_body: str, access_token: str) -> str:
    pattern = re.compile(r'(<img\b[^>]*\bsrc=")([^"]+)(")', re.IGNORECASE)
    cache: Dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        original = match.group(2)
        if original.startswith("data:"):
            return match.group(0)
        if original not in cache:
            cache[original] = upload_content_image(access_token, original)
        return f"{match.group(1)}{cache[original]}{match.group(3)}"

    return pattern.sub(replace, html_body)


def normalize_html_for_wechat(html_body: str) -> str:
    return html_body.replace("<hr />", "<hr>").replace("<br />", "<br>").strip()


def build_article_payload(
    *,
    title: str,
    author: str,
    digest: str,
    content: str,
    content_source_url: str,
    thumb_media_id: str,
    open_comment: bool,
    fans_only_comment: bool,
) -> Dict[str, Any]:
    if not thumb_media_id:
        raise SystemExit(
            "Missing cover media_id. Set WECHAT_DEFAULT_THUMB_MEDIA_ID, "
            "pass --thumb-media-id, or pass --thumb-image."
        )

    return {
        "articles": [
            {
                "title": title,
                "author": author,
                "digest": digest,
                "content": content,
                "content_source_url": content_source_url,
                "thumb_media_id": thumb_media_id,
                "need_open_comment": 1 if open_comment else 0,
                "only_fans_can_comment": 1 if fans_only_comment else 0,
            }
        ]
    }


def create_draft(access_token: str, payload: Dict[str, Any]) -> str:
    response = request_json(
        DRAFT_ADD_URL,
        method="POST",
        params={"access_token": access_token},
        json_body=payload,
    )
    if response.get("media_id"):
        return str(response["media_id"])
    raise_wechat_error("Failed to create draft", response)
    raise AssertionError("unreachable")


def submit_publish(access_token: str, media_id: str) -> str:
    response = request_json(
        FREEPUBLISH_SUBMIT_URL,
        method="POST",
        params={"access_token": access_token},
        json_body={"media_id": media_id},
    )
    publish_id = response.get("publish_id")
    if publish_id:
        return str(publish_id)
    if response.get("errcode") == 0:
        return ""
    raise_wechat_error("Failed to submit publish task", response)
    raise AssertionError("unreachable")


def main() -> int:
    args = parse_args()
    if args.fans_only_comment and not args.open_comment:
        raise SystemExit("--fans-only-comment requires --open-comment.")

    config = read_config(args)
    path, markdown_text = load_markdown(args.markdown_path)
    title = (args.title or derive_title(path, markdown_text, fallback="AI Daily")).strip()
    digest = config.digest or summarize_markdown(markdown_text)
    html_body = normalize_html_for_wechat(markdown_to_wechat_html(markdown_text))

    if args.dry_run:
        thumb_media_id = config.thumb_media_id or (
            f"<upload:{args.thumb_image}>" if args.thumb_image else ""
        )
        payload = build_article_payload(
            title=title,
            author=config.author,
            digest=digest,
            content=html_body,
            content_source_url=config.content_source_url,
            thumb_media_id=thumb_media_id,
            open_comment=args.open_comment,
            fans_only_comment=args.fans_only_comment,
        )
        if args.payload_output:
            Path(args.payload_output).expanduser().resolve().write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        print(f"markdown_path={path}")
        print(f"title={title}")
        print(f"author={config.author}")
        print(f"digest={digest}")
        print(f"thumb_media_id={thumb_media_id}")
        print(f"content_source_url={config.content_source_url}")
        print(f"publish={args.publish}")
        print(f"skip_image_upload={args.skip_image_upload}")
        print(f"html_chars={len(html_body)}")
        if args.payload_output:
            print(f"payload_output={Path(args.payload_output).expanduser().resolve()}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    access_token = get_access_token(config)
    thumb_media_id = config.thumb_media_id
    if args.thumb_image:
        thumb_media_id = upload_thumb_media(access_token, args.thumb_image)

    if not args.skip_image_upload:
        html_body = rewrite_inline_images(html_body, access_token)

    payload = build_article_payload(
        title=title,
        author=config.author,
        digest=digest,
        content=html_body,
        content_source_url=config.content_source_url,
        thumb_media_id=thumb_media_id,
        open_comment=args.open_comment,
        fans_only_comment=args.fans_only_comment,
    )

    if args.payload_output:
        Path(args.payload_output).expanduser().resolve().write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    media_id = create_draft(access_token, payload)
    print(f"Created WeChat draft for {path.name}: media_id={media_id}")

    if args.publish:
        publish_id = submit_publish(access_token, media_id)
        if publish_id:
            print(f"Submitted publish task: publish_id={publish_id}")
        else:
            print("Submitted publish task.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
