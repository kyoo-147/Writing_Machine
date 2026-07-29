from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

from .core import Database
from .dashboard import serve
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
    pub = sub.add_parser("publish", help="Publish through a configured adapter")
    pub.add_argument("story_id"); pub.add_argument("--platform", required=True)
    pub.add_argument("--approve", action="store_true"); pub.add_argument("--webhook")
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
    args = build_parser().parse_args(argv)
    if args.command == "dashboard":
        serve(args.host, args.port); return 0
    db = Database(args.database)
    machine = ContentMachine(db)
    try:
        if args.command == "discover":
            emit([vars(s) for s in machine.discover(args.query, args.count, [x.strip() for x in args.sources.split(",")])])
        elif args.command == "develop": emit(machine.develop(args.story_id))
        elif args.command == "produce": emit(machine.produce(args.story_id, args.platform, args.format, args.tone))
        elif args.command == "publish": emit(machine.publish(args.story_id, args.platform, args.approve, args.webhook))
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
