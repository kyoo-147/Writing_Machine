---
name: ai-content-machine
description: Research, verify, develop, and package current AI news, tools, repositories, papers, demos, and community discussions into human-sounding TikTok, Facebook, X, carousel, image, or short-video content. Use when the user asks for AI trends, daily content ideas, source collection, logged-in browser research, fact-checking, content angles, scripts, captions, visual assets, or a ready-to-upload social content package.
---

# AI Content Machine

Operate as the conversational coordinator for the VN Tech Lab content pipeline. Reuse the vendored browser and marketing projects; do not recreate their capabilities.

## Start

1. Identify the requested phase:
   - `discover`: find and rank topics.
   - `develop`: verify a selected topic and propose angles.
   - `produce`: create the final content package.
2. Ask only for missing information that materially changes the result.
3. Default to three topics, Vietnamese, mixed technical audience, and manual publishing.
4. Never publish automatically unless the user explicitly enables a later publishing phase.
5. Source media is mandatory. Every production package must contain at least one image or video taken from the original source or another user-approved source, with provenance and attribution. Do not complete production without it.
6. Never create SVG assets. If the user explicitly requests an original illustration or architecture diagram, invoke the installed ImageGen skill and save the result as PNG or JPG. ImageGen output is optional supporting media and never replaces the mandatory source media.
7. For TikTok, include no more than five hashtags. Prefer current trend signals that are genuinely relevant to the topic, then add specific technology and channel tags. Never add an unrelated viral hashtag merely because it is popular.

Use the real CLI for every phase so results are persisted, deduplicated, auditable, and reusable:

```powershell
.\cm.ps1 doctor
.\cm.ps1 discover "AI news today" --count 3
.\cm.ps1 develop <story-id>
.\cm.ps1 produce <story-id> --platform tiktok --format carousel --tone skeptical
.\cm.ps1 dashboard
```

Before any publishing promise or action, read [publishing-routing.md](references/publishing-routing.md), run `.\cm.ps1 publish-capabilities --platform <platform>`, and inspect the current agent's callable tools. A skill describes how to use capabilities; it does not grant browser access, authentication, platform scopes, or credentials.

When Browser is used for an authenticated social page, extract only visible post fields into the `ingest-social` contract: platform, URL, author, text, published timestamp, metrics, and media metadata. Never extract cookies or storage. Feed that JSON to `.\cm.ps1 ingest-social <file>`.

Use `produce --llm` when a configured model provider is available. Otherwise let the active agent write in the user's language and preserve the same package schema. Native publishing always requires an approved review, explicit `--approve`, platform OAuth scopes, and a final user-confirmed publishing request.

For a conversational terminal, run `.\cm.ps1 chat`. Infer discover, develop, and produce intents from the user's language; keep project files in English and answer in the user's language.

At the end of each phase, confirm its QA canary exists in the database event log. Canary text is internal only and must never appear in public scripts, captions, assets, or posts.

## Route tools

Read [tool-routing.md](references/tool-routing.md) before accessing social sites, authenticated pages, or dynamic applications.

Use this priority:

1. Official release notes, papers, repositories, RSS, and public APIs.
2. Direct readable extraction for public pages.
3. OpenTabs for authenticated web-app APIs exposed through an already logged-in tab.
4. BrowserOS/BrowserClaw for visible, logged-in browser work and auditable sessions.
5. agent-browser for deterministic CLI automation, isolated profiles, screenshots, and fallback DOM interaction.

Do not export cookies into the project. Do not bypass CAPTCHA, access controls, platform limits, or private data boundaries.

## Discover

1. Search primary sources first: official company news, changelogs, GitHub releases, papers, and project documentation.
2. Add community signals from X, Reddit, TikTok, Hacker News, and GitHub only as trend evidence.
3. Deduplicate stories describing the same event.
4. Score each candidate:
   - novelty: 25%
   - visual or demo strength: 20%
   - buildability: 15%
   - AI engineering relevance: 15%
   - source authority: 10%
   - discussion or controversy: 10%
   - Vietnamese audience fit: 5%
