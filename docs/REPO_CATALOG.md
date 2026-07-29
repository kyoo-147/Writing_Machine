# Repository integration catalog

The product core is local-first Python. Upstreams are references or replaceable adapters, not copied implementations.

| Capability | Primary | Fallback | Integration |
|---|---|---|---|
| Public extraction | Firecrawl | Crawl4AI, RSSHub | REST API / separate process |
| Logged-in X/Facebook | OpenTabs | BrowserOS, agent-browser, browser-use | Existing browser session; never export cookies |
| Structured social crawl | Apify | Maxun | Actor REST API / separate service |
| Primary AI signals | GitHub Releases, arXiv, official RSS | public web | Native collectors |
| Research workflow | ai-berkshire, deer-flow | agency-agents | Patterns only |
| Editorial workflow | marketingskills | social-media-skills, agency-agents | Load selected `SKILL.md` |
| Agent discipline | superpowers | mattpocock/skills | Planning and verification patterns |
| GUI automation | BrowserOS | Horizon | Process boundary |

## Runtime policy

- Native core: SQLite/PostgreSQL, ranking, deduplication, verification ledger, package/archive/analytics.
- Optional service adapters: Firecrawl, Apify and publish webhooks.
- Authenticated research stays in a dedicated, visible browser profile. Login and MFA are manual.
- Auto-publishing is dry-run by default and requires both `--approve` and a configured platform webhook.
- QA canaries are written to internal event logs; they are never included in public captions or scripts.

## Why the repositories are not merged wholesale

The pinned sources have different runtimes and licenses. Keeping them behind adapters preserves upgrades, prevents cookie leakage, and avoids importing AGPL code into the product core. `VENDOR_LOCK.md` records the exact reviewed revisions.

