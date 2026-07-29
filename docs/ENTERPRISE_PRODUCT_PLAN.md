# VN Tech Lab Content Machine — Enterprise Product Plan

## 1. Product objective

Build a governed AI content operations platform that discovers current AI information, verifies claims, develops differentiated editorial angles, produces platform-native media packages, and later publishes and optimizes content with human approval.

The first product is a local CLI and conversational skill. The enterprise product evolves into a multi-user research and content operations system.

## 2. Product principles

1. Reuse proven open source through adapters.
2. Prefer primary sources and auditable evidence.
3. Keep authenticated browser sessions local where possible.
4. Separate facts, inference, and editorial opinion.
5. Require human approval for public actions.
6. Store provenance for every claim and asset.
7. Treat platform access, copyright, privacy, and security as product features.
8. Avoid coupling the core domain model to a single browser or model provider.

## 3. Reuse architecture

| Capability | Reused component | Product boundary |
|---|---|---|
| Logged-in visible browser | BrowserOS/BrowserClaw | External local process over MCP |
| Deterministic browser CLI | agent-browser | CLI adapter |
| Authenticated web-app APIs | OpenTabs | Local extension and MCP/CLI |
| Marketing expertise | marketingskills | Selective skill loading |
| Search/crawl later | Firecrawl, Crawl4AI, Apify | Provider adapters |
| Feed ingestion later | RSSHub | Feed connector |
| Workflow orchestration later | Temporal, LangGraph, or n8n | Job orchestration adapter |

Do not modify vendored sources for routine customization. Maintain small adapters and pin tested revisions.

## 4. User journeys

### Daily discovery

1. User requests a number of AI posts.
2. System asks only for missing editorial constraints.
3. Scouts collect official sources and community signals.
4. Deduplication groups the same event.
5. Ranking produces a shortlist.
6. User selects topics.

### Content development

1. System builds a source graph and claim ledger.
2. Research agents explain technical context and limitations.
3. Strategist proposes news, builder, skeptical, and visual angles.
4. User approves an angle and format.

### Production

1. Script, carousel, image, or video brief is generated.
2. Assets are sourced or generated with rights metadata.
3. Human-likeness and fact-check reviews run.
4. The user receives a complete upload package.

### Publishing phase

1. User connects platform accounts.
2. Publisher prepares drafts.
3. Human approves each public action.
4. System publishes, records links, and captures analytics.

## 5. Logical architecture

```text
Clients
  CLI | Chat | Web dashboard | Mobile approval
                         |
API gateway and identity
                         |
Content Coordinator / Workflow Engine
  |          |           |            |
Discovery  Research    Production   Publishing
  |          |           |            |
Connector and Tool Gateway
  |        |         |         |       |
RSS/API  Crawlers  Browser  OpenTabs  Media
                         |
Governance Layer
  policy | approvals | secrets | audit | quotas
                         |
Data Layer
  Postgres | object storage | search index | event log
```

## 6. Core services

### Content coordinator

- Converts conversational requests into jobs.
- Controls phase transitions.
- Chooses tools and models by policy.
- Enforces approval gates.
- Handles retries and partial failures.

### Source registry

- Stores sources, ownership, reliability tier, crawl policy, and refresh interval.
- Supports official, repository, paper, media, and community source classes.
- Tracks platform-specific access terms.

### Ingestion service

- RSS and webhook polling.
- Search and crawl jobs.
- Browser-assisted extraction.
- Social metadata and media discovery.
- Normalized content records.

### Deduplication and clustering

- URL canonicalization.
- Content fingerprinting.
- Entity and event clustering.
- Near-duplicate visual detection.

### Verification service

- Claim extraction.
- Primary-source matching.
- Contradiction search.
- Benchmark and date validation.
- Confidence and reviewer notes.

### Editorial intelligence

- Audience and channel fit.
- Topic scoring.
- Angle generation.
- Voice profile application.
- Repetition and archive awareness.

### Asset service

- Screenshot and video capture.
- Paper figure extraction.
- Image generation.
- Transcoding and subtitles.
- Rights, attribution, checksum, and source tracking.

### Publishing service

- Platform draft creation.
- Human approval.
- Scheduled publishing.
- Retry and idempotency.
- Link and platform post ID capture.

### Analytics service

- Views, watch time, retention, saves, shares, comments, and follows.
- Cross-platform normalization.
- Hook, format, topic, and voice attribution.
- Editorial experiments and recommendations.

## 7. Data model

Primary entities:

- `workspace`
- `user`
- `role`
- `source`
- `source_credential_reference`
- `document`
- `event_cluster`
- `claim`
- `evidence`
- `content_item`
- `content_angle`
- `production_brief`
- `asset`
- `content_version`
- `approval`
- `publication`
- `performance_snapshot`
- `workflow_run`
- `tool_call`
- `audit_event`

Every derived item must point to its input documents, model/tool version, prompt or skill revision, and timestamp.

## 8. Workflow states

```text
requested
→ collecting
→ clustered
→ verifying
→ shortlisted
→ selected
→ developing
→ awaiting_angle_approval
→ producing
→ editorial_review
→ awaiting_publish_approval
→ scheduled
→ published
→ measuring
→ archived
```

Failed states must preserve partial artifacts and support retry from the last safe checkpoint.

## 9. Authentication and browser strategy

### Public data

