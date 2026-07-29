from __future__ import annotations

import json
import os
import re
import shutil
import time
import urllib.parse
import urllib.request
import uuid
import base64
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .connectors import request
from .core import Database, Story, utcnow


ROLE_PERMISSIONS = {
    "viewer": {"read"},
    "creator": {"read", "produce"},
    "reviewer": {"read", "produce", "review"},
    "publisher": {"read", "produce", "review", "publish"},
    "admin": {"read", "produce", "review", "publish", "manage"},
}


class AccessControl:
    def __init__(self, db: Database):
        self.db = db

    def create_workspace(self, name: str) -> str:
        workspace_id = uuid.uuid4().hex[:16]
        self.db.execute("INSERT INTO workspaces(workspace_id,name,created_at) VALUES(?,?,?)", (workspace_id, name, utcnow()))
        return workspace_id

    def add_member(self, workspace_id: str, user_id: str, role: str) -> None:
        if role not in ROLE_PERMISSIONS:
            raise ValueError(f"Unknown role: {role}")
        self.db.execute(
            """INSERT INTO members(workspace_id,user_id,role) VALUES(?,?,?)
            ON CONFLICT(workspace_id,user_id) DO UPDATE SET role=excluded.role""",
            (workspace_id, user_id, role),
        )

    def require(self, workspace_id: str, user_id: str, permission: str) -> None:
        row = self.db.execute("SELECT role FROM members WHERE workspace_id=? AND user_id=?", (workspace_id, user_id)).fetchone()
        if not row or permission not in ROLE_PERMISSIONS.get(row[0], set()):
            raise PermissionError(f"{user_id} lacks {permission} permission")

    def review(self, story_id: str, reviewer_id: str, decision: str, comment: str = "") -> None:
        if decision not in {"approved", "changes_requested", "rejected"}:
            raise ValueError("Invalid review decision")
        self.db.execute(
            "INSERT INTO reviews(story_id,reviewer_id,decision,comment,created_at) VALUES(?,?,?,?,?)",
            (story_id, reviewer_id, decision, comment, utcnow()),
        )


class JobQueue:
    def __init__(self, db: Database):
        self.db = db

    def enqueue(self, command: str, payload: dict[str, Any], max_attempts: int = 3) -> str:
        job_id, now = uuid.uuid4().hex, utcnow()
        self.db.execute(
            """INSERT INTO jobs(job_id,command,payload,status,max_attempts,available_at,created_at,updated_at)
            VALUES(?,?,?,'queued',?,?,?,?)""",
            (job_id, command, json.dumps(payload, ensure_ascii=False), max_attempts, now, now, now),
        )
        return job_id

    def lease(self) -> dict[str, Any] | None:
        row = self.db.execute(
            """SELECT job_id,command,payload,attempts,max_attempts FROM jobs
            WHERE status IN ('queued','retry') AND available_at<=? ORDER BY row_id LIMIT 1""", (utcnow(),)
        ).fetchone()
        if not row:
            return None
        self.db.execute(
            "UPDATE jobs SET status='running',attempts=attempts+1,locked_at=?,updated_at=? WHERE job_id=?",
            (utcnow(), utcnow(), row[0]),
        )
        return {"job_id": row[0], "command": row[1], "payload": json.loads(row[2]), "attempts": row[3] + 1, "max_attempts": row[4]}

    def complete(self, job_id: str) -> None:
        self.db.execute("UPDATE jobs SET status='completed',updated_at=? WHERE job_id=?", (utcnow(), job_id))

    def fail(self, job_id: str, error: str, retry_delay: int = 60) -> None:
        row = self.db.execute("SELECT attempts,max_attempts FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        terminal = row and row[0] >= row[1]
        available = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() + retry_delay))
        self.db.execute(
            "UPDATE jobs SET status=?,last_error=?,available_at=?,updated_at=? WHERE job_id=?",
            ("failed" if terminal else "retry", error[-2000:], available, utcnow(), job_id),
        )

    def stats(self) -> dict[str, int]:
        return {row[0]: row[1] for row in self.db.execute("SELECT status,COUNT(*) FROM jobs GROUP BY status").fetchall()}


class ObjectStore:
    def __init__(self, root: str | Path = "data/objects"):
        self.root = Path(root)

    def put(self, source: Path, key: str) -> str:
        bucket = os.getenv("S3_BUCKET")
        if bucket:
            try:
                import boto3  # type: ignore
            except ImportError as exc:
                raise RuntimeError("Install S3 support with pip install '.[s3]'") from exc
            boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT_URL")).upload_file(str(source), bucket, key)
            return f"s3://{bucket}/{key}"
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return str(target)


def _terms(text: str) -> set[str]:
    stop = {"the", "a", "an", "and", "or", "to", "of", "in", "is", "it", "for", "with", "on"}
    return {x for x in re.findall(r"[a-z0-9.%-]+", text.lower()) if len(x) > 2 and x not in stop}


