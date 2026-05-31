#!/usr/bin/env python3
"""Create or publish a WeChat official account article from Markdown."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import uuid
import struct
import zlib
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
SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_THUMB_IMAGE = SKILL_DIR / "asset" / "ai-news-daily.png"
DEFAULT_SMALL_THUMB_IMAGE = SKILL_DIR / "asset" / "ai-news-daily-small.png"
COVER_CACHE_PATH = SKILL_DIR / ".cache" / "wechat_cover_media.json"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


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
        help="Upload a local or remote image as the main cover and use its media_id.",
    )
    parser.add_argument(
        "--small-thumb-image",
        help=(
            "Local PNG to use as the 1:1 small cover. Defaults to "
            "asset/ai-news-daily-small.png when uploading a cover."
        ),
    )
    parser.add_argument(
        "--refresh-thumb-media",
        action="store_true",
        help="Re-upload the cover image and refresh the cached media_id.",
    )
    parser.add_argument(
        "--open-comment",
        dest="open_comment",
        action="store_true",
        default=True,
        help="Enable article comments. This is the default.",
    )
    parser.add_argument(
        "--no-open-comment",
        dest="open_comment",
        action="store_false",
        help="Disable article comments.",
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


def upload_thumb_media_bytes(access_token: str, content: bytes, filename: str) -> str:
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
    raise_wechat_error(f"Failed to upload cover image {filename}", payload)
    raise AssertionError("unreachable")


def upload_thumb_media(access_token: str, image_ref: str) -> str:
    content, filename = read_binary_from_path_or_url(image_ref)
    return upload_thumb_media_bytes(access_token, content, filename)


def load_cover_cache() -> Dict[str, Any]:
    if not COVER_CACHE_PATH.is_file():
        return {}
    try:
        payload = json.loads(COVER_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_cover_cache(cache: Dict[str, Any]) -> None:
    COVER_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    COVER_CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def cover_cache_key(app_id: str, mode: str, content: bytes) -> str:
    digest = hashlib.sha256(content).hexdigest()
    return f"{app_id}:{mode}:sha256:{digest}"


def get_cached_cover_media(cache_key: str) -> str:
    cached = load_cover_cache().get(cache_key)
    if isinstance(cached, dict):
        media_id = cached.get("media_id", "")
        if isinstance(media_id, str):
            return media_id
    return ""


def cache_cover_media(cache_key: str, media_id: str) -> None:
    cache = load_cover_cache()
    cache[cache_key] = {"media_id": media_id}
    save_cover_cache(cache)


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


def paeth_predictor(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def decode_png(path: Path) -> tuple[int, int, list[bytearray]]:
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise SystemExit(f"Small cover composition only supports PNG files: {path}")

    pos = len(PNG_SIGNATURE)
    width = height = bit_depth = color_type = None
    idat = bytearray()
    while pos < len(data):
        if pos + 8 > len(data):
            raise SystemExit(f"Invalid PNG file: {path}")
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        chunk_type = data[pos + 4 : pos + 8]
        chunk_data = data[pos + 8 : pos + 8 + length]
        pos += 12 + length

        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, compression, png_filter, interlace = (
                struct.unpack(">IIBBBBB", chunk_data)
            )
            if bit_depth != 8 or color_type not in {2, 6} or interlace != 0:
                raise SystemExit(f"Unsupported PNG format for cover composition: {path}")
            if compression != 0 or png_filter != 0:
                raise SystemExit(f"Unsupported PNG compression/filter method: {path}")
        elif chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            break

    if width is None or height is None or color_type is None:
        raise SystemExit(f"Invalid PNG file: {path}")

    channels = 4 if color_type == 6 else 3
    stride = width * channels
    raw = zlib.decompress(bytes(idat))
    rows: list[bytearray] = []
    cursor = 0
    prev = bytearray(stride)
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        scan = bytearray(raw[cursor : cursor + stride])
        cursor += stride
        recon = bytearray(stride)
        for i, value in enumerate(scan):
            left = recon[i - channels] if i >= channels else 0
            up = prev[i]
            up_left = prev[i - channels] if i >= channels else 0
            if filter_type == 0:
                recon[i] = value
            elif filter_type == 1:
                recon[i] = (value + left) & 0xFF
            elif filter_type == 2:
                recon[i] = (value + up) & 0xFF
            elif filter_type == 3:
                recon[i] = (value + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                recon[i] = (value + paeth_predictor(left, up, up_left)) & 0xFF
            else:
                raise SystemExit(f"Unsupported PNG filter type {filter_type}: {path}")
        rows.append(to_rgb_row(recon, channels))
        prev = recon
    return width, height, rows


def to_rgb_row(row: bytearray, channels: int) -> bytearray:
    if channels == 3:
        return row
    rgb = bytearray()
    for i in range(0, len(row), 4):
        alpha = row[i + 3] / 255
        rgb.extend(round(row[i + j] * alpha + 255 * (1 - alpha)) for j in range(3))
    return rgb


def encode_png(width: int, height: int, rows: list[bytearray]) -> bytes:
    def chunk(name: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + name
            + payload
            + struct.pack(">I", zlib.crc32(name + payload) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + bytes(row) for row in rows)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return PNG_SIGNATURE + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def center_crop_rows(
    width: int,
    height: int,
    rows: list[bytearray],
    target_ratio: float,
) -> tuple[int, int, list[bytearray]]:
    current_ratio = width / height
    if abs(current_ratio - target_ratio) < 0.0001:
        return width, height, rows

    if current_ratio > target_ratio:
        crop_width = max(1, round(height * target_ratio))
        left = (width - crop_width) // 2
        return crop_width, height, [
            bytearray(row[left * 3 : (left + crop_width) * 3]) for row in rows
        ]

    crop_height = max(1, round(width / target_ratio))
    top = (height - crop_height) // 2
    return width, crop_height, rows[top : top + crop_height]


def format_crop(x1: int, y1: int, x2: int, y2: int, width: int, height: int) -> str:
    values = (x1 / width, y1 / height, x2 / width, y2 / height)
    return "_".join(f"{value:.6f}".rstrip("0").rstrip(".") for value in values)


def build_composite_cover(main_image: Path, small_image: Path) -> tuple[bytes, str, str]:
    main_w, main_h, main_rows = decode_png(main_image)
    small_w, small_h, small_rows = decode_png(small_image)
    main_w, main_h, main_rows = center_crop_rows(main_w, main_h, main_rows, 2.35)
    small_w, small_h, small_rows = center_crop_rows(small_w, small_h, small_rows, 1.0)

    width = max(main_w, small_w)
    height = main_h + small_h
    blank = bytearray([255, 255, 255] * width)
    rows = [bytearray(blank) for _ in range(height)]

    for y, row in enumerate(main_rows):
        rows[y][0 : main_w * 3] = row
    for y, row in enumerate(small_rows, start=main_h):
        rows[y][0 : small_w * 3] = row

    pic_crop_235_1 = format_crop(0, 0, main_w, main_h, width, height)
    pic_crop_1_1 = format_crop(0, main_h, small_w, main_h + small_h, width, height)
    return encode_png(width, height, rows), pic_crop_235_1, pic_crop_1_1


def default_path(path: Path) -> str:
    return str(path) if path.is_file() else ""


def resolve_cover_images(args: argparse.Namespace) -> tuple[str, str]:
    main_image = args.thumb_image or default_path(DEFAULT_THUMB_IMAGE)
    small_image = args.small_thumb_image or (
        default_path(DEFAULT_SMALL_THUMB_IMAGE) if not args.thumb_image else ""
    )
    return main_image, small_image


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
    pic_crop_235_1: str = "",
    pic_crop_1_1: str = "",
) -> Dict[str, Any]:
    if not thumb_media_id:
        raise SystemExit(
            "Missing cover media_id. Set WECHAT_DEFAULT_THUMB_MEDIA_ID, "
            "pass --thumb-media-id, or pass --thumb-image."
        )

    article: Dict[str, Any] = {
        "title": title,
        "author": author,
        "digest": digest,
        "content": content,
        "content_source_url": content_source_url,
        "thumb_media_id": thumb_media_id,
        "need_open_comment": 1 if open_comment else 0,
        "only_fans_can_comment": 1 if fans_only_comment else 0,
    }
    if pic_crop_235_1:
        article["pic_crop_235_1"] = pic_crop_235_1
    if pic_crop_1_1:
        article["pic_crop_1_1"] = pic_crop_1_1

    return {"articles": [article]}


def upload_cover_and_crops(
    access_token: str,
    app_id: str,
    main_image: str,
    small_image: str,
    refresh_cache: bool,
) -> tuple[str, str, str]:
    main_path = Path(main_image).expanduser().resolve()
    small_path = Path(small_image).expanduser().resolve() if small_image else None
    if small_path:
        content, pic_crop_235_1, pic_crop_1_1 = build_composite_cover(main_path, small_path)
        cache_key = cover_cache_key(app_id, "composite-cover", content)
        cached_media_id = "" if refresh_cache else get_cached_cover_media(cache_key)
        if cached_media_id:
            return cached_media_id, pic_crop_235_1, pic_crop_1_1
        media_id = upload_thumb_media_bytes(access_token, content, "ai-news-daily-cover-composite.png")
        cache_cover_media(cache_key, media_id)
        return media_id, pic_crop_235_1, pic_crop_1_1

    content, filename = read_binary_from_path_or_url(main_image)
    cache_key = cover_cache_key(app_id, "single-cover", content)
    cached_media_id = "" if refresh_cache else get_cached_cover_media(cache_key)
    if cached_media_id:
        return cached_media_id, "", ""
    media_id = upload_thumb_media_bytes(access_token, content, filename)
    cache_cover_media(cache_key, media_id)
    return media_id, "", ""


def dry_run_cover_metadata(
    args: argparse.Namespace,
    config: WeChatConfig,
) -> tuple[str, str, str, str, str]:
    if args.thumb_media_id:
        return config.thumb_media_id, "", "", "", ""

    main_image, small_image = resolve_cover_images(args)
    if main_image:
        if small_image:
            content, pic_crop_235_1, pic_crop_1_1 = build_composite_cover(
                Path(main_image).expanduser().resolve(),
                Path(small_image).expanduser().resolve(),
            )
            cache_key = cover_cache_key(config.app_id, "composite-cover", content)
            cached_media_id = "" if args.refresh_thumb_media else get_cached_cover_media(cache_key)
            thumb_media_id = cached_media_id or f"<upload-composite:{main_image}+{small_image}>"
            return thumb_media_id, pic_crop_235_1, pic_crop_1_1, main_image, small_image
        content, _ = read_binary_from_path_or_url(main_image)
        cache_key = cover_cache_key(config.app_id, "single-cover", content)
        cached_media_id = "" if args.refresh_thumb_media else get_cached_cover_media(cache_key)
        return cached_media_id or f"<upload:{main_image}>", "", "", main_image, ""

    return config.thumb_media_id, "", "", "", ""


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
        thumb_media_id, pic_crop_235_1, pic_crop_1_1, main_image, small_image = (
            dry_run_cover_metadata(args, config)
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
            pic_crop_235_1=pic_crop_235_1,
            pic_crop_1_1=pic_crop_1_1,
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
        if main_image:
            print(f"thumb_image={main_image}")
        if small_image:
            print(f"small_thumb_image={small_image}")
        if pic_crop_235_1:
            print(f"pic_crop_235_1={pic_crop_235_1}")
        if pic_crop_1_1:
            print(f"pic_crop_1_1={pic_crop_1_1}")
        print(f"content_source_url={config.content_source_url}")
        print(f"open_comment={args.open_comment}")
        print(f"fans_only_comment={args.fans_only_comment}")
        print(f"publish={args.publish}")
        print(f"skip_image_upload={args.skip_image_upload}")
        print(f"html_chars={len(html_body)}")
        if args.payload_output:
            print(f"payload_output={Path(args.payload_output).expanduser().resolve()}")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    access_token = get_access_token(config)
    pic_crop_235_1 = ""
    pic_crop_1_1 = ""
    if args.thumb_media_id:
        thumb_media_id = config.thumb_media_id
    else:
        main_image, small_image = resolve_cover_images(args)
        if main_image:
            thumb_media_id, pic_crop_235_1, pic_crop_1_1 = upload_cover_and_crops(
                access_token,
                config.app_id,
                main_image,
                small_image,
                args.refresh_thumb_media,
            )
        else:
            thumb_media_id = config.thumb_media_id

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
        pic_crop_235_1=pic_crop_235_1,
        pic_crop_1_1=pic_crop_1_1,
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
