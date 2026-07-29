# VN Tech Lab Content Machine

Chat-first pipeline for finding, verifying, producing, scheduling and publishing AI content.

## Quick start

```powershell
cd D:\working\Content_Machine
python -m pip install -e .
.\cm.ps1 doctor
.\cm.ps1 discover "AI agents" --count 10
.\cm.ps1 ingest "https://blog.google/example"
.\cm.ps1 ingest-social .\browser-export.json
.\cm.ps1 develop <story-id>
.\cm.ps1 produce <story-id> --platform tiktok --format carousel --tone skeptical
.\cm.ps1 produce <story-id> --platform tiktok --llm --language vi --voice skeptical-builder
.\cm.ps1 dashboard
```

Production enforces a source-required asset policy. Every package must include at least one image or video from the original or user-approved source, stored with provenance and attribution; otherwise `produce` stops with an error. SVG and locally generated placeholders are rejected. If an additional illustration is explicitly requested in chat, the agent must use the installed ImageGen skill, save a PNG/JPG named `imagegen-<name>`, and keep it supplemental to the mandatory source media.

TikTok packages contain at most five hashtags. Current trend signals are accepted through story metadata or `TIKTOK_TRENDING_HASHTAGS`, filtered for topic relevance, and combined with specific technology and channel tags.

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
.\cm.ps1 publish-capabilities --platform tiktok
.\cm.ps1 publish <story-id> --platform tiktok
.\cm.ps1 publish <story-id> --platform tiktok --approve
```

The capability command reports safe routes without exposing credentials. The unapproved publish command is a dry run. The approved command requires `TIKTOK_PUBLISH_WEBHOOK` (or a `--webhook`) and archives the result to prevent reposting.

Native platform adapters are also available after OAuth configuration:

```powershell
.\cm.ps1 oauth url x --state <random-state> --code-challenge <pkce-challenge>
.\cm.ps1 publish <story-id> --platform x --native --approve
.\cm.ps1 platform-analytics x <post-id>
```

Authorization codes are read from a hidden prompt or `OAUTH_CODE`; tokens are stored through the operating-system keyring. The project never writes OAuth tokens to its database.

Retryable workers and editorial controls:

```powershell
.\cm.ps1 queue add --job-command discover --payload-file .\discover-job.json
.\cm.ps1 queue work
.\cm.ps1 workspace create --name Editorial
.\cm.ps1 review <story-id> --reviewer editor@example.com --decision approved
```

See [the product plan](docs/ENTERPRISE_PRODUCT_PLAN.md), [repository catalog](docs/REPO_CATALOG.md), and [pinned dependencies](VENDOR_LOCK.md).

## Docker and PostgreSQL

```powershell
$env:POSTGRES_PASSWORD = "use-a-secret-manager"
docker compose up --build
```

This starts PostgreSQL and the dashboard at `http://localhost:8787`.
