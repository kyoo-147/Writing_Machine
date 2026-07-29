from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .core import Database
from .dashboard import serve
from .enterprise import AccessControl, JobQueue, LLMWriter, OAuthManager, PlatformAnalytics, PlatformPublisher
from .pipeline import ContentMachine


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="content-machine", description="Chat-first AI content research and production.")
    p.add_argument("--database", default=os.getenv("CONTENT_MACHINE_DATABASE_URL"))
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("discover", help="Find, deduplicate and score current topics")
    d.add_argument("query", nargs="?", default="artificial intelligence")
    d.add_argument("--count", type=int, default=10)
    d.add_argument("--sources", default="github,arxiv,rss")
    dev = sub.add_parser("develop", help="Verify a selected topic")
    dev.add_argument("story_id")
    prod = sub.add_parser("produce", help="Create a ready-to-post package")
    prod.add_argument("story_id")
    prod.add_argument("--platform", default="tiktok")
    prod.add_argument("--format", default="carousel")
    prod.add_argument("--tone", default="skeptical")
    prod.add_argument("--llm", action="store_true")
    prod.add_argument("--language", default="vi")
    prod.add_argument("--voice", default="skeptical-builder")
    pub = sub.add_parser("publish", help="Publish through a configured adapter")
    pub.add_argument("story_id"); pub.add_argument("--platform", required=True)
    pub.add_argument("--approve", action="store_true"); pub.add_argument("--webhook"); pub.add_argument("--native", action="store_true")
    ingest = sub.add_parser("ingest", help="Ingest a public article URL")
    ingest.add_argument("url")
    social = sub.add_parser("ingest-social", help="Ingest structured data exported from an authenticated browser")
    social.add_argument("json_file")
    queue = sub.add_parser("queue", help="Manage persistent retryable jobs")
    queue.add_argument("action", choices=["add", "lease", "complete", "fail", "stats", "work"])
    queue.add_argument("--job-id"); queue.add_argument("--job-command"); queue.add_argument("--payload", default="{}")
    queue.add_argument("--payload-file")
    workspace = sub.add_parser("workspace", help="Manage workspace RBAC")
    workspace.add_argument("action", choices=["create", "add-member", "check"])
    workspace.add_argument("--name"); workspace.add_argument("--workspace-id"); workspace.add_argument("--user-id")
    workspace.add_argument("--role"); workspace.add_argument("--permission")
    review = sub.add_parser("review", help="Record an editorial decision")
    review.add_argument("story_id"); review.add_argument("--reviewer", required=True)
    review.add_argument("--decision", required=True, choices=["approved", "changes_requested", "rejected"])
    review.add_argument("--comment", default="")
    metrics = sub.add_parser("platform-analytics", help="Fetch post-publish metrics")
    metrics.add_argument("platform"); metrics.add_argument("external_id")
    oauth = sub.add_parser("oauth", help="Create an OAuth URL or securely exchange a code")
    oauth.add_argument("action", choices=["url", "exchange"]); oauth.add_argument("platform", choices=["x", "facebook", "tiktok"])
    oauth.add_argument("--state", default="content-machine"); oauth.add_argument("--code-challenge", default="")
    oauth.add_argument("--code-verifier", default="")
    sub.add_parser("analytics")
    dash = sub.add_parser("dashboard"); dash.add_argument("--host", default="127.0.0.1"); dash.add_argument("--port", type=int, default=8787)
    sched = sub.add_parser("schedule"); sched.add_argument("action", choices=["add", "list", "run"])
    sched.add_argument("--job-command"); sched.add_argument("--run-at"); sched.add_argument("--every", type=int)
    sub.add_parser("doctor")
    sub.add_parser("chat")
    browser = sub.add_parser("browser", help="Open a visible, isolated research browser")
    browser.add_argument("url")
    browser.add_argument("--backend", choices=["auto", "agent-browser", "opentabs", "browseros"], default="auto")
    browser.add_argument("--profile", default="research")
    auth = sub.add_parser("auth", help="Open a platform for manual login and MFA")
    auth.add_argument("platform", choices=["x", "facebook", "tiktok", "reddit", "github"])
    auth.add_argument("--backend", choices=["auto", "agent-browser", "opentabs", "browseros"], default="auto")
    return p


