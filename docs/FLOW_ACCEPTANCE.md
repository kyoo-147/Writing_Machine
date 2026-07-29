# Manual TikTok Content Flow Acceptance

## Target flow

1. The user asks for a number of current AI content ideas in chat.
2. The agent asks only for missing decisions that materially affect the result.
3. Discovery collects and ranks current primary sources, research, repositories, demos, and community signals.
4. The user selects a topic.
5. Development creates a claim ledger, citations, angles, limitations, and a production brief.
6. Production requires at least one attributed source image or video.
7. The agent applies the selected language and voice profile.
8. The result is a self-contained package for manual TikTok upload.
9. Publishing remains disabled unless the user explicitly approves it.

## Acceptance status

| Requirement | Status | Evidence |
|---|---|---|
| Chat-first orchestration through the installed skill | Pass | The skill defines defaults, phase routing, selection stops, and approval gates |
| Current-topic discovery | Pass | Live GitHub, arXiv, and RSS discovery returned three ranked records during the final audit |
| Persistence, deduplication, and archive filtering | Pass | SQLite/PostgreSQL pipeline and automated tests |
| Topic development and claim ledger | Pass with limitation | Claim extraction, contradiction checks, citation reachability, and three angles work; deep semantic verification still benefits from an active agent or configured LLM |
| Mandatory source image/video | Pass | Production rejects SVG-only and ImageGen-only inputs |
| Source media packaged for upload | Pass | Source files are copied into each result package with provenance |
| No SVG or generated placeholders | Pass | SVG is excluded; legacy cover and preview placeholders are removed during production |
| Optional original illustration | Pass through agent | The skill requires ImageGen and PNG/JPG; the project contains no direct image-generation command |
| Configurable voice profiles | Pass through agent or LLM | Research, skeptical-builder, and playful-contrarian profiles are configured |
| Human-sounding Vietnamese output | Conditional | Works through the active Codex agent or a configured LLM provider; the deterministic CLI fallback remains English |
| Friendly Vietnamese natural-language CLI | Partial | `cm chat` is a basic command shell, not a full multilingual conversational model |
| Self-contained manual-upload package | Pass | Brief, hooks, script, caption, sources, fact check, asset manifest, checklist, package JSON, and assets are generated |
| Automatic publishing | Out of current scope | Adapters exist but are approval-gated; manual upload remains the default |

## Final audit use cases

The final acceptance run used three persisted stories:

- Google Blog model announcement with its official hero image.
- An X community demo with its downloaded source video and thumbnail.
- A GitHub announcement with its official source image.

All three produced a complete package with at least one source asset, source attribution, no missing required files, and no legacy placeholder media.

## Operational boundary

The intended user experience is the Codex skill conversation. The CLI provides deterministic persistence and phase execution underneath it. It is not intended to replace the language understanding of the active agent.
