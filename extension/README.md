# fork-scout browser extension (version 0.2.0)

Adds a **Forks worth copying** button to GitHub repo pages, and a full results page with optional AI review and one-click forking. Forks are ranked the same way the skill ranks them (recent, close to the original, real code, not stars), each with a pattern safety scan of what the fork changed.

## Try it

1. Open `chrome://extensions` (or `brave://extensions`) and turn on **Developer mode**.
2. Choose **Load unpacked** and pick this `extension` folder.
3. Open any repo on github.com. Click the button at the bottom right for a short list, or the toolbar icon for the full results page.

## Three tiers, each optional

| Tier | Needs | You get |
| --- | --- | --- |
| Nothing set up | Nothing | Ranked fork list, latest commit titles, the pattern scan. GitHub allows about 60 anonymous requests an hour, so it looks at up to 12 forks per load |
| AI review | Your own Anthropic API key (Settings) | Plain-English summary, "why it might be better", "catch", and a second-opinion verdict (clear, concerns, unsafe) per fork. **Sends the fork's changed code to Anthropic; your key is billed** |
| Forking | A GitHub token that can create forks (Settings) | A "Fork a copy" button that creates a public fork of the fork's default branch in your account, after a confirmation screen each time |

A separate read-only GitHub token (Settings) raises the request limit.

## Safety design

- **The scan is never optional.** It always runs. A serious scan finding blocks forking whatever the AI says. Medium findings, and AI "concerns", need you to tick an acceptance box. The AI can only make the outcome stricter.
- **AI off is labelled.** Results without an AI review say "pattern scan only". The confirmation screen says "No AI review was run".
- **The AI is treated as untrusted.** It gets the fork's text inside tags with instructions to treat it as data, has no tools, and its answer is parsed defensively. It cannot say "clear" about code it was not fully shown.
- **Fork re-checks everything.** At fork time the background worker re-reads the fork from GitHub, re-scans it, and refuses if it changed since you looked (or since the AI review).
- **Least reach.** The extension only makes read requests of a short, tested shape to GitHub (`extension/policy.js`) plus one write: forking. Write, AI and key-holding actions are accepted only from the extension's own pages, never from a GitHub page. Keys never leave the background worker.
- **Plain text only.** Names, commit titles, file names and AI text are inserted as text, never as HTML.
- A clean result means "no red flags found", never "safe". Nothing from a fork is ever run, and forking installs nothing.

## Not in the extension

Building one copy that combines features from several forks, the private one-commit snapshot, and the independent Claude Code reviewer stay in the skill. Forking here creates a **public** GitHub fork.

## Notes for reviewers

- The AI call is one `fetch` to the Messages API from `background.js`, deliberately without the Anthropic SDK: no build step and no third-party code to audit in a security tool. The `anthropic-dangerous-direct-browser-access` header is required by the API for any browser origin.
- Default model is Claude Opus 5.5; Sonnet 5.5 and Haiku 5.5 are selectable in Settings. Where the model supports it, server-side fallback is requested so a safety-filter decline retries on a recommended model.
- `api.anthropic.com` is a required host permission (so it appears in the install prompt), but nothing is sent there unless an AI key is set.

## Keeping the rules in sync

`rules.json` here is a copy of `skills/fork-scout/rules.json`. After changing the skill's rules run `cp skills/fork-scout/rules.json extension/rules.json`. The test suite fails if the two differ.

## Tests

`node --test extension/test/` holds the JavaScript scanner to the same attack cases (`tests/cases.json`) as the Python one, and tests the copy gate, the AI input and output handling, and the request allowlist.
