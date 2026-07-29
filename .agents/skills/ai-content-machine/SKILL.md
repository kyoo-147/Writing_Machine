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

Run the CLI helper when useful:

```powershell
.\cm.ps1 doctor
.\cm.ps1 new -Query "AI news today" -Count 3 -Format auto -Tone skeptical
.\cm.ps1 prompt
.\cm.ps1 auth -Platform x
```

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
6. Stop for selection unless the user asked for autonomous production.

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
7. Obtain user approval before expensive asset generation or video downloading.

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
5. Run an editorial pass:
   - remove generic AI phrases and fake enthusiasm
   - vary sentence length
   - distinguish facts, inference, and opinion
   - preserve uncertainty
   - ensure the piece adds a new angle
6. Save deliverables under `data/results/<content-id>/` when working in the project.

## Authentication

Prefer a dedicated browser profile for research accounts. Ask the user to complete login and MFA manually in the visible browser. Reuse the resulting local session without reading or printing credentials.

For X and Facebook:

- Prefer OpenTabs when a supported plugin can use the site's authenticated API.
- Otherwise use BrowserClaw/BrowserOS in a dedicated profile.
- Use agent-browser with a persistent isolated profile only as fallback.
- Keep human approval for posting, messaging, account changes, and downloads with unclear rights.

## Output contract

Follow [content-contract.md](references/content-contract.md). Keep discovery responses concise. A production response must include all files and decisions needed for the user to upload manually.

