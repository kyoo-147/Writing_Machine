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

    @staticmethod
    def select_hashtags(story: Story, platform: str = "tiktok") -> list[str]:
        text = f"{story.title} {story.summary} {story.source} {story.kind}".lower()
        topic_rules = [
            (("gemini", "google ai"), "#GeminiAI"),
            (("claude", "anthropic"), "#ClaudeAI"),
            (("openai", "chatgpt", "codex"), "#OpenAI"),
            (("agent", "agentic"), "#AIAgents"),
            (("github", "open source", "repository"), "#OpenSourceAI"),
            (("research", "paper", "arxiv", "benchmark"), "#AIResearch"),
            (("multimodal", "image", "video", "vision"), "#MultimodalAI"),
            (("code", "coding", "developer", "sdk", "programming"), "#AICoding"),
        ]
        raw_trends = story.metadata.get("trending_hashtags", [])
        if isinstance(raw_trends, str):
            raw_trends = re.split(r"[\s,]+", raw_trends)
        raw_trends = [*raw_trends, *re.split(r"[\s,]+", os.getenv("TIKTOK_TRENDING_HASHTAGS", ""))]
        text_tokens = {token for token in re.findall(r"[a-z0-9]+", text) if len(token) >= 3}
        contextual = {"ai", "aitools", "techtok", "technology", "technews", "learnontiktok"}
        selected: list[str] = []

        def add(tag: str) -> None:
            normalized = "#" + re.sub(r"[^A-Za-z0-9_]", "", tag.lstrip("#"))
            if len(normalized) > 1 and normalized.lower() not in {item.lower() for item in selected}:
                selected.append(normalized)

        for trend in raw_trends:
            core = re.sub(r"[^a-z0-9]", "", str(trend).lower())
            if core and (core in contextual or any(token in core for token in text_tokens)):
                add(str(trend))
        for keywords, tag in topic_rules:
            if any(keyword in text for keyword in keywords):
                add(tag)
        for fallback in ("#AI", "#AITools", "#TechTok", "#VNTechLab", "#AICommunity"):
            add(fallback)
        return selected[:5] if platform.lower() == "tiktok" else selected[:10]

    def download_asset(self, url: str, story_id: str, name: str | None = None) -> Path:
        data = request(url)
        ext = Path(urllib.parse.urlsplit(url).path).suffix[:6] or ".bin"
        target = self.root / "assets" / story_id / (name or f"{hashlib.sha1(url.encode()).hexdigest()[:10]}{ext}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        self.db.event("asset_downloaded", story_id, {"url": url, "path": str(target), "bytes": len(data)})
        return target

    @staticmethod
    def _deduplicate_visuals(paths: list[Path]) -> list[Path]:
        try:
            from PIL import Image, ImageOps
        except ImportError:
            return paths
        kept: list[dict[str, Any]] = []
        videos: list[Path] = []
        for path in paths:
            if path.suffix.lower() in {".mp4", ".mov", ".webm"}:
                videos.append(path)
                continue
            try:
                with Image.open(path) as raw:
                    image = ImageOps.exif_transpose(raw).convert("L")
                    area = image.width * image.height
                    resized = image.resize((9, 8))
                    pixels = list(
                        resized.get_flattened_data() if hasattr(resized, "get_flattened_data") else resized.getdata()
                    )
                signature = sum(
                    1 << index
                    for index, (left, right) in enumerate(zip(pixels, pixels[1:]))
                    if index % 9 != 8 and left > right
                )
            except Exception:
                kept.append({"path": path, "signature": None, "area": 0})
                continue
            duplicate_index = next(
                (
                    index for index, item in enumerate(kept)
                    if item["signature"] is not None and (item["signature"] ^ signature).bit_count() <= 1
                ),
                None,
            )
            record = {"path": path, "signature": signature, "area": area}
            if duplicate_index is None:
                kept.append(record)
            elif area > kept[duplicate_index]["area"]:
                kept[duplicate_index] = record
        return [item["path"] for item in kept] + videos

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
        existing_digests = {
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in existing_images
        }
        image_entries = story.metadata.get("images", [])
        if not isinstance(image_entries, list):
            image_entries = []
        normalized_entries = [
            item if isinstance(item, dict) else {"url": str(item), "alt": ""}
            for item in image_entries
        ]
        if image_url and image_url not in {item.get("url") for item in normalized_entries}:
            normalized_entries.insert(0, {"url": image_url, "alt": "Article hero"})
        source_manifest_path = source_asset_dir / "source-assets.json"
        try:
            source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            source_manifest = {}
        for index, item in enumerate(normalized_entries, 1):
            asset_url = str(item.get("url") or "")
            if not asset_url:
                continue
            suffix = Path(urllib.parse.urlsplit(asset_url).path).suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                suffix = ".jpg"
            filename = f"source-page-{index:02d}-{hashlib.sha1(asset_url.encode()).hexdigest()[:8]}{suffix}"
            target = source_asset_dir / filename
            if target.exists():
                source_manifest[filename] = {"url": asset_url, "alt": str(item.get("alt") or ""), "article_url": story.url}
                continue
            try:
                payload = request(asset_url)
                digest = hashlib.sha256(payload).hexdigest()
                if digest in existing_digests:
                    continue
                target.write_bytes(payload)
                existing_digests.add(digest)
                source_manifest[filename] = {"url": asset_url, "alt": str(item.get("alt") or ""), "article_url": story.url}
            except Exception as exc:
                self.db.event("source_asset_download_failed", story.id, {"url": asset_url, "error": str(exc)})
        if source_manifest:
            source_manifest_path.write_text(json.dumps(source_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        source_files = [
            path for path in source_asset_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".webm"}
            and not path.name.lower().startswith(("generated", "cover", "preview"))
            and (not path.name.lower().startswith("imagegen-") or path.suffix.lower() in {".jpg", ".jpeg", ".png"})
        ]
        source_files = self._deduplicate_visuals(source_files)
        for path in source_files:
            media_type = "video" if path.suffix.lower() in {".mp4", ".mov", ".webm"} else "image"
            is_imagegen = path.name.lower().startswith("imagegen-") and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
            assets.append({
                "path": str(path), "type": media_type,
                "origin": "imagegen" if is_imagegen else "source",
                "source_url": None if is_imagegen else source_manifest.get(path.name, {}).get("url", story.url),
                "article_url": None if is_imagegen else story.url,
                "alt": source_manifest.get(path.name, {}).get("alt", ""),
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
        hashtags = self.select_hashtags(story, platform)
        caption = (
            f"{story.title}\n\nLook beyond the demo: save this for the verification notes and build breakdown."
            f"\n\nSource: {story.source} - {story.url}\n\n{' '.join(hashtags)}"
        )
        package = {
            "id": story.id, "platform": platform, "format": fmt, "tone": tone,
            "title": story.title, "hooks": hooks, "script": script,
            "caption": caption,
            "hashtags": hashtags,
            "hashtag_policy": {"limit": 5 if platform.lower() == "tiktok" else 10, "strategy": "current-trend-signal-plus-topic-relevance"},
            "claims": developed["claims"], "citations": developed["citations"],
            "assets": assets,
            "asset_policy": "source-required",
            "image_text": {
                "status": "awaiting-user-decision",
                "allowed_outputs": ["png", "jpg"],
                "requirements": [
                    "Ask the user before adding text to any image",
                    "Analyze contrast, saliency, existing text, faces, logos and protected content before placement",
                    "Use only short summaries or key points on the image",
                    "Keep the long caption in the post caption",
                    "Preserve every original source image unchanged",
                ],
            },
            "checklist": [
                "Confirm whether the user wants summary text on images",
                "Review unverified claims",
                "Review source attribution and reuse rights",
                "Validate source links",
                "Obtain human approval before publishing",
            ],
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