class ClaimChecker:
    NEGATIONS = {"not", "never", "without", "fails", "no"}

    def check(self, claim: str, evidence: list[Story]) -> dict[str, Any]:
        terms = _terms(claim)
        ranked = sorted(evidence, key=lambda item: len(terms & _terms(f"{item.title} {item.summary}")) / max(1, len(terms)), reverse=True)
        best = ranked[0] if ranked else None
        candidates = re.split(r"(?<=[.!?])\s+", f"{best.title}. {best.summary}") if best else []
        excerpt = max(candidates, key=lambda text: len(terms & _terms(text)), default="")
        entailment = len(terms & _terms(excerpt)) / max(1, len(terms))
        quantitative = "%" in claim or "$" in claim or bool(re.search(r"\d+\s+(?:tokens?|seconds?|views?|likes?|reposts?|bookmarks?)", claim.lower()))
        claim_numbers = set(re.findall(r"\$?\d+(?:\.\d+)?%?", claim)) if quantitative else set()
        evidence_numbers = set(re.findall(r"\$?\d+(?:\.\d+)?%?", excerpt))
        number_conflict = bool(claim_numbers and evidence_numbers and not claim_numbers.issubset(evidence_numbers))
        negation_conflict = bool(best and entailment > 0.55 and bool(terms & self.NEGATIONS) != bool(_terms(excerpt) & self.NEGATIONS))
        verdict = "contradicted" if number_conflict or negation_conflict else "verified" if entailment >= 0.55 else "unverified"
        return {"claim": claim, "verdict": verdict, "entailment": round(entailment, 3),
                "evidence_url": best.url if best else "", "evidence_excerpt": excerpt,
                "number_conflict": number_conflict}

    def validate_citation(self, claim: str, source: Story) -> dict[str, Any]:
        result = self.check(claim, [source])
        result["accessible"] = source.url.startswith(("http://", "https://"))
        result["primary"] = source.kind in {"release", "paper"} or any(
            host in source.url for host in ("blog.google", "openai.com", "anthropic.com", "github.com", "arxiv.org"))
        return result


