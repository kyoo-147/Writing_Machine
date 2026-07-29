# Content Machine

Source-backed AI content research and production for upload-ready social posts.

Content Machine helps an editor move from a current AI topic to a verified, reusable content package:

```text
discover -> select -> develop -> collect source media -> produce -> manual upload
```

The current product is optimized for human-reviewed, manual publishing. It can discover and rank topics, build a claim ledger, collect article visuals, and generate a complete package containing hooks, script, caption, sources, fact-check notes, assets, and an upload checklist.

Publishing adapters, OAuth helpers, analytics clients, scheduling, and collaboration primitives are included, but they require real platform credentials and deployment-specific validation. They are not a claim that production publishing has been verified end to end.

## Product status

| Area | Status |
|---|---|
| AI topic discovery | Available with GitHub, arXiv, RSS/Atom, and configured connectors |
| Claim and citation development | Available; final editorial verification is still required |
| Source-backed content packages | Available for stories with collected source image or video |
| Article visual collection | Available; collects relevant in-article images and deduplicates them |
| Local persistence and dashboard | Available with SQLite |
| PostgreSQL, S3, Firecrawl, and Apify | Optional; require dependencies, credentials, or deployment |
| Manual upload | Supported and recommended |
| Webhook publishing | Implemented and approval-gated; requires a configured endpoint |
| Native X, Meta, and TikTok publishing | Adapter-level support; not verified end to end with production accounts |
| Post-publish analytics | Client contracts available; require real platform access |

## Core workflow

### 1. Discover

Collect, normalize, deduplicate, and rank current AI stories.

```powershell
.\cm.ps1 discover "AI agents" --count 10
.\cm.ps1 discover "multimodal models" --sources github,arxiv,rss
.\cm.ps1 discover "SDK releases" --sources releases:openai/openai-python,anthropics/anthropic-sdk-python
```

### 2. Select and develop

Choose a returned story ID, then create a claim ledger, citation checks, limitations, and content angles.

```powershell
.\cm.ps1 develop <story-id>
```

Automated claim checks use lexical relevance, numeric conflict detection, negation checks, and URL reachability. A claim is marked `verified` only when a separate stored source supports it; support from the selected story itself is labeled `source-supported`. These checks assist review and do not replace a human fact-check.

### 3. Collect source media

Every production package must contain at least one image or video from the original source or another user-approved source, with provenance and attribution.

Public article ingestion collects relevant in-article images at the best practical responsive resolution:

```powershell
.\cm.ps1 ingest "https://example.com/article"
```

Repository, paper, or social stories may still need their official screenshots, figures, thumbnails, or videos collected during the editorial workflow. If no valid source media is present, `produce` stops instead of generating a placeholder.

### 4. Produce

Create a self-contained package for manual upload:

```powershell
.\cm.ps1 produce <story-id> --platform tiktok --format carousel --tone neutral
```

With a configured model provider:

```powershell
.\cm.ps1 produce <story-id> --platform tiktok --llm --language vi --voice skeptical-builder
```

Results are written under `data/results/<content-id>/` and include:

- title and hook options
- scene-by-scene script or carousel outline
- caption, CTA, and hashtags
- sources and claim notes
- source assets and provenance
- upload checklist and machine-readable package metadata

## Editorial and media rules

- Source media is mandatory; generated illustrations cannot replace it.
- Article ingestion collects all relevant content images, not only the Open Graph image.
- Logos, icons, tracking pixels, unrelated recommendations, and duplicate images are excluded where detectable.
- SVG and locally generated placeholder media are rejected.
- Optional illustrations must be created through the agent's ImageGen capability and saved as PNG or JPG.
- Text is never added to an image or video without explicit user approval.
- Approved overlays preserve the original and must avoid faces, logos, charts, existing text, low-contrast areas, and other protected regions.
- TikTok output contains no more than five familiar, relevant, searchable hashtags.
- Attribution is recorded, but attribution alone does not grant reuse rights. The editor remains responsible for confirming permitted use.

## Quick start

Requirements:

- Python 3.11 or newer
- FFmpeg for video-related workflows

Install and inspect the local runtime:

```powershell
git clone https://github.com/kyoo-147/Writing_Machine.git
cd Writing_Machine
python -m pip install -e .
.\cm.ps1 doctor
```

SQLite is the default and requires no external database. The CLI can also be invoked as `content-machine` or `python -m content_machine`.

For a basic terminal command loop:

```powershell
.\cm.ps1 chat
```

