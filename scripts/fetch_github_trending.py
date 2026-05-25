#!/usr/bin/env python3
"""Fetch and analyze GitHub Trending repositories."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_TRENDING_URL = "https://github.com/trending"
DEFAULT_KEYWORDS = [
    "ai",
    "agent",
    "agents",
    "llm",
    "gpt",
    "rag",
    "inference",
    "multimodal",
    "vision",
    "audio",
    "speech",
    "voice",
    "image",
    "video",
    "diffusion",
    "transformer",
    "embedding",
    "eval",
    "benchmark",
    "model",
    "reasoning",
    "token",
    "dataset",
    "prompt",
    "fine-tuning",
    "finetuning",
    "vector",
    "search",
    "retrieval",
    "ml",
    "machine learning",
    "deep learning",
    "neural",
    "vllm",
    "cuda",
    "pytorch",
    "gpu",
    "coding agent",
    "claude code",
    "codex",
    "cursor",
    "copilot",
]


@dataclass
class TrendingRepo:
    repo: str = ""
    owner: str = ""
    name: str = ""
    url: str = ""
    description: str = ""
    language: str = ""
    stars: Optional[int] = None
    stars_text: str = ""
    today_stars: Optional[int] = None
    today_stars_text: str = ""
    forks: Optional[int] = None
    forks_text: str = ""
    built_by: List[str] = field(default_factory=list)
    ai_score: int = 0
    ai_keywords: List[str] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch GitHub Trending repositories and score AI relevance."
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_TRENDING_URL,
        help=f"Trending base URL. Defaults to {DEFAULT_TRENDING_URL}.",
    )
    parser.add_argument(
        "--language",
        help="Optional language path segment, such as python or typescript.",
    )
    parser.add_argument(
        "--since",
        choices=["daily", "weekly", "monthly"],
        default="daily",
        help="Trending window. Defaults to daily.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Maximum number of repositories to keep after filtering. Defaults to 25.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Optional maximum number of parsed entries before filtering.",
    )
    parser.add_argument(
        "--keyword",
        action="append",
        default=[],
        help="Additional AI relevance keyword. Repeatable.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Keep all trending repositories instead of only AI-relevant matches.",
    )
    parser.add_argument(
        "--json-output",
        help="Optional path to write the JSON result.",
    )
    parser.add_argument(
        "--html-output",
        help="Optional path to write fetched HTML for debugging.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print compact JSON instead of pretty JSON.",
    )
    return parser.parse_args()


def request_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"HTTP {exc.code} for {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Network error for {url}: {exc}") from exc


def build_trending_url(base_url: str, language: Optional[str], since: str) -> str:
    clean_base = base_url.rstrip("/")
    path = clean_base
    if language:
        quoted = urllib.parse.quote(language.strip("/"))
        path = f"{clean_base}/{quoted}"
    return f"{path}?since={urllib.parse.quote(since)}"


def normalize_space(text: str) -> str:
    return " ".join(unescape(text).split())


def parse_count(text: str) -> Optional[int]:
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    return int(digits)


class TrendingHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.repos: List[TrendingRepo] = []
        self.current: Optional[TrendingRepo] = None
        self.in_article = False
        self.article_depth = 0

        self.capture_heading = False
        self.capture_description = False
        self.capture_language = False
        self.capture_today = False
        self.capture_link_text = False
        self.link_inside_heading = False

        self.heading_parts: List[str] = []
        self.description_parts: List[str] = []
        self.language_parts: List[str] = []
        self.today_parts: List[str] = []
        self.link_text_parts: List[str] = []
        self.current_link_href: Optional[str] = None

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        attr_map = dict(attrs)
        class_name = attr_map.get("class", "") or ""

        if tag == "article" and "Box-row" in class_name:
            self.in_article = True
            self.article_depth = 1
            self.current = TrendingRepo()
            return

        if not self.in_article or self.current is None:
            return

        self.article_depth += 1

        if tag == "h2" and "lh-condensed" in class_name:
            self.capture_heading = True
            self.heading_parts = []
        elif tag == "p" and "color-fg-muted" in class_name and not self.current.description:
            self.capture_description = True
            self.description_parts = []
        elif tag == "span" and attr_map.get("itemprop") == "programmingLanguage":
            self.capture_language = True
            self.language_parts = []
        elif tag == "span" and "float-sm-right" in class_name:
            self.capture_today = True
            self.today_parts = []
        elif tag == "a":
            self.current_link_href = attr_map.get("href")
            self.capture_link_text = True
            self.link_text_parts = []
            self.link_inside_heading = self.capture_heading
        elif tag == "img":
            alt = attr_map.get("alt")
            if alt and alt.startswith("@"):
                self.current.built_by.append(alt)

    def handle_endtag(self, tag: str) -> None:
        if not self.in_article or self.current is None:
            return

        if tag == "h2" and self.capture_heading:
            heading_text = normalize_space("".join(self.heading_parts))
            repo = heading_text.replace(" / ", "/").replace(" /", "/").replace("/ ", "/")
            if "/" in repo:
                owner, name = repo.split("/", 1)
                self.current.owner = owner
                self.current.name = name
                self.current.repo = f"{owner}/{name}"
            self.capture_heading = False

        elif tag == "p" and self.capture_description:
            self.current.description = normalize_space("".join(self.description_parts))
            self.capture_description = False

        elif tag == "span" and self.capture_language:
            self.current.language = normalize_space("".join(self.language_parts))
            self.capture_language = False

        elif tag == "span" and self.capture_today:
            today_text = normalize_space("".join(self.today_parts))
            self.current.today_stars_text = today_text
            self.current.today_stars = parse_count(today_text)
            self.capture_today = False

        elif tag == "a" and self.capture_link_text:
            href = self.current_link_href or ""
            link_text = normalize_space("".join(self.link_text_parts))

            if (
                self.link_inside_heading
                and href.startswith("/")
                and href.count("/") == 2
                and not self.current.url
            ):
                self.current.url = f"https://github.com{href}"
                if not self.current.repo and link_text:
                    repo = link_text.replace(" / ", "/").replace(" /", "/").replace("/ ", "/")
                    if "/" in repo:
                        owner, name = repo.split("/", 1)
                        self.current.owner = owner
                        self.current.name = name
                        self.current.repo = f"{owner}/{name}"
            elif href.endswith("/stargazers") and link_text and not self.current.stars_text:
                self.current.stars_text = link_text
                self.current.stars = parse_count(link_text)
            elif href.endswith("/forks") and link_text and not self.current.forks_text:
                self.current.forks_text = link_text
                self.current.forks = parse_count(link_text)

            self.current_link_href = None
            self.link_text_parts = []
            self.capture_link_text = False
            self.link_inside_heading = False

        self.article_depth -= 1
        if tag == "article" and self.article_depth == 0:
            if self.current.repo and self.current.url:
                self.current.built_by = list(dict.fromkeys(self.current.built_by))
                self.repos.append(self.current)
            self.current = None
            self.in_article = False

    def handle_data(self, data: str) -> None:
        if self.capture_heading:
            self.heading_parts.append(data)
        if self.capture_description:
            self.description_parts.append(data)
        if self.capture_language:
            self.language_parts.append(data)
        if self.capture_today:
            self.today_parts.append(data)
        if self.capture_link_text:
            self.link_text_parts.append(data)


def analyze_repo(repo: TrendingRepo, keywords: List[str]) -> TrendingRepo:
    haystack = " ".join(
        part.lower()
        for part in [
            repo.repo,
            repo.description,
            repo.language,
        ]
        if part
    )

    matched: List[str] = []
    score = 0
    for keyword in keywords:
        if keyword in haystack:
            matched.append(keyword)
            score += 1

    boosted_terms = {
        "agent",
        "agents",
        "llm",
        "multimodal",
        "inference",
        "reasoning",
        "vision",
        "speech",
        "voice",
        "image",
        "video",
        "diffusion",
        "embedding",
        "dataset",
        "rag",
        "vllm",
        "pytorch",
        "cuda",
        "codex",
        "claude code",
        "cursor",
        "copilot",
    }
    for keyword in matched:
        if keyword in boosted_terms:
            score += 2

    repo.ai_keywords = matched
    repo.ai_score = score
    return repo


def parse_trending(html_text: str) -> List[TrendingRepo]:
    parser = TrendingHTMLParser()
    parser.feed(html_text)
    return parser.repos


def render_output(result: Dict[str, Any], compact: bool) -> str:
    if compact:
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(result, ensure_ascii=False, indent=2)


def repo_to_dict(repo: TrendingRepo) -> Dict[str, Any]:
    return {
        "repo": repo.repo,
        "owner": repo.owner,
        "name": repo.name,
        "url": repo.url,
        "description": repo.description,
        "language": repo.language,
        "stars": repo.stars,
        "stars_text": repo.stars_text,
        "today_stars": repo.today_stars,
        "today_stars_text": repo.today_stars_text,
        "forks": repo.forks,
        "forks_text": repo.forks_text,
        "built_by": repo.built_by,
        "ai_score": repo.ai_score,
        "ai_keywords": repo.ai_keywords,
    }


def main() -> int:
    args = parse_args()
    keywords = [keyword.lower() for keyword in DEFAULT_KEYWORDS + list(args.keyword)]
    url = build_trending_url(args.base_url, args.language, args.since)
    html_text = request_text(url)

    if args.html_output:
        Path(args.html_output).write_text(html_text, encoding="utf-8")

    parsed = parse_trending(html_text)
    if args.top is not None:
        parsed = parsed[: max(args.top, 0)]

    analyzed = [analyze_repo(repo, keywords) for repo in parsed]
    ai_relevant = [repo for repo in analyzed if repo.ai_score > 0]
    ai_relevant.sort(
        key=lambda repo: (
            repo.ai_score,
            repo.today_stars or -1,
            repo.stars or -1,
        ),
        reverse=True,
    )

    selected = analyzed if args.all else ai_relevant
    if args.limit is not None:
        selected = selected[: max(args.limit, 0)]

    result = {
        "fetched_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "source_url": url,
        "language": args.language,
        "since": args.since,
        "requested_limit": args.limit,
        "parsed_count": len(analyzed),
        "ai_relevant_count": len(ai_relevant),
        "keywords": keywords,
        "repositories": [repo_to_dict(repo) for repo in selected],
    }

    output = render_output(result, args.compact)
    if args.json_output:
        output_path = Path(args.json_output)
        output_path.write_text(output + ("\n" if not args.compact else ""), encoding="utf-8")

    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