class LLMWriter:
    def __init__(self, provider: str | None = None, model: str | None = None):
        self.provider = provider or os.getenv("CONTENT_LLM_PROVIDER", "openai")
        self.model = model or os.getenv("CONTENT_LLM_MODEL", "gpt-5-mini")

    def generate(self, story: Story, voice: dict[str, Any], platform: str, language: str = "vi") -> dict[str, Any]:
        prompt = json.dumps({
            "task": "Create a human-sounding social content package as strict JSON.",
            "language": language, "platform": platform, "voice": voice, "story": asdict(story),
            "schema": {"title": "string", "hooks": ["string"], "script": [{"scene": 1, "voice": "string", "visual": "string"}],
                       "caption": "string", "hashtags": ["string"], "claims": ["string"]},
            "rules": ["Separate facts from opinion", "Preserve uncertainty", "Avoid generic AI hype", "Use primary-source citations"],
        }, ensure_ascii=False)
        if self.provider == "gemini":
            key = os.getenv("GEMINI_API_KEY")
            if not key:
                raise RuntimeError("GEMINI_API_KEY is required")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={key}"
            raw = json.loads(request(url, headers={"Content-Type": "application/json"}, data={
                "contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}}))
            text = raw["candidates"][0]["content"]["parts"][0]["text"]
        else:
            key = os.getenv("OPENAI_API_KEY")
            if not key:
                raise RuntimeError("OPENAI_API_KEY is required")
            raw = json.loads(request(f"{os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                data={"model": self.model, "response_format": {"type": "json_object"},
                      "messages": [{"role": "user", "content": prompt}]}))
            text = raw["choices"][0]["message"]["content"]
        return json.loads(text)


class PlatformPublisher:
    def __init__(self, platform: str):
        self.platform = platform.lower()

    def publish(self, package: dict[str, Any]) -> dict[str, Any]:
        if self.platform == "x":
            token, endpoint = os.getenv("X_ACCESS_TOKEN"), "https://api.x.com/2/tweets"
            payload, headers = {"text": package["caption"][:280]}, {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        elif self.platform == "facebook":
            token, page = os.getenv("META_ACCESS_TOKEN"), os.getenv("META_PAGE_ID")
            endpoint, payload = f"https://graph.facebook.com/v23.0/{page}/feed", {"message": package["caption"], "access_token": token}
            headers = {"Content-Type": "application/json"}
        elif self.platform == "tiktok":
            token, endpoint = os.getenv("TIKTOK_ACCESS_TOKEN"), "https://open.tiktokapis.com/v2/post/publish/content/init/"
            payload, headers = package["tiktok_payload"], {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
        else:
            raise ValueError(f"Unsupported platform: {self.platform}")
        if not token:
            raise RuntimeError(f"{self.platform.upper()} credentials are not configured")
        return json.loads(request(endpoint, headers=headers, data=payload))


class PlatformAnalytics:
    def fetch(self, platform: str, external_id: str) -> dict[str, Any]:
        platform = platform.lower()
        if platform == "x":
            url = f"https://api.x.com/2/tweets/{external_id}?tweet.fields=public_metrics,non_public_metrics,organic_metrics"
            return json.loads(request(url, headers={"Authorization": f"Bearer {os.getenv('X_ACCESS_TOKEN')}"}))
        if platform == "facebook":
            token = urllib.parse.quote(os.getenv("META_ACCESS_TOKEN", ""))
            url = f"https://graph.facebook.com/v23.0/{external_id}/insights?metric=post_impressions,post_engaged_users&access_token={token}"
            return json.loads(request(url))
        if platform == "tiktok":
            url = "https://open.tiktokapis.com/v2/video/query/?fields=id,view_count,like_count,comment_count,share_count"
            return json.loads(request(url, headers={"Authorization": f"Bearer {os.getenv('TIKTOK_ACCESS_TOKEN')}",
                "Content-Type": "application/json"}, data={"filters": {"video_ids": [external_id]}}))
        raise ValueError(platform)


class OAuthManager:
    CONFIG = {
        "x": {
            "authorize": "https://x.com/i/oauth2/authorize",
            "token": "https://api.x.com/2/oauth2/token",
            "scopes": "tweet.read tweet.write users.read offline.access",
        },
        "facebook": {
            "authorize": "https://www.facebook.com/v23.0/dialog/oauth",
            "token": "https://graph.facebook.com/v23.0/oauth/access_token",
            "scopes": "pages_manage_posts,pages_read_engagement,read_insights",
        },
        "tiktok": {
            "authorize": "https://www.tiktok.com/v2/auth/authorize/",
            "token": "https://open.tiktokapis.com/v2/oauth/token/",
            "scopes": "user.info.basic,video.publish,video.list",
        },
    }

    def authorization_url(self, platform: str, state: str, code_challenge: str = "") -> str:
        platform = platform.lower()
        config = self.CONFIG[platform]
        prefix = platform.upper()
        params = {
            "client_id" if platform != "tiktok" else "client_key": os.getenv(f"{prefix}_CLIENT_ID"),
            "redirect_uri": os.getenv(f"{prefix}_REDIRECT_URI"),
            "response_type": "code",
            "scope": config["scopes"],
            "state": state,
        }
        if platform == "x":
            params.update({"code_challenge": code_challenge, "code_challenge_method": "S256"})
        if not params[next(iter(params))] or not params["redirect_uri"]:
            raise RuntimeError(f"{prefix} OAuth client configuration is missing")
        return f"{config['authorize']}?{urllib.parse.urlencode(params)}"

    def exchange(self, platform: str, code: str, code_verifier: str = "") -> dict[str, Any]:
        platform = platform.lower()
        prefix, config = platform.upper(), self.CONFIG[platform]
        form = {
            "client_id" if platform != "tiktok" else "client_key": os.getenv(f"{prefix}_CLIENT_ID", ""),
            "client_secret": os.getenv(f"{prefix}_CLIENT_SECRET", ""),
            "redirect_uri": os.getenv(f"{prefix}_REDIRECT_URI", ""),
            "code": code,
            "grant_type": "authorization_code",
        }
        if platform == "x":
            form["code_verifier"] = code_verifier
        body = urllib.parse.urlencode(form).encode()
        req = urllib.request.Request(config["token"], data=body, headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "VN-Content-Machine/0.3"})
        with urllib.request.urlopen(req, timeout=35) as response:
            token = json.loads(response.read())
        self._store_token(platform, token)
        return {"stored": True, "platform": platform, "expires_in": token.get("expires_in")}

    @staticmethod
    def _store_token(platform: str, token: dict[str, Any]) -> None:
        try:
            import keyring  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Install secure OAuth storage with pip install '.[oauth]'") from exc
        keyring.set_password("content-machine", platform, json.dumps(token))


class MediaGenerator:
    def generate_image(self, prompt: str, target: Path, size: str = "1024x1536") -> Path:
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is required for model image generation")
        raw = json.loads(request(f"{os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')}/images/generations",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            data={"model": os.getenv("IMAGE_MODEL", "gpt-image-1"), "prompt": prompt, "size": size, "response_format": "b64_json"}))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(raw["data"][0]["b64_json"]))
        return target

    def generate_video(self, prompt: str, target: Path) -> Path:
        endpoint = os.getenv("VIDEO_GENERATION_WEBHOOK")
        if not endpoint:
            raise RuntimeError("VIDEO_GENERATION_WEBHOOK is required for model video generation")
        raw = json.loads(request(endpoint, headers={"Content-Type": "application/json"}, data={"prompt": prompt}))
        media_url = raw.get("url")
        if not media_url:
            raise RuntimeError("Video provider did not return a downloadable URL")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(request(media_url))
        return target
