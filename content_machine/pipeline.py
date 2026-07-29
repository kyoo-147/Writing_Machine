from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import textwrap
import urllib.parse
import urllib.error
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .connectors import DEFAULT_RSS, collect_apify, collect_arxiv, collect_firecrawl, collect_github, collect_github_releases, collect_rss, collect_web, request, story_from_social
from .core import Database, Story, deduplicate, fingerprint, qa_canary, score_story, slugify, utcnow


class ContentMachine:
    def __init__(self, db: Database | None = None, root: Path | None = None):
        self.db = db or Database()
        self.root = root or Path(os.getenv("CONTENT_MACHINE_DATA_DIR", "data"))
        self.root.mkdir(parents=True, exist_ok=True)

    def discover(self, query: str = "AI", count: int = 10, sources: list[str] | None = None) -> list[Story]:
        sources = sources or ["github", "arxiv", "rss"]
        stories: list[Story] = []
        errors: list[dict[str, str]] = []
        for source in sources:
            try:
                if source == "github":
                    stories += collect_github(query if ":" in query else f"{query} in:name,description", limit=max(count, 10))
                elif source == "arxiv":
                    stories += collect_arxiv(f'all:"{query}"', limit=max(count, 10))
                elif source == "rss":
                    for feed in DEFAULT_RSS:
                        try:
                            stories += collect_rss(feed, limit=10)
                        except Exception as exc:
                            errors.append({"source": feed, "error": str(exc)})
                elif source.startswith("rss:"):
                    stories += collect_rss(source[4:])
                elif source.startswith("firecrawl:"):
                    stories += collect_firecrawl(source.split(":", 1)[1])
                elif source.startswith("apify:"):
                    stories += collect_apify(source.split(":", 1)[1], {"search": query, "maxItems": count})
                elif source.startswith("releases:"):
                    stories += collect_github_releases(source.split(":", 1)[1].split(","))
                elif source.startswith("web:"):
                    stories += collect_web(source.split(":", 1)[1])
            except Exception as exc:
                errors.append({"source": source, "error": str(exc)})
        stories = [s for s in deduplicate(stories) if not self.db.is_archived(s.title, s.url)]
        for story in stories:
            score_story(story)
            self.db.save_story(story)
        stories.sort(key=lambda x: x.score, reverse=True)
        self.db.event("discover", payload={"query": query, "found": len(stories), "errors": errors, "canary": qa_canary(self.db, "discover")})
        return stories[:count]

    def ingest_social(self, payload: dict[str, Any]) -> Story:
        story = story_from_social(payload).finalize()
        self.db.record_metrics(story.id, story.source, story.metadata)
        velocity = self.db.metric_velocity(story.id)
        story.metadata["velocity"] = velocity
        if velocity["views_per_hour"] or velocity["engagement_per_hour"]:
            story.signals["discussion"] = min(10.0, 5.0 + math.log10(1 + velocity["engagement_per_hour"]))
            story.signals["novelty"] = min(10.0, 7.0 + math.log10(1 + velocity["views_per_hour"]) / 2)
        score_story(story)
        self.db.save_story(story)
        self.db.event("social_ingested", story.id, {"platform": story.source})
        return story

    def develop(self, story_id: str) -> dict[str, Any]:
        from .enterprise import ClaimChecker

        story = self.db.get_story(story_id)
        if not story:
            raise KeyError(f"Unknown story: {story_id}")
        text = f"{story.title}. {story.summary}"
        claims = self._claims(text)
        sources = self._citation_urls(story)
        evidence_rows = self.db.execute("SELECT payload FROM stories ORDER BY score DESC LIMIT 100").fetchall()
        evidence = [Story(**json.loads(row[0])) for row in evidence_rows]
        checker = ClaimChecker()
        ledger = []
        for claim in claims:
            checked = checker.check(claim, evidence)
            verdict = checked["verdict"]
            evidence_text = next((item.summary[:500] for item in evidence if item.url == checked["evidence_url"]), "")
            ledger.append({"claim": claim, "verdict": verdict, "entailment": checked["entailment"],
                           "evidence": evidence_text or "A second primary source is required before asserting this claim.",
                           "source_url": checked["evidence_url"]})
            self.db.execute(
                "INSERT INTO claims(story_id,claim,verdict,evidence,source_url,checked_at) VALUES(?,?,?,?,?,?)",
                (story.id, claim, verdict, evidence_text, checked["evidence_url"], utcnow()),
            )
        result = {
            "story": asdict(story), "claims": ledger,
            "citations": [{"url": u, "valid": self.validate_citation(u),
                           "semantic": checker.validate_citation(claims[0], next(
                               (item for item in evidence if item.url == u), story))} for u in sources],
            "angles": [
                {"type": "news", "hook": f"{story.title}: what is actually new?"},
                {"type": "technical", "hook": "If we rebuild this demo, where is the hard engineering work?"},
                {"type": "skeptical", "hook": "The demo looks great, but does it survive outside a 30-second video?"},
            ],
            "recommended_angle": "skeptical",
            "qa": qa_canary(self.db, "develop"),
        }
        out = self.root / "develop" / story.id
        out.mkdir(parents=True, exist_ok=True)
        (out / "brief.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        self.db.event("develop", story.id, {"claims": len(ledger)})
        return result

    @staticmethod
    def _claims(text: str) -> list[str]:
        parts = [x.strip() for x in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text)) if len(x.strip()) > 24]
        return parts[:8] or [text[:300]]

    @staticmethod
    def _citation_urls(story: Story) -> list[str]:
        urls = re.findall(r"https?://[^\s>)\]\"']+", story.summary)
        return list(dict.fromkeys([story.url, *urls]))[:12]

    @staticmethod
    def validate_citation(url: str) -> bool:
        if not url.startswith(("http://", "https://")):
            return False
        try:
            request(url, headers={"Range": "bytes=0-1024"})
            return True
        except urllib.error.HTTPError as exc:
            exc.close()
            return False
        except Exception:
            return False

    def download_asset(self, url: str, story_id: str, name: str | None = None) -> Path:
        data = request(url)
        ext = Path(urllib.parse.urlsplit(url).path).suffix[:6] or ".bin"
        target = self.root / "assets" / story_id / (name or f"{hashlib.sha1(url.encode()).hexdigest()[:10]}{ext}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        self.db.event("asset_downloaded", story_id, {"url": url, "path": str(target), "bytes": len(data)})
        return target

    def generate_card(self, story: Story, target: Path) -> Path:
        from PIL import Image, ImageDraw, ImageFont

        target.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (1080, 1920), "#090b12")
        draw = ImageDraw.Draw(image)
        for y in range(1920):
            ratio = y / 1919
            draw.line((0, y, 1080, y), fill=(9 + int(18 * ratio), 11 + int(25 * ratio), 18 + int(65 * ratio)))
        try:
            brand_font = ImageFont.truetype("arial.ttf", 44)
            title_font = ImageFont.truetype("arialbd.ttf", 78)
            source_font = ImageFont.truetype("arial.ttf", 34)
        except OSError:
            brand_font = ImageFont.load_default(size=44)
            title_font = ImageFont.load_default(size=78)
            source_font = ImageFont.load_default(size=34)
        draw.rounded_rectangle((52, 72, 1028, 1848), radius=36, outline="#293659", width=3)
        draw.text((80, 130), "VN TECH LAB", fill="#76f7c8", font=brand_font)
        draw.multiline_text((80, 390), "\n".join(textwrap.wrap(story.title, 21)), fill="white", font=title_font, spacing=22)
        draw.text((80, 1760), f"Source: {story.source}", fill="#aab4d4", font=source_font)
        image.save(target, quality=92)
        return target

    def generate_video(self, image: Path, target: Path, duration: int = 8) -> Path | None:
        if not shutil.which("ffmpeg"):
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", str(image), "-t", str(duration),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
            "-r", "30", "-pix_fmt", "yuv420p", str(target),
        ], check=True, capture_output=True)
        return target

    def produce(self, story_id: str, platform: str = "tiktok", fmt: str = "carousel", tone: str = "skeptical") -> dict[str, Any]:
        story = self.db.get_story(story_id)
        if not story:
            raise KeyError(f"Unknown story: {story_id}")
        developed = self.develop(story_id)
        package_dir = self.root / "results" / f"{story.id}-{slugify(story.title)}"
        package_dir.mkdir(parents=True, exist_ok=True)
        card = self.generate_card(story, package_dir / "cover.png")
        hooks = [
            f"{story.title}: it sounds impressive, but do not trust the demo yet.",
            "This AI just appeared. The question is not what it can do, but what the demo leaves out.",
            "A new repository worth rebuilding instead of merely sharing its headline.",
        ]
        script = [
            {"scene": 1, "duration": "0-3s", "visual": "Cover + demo", "voice": hooks[0]},
            {"scene": 2, "duration": "3-12s", "visual": "Primary source", "voice": story.summary[:280] or "This is the information provided by the original project."},
            {"scene": 3, "duration": "12-25s", "visual": "Mechanism", "voice": "The interesting part is how it turns a model into a usable and testable workflow."},
            {"scene": 4, "duration": "25-38s", "visual": "Limitations", "voice": "Benchmarks, cost, and reliability outside the demo remain open questions."},
            {"scene": 5, "duration": "38-45s", "visual": "CTA", "voice": "Should we rebuild it and measure the real cost?"},
        ]
        package = {
            "id": story.id, "platform": platform, "format": fmt, "tone": tone,
            "title": story.title, "hooks": hooks, "script": script,
            "caption": f"{story.title}\n\nLook beyond the demo: save this for the verification notes and build breakdown.\n\nPrimary source: {story.url}",
            "hashtags": ["#AI", "#AITools", "#TechTok", "#LapTrinh", "#VNTechLab"],
            "claims": developed["claims"], "citations": developed["citations"],
            "assets": [{"path": str(card), "type": "cover", "origin": "generated", "rights": "project-owned"}],
            "checklist": ["Review unverified claims", "Review the 9:16 cover", "Listen to the voice-over", "Validate source links", "Obtain human approval before publishing"],
            "qa_internal": qa_canary(self.db, "produce"),
            "created_at": utcnow(),
        }
        if fmt in {"video", "short-video"}:
            video = package_dir / "preview.mp4"
            try:
                generated = self.generate_video(card, video)
                if generated:
                    package["assets"].append({"path": str(generated), "type": "video", "origin": "generated", "rights": "project-owned"})
            except subprocess.CalledProcessError as exc:
                self.db.event("media_generation_failed", story.id, {"error": exc.stderr.decode(errors="replace")[-1000:]})
        for name, value in [("package.json", package), ("sources.json", developed["citations"]), ("claims.json", developed["claims"])]:
            (package_dir / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        (package_dir / "caption.txt").write_text(package["caption"], encoding="utf-8")
        (package_dir / "script.md").write_text("\n".join(
            f"## Scene {s['scene']} ({s['duration']})\n\nVisual: {s['visual']}\n\nVoice: {s['voice']}\n" for s in script
        ), encoding="utf-8")
        self.db.execute(
            "INSERT INTO packages(story_id,package_path,platform,status,payload,created_at) VALUES(?,?,?,?,?,?)",
            (story.id, str(package_dir), platform, "ready", json.dumps(package, ensure_ascii=False), utcnow()),
        )
        self.db.event("produce", story.id, {"path": str(package_dir)})
        return {"path": str(package_dir), **package}

    def publish(self, story_id: str, platform: str, approve: bool = False, webhook: str | None = None) -> dict[str, Any]:
        if not approve:
            return {"status": "dry-run", "message": "Add --approve after human review."}
        story = self.db.get_story(story_id)
        if not story:
            raise KeyError(story_id)
        package_row = self.db.execute(
            "SELECT payload FROM packages WHERE story_id=? AND platform=? ORDER BY row_id DESC LIMIT 1", (story_id, platform)
        ).fetchone()
        if not package_row:
            raise RuntimeError("Produce the package first.")
        package = json.loads(package_row[0])
        endpoint = webhook or os.getenv(f"{platform.upper()}_PUBLISH_WEBHOOK")
        if not endpoint:
            raise RuntimeError(f"No {platform} publisher configured. Set {platform.upper()}_PUBLISH_WEBHOOK.")
        response = json.loads(request(endpoint, headers={"Content-Type": "application/json"}, data=package))
        external_id = str(response.get("id") or response.get("post_id") or "")
        self.db.execute(
            "INSERT INTO archive(fingerprint,story_id,platform,published_at,external_id,payload) VALUES(?,?,?,?,?,?)",
            (fingerprint(story.title, story.url), story.id, platform, utcnow(), external_id, json.dumps(response)),
        )
        self.db.event("publish", story.id, {"platform": platform, "canary": qa_canary(self.db, "publish")})
        return {"status": "published", "platform": platform, "external_id": external_id, "response": response}

    def analytics(self) -> dict[str, Any]:
        def scalar(sql: str) -> int:
            row = self.db.execute(sql).fetchone()
            return int(row[0] if row else 0)
        events = self.db.execute("SELECT event,COUNT(*) count FROM events GROUP BY event ORDER BY count DESC").fetchall()
        return {
            "stories": scalar("SELECT COUNT(*) FROM stories"),
            "packages": scalar("SELECT COUNT(*) FROM packages"),
            "published": scalar("SELECT COUNT(*) FROM archive"),
            "pending_reviews": scalar("SELECT COUNT(*) FROM packages WHERE status='ready'"),
            "failed_jobs": scalar("SELECT COUNT(*) FROM jobs WHERE status='failed'"),
            "events": [{"event": r[0], "count": r[1]} for r in events],
        }
