from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
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
        self.db.execute("DELETE FROM claims WHERE story_id=?", (story.id,))
        ledger = []
        for claim in claims:
            checked = checker.check(claim, evidence)
            verdict = checked["verdict"]
            evidence_text = checked.get("evidence_excerpt", "")
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

    def produce(self, story_id: str, platform: str = "tiktok", fmt: str = "carousel", tone: str = "skeptical") -> dict[str, Any]:
        story = self.db.get_story(story_id)
        if not story:
            raise KeyError(f"Unknown story: {story_id}")
        developed = self.develop(story_id)
        package_dir = self.root / "results" / f"{story.id}-{slugify(story.title)}"
        package_dir.mkdir(parents=True, exist_ok=True)
        for legacy_name in ("cover.png", "preview.mp4"):
            legacy_path = package_dir / legacy_name
            if legacy_path.exists():
                legacy_path.unlink()
        assets: list[dict[str, Any]] = []
        source_asset_dir = self.root / "assets" / story.id
        source_asset_dir.mkdir(parents=True, exist_ok=True)
        image_url = story.metadata.get("image")
        existing_images = [
            path for path in source_asset_dir.iterdir()
            if path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"}
            and not path.name.lower().startswith(("imagegen-", "generated", "cover", "preview"))
        ]
        if image_url and not existing_images:
            suffix = Path(urllib.parse.urlsplit(image_url).path).suffix or ".jpg"
            try:
                (source_asset_dir / f"source-image{suffix}").write_bytes(request(image_url))
            except Exception as exc:
                self.db.event("source_asset_download_failed", story.id, {"url": image_url, "error": str(exc)})
        source_files = [
            path for path in source_asset_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".webm"}
            and not path.name.lower().startswith(("generated", "cover", "preview"))
            and (not path.name.lower().startswith("imagegen-") or path.suffix.lower() in {".jpg", ".jpeg", ".png"})
        ]
        for path in source_files:
            media_type = "video" if path.suffix.lower() in {".mp4", ".mov", ".webm"} else "image"
            is_imagegen = path.name.lower().startswith("imagegen-") and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
            assets.append({
                "path": str(path), "type": media_type,
                "origin": "imagegen" if is_imagegen else "source",
                "source_url": None if is_imagegen else story.url,
                "attribution": "ImageGen illustration" if is_imagegen else story.source,
                "rights": "project-generated" if is_imagegen else "source-owned; review reuse rights and provide attribution",
            })
        if not any(asset["origin"] == "source" for asset in assets):
            raise RuntimeError(
                "Source media is required. Download at least one image or video from the original source before production. "
                "ImageGen illustrations cannot replace source media, and SVG assets are not accepted."
            )
        package_assets = package_dir / "assets"
        if package_assets.exists():
            resolved_assets = package_assets.resolve()
            resolved_results = (self.root / "results").resolve()
            if resolved_results not in resolved_assets.parents:
                raise RuntimeError(f"Refusing to replace assets outside the managed results directory: {resolved_assets}")
            shutil.rmtree(package_assets)
        package_assets.mkdir()
        for asset in assets:
            source_path = Path(asset["path"])
            packaged_path = package_assets / source_path.name
            shutil.copy2(source_path, packaged_path)
            asset["source_path"] = str(source_path)
            asset["path"] = str(packaged_path)
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
            "caption": f"{story.title}\n\nLook beyond the demo: save this for the verification notes and build breakdown.\n\nSource: {story.source} - {story.url}",
            "hashtags": ["#AI", "#AITools", "#TechTok", "#LapTrinh", "#VNTechLab"],
            "claims": developed["claims"], "citations": developed["citations"],
            "assets": assets,
            "asset_policy": "source-required",
            "checklist": ["Review unverified claims", "Review source attribution and reuse rights", "Validate source links", "Obtain human approval before publishing"],
            "qa_internal": qa_canary(self.db, "produce"),
            "created_at": utcnow(),
        }
        for name, value in [("package.json", package), ("sources.json", developed["citations"]), ("claims.json", developed["claims"])]:
            (package_dir / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        (package_dir / "caption.txt").write_text(package["caption"], encoding="utf-8")
        (package_dir / "caption.md").write_text(package["caption"] + "\n", encoding="utf-8")
        (package_dir / "brief.json").write_text(json.dumps(developed, ensure_ascii=False, indent=2), encoding="utf-8")
        (package_dir / "title-and-hooks.md").write_text(
            f"# {story.title}\n\n" + "\n".join(f"{index}. {hook}" for index, hook in enumerate(hooks, 1)) + "\n",
            encoding="utf-8",
        )
        (package_dir / "script.md").write_text("\n".join(
            f"## Scene {s['scene']} ({s['duration']})\n\nVisual: {s['visual']}\n\nVoice: {s['voice']}\n" for s in script
        ), encoding="utf-8")
        (package_dir / "sources.md").write_text(
            "# Sources\n\n" + "\n".join(
                f"- [{citation['url']}]({citation['url']}) - {'valid' if citation['valid'] else 'unreachable'}"
                for citation in developed["citations"]
            ) + "\n",
            encoding="utf-8",
        )
        (package_dir / "fact-check.md").write_text(
            "# Fact check\n\n" + "\n".join(
                f"- **{claim['verdict']}**: {claim['claim']}\n  - Evidence: {claim['evidence']}\n"
                f"  - Source: {claim['source_url'] or 'Additional source required'}"
                for claim in developed["claims"]
            ) + "\n",
            encoding="utf-8",
        )
        (package_dir / "asset-manifest.json").write_text(
            json.dumps(assets, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (package_dir / "upload-checklist.md").write_text(
            "# Upload checklist\n\n" + "\n".join(f"- [ ] {item}" for item in package["checklist"]) + "\n",
            encoding="utf-8",
        )
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
