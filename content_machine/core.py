from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import time
import urllib.parse
from email.utils import parsedate_to_datetime
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(value: str) -> str:
    value = re.sub(r"[^\w\s-]", "", value.lower(), flags=re.UNICODE)
    return re.sub(r"[-\s]+", "-", value).strip("-")[:72] or "story"


def canonical_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
    query = [(k, v) for k, v in query if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
    return urllib.parse.urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), urllib.parse.urlencode(query), "")
    )


def fingerprint(title: str, url: str = "") -> str:
    normalized = re.sub(r"\W+", " ", title.lower()).strip()
    return hashlib.sha256(f"{normalized}|{canonical_url(url)}".encode()).hexdigest()[:24]


@dataclass
class Story:
    title: str
    url: str
    source: str
    summary: str = ""
    published_at: str = ""
    kind: str = "news"
    signals: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    id: str = ""

    def finalize(self) -> "Story":
        self.url = canonical_url(self.url)
        self.id = self.id or fingerprint(self.title, self.url)
        return self


class Database:
    """SQLite-first persistence with an optional PostgreSQL URL."""

    def __init__(self, url: str | None = None):
        self.url = url or os.getenv("CONTENT_MACHINE_DATABASE_URL", "sqlite:///data/content-machine.db")
        if self.url.startswith("postgres"):
            try:
                import psycopg  # type: ignore
            except ImportError as exc:
                raise RuntimeError("Install PostgreSQL support: pip install '.[postgres]'") from exc
            self.kind = "postgres"
            self.conn = psycopg.connect(self.url, autocommit=True)
        else:
            self.kind = "sqlite"
            path = Path(self.url.removeprefix("sqlite:///"))
            path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
        self._init()

    def execute(self, sql: str, params: tuple[Any, ...] = ()):
        if self.kind == "postgres":
            sql = sql.replace("?", "%s")
        cur = self.conn.cursor()
        cur.execute(sql, params)
        if self.kind == "sqlite":
            self.conn.commit()
        return cur

    def _init(self) -> None:
        id_type = "INTEGER PRIMARY KEY AUTOINCREMENT" if self.kind == "sqlite" else "BIGSERIAL PRIMARY KEY"
        for sql in [
            f"""CREATE TABLE IF NOT EXISTS stories (
                row_id {id_type}, story_id TEXT UNIQUE, title TEXT, url TEXT, source TEXT,
                summary TEXT, published_at TEXT, kind TEXT, score REAL, payload TEXT,
                status TEXT DEFAULT 'discovered', created_at TEXT)""",
            f"""CREATE TABLE IF NOT EXISTS claims (
                row_id {id_type}, story_id TEXT, claim TEXT, verdict TEXT, evidence TEXT,
                source_url TEXT, checked_at TEXT)""",
            f"""CREATE TABLE IF NOT EXISTS packages (
                row_id {id_type}, story_id TEXT, package_path TEXT, platform TEXT,
                status TEXT, payload TEXT, created_at TEXT)""",
            f"""CREATE TABLE IF NOT EXISTS archive (
                row_id {id_type}, fingerprint TEXT UNIQUE, story_id TEXT, platform TEXT,
                published_at TEXT, external_id TEXT, payload TEXT)""",
            f"""CREATE TABLE IF NOT EXISTS events (
                row_id {id_type}, event TEXT, story_id TEXT, payload TEXT, created_at TEXT)""",
            f"""CREATE TABLE IF NOT EXISTS schedules (
                row_id {id_type}, command TEXT, run_at TEXT, interval_minutes INTEGER,
                enabled INTEGER DEFAULT 1, last_run TEXT)""",
            f"""CREATE TABLE IF NOT EXISTS metric_snapshots (
                row_id {id_type}, story_id TEXT, platform TEXT, views INTEGER, likes INTEGER,
                comments INTEGER, shares INTEGER, reposts INTEGER, bookmarks INTEGER, captured_at TEXT)""",
            f"""CREATE TABLE IF NOT EXISTS workspaces (
                row_id {id_type}, workspace_id TEXT UNIQUE, name TEXT, created_at TEXT)""",
            f"""CREATE TABLE IF NOT EXISTS members (
                row_id {id_type}, workspace_id TEXT, user_id TEXT, role TEXT,
                UNIQUE(workspace_id,user_id))""",
            f"""CREATE TABLE IF NOT EXISTS reviews (
                row_id {id_type}, story_id TEXT, reviewer_id TEXT, decision TEXT,
                comment TEXT, created_at TEXT)""",
            f"""CREATE TABLE IF NOT EXISTS jobs (
                row_id {id_type}, job_id TEXT UNIQUE, command TEXT, payload TEXT, status TEXT,
                attempts INTEGER DEFAULT 0, max_attempts INTEGER DEFAULT 3, available_at TEXT,
                locked_at TEXT, last_error TEXT, created_at TEXT, updated_at TEXT)""",
        ]:
            self.execute(sql)

    def close(self) -> None:
        self.conn.close()

    def event(self, event: str, story_id: str = "", payload: dict[str, Any] | None = None) -> None:
        self.execute(
            "INSERT INTO events(event,story_id,payload,created_at) VALUES(?,?,?,?)",
            (event, story_id, json.dumps(payload or {}, ensure_ascii=False), utcnow()),
        )

    def save_story(self, story: Story) -> None:
        story.finalize()
        values = (
            story.id, story.title, story.url, story.source, story.summary, story.published_at,
            story.kind, story.score, json.dumps(asdict(story), ensure_ascii=False), utcnow(),
        )
        if self.kind == "sqlite":
            self.execute(
                """INSERT INTO stories(story_id,title,url,source,summary,published_at,kind,score,payload,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(story_id) DO UPDATE SET
                score=excluded.score,payload=excluded.payload""",
                values,
            )
        else:
            self.execute(
                """INSERT INTO stories(story_id,title,url,source,summary,published_at,kind,score,payload,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(story_id) DO UPDATE SET
                score=EXCLUDED.score,payload=EXCLUDED.payload""",
                values,
            )

    def get_story(self, story_id: str) -> Story | None:
        row = self.execute("SELECT payload FROM stories WHERE story_id=?", (story_id,)).fetchone()
        if not row:
            return None
        raw = row[0] if not isinstance(row, sqlite3.Row) else row["payload"]
        return Story(**json.loads(raw))

    def list_stories(self, limit: int = 30) -> list[dict[str, Any]]:
        rows = self.execute(
            "SELECT story_id,title,url,source,score,status,created_at FROM stories ORDER BY score DESC,created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) if isinstance(r, sqlite3.Row) else dict(zip(
            ["story_id", "title", "url", "source", "score", "status", "created_at"], r
        )) for r in rows]

    def is_archived(self, title: str, url: str) -> bool:
        fp = fingerprint(title, url)
        return bool(self.execute("SELECT 1 FROM archive WHERE fingerprint=?", (fp,)).fetchone())

    def record_metrics(self, story_id: str, platform: str, values: dict[str, Any]) -> None:
        self.execute(
            """INSERT INTO metric_snapshots(story_id,platform,views,likes,comments,shares,reposts,bookmarks,captured_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (story_id, platform, *(int(values.get(k, 0) or 0) for k in
              ("views", "likes", "comments", "shares", "reposts", "bookmarks")), utcnow()),
        )

    def metric_velocity(self, story_id: str) -> dict[str, float]:
        rows = self.execute(
            """SELECT views,likes,comments,shares,reposts,bookmarks,captured_at
            FROM metric_snapshots WHERE story_id=? ORDER BY captured_at DESC LIMIT 2""", (story_id,)
        ).fetchall()
        if len(rows) < 2:
            return {"views_per_hour": 0.0, "engagement_per_hour": 0.0}
        latest, previous = rows[0], rows[1]
        seconds = max(1.0, datetime.fromisoformat(latest[6]).timestamp() - datetime.fromisoformat(previous[6]).timestamp())
        views = max(0, latest[0] - previous[0]) * 3600 / seconds
        engagement = max(0, sum(latest[1:6]) - sum(previous[1:6])) * 3600 / seconds
        return {"views_per_hour": round(views, 2), "engagement_per_hour": round(engagement, 2)}


def similarity(a: str, b: str) -> float:
    aa = set(re.findall(r"\w+", a.lower()))
    bb = set(re.findall(r"\w+", b.lower()))
    return len(aa & bb) / max(1, len(aa | bb))


def deduplicate(stories: Iterable[Story], threshold: float = 0.72) -> list[Story]:
    result: list[Story] = []
    urls: set[str] = set()
    for story in stories:
        story.finalize()
        if story.url in urls or any(similarity(story.title, other.title) >= threshold for other in result):
            continue
        urls.add(story.url)
        result.append(story)
    return result


WEIGHTS = {
    "novelty": 0.25, "visual": 0.20, "buildability": 0.15, "engineering": 0.15,
    "authority": 0.10, "discussion": 0.10, "vn_fit": 0.05,
}


def score_story(story: Story, now: float | None = None) -> float:
    text = f"{story.title} {story.summary}".lower()
    now = now or time.time()
    age_days = 7.0
    if story.published_at:
        try:
            published = datetime.fromisoformat(story.published_at.replace("Z", "+00:00"))
            age_days = max(0.0, (now - published.timestamp()) / 86400)
        except ValueError:
            try:
                age_days = max(0.0, (now - parsedate_to_datetime(story.published_at).timestamp()) / 86400)
            except (TypeError, ValueError):
                pass
    novelty = max(1.0, 10.0 - min(age_days, 30.0) * 0.3)
    host = urllib.parse.urlsplit(story.url).netloc.lower()
    primary_hosts = ("github.com", "arxiv.org", "openai.com", "anthropic.com", "deepmind.google", "ai.google", "blog.google")
    defaults = {
        "novelty": novelty,
        "visual": 8.0 if story.metadata.get("image") or story.metadata.get("media") or any(
            x in text for x in ("demo", "video", "image", "multimodal", "robot")) else 5.0,
        "buildability": 8.0 if any(x in text for x in ("github", "open source", "api", "sdk", "code")) else 5.0,
        "engineering": 8.0 if any(x in text for x in ("agent", "model", "benchmark", "inference", "research")) else 6.0,
        "authority": 9.0 if story.kind in {"paper", "release"} or any(host.endswith(x) for x in primary_hosts) else 6.0,
        "discussion": min(10.0, 4.0 + math.log10(1 + story.metadata.get("engagement", 0))),
        "vn_fit": 7.0,
    }
    values = {k: max(0.0, min(10.0, float(story.signals.get(k, v)))) for k, v in defaults.items()}
    story.signals = values
    story.score = round(sum(values[k] * WEIGHTS[k] for k in WEIGHTS) * 10, 1)
    return story.score


def qa_canary(db: Database, phase: str) -> str:
    phrases = {
        "discover": os.getenv("QA_CANARY_DISCOVER", "DISCOVERY_SOURCE_CHECKED"),
        "develop": os.getenv("QA_CANARY_DEVELOP", "CLAIM_LEDGER_CHECKED"),
        "produce": os.getenv("QA_CANARY_PRODUCE", "PACKAGE_ASSETS_CHECKED"),
        "publish": os.getenv("QA_CANARY_PUBLISH", "HUMAN_APPROVAL_CONFIRMED"),
    }
    phrase = phrases.get(phase, "qa checked")
    db.event("qa_canary", payload={"phase": phase, "phrase": phrase})
    return phrase
