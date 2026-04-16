#!/usr/bin/env python3
"""Fetch recent WeChat public account articles via mptext.top."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_BASE_URL = "https://down.mptext.top"
DEFAULT_ACCOUNT_CONFIG = (
    Path(__file__).resolve().parents[1] / "references" / "source_accounts.json"
)
DEFAULT_RETRY_ATTEMPTS = 3
DEFAULT_RETRY_BACKOFF_SECONDS = 1.5


class MpTextError(RuntimeError):
    """Raised when the mptext API returns an unexpected result."""


@dataclass
class AccountSpec:
    name: str
    search_keyword: str
    expected_nickname: Optional[str] = None
    expected_alias: Optional[str] = None
    preferred_fakeid: Optional[str] = None

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "AccountSpec":
        return cls(
            name=raw["name"],
            search_keyword=raw.get("search_keyword", raw["name"]),
            expected_nickname=raw.get("expected_nickname"),
            expected_alias=raw.get("expected_alias"),
            preferred_fakeid=raw.get("preferred_fakeid"),
        )

    @classmethod
    def ad_hoc(cls, name: str) -> "AccountSpec":
        return cls(name=name, search_keyword=name, expected_nickname=name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve configured WeChat official accounts and fetch article lists."
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("MPTEXT_API_KEY"),
        help="mptext API key. Defaults to env MPTEXT_API_KEY.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("MPTEXT_BASE_URL", DEFAULT_BASE_URL),
        help=f"mptext base URL. Defaults to {DEFAULT_BASE_URL}.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_ACCOUNT_CONFIG),
        help="Path to the account config JSON file.",
    )
    parser.add_argument(
        "--account",
        action="append",
        default=[],
        help="Limit fetching to a configured account name. Repeatable.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="How many articles to fetch per account. Max 20 per mptext API.",
    )
    parser.add_argument(
        "--begin",
        type=int,
        default=0,
        help="Pagination offset for the article list endpoint.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Keep only articles published within the last N days.",
    )
    parser.add_argument(
        "--search-size",
        type=int,
        default=10,
        help="How many account search candidates to inspect.",
    )
    parser.add_argument(
        "--json-output",
        help="Optional path to write the JSON result.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print compact JSON instead of pretty JSON.",
    )
    parser.add_argument(
        "--summary-max-chars",
        type=int,
        default=180,
        help="Maximum number of characters kept from the digest field.",
    )
    return parser.parse_args()


def build_headers(api_key: str) -> Dict[str, str]:
    return {
        "X-Auth-Key": api_key,
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }


def request_json(
    base_url: str,
    api_key: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    query = urllib.parse.urlencode(params or {})
    url = f"{base_url.rstrip('/')}{path}"
    if query:
        url = f"{url}?{query}"

    request = urllib.request.Request(url, headers=build_headers(api_key))
    for attempt in range(1, DEFAULT_RETRY_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise MpTextError(f"HTTP {exc.code} for {url}: {detail}") from exc
        except (
            urllib.error.URLError,
            http.client.RemoteDisconnected,
            TimeoutError,
            socket.timeout,
            ConnectionResetError,
        ) as exc:
            if attempt >= DEFAULT_RETRY_ATTEMPTS:
                raise MpTextError(f"Network error for {url}: {exc}") from exc
            time.sleep(DEFAULT_RETRY_BACKOFF_SECONDS * attempt)

    raise MpTextError(f"Network error for {url}: exhausted retries")


def load_account_specs(config_path: str) -> List[AccountSpec]:
    with open(config_path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return [AccountSpec.from_dict(item) for item in raw["accounts"]]


def pick_specs(all_specs: Iterable[AccountSpec], names: List[str]) -> List[AccountSpec]:
    by_name = {spec.name: spec for spec in all_specs}
    if not names:
        return list(all_specs)

    picked: List[AccountSpec] = []
    for name in names:
        picked.append(by_name.get(name, AccountSpec.ad_hoc(name)))
    return picked


def score_candidate(spec: AccountSpec, candidate: Dict[str, Any]) -> int:
    score = 0
    nickname = candidate.get("nickname", "")
    alias = candidate.get("alias", "")
    fakeid = candidate.get("fakeid", "")

    if spec.preferred_fakeid and fakeid == spec.preferred_fakeid:
        score += 1000
    if spec.expected_nickname and nickname == spec.expected_nickname:
        score += 500
    if nickname == spec.name:
        score += 400
    if spec.expected_alias and alias == spec.expected_alias:
        score += 300
    if nickname == spec.search_keyword:
        score += 200
    if spec.search_keyword and spec.search_keyword in nickname:
        score += 100
    if spec.expected_alias and spec.expected_alias and spec.expected_alias in alias:
        score += 50
    if candidate.get("verify_status") == 2:
        score += 20

    return score


def resolve_account(
    spec: AccountSpec,
    base_url: str,
    api_key: str,
    search_size: int,
) -> Dict[str, Any]:
    payload = request_json(
        base_url,
        api_key,
        "/api/public/v1/account",
        {"keyword": spec.search_keyword},
    )
    candidates = payload.get("list") or []
    if not candidates:
        raise MpTextError(f"No account candidates found for {spec.name}.")

    ranked = sorted(
        candidates[:search_size],
        key=lambda item: score_candidate(spec, item),
        reverse=True,
    )
    best = ranked[0]
    best_score = score_candidate(spec, best)

    if spec.expected_nickname or spec.expected_alias or spec.preferred_fakeid:
        exact_match = any(
            [
                spec.preferred_fakeid and best.get("fakeid") == spec.preferred_fakeid,
                spec.expected_nickname and best.get("nickname") == spec.expected_nickname,
                spec.expected_alias and best.get("alias") == spec.expected_alias,
                best.get("nickname") == spec.name,
            ]
        )
        if not exact_match or best_score <= 0:
            raise MpTextError(
                f"Could not safely resolve {spec.name}; top candidate was "
                f"{best.get('nickname')} ({best.get('alias')}, {best.get('fakeid')})."
            )

    return best


def normalize_timestamp(timestamp: Optional[int]) -> Optional[str]:
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone().isoformat()


def trim_text(text: str, max_chars: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def fetch_articles(
    fakeid: str,
    base_url: str,
    api_key: str,
    begin: int,
    limit: int,
) -> List[Dict[str, Any]]:
    safe_limit = min(max(limit, 1), 20)
    payload = request_json(
        base_url,
        api_key,
        "/api/public/v1/article",
        {"fakeid": fakeid, "begin": begin, "size": safe_limit},
    )
    return payload.get("articles") or []


def filter_articles(articles: List[Dict[str, Any]], days: Optional[int]) -> List[Dict[str, Any]]:
    if days is None:
        return articles

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    kept: List[Dict[str, Any]] = []
    for article in articles:
        timestamp = article.get("create_time") or article.get("update_time")
        if not timestamp:
            continue
        published_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        if published_at >= cutoff:
            kept.append(article)
    return kept


def normalize_article(article: Dict[str, Any], summary_max_chars: int) -> Dict[str, Any]:
    timestamp = article.get("create_time") or article.get("update_time")
    return {
        "title": article.get("title"),
        "url": article.get("link"),
        "summary": trim_text(article.get("digest") or "", summary_max_chars),
        "published_timestamp": timestamp,
        "published_at": normalize_timestamp(timestamp),
        "author_name": article.get("author_name") or "",
        "cover": article.get("cover") or article.get("cover_img") or "",
        "copyright_type": article.get("copyright_type"),
    }


def ensure_api_key(api_key: Optional[str]) -> str:
    if api_key:
        return api_key
    raise SystemExit("Missing mptext API key. Set MPTEXT_API_KEY or pass --api-key.")


def render_output(result: Dict[str, Any], compact: bool) -> str:
    if compact:
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(result, ensure_ascii=False, indent=2)


def main() -> int:
    args = parse_args()
    api_key = ensure_api_key(args.api_key)
    specs = pick_specs(load_account_specs(args.config), args.account)

    sources: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []

    for spec in specs:
        try:
            account = resolve_account(spec, args.base_url, api_key, args.search_size)
            articles = fetch_articles(
                fakeid=account["fakeid"],
                base_url=args.base_url,
                api_key=api_key,
                begin=args.begin,
                limit=args.limit,
            )
            filtered = filter_articles(articles, args.days)[: min(max(args.limit, 1), 20)]
            sources.append(
                {
                    "requested_name": spec.name,
                    "resolved_account": {
                        "nickname": account.get("nickname"),
                        "alias": account.get("alias"),
                        "fakeid": account.get("fakeid"),
                        "signature": account.get("signature") or "",
                    },
                    "articles": [
                        normalize_article(article, args.summary_max_chars)
                        for article in filtered
                    ],
                }
            )
        except MpTextError as exc:
            errors.append({"account": spec.name, "error": str(exc)})

    result = {
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "base_url": args.base_url.rstrip("/"),
        "requested_accounts": [spec.name for spec in specs],
        "per_account_limit": min(max(args.limit, 1), 20),
        "days_filter": args.days,
        "sources": sources,
        "errors": errors,
    }

    output = render_output(result, args.compact)
    if args.json_output:
        output_path = Path(args.json_output)
        output_path.write_text(output + ("\n" if not args.compact else ""), encoding="utf-8")

    print(output)
    if errors and not sources:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