def chat(machine: ContentMachine) -> None:
    print("Content Machine is ready. Try: find 10 AI stories | develop <id> | produce <id> | analytics | quit")
    while True:
        try:
            line = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if line.lower() in {"quit", "exit"}:
            return
        try:
            match = __import__("re").search(r"(?:find|discover)\s*(\d+)?\s*(.*)", line, __import__("re").I)
            if match:
                emit([vars(s) for s in machine.discover(match.group(2) or "AI", int(match.group(1) or 5))]); continue
            parts = shlex.split(line)
            if parts and parts[0] in {"develop", "verify"}:
                emit(machine.develop(parts[1])); continue
            if parts and parts[0] in {"produce", "write"}:
                emit(machine.produce(parts[1])); continue
            if "analytics" in line or "metrics" in line:
                emit(machine.analytics()); continue
            print("Supported intents: find/discover, develop/verify, produce/write, analytics.")
        except Exception as exc:
            emit({"error": str(exc)})


def scheduler(db: Database, action: str, command: str | None, run_at: str | None, every: int | None):
    if action == "add":
        if not command:
            raise ValueError("--command is required")
        db.execute("INSERT INTO schedules(command,run_at,interval_minutes,enabled) VALUES(?,?,?,1)", (command, run_at, every))
        return {"status": "scheduled", "command": command}
    if action == "list":
        rows = db.execute("SELECT row_id,command,run_at,interval_minutes,enabled,last_run FROM schedules").fetchall()
        return [dict(r) if hasattr(r, "keys") else list(r) for r in rows]
    while True:
        rows = db.execute("SELECT row_id,command,run_at,interval_minutes,last_run FROM schedules WHERE enabled=1").fetchall()
        now = datetime.now(timezone.utc)
        for row in rows:
            rid, cmd, at, interval, last = tuple(row)
            due = at and datetime.fromisoformat(at).astimezone(timezone.utc) <= now
            if interval and (not last or (now - datetime.fromisoformat(last)).total_seconds() >= interval * 60):
                due = True
            if due:
                os.system(cmd)
                db.execute("UPDATE schedules SET last_run=? WHERE row_id=?", (now.isoformat(), rid))
        time.sleep(15)