The chat command is a small deterministic shell for `discover`, `develop`, `produce`, and `analytics`. The richer conversational experience is provided by the project skill at `.agents/skills/ai-content-machine/SKILL.md`.

## Configuration

Environment variables are documented in [`.env.example`](.env.example). Do not commit credentials, browser profiles, cookies, OAuth tokens, or session exports.

Optional installs:

```powershell
python -m pip install -e ".[postgres]"
python -m pip install -e ".[s3]"
python -m pip install -e ".[oauth]"
python -m pip install -e ".[dev]"
```

Common integrations:

| Integration | Configuration |
|---|---|
| PostgreSQL | `CONTENT_MACHINE_DATABASE_URL` and the `postgres` extra |
| Firecrawl | `FIRECRAWL_API_KEY` |
| Apify | `APIFY_TOKEN` |
| GitHub API | Optional `GITHUB_TOKEN` for authenticated limits |
| OpenAI-compatible writing | `OPENAI_API_KEY`, `CONTENT_LLM_PROVIDER`, and `CONTENT_LLM_MODEL` |
| Gemini writing | `GEMINI_API_KEY`, provider, and model |
| S3-compatible storage | `S3_BUCKET`, optional `S3_ENDPOINT_URL`, and the `s3` extra |
| OAuth token storage | Platform client settings and the `oauth` extra; runtime clients prefer environment tokens, then OS keyring tokens |

Firecrawl and Apify examples:

```powershell
.\cm.ps1 discover "AI demo" --sources firecrawl:https://example.com
.\cm.ps1 discover "AI" --sources apify:apify/instagram-scraper
```

## Publishing safety

Manual upload is the default. Inspect available routes before attempting any automated publish:

```powershell
.\cm.ps1 publish-capabilities --platform tiktok
```

Webhook publishing is a dry run unless `--approve` is supplied:

```powershell
.\cm.ps1 publish <story-id> --platform tiktok
.\cm.ps1 publish <story-id> --platform tiktok --approve
```

The approved command requires `TIKTOK_PUBLISH_WEBHOOK`, `FACEBOOK_PUBLISH_WEBHOOK`, or `X_PUBLISH_WEBHOOK`, unless `--webhook` is passed explicitly. A webhook response is archived as published only when it contains a stable post ID or public URL.

Native adapters are also approval-gated:

```powershell
.\cm.ps1 oauth url x --state <random-state> --code-challenge <pkce-challenge>
.\cm.ps1 publish <story-id> --platform x --native --approve
.\cm.ps1 platform-analytics x <post-id>
```

Treat these as integration building blocks until OAuth, media upload, publish status, and returned post URL or ID have all been verified with the target account. TikTok native publishing is currently initialization-only until its media upload flow is validated.

OAuth code exchange stores the returned token in the operating-system keyring. Native publishers, capability checks, and analytics clients use an explicit environment token first and fall back to that keyring entry.

## Operations

Run the local dashboard:

```powershell
.\cm.ps1 dashboard
```

Use PostgreSQL and Docker:

```powershell
$env:POSTGRES_PASSWORD = "use-a-secret-manager"
docker compose up --build
```

This starts PostgreSQL and exposes the dashboard at `http://localhost:8787`.

Queue and editorial examples:

```powershell
.\cm.ps1 queue add --job-command discover --payload-file .\examples\discover-job.json
.\cm.ps1 queue work
.\cm.ps1 workspace create --name Editorial
.\cm.ps1 review <story-id> --reviewer editor@example.com --decision approved
```

These are local workflow primitives. Enterprise-grade deployment, monitoring, concurrency, RBAC enforcement across a hosted application, and production object storage still require deployment work.

Scheduled commands are parsed into an argument vector and executed without a command shell. Prefer explicit commands such as `python -m content_machine ...`.

## Verification

Run the complete automated suite:

```powershell
python -m pytest -q
```

The current suite covers pipeline behavior, connector contracts, required source media, visual deduplication, claim checks, publishing gates, queue retry behavior, RBAC, review records, object storage, OAuth URL generation, and analytics contracts.

Contract tests mock external publishing and connector responses. Passing tests do not prove that third-party credentials, scopes, platform review, or production APIs are configured correctly.

## Documentation

- [Implementation status](docs/IMPLEMENTATION_STATUS.md)
- [Manual flow acceptance](docs/FLOW_ACCEPTANCE.md)
- [Scoring model](docs/SCORING.md)
- [Enterprise product plan](docs/ENTERPRISE_PRODUCT_PLAN.md)
- [Integrated repository catalog](docs/REPO_CATALOG.md)
- [Pinned upstream dependencies](VENDOR_LOCK.md)