5. Return a compact shortlist with title, why it matters, source links, visual availability, format fit, and score.
6. The command persists results in SQLite/PostgreSQL and excludes archived stories.
7. Stop for selection unless the user asked for autonomous production.

## Develop

1. Build a claim ledger using [content-contract.md](references/content-contract.md).
2. Find the original source, author, date, repository or paper, and official media.
3. Mark every important claim as `verified`, `disputed`, or `unverified`.
4. Explain the technical mechanism, limitations, and prior art.
5. Produce at least three distinct angles:
   - news/update
   - technical/build
   - skeptical/contrarian
6. Recommend one angle and explain the tradeoff in one sentence.
7. Run citation validation and preserve `unverified` claims as uncertainty.
8. Collect official/source assets during development. Record the original URL, author, attribution, and reuse-rights status. Do not assume attribution alone grants reuse rights.
9. Stop production if no source image or video has been collected. Source-media downloads are allowed when requested, but preserve provenance and never bypass access controls.
10. Use ImageGen only when the user asks for an additional original illustration. Store it as `data/assets/<story-id>/imagegen-<name>.png` or `.jpg`; never use SVG, local placeholder art, or a direct image-model API in this project.

## Produce

1. Confirm platform, format, duration, audience, tone, asset requirements, and CTA.
2. Load only the relevant vendored marketing skills:
   - strategy: `vendor/marketingskills/skills/content-strategy/SKILL.md`
   - social: `vendor/marketingskills/skills/social/SKILL.md`
   - video: `vendor/marketingskills/skills/video/SKILL.md`
   - editing: `vendor/marketingskills/skills/copy-editing/SKILL.md`
   - psychology: `vendor/marketingskills/skills/marketing-psychology/SKILL.md`
   - images: `vendor/marketingskills/skills/image/SKILL.md`
3. Apply the selected profile from [voice-system.md](references/voice-system.md).
4. Create:
   - title and 3 hook options
   - scene-by-scene script or carousel outline
   - on-screen text
   - caption, CTA, and hashtags
   - source list and fact-check notes
   - asset manifest with origin and usage rights
   - upload checklist
5. Use source media as the required visual baseline and add explicit source attribution to the caption. Reject production if source media is missing.
6. Do not add generated covers, decorative AI art, or placeholder videos. When an illustration is explicitly requested, use the ImageGen skill, output PNG/JPG, and keep it supplemental to source media.
7. For TikTok, verify current hashtag signals when accessible, keep only relevant tags, and enforce a maximum of five. If trend data is unavailable, use relevance-first topic tags and do not claim that they are trending.
8. Run an editorial pass:
   - remove generic AI phrases and fake enthusiasm
   - vary sentence length
   - distinguish facts, inference, and opinion
   - preserve uncertainty
   - ensure the piece adds a new angle
9. Save deliverables under `data/results/<content-id>/` when working in the project.
10. Do not auto-publish without explicit approval. The CLI enforces a dry run unless `--approve` is present.

## Authentication

Prefer a dedicated browser profile for research accounts. Ask the user to complete login and MFA manually in the visible browser. Reuse the resulting local session without reading or printing credentials.

For X and Facebook:

- Prefer OpenTabs when a supported plugin can use the site's authenticated API.
- Otherwise use BrowserClaw/BrowserOS in a dedicated profile.
- Use agent-browser with a persistent isolated profile only as fallback.
- Keep human approval for posting, messaging, account changes, and downloads with unclear rights.

## Publish

1. Confirm the exact package, destination account, and user approval.
2. Negotiate capabilities using [publishing-routing.md](references/publishing-routing.md).
3. Use only an end-to-end capable route. Do not infer access from installed repositories, executables, or an unrelated logged-in browser.
4. Verify the destination account before upload.
5. For multiple posts, publish sequentially and check the archive before each post.
6. Report success only with a visible success state and post ID or public URL.
7. If no safe route exists, return the manual package and state that publishing did not occur.

## Output contract

Follow [content-contract.md](references/content-contract.md). Keep discovery responses concise. A production response must include all files and decisions needed for the user to upload manually.

