# Implementation status

## Available now

| Feature | Implementation |
|---|---|
| Discover | Multi-source collection, normalization, deduplication, archive exclusion and weighted trend ranking |
| Develop | Multi-source claim ledger, numeric/negation contradiction checks, lexical entailment and live URL validation |
| Produce | Template fallback plus OpenAI-compatible or Gemini structured generation with configurable voice profiles |
| RSS | Native RSS and Atom ingestion; configurable custom feeds |
| Firecrawl | REST connector using `FIRECRAWL_API_KEY` |
| Apify | Synchronous Actor connector using `APIFY_TOKEN` |
| GitHub | Search and repository release collectors |
| arXiv | Native Atom API collector |
| Persistence | SQLite by default; PostgreSQL through the optional psycopg adapter |
| Archive | Published-content fingerprint archive prevents duplicate discovery |
| Scheduler | Persistent one-time and interval command scheduler |
| Dashboard | Local responsive dashboard and JSON analytics endpoints |
| Analytics | Workflow counts, metric snapshots, velocity calculation and native platform analytics adapters |
| Publishing | Generic webhook plus X, Meta and TikTok native adapters; dry-run default and explicit human approval |
| Skill | Chat-first routing contract for Codex and compatible agents |
| QA canaries | Configurable per-phase internal checkpoints, excluded from public outputs |
| Operations | Persistent retry queue, worker, health endpoint, event monitoring and failure counts |
| Collaboration | Workspace RBAC and editorial review decisions |
| Object storage | Local object store and optional S3-compatible backend |
| OAuth | Authorization URL and code exchange for X, Meta and TikTok with OS-keyring token storage |

## Adapter boundaries

BrowserOS, OpenTabs, agent-browser, browser-use, Firecrawl, RSSHub and Maxun keep their own runtimes. The core invokes them through CLI, MCP, REST or browser-session boundaries. This is deliberate: authenticated sessions remain local, upstream upgrades remain manageable, and AGPL code is not copied into this core.

Direct TikTok, Meta and X adapters require approved developer applications, scopes and credentials. Contract tests run without credentials; an actual external publish is intentionally impossible until those prerequisites are supplied.

## Live validation

- Google Blog article ingestion was tested with the Gemini 3.6 Flash announcement, including canonical URL, primary-source authority, article text and hero image.
- Authenticated X extraction was tested against Yohei Nakajima's graph-slide post, including text, video duration and engagement metrics.
- Facebook public-page extraction works without login; the current browser session is not signed in to Facebook.
- TikTok loads but its current unauthenticated web runtime exposes no stable content DOM. TikTok API and structured browser-import contracts are tested; account-level crawling needs a signed-in research session.

## Operational safety

- Public research is preferred over logged-in extraction.
- Login and MFA are completed by a human in a dedicated browser profile.
- CAPTCHA and access controls are never bypassed.
- Asset origin and rights are recorded in each package.
- Publishing cannot occur without `--approve`.