def open_browser(url: str, backend: str = "auto", profile: str = "research") -> dict[str, str]:
    def executable(name: str) -> str | None:
        return shutil.which(f"{name}.cmd") if os.name == "nt" else shutil.which(name)

    available = {
        "agent-browser": executable("agent-browser"),
        "opentabs": executable("opentabs"),
        "browseros": executable("browseros-cli") or executable("bos"),
    }
    if backend == "auto":
        backend = next((name for name in ("browseros", "opentabs", "agent-browser") if available[name]), "system")
    if backend == "agent-browser" and available["agent-browser"]:
        profile_path = os.path.abspath(os.path.join("data", "browser-profiles", profile))
        subprocess.Popen([available["agent-browser"], "--profile", profile_path, "open", url, "--headed"])
    elif backend == "opentabs" and available["opentabs"]:
        subprocess.Popen([available["opentabs"], "start"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        os.startfile(url)
    elif backend == "browseros" and available["browseros"]:
        subprocess.Popen([available["browseros"], "launch"])
        subprocess.run([available["browseros"], "open", url], check=True)
    else:
        os.startfile(url)
        backend = "system"
    return {"status": "opened", "url": url, "backend": backend, "instruction": "Complete login and MFA manually. Browser session data is not exported."}


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    if args.command == "dashboard":
        serve(args.host, args.port, args.database); return 0
    db = Database(args.database)
    machine = ContentMachine(db)
    try:
        if args.command == "discover":
            emit([vars(s) for s in machine.discover(args.query, args.count, [x.strip() for x in args.sources.split(",")])])
        elif args.command == "develop": emit(machine.develop(args.story_id))
        elif args.command == "produce":
            package = machine.produce(args.story_id, args.platform, args.format, args.tone)
            if args.llm:
                story = db.get_story(args.story_id)
                profiles = json.loads(Path("config/voice-profiles.json").read_text(encoding="utf-8"))
                generated = LLMWriter().generate(story, profiles[args.voice], args.platform, args.language)
                generated["hashtags"] = machine.select_hashtags(story, args.platform)
                generated["caption"] = re.sub(
                    r"(?<!\w)#[A-Za-z0-9_]+", "", generated.get("caption", "")
                ).strip()
                generated["caption"] += "\n\n" + " ".join(generated["hashtags"])
                target = Path(package["path"], "llm-package.json")
                target.write_text(json.dumps(generated, ensure_ascii=False, indent=2), encoding="utf-8")
                package["llm_package"] = str(target)
            emit(package)
        elif args.command == "publish":
            if args.native:
                if not args.approve:
                    emit({"status": "dry-run", "message": "Add --approve after human review."})
                else:
                    row = db.execute("SELECT payload FROM packages WHERE story_id=? ORDER BY row_id DESC LIMIT 1", (args.story_id,)).fetchone()
                    if not row:
                        raise RuntimeError("Produce the package first.")
                    emit(PlatformPublisher(args.platform).publish(json.loads(row[0])))
            else:
                emit(machine.publish(args.story_id, args.platform, args.approve, args.webhook))
        elif args.command == "ingest":
            emit([vars(s) for s in machine.discover(args.url, 1, [f"web:{args.url}"])])
        elif args.command == "ingest-social":
            emit(vars(machine.ingest_social(json.loads(Path(args.json_file).read_text(encoding="utf-8")))))
        elif args.command == "queue":
            queue = JobQueue(db)
            if args.action == "add":
                if not args.job_command:
                    raise ValueError("--job-command is required")
                raw_payload = Path(args.payload_file).read_text(encoding="utf-8") if args.payload_file else args.payload
                emit({"job_id": queue.enqueue(args.job_command, json.loads(raw_payload))})
            elif args.action == "lease": emit(queue.lease())
            elif args.action == "complete": queue.complete(args.job_id); emit({"status": "completed"})
            elif args.action == "fail": queue.fail(args.job_id, "Manually failed"); emit({"status": "recorded"})
            elif args.action == "work":
                job = queue.lease()
                if not job:
                    emit({"status": "idle"})
                else:
                    try:
                        payload = job["payload"]
                        if job["command"] == "discover":
                            result = [vars(s) for s in machine.discover(**payload)]
                        elif job["command"] == "develop":
                            result = machine.develop(**payload)
                        elif job["command"] == "produce":
                            result = machine.produce(**payload)
                        else:
                            raise ValueError(f"Unsupported queued command: {job['command']}")
                        queue.complete(job["job_id"])
                        emit({"status": "completed", "job_id": job["job_id"], "result": result})
                    except Exception as exc:
                        queue.fail(job["job_id"], str(exc))
                        raise
            else: emit(queue.stats())
        elif args.command == "workspace":
            access = AccessControl(db)
            if args.action == "create": emit({"workspace_id": access.create_workspace(args.name)})
            elif args.action == "add-member": access.add_member(args.workspace_id, args.user_id, args.role); emit({"status": "added"})
            else: access.require(args.workspace_id, args.user_id, args.permission); emit({"allowed": True})
        elif args.command == "review":
            AccessControl(db).review(args.story_id, args.reviewer, args.decision, args.comment); emit({"status": args.decision})
        elif args.command == "platform-analytics": emit(PlatformAnalytics().fetch(args.platform, args.external_id))
        elif args.command == "oauth":
            manager = OAuthManager()
            if args.action == "url": emit({"url": manager.authorization_url(args.platform, args.state, args.code_challenge)})
            else:
                import getpass
                code = os.getenv("OAUTH_CODE") or getpass.getpass("Authorization code: ")
                emit(manager.exchange(args.platform, code, args.code_verifier))
        elif args.command == "analytics": emit(machine.analytics())
        elif args.command == "schedule": emit(scheduler(db, args.action, args.job_command, args.run_at, args.every))
        elif args.command == "chat": chat(machine)
        elif args.command == "browser": emit(open_browser(args.url, args.backend, args.profile))
        elif args.command == "auth":
            urls = {"x": "https://x.com", "facebook": "https://www.facebook.com", "tiktok": "https://www.tiktok.com",
                    "reddit": "https://www.reddit.com", "github": "https://github.com"}
            emit(open_browser(urls[args.platform], args.backend, args.platform))
        elif args.command == "doctor":
            emit({"python": sys.version, "database": db.url, "ffmpeg": bool(__import__("shutil").which("ffmpeg")),
                  "firecrawl": bool(os.getenv("FIRECRAWL_API_KEY")), "apify": bool(os.getenv("APIFY_TOKEN")),
                  "github": bool(os.getenv("GITHUB_TOKEN")), "agent_browser": bool(shutil.which("agent-browser")),
                  "opentabs": bool(shutil.which("opentabs")),
                  "browseros": bool(shutil.which("browseros-cli") or shutil.which("bos")), "status": "ready"})
        return 0
    except Exception as exc:
        emit({"error": str(exc), "type": type(exc).__name__})
        return 1
