# fork-scout browser extension (early version 0.1.0)

Adds a **Forks worth copying** button to GitHub repo pages. Click it to see the repo's recent forks ranked the same way the skill ranks them (recent, close to the original, real code, not stars), each with a pattern safety scan of what the fork changed.

## Try it

1. Open `chrome://extensions` (or `brave://extensions`) and turn on **Developer mode**.
2. Choose **Load unpacked** and pick this `extension` folder.
3. Open any repo on github.com and click the button at the bottom right.

## What works with nothing set up

- Ranked fork list and the latest commit titles of each fork.
- The same scan rules as the skill, read from the same rules file. A serious finding is shown as "Serious flags".
- No account, no key. GitHub allows about 60 anonymous requests an hour, so the extension looks at up to 12 forks per click.

## Optional settings

- **GitHub token** (read-only public access only): raises the request limit. Stored in this browser, sent only to api.github.com.
- **AI review**: not in this version. Results are labelled "pattern scan only, no AI review" so an AI-off result is never mistaken for a reviewed one.

## Safety design

- The extension never runs code from a fork and never writes to GitHub. Its background worker only allows read-only requests to a short list of GitHub address shapes.
- Text from forks (names, commit titles, file names) is inserted as plain text, never as HTML.
- A clean result means "no red flags found", never "safe".

## Keeping the rules in sync

`rules.json` here is a copy of `skills/fork-scout/rules.json`. After changing the skill's rules run `cp skills/fork-scout/rules.json extension/rules.json`. The test suite fails if the two differ.

## Tests

`node --test extension/test/` holds the JavaScript scanner to the same attack cases (`tests/cases.json`) as the Python one.
