# Tool routing

## Decision table

| Situation | Preferred tool | Fallback | Reason |
|---|---|---|---|
| Official RSS, changelog, paper, GitHub release | Direct fetch/search | agent-browser `read` | Stable primary source |
| Public static article | Direct readable extraction | agent-browser `read` | Low overhead |
| JavaScript-heavy public page | agent-browser | BrowserOS | Deterministic CLI |
| Logged-in X/Facebook/Reddit tab | OpenTabs plugin/API | BrowserClaw | Reuse authenticated session |
| Login, MFA, CAPTCHA, consent | Visible BrowserOS/BrowserClaw | headed agent-browser | Human can intervene |
| Screenshot or repeatable UI flow | agent-browser | BrowserOS CLI | Stable refs and sessions |
| Internal web-app API discovery | OpenTabs | BrowserOS network tools | API is more stable than DOM |
| Scheduled research later | BrowserOS scheduled task | orchestrator worker | Local persistent session |

## Vendored components

### BrowserOS and BrowserClaw

Path: `vendor/BrowserOS`

Use for authenticated, visible, local browser sessions. Connect through MCP or the `browseros-cli`/`bos` CLI. Keep this component process-separated because it is AGPL-3.0.

Typical setup:

```powershell
browseros-cli launch
browseros-cli init http://127.0.0.1:9000/mcp
browseros-cli health
browseros-cli open --json https://x.com
```

### agent-browser

Path: `vendor/agent-browser`

Use for CLI automation, snapshots, screenshots, deterministic interaction, and isolated profiles.

```powershell
agent-browser install
agent-browser --profile ".\data\browser-profiles\research" open https://x.com --headed
agent-browser snapshot
agent-browser screenshot .\data\assets\x.png
```

Never commit profile directories or saved state. State files may contain session tokens.

### OpenTabs

Path: `vendor/opentabs`

Use the API of an already logged-in browser tab. Prefer plugins over DOM scraping.

```powershell
npm install -g @opentabs-dev/cli
opentabs start
opentabs plugin install <plugin-name>
```

Load the extension from the location printed by OpenTabs. Review plugin source and permissions before enabling it.

### Marketing Skills

Path: `vendor/marketingskills`

Read only the skill relevant to the current production step. Do not copy the full pack into context.

## Authenticated platform policy

1. Create a dedicated research profile.
2. Let the user enter credentials and MFA in a visible window.
3. Reuse local browser state without exposing it to the model or project files.
4. Prefer read-only permissions.
5. Require approval for write actions.
6. Respect robots directives, platform terms, rate limits, copyrights, and privacy.
7. Do not circumvent anti-bot challenges.

