# Implementation status

## Available now

| Feature | Implementation |
|---|---|
| Discover | Multi-source collection, normalization, deduplication, archive exclusion and weighted trend ranking |
| Develop | Claim ledger, source classification, citation extraction and live URL validation |
| Produce | TikTok/social package writer, hooks, scene script, caption, hashtags, generated cover and optional FFmpeg preview |
| RSS | Native RSS and Atom ingestion; configurable custom feeds |
| Firecrawl | REST connector using `FIRECRAWL_API_KEY` |
| Apify | Synchronous Actor connector using `APIFY_TOKEN` |
| GitHub | Search and repository release collectors |
| arXiv | Native Atom API collector |
| Persistence | SQLite by default; PostgreSQL through the optional psycopg adapter |
| Archive | Published-content fingerprint archive prevents duplicate discovery |
| Scheduler | Persistent one-time and interval command scheduler |
| Dashboard | Local responsive dashboard and JSON analytics endpoints |
| Analytics | Story, package, publishing and workflow-event counts |
| Publishing | Generic per-platform webhook adapter, dry-run default and explicit human approval |
| Skill | Chat-first routing contract for Codex and compatible agents |
| QA canaries | Configurable per-phase internal checkpoints, excluded from public outputs |

## Adapter boundaries

BrowserOS, OpenTabs, agent-browser, browser-use, Firecrawl, RSSHub and Maxun keep their own runtimes. The core invokes them through CLI, MCP, REST or browser-session boundaries. This is deliberate: authenticated sessions remain local, upstream upgrades remain manageable, and AGPL code is not copied into this core.

Direct TikTok, Meta and X API implementations require an approved developer application and platform credentials. Until those are supplied, the generic webhook publisher is the production boundary for an n8n, Make, Zapier or private publishing service.

## Operational safety

- Public research is preferred over logged-in extraction.
- Login and MFA are completed by a human in a dedicated browser profile.
- CAPTCHA and access controls are never bypassed.
- Asset origin and rights are recorded in each package.
- Publishing cannot occur without `--approve`.