Use RSS, official APIs, search, and direct extraction.

### Authenticated read access

Priority:

1. OpenTabs plugin calling the site's authenticated API.
2. BrowserClaw/BrowserOS using a dedicated local profile.
3. agent-browser persistent isolated profile.
4. Official platform API when available and sufficient.

### Security controls

- Credentials stay in OS keychain or provider vault.
- Models never receive plaintext passwords.
- Session files are excluded from source control.
- Browser profiles are isolated per workspace and purpose.
- Write tools default to approval-required.
- Domain allowlists apply where compatible with authentication mode.
- Sessions have idle timeout and revocation controls.
- Audit logs redact secrets and personal data.

Do not bypass CAPTCHA or platform controls. Present login and MFA to the user.

## 10. Licensing strategy

- BrowserOS/BrowserClaw: AGPL-3.0. Keep process-separated and use published MCP/CLI interfaces. Obtain legal review before redistribution, hosted modification, or embedding.
- agent-browser: Apache-2.0. Preserve notices and license.
- marketingskills: MIT. Preserve copyright and license.
- OpenTabs: MIT. Preserve copyright and license.

Maintain an automated software bill of materials, license scan, vulnerability scan, and revision lock.

## 11. Multi-tenancy

- Workspace-scoped data and browser profiles.
- Tenant-specific encryption keys.
- RBAC: owner, strategist, researcher, editor, publisher, analyst, viewer.
- Row-level security in Postgres.
- Object-storage prefixes and signed URLs per workspace.
- Per-tenant quotas for crawl, models, generation, and storage.
- Data retention and export policies.

## 12. Reliability

Initial service objectives:

- API availability: 99.9%.
- No duplicate publication for the same idempotency key.
- 99% of claims retain at least one evidence link.
- 100% of public actions have an approval or explicit automation policy.
- Recoverable workflow checkpoint after every phase.

Use durable queues, idempotent workers, exponential backoff, dead-letter queues, and provider circuit breakers.

## 13. Observability

- Structured logs with workflow, content, tenant, and tool-call IDs.
- Distributed traces across coordinator, connectors, and workers.
- Metrics for source freshness, extraction success, verification coverage, cost, latency, and publication failures.
- Browser session replay for approved enterprise use.
- Prompt/skill/model revision attached to every generated artifact.

## 14. AI and model governance

- Provider abstraction for OpenAI, Anthropic, Gemini, and local models.
- Model routing by task, sensitivity, latency, and budget.
- Evaluation sets for Vietnamese style, factuality, citation coverage, and AI-slop.
- Regression testing before skill or model upgrades.
- Prompt-injection scanning for browsed content.
- Tool outputs treated as untrusted data.
- No source page may alter system policy or approval rules.

## 15. Editorial governance

- Workspace brand profile and prohibited-claim policy.
- Configurable voice profiles and intensity.
- Sensitive-topic review.
- Duplicate-topic cooldown.
- Required citation count by content type.
- Asset-rights approval.
- Version history and reviewer comments.

## 16. Deployment options

### Local creator edition

- CLI, skill, SQLite, local files, local browser.
- Manual upload.

### Team edition

- Web dashboard, Postgres, object storage, shared source registry.
- Local browser bridge for authenticated sessions.
- Central orchestration and approvals.

### Enterprise edition

- SSO/SAML, SCIM, RBAC, audit export, private networking, customer-managed keys, retention controls, regional deployment, and policy packs.

## 17. Roadmap

### Phase 0 — Current foundation

- Vendor and pin selected projects.
- Deliver `ai-content-machine` skill.
- Deliver PowerShell CLI for jobs and browser login.
- Define schemas, routing, voice, and product plan.

### Phase 1 — Local MVP

- Implement discovery jobs and result folders.
- Add RSS and GitHub connectors.
- Add claim ledger and asset manifest.
- Validate BrowserOS, agent-browser, and OpenTabs on X/Facebook test accounts.
- Add three representative content packages.

### Phase 2 — Creator workstation

- Local web dashboard.
- SQLite/Postgres.
- Background source polling.
- Deduplication and ranking.
- Asset downloads and generation.
- Manual approval workflow.

### Phase 3 — Team product

- Multi-user workspaces and RBAC.
- Central source registry.
- Review queues and comments.
- Publishing drafts and scheduling.
- Analytics ingestion.

### Phase 4 — Enterprise

- SSO/SCIM.
- Policy engine and audit export.
- Tenant isolation.
- Model governance and evaluation service.
- Private deployment and managed browser bridge.

### Phase 5 — Optimization

- Performance-driven topic and hook recommendations.
- Controlled editorial experiments.
- Forecasting and content-calendar optimization.
- Automated publishing only for explicitly approved low-risk workflows.

## 18. Immediate engineering backlog

1. Install and test one authenticated browser backend.
2. Build source and content-item persistence.
3. Implement `discover`, `develop`, and `produce` CLI lifecycle commands.
4. Add RSS, GitHub release, arXiv, and official blog connectors.
5. Implement claim ledger and citation validation.
6. Add OpenTabs feasibility tests for X, Facebook, Reddit, and TikTok.
7. Add isolated browser-profile management and secret redaction.
8. Create a small Vietnamese editorial evaluation set.
9. Produce three end-to-end sample posts.
10. Decide the Phase 2 workflow engine after measuring local MVP complexity.

