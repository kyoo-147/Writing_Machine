from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any

from .core import Story


UA = "VN-Content-Machine/0.2 (+https://github.com/kyoo-147/Writing_Machine)"


def request(url: str, *, headers: dict[str, str] | None = None, data: dict[str, Any] | None = None) -> bytes:
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=35) as response:
        return response.read()


def _text(node: ET.Element | None, names: tuple[str, ...]) -> str:
    if node is None:
        return ""
    for child in list(node):
        if child.tag.split("}")[-1] in names and child.text:
            return child.text.strip()
    return ""


def collect_rss(url: str, limit: int = 30) -> list[Story]:
    root = ET.fromstring(request(url))
    items = root.findall(".//item") or root.findall(".//{*}entry")
    stories = []
    for item in items[:limit]:
        link = _text(item, ("link",))
        if not link:
            link_node = next((x for x in list(item) if x.tag.split("}")[-1] == "link"), None)
            link = (link_node.attrib.get("href", "") if link_node is not None else "")
        stories.append(Story(
            title=_text(item, ("title",)),
            url=link,
            source=urllib.parse.urlsplit(url).netloc,
            summary=re.sub("<[^>]+>", " ", _text(item, ("description", "summary", "content"))),
            published_at=_text(item, ("pubDate", "published", "updated")),
            kind="rss",
        ))
    return stories


def collect_github(query: str = "topic:artificial-intelligence", days: int = 7, limit: int = 20) -> list[Story]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    q = urllib.parse.quote(f"{query} pushed:>{since}")
    headers = {"Accept": "application/vnd.github+json"}
    if os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    payload = json.loads(request(f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page={limit}", headers=headers))
    return [Story(
        title=f"{repo['full_name']}: {repo.get('description') or 'AI project'}",
        url=repo["html_url"], source="GitHub", summary=repo.get("description") or "",
        published_at=repo.get("pushed_at", ""), kind="release",
        metadata={"stars": repo.get("stargazers_count", 0), "engagement": repo.get("stargazers_count", 0)},
    ) for repo in payload.get("items", [])]


def collect_github_releases(repositories: list[str], limit: int = 10) -> list[Story]:
    headers = {"Accept": "application/vnd.github+json"}
    if os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    stories: list[Story] = []
    for repo in repositories:
        try:
            releases = json.loads(request(f"https://api.github.com/repos/{repo}/releases?per_page={limit}", headers=headers))
        except urllib.error.HTTPError:
            continue
        for release in releases:
            stories.append(Story(
                title=f"{repo} {release.get('name') or release.get('tag_name')}",
                url=release["html_url"], source=f"GitHub/{repo}",
                summary=(release.get("body") or "")[:1200], published_at=release.get("published_at", ""),
                kind="release", metadata={"tag": release.get("tag_name")},
            ))
    return stories


def collect_arxiv(query: str = "all:artificial intelligence", limit: int = 20) -> list[Story]:
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({
        "search_query": query, "start": 0, "max_results": limit, "sortBy": "submittedDate", "sortOrder": "descending",
    })
    root = ET.fromstring(request(url))
    stories = []
    for entry in root.findall(".//{*}entry"):
        stories.append(Story(
            title=_text(entry, ("title",)).replace("\n", " "),
            url=_text(entry, ("id",)), source="arXiv",
            summary=_text(entry, ("summary",)).replace("\n", " "),
            published_at=_text(entry, ("published",)), kind="paper",
        ))
    return stories


def collect_firecrawl(url: str) -> list[Story]:
    key = os.getenv("FIRECRAWL_API_KEY")
    if not key:
        raise RuntimeError("FIRECRAWL_API_KEY is not configured")
    endpoint = os.getenv("FIRECRAWL_API_URL", "https://api.firecrawl.dev/v1/scrape")
    payload = json.loads(request(endpoint, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, data={
        "url": url, "formats": ["markdown"],
    }))
    data = payload.get("data", payload)
    meta = data.get("metadata", {})
    return [Story(meta.get("title") or url, url, "Firecrawl", data.get("markdown", "")[:5000], kind="web")]


def collect_apify(actor: str, actor_input: dict[str, Any]) -> list[Story]:
    token = os.getenv("APIFY_TOKEN")
    if not token:
        raise RuntimeError("APIFY_TOKEN is not configured")
    endpoint = f"https://api.apify.com/v2/acts/{urllib.parse.quote(actor, safe='~')}/run-sync-get-dataset-items?token={token}"
    items = json.loads(request(endpoint, headers={"Content-Type": "application/json"}, data=actor_input))
    stories = []
    for item in items:
        url = item.get("url") or item.get("link") or item.get("postUrl") or ""
        title = item.get("title") or item.get("text") or item.get("caption") or url
        stories.append(Story(str(title)[:240], url, f"Apify/{actor}", json.dumps(item, ensure_ascii=False)[:3000], kind="social", metadata=item))
    return stories


DEFAULT_RSS = [
    "https://openai.com/news/rss.xml",
    "https://deepmind.google/discover/blog/rss.xml",
    "https://www.anthropic.com/rss.xml",
    "https://huggingface.co/blog/feed.xml",
]

