# VN Tech Lab Content Machine

Chat-first pipeline for finding, verifying, producing, scheduling and publishing AI content.

## Quick start

```powershell
cd D:\working\Content_Machine
python -m pip install -e .
.\cm.ps1 doctor
.\cm.ps1 discover "AI agents" --count 10
.\cm.ps1 develop <story-id>
.\cm.ps1 produce <story-id> --platform tiktok --format carousel --tone skeptical
.\cm.ps1 dashboard
```

Or start a friendly terminal session:

```powershell
.\cm.ps1 chat
```

For authenticated research, open a dedicated profile and complete login or MFA manually:

```powershell
.\cm.ps1 auth x
.\cm.ps1 browser https://www.facebook.com --backend agent-browser --profile facebook-research
```

## Configuration

Copy `.env.example` values into your environment. SQLite works with no setup. For PostgreSQL install `pip install -e ".[postgres]"` and set `CONTENT_MACHINE_DATABASE_URL`.

Connectors can be combined:

```powershell
.\cm.ps1 discover "multimodal agents" --sources github,arxiv,rss
.\cm.ps1 discover "Claude" --sources releases:anthropics/anthropic-sdk-python,openai/openai-python
.\cm.ps1 discover "AI demo" --sources firecrawl:https://example.com
.\cm.ps1 discover "AI" --sources apify:apify/instagram-scraper
```

Publishing is intentionally gated:

```powershell
.\cm.ps1 publish <story-id> --platform tiktok
.\cm.ps1 publish <story-id> --platform tiktok --approve
```

The first command is a dry run. The approved command requires `TIKTOK_PUBLISH_WEBHOOK` (or a `--webhook`) and archives the result to prevent reposting.

See [the product plan](docs/ENTERPRISE_PRODUCT_PLAN.md), [repository catalog](docs/REPO_CATALOG.md), and [pinned dependencies](VENDOR_LOCK.md).

## Docker and PostgreSQL

```powershell
$env:POSTGRES_PASSWORD = "use-a-secret-manager"
docker compose up --build
```

This starts PostgreSQL and the dashboard at `http://localhost:8787`.
