# Publishing capability routing

Read this reference before promising or attempting to publish.

## Capability negotiation

1. Run `.\cm.ps1 publish-capabilities --platform <platform>`.
2. Inspect the current agent runtime for callable browser, connector, or API tools.
3. Select the first route that is both available and end-to-end capable:
   - verified native platform API;
   - callable browser surface connected to the user's authenticated session;
   - dedicated BrowserOS, OpenTabs, or agent-browser profile with a user-completed login;
   - manual upload package.
4. Do not treat installed source code, a browser executable, an open tab, or the user's statement that they are logged in as proof that the current agent can control that session.
5. Never extract cookies, tokens, passwords, or browser storage to bridge runtimes.

## Route requirements

### Native API

- Require configured credentials, required scopes, media upload support, and an end-to-end tested adapter.
- TikTok content initialization alone is not a completed publisher; the media upload and publish-status steps must also succeed.
- Use `--approve` only after the user approves the exact content and destination.

### Browser runtime

- Require a callable browser tool for the exact browser selected by the user.
- Verify the visible account identity before uploading.
- Let the user complete login, MFA, CAPTCHA, and consent.
- Do not switch to a different browser after the user explicitly selects one unless the user approves the switch.

### Browser CLI

- Use only a dedicated profile created for this product.
- An installed CLI does not inherit the user's normal Chrome session.
- Keep session files outside version control and never print their contents.

### Manual package

- Use when no safe automated route is available.
- Return the self-contained result folder and exact caption.
- State clearly that nothing was published.

## Publication proof

Do not report success until the platform returns or visibly shows:

- the intended account;
- a post ID or public URL;
- a successful or processing status;
- the expected media and caption.

After success, record the post ID, URL, timestamp, package ID, and platform in the archive. For multiple posts, publish sequentially and check the archive before each attempt.
