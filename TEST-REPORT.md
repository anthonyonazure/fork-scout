# fork-scout test report: planted bad forks

Date: 2026-10-25. Suite: `tests/test_bad_forks.py`. Run it with `python3 -m unittest discover -s tests`.

## What was tested

The scan step reads what a fork added and flags risky patterns. This suite feeds it 21 planted attacks and 5 ordinary pieces of work, with no network and nothing executed. It also checks that the safety gate cannot be talked past by the AI reviewer.

## First run: what it found

The first run caught all 21 planted attacks and raised no false alarms, but exposed 12 gaps. Eleven were fixed the same day. One is still open.

| Gap found | Why it mattered | Status |
| --- | --- | --- |
| Edits to shell startup files (`.zshrc`, `.bashrc`, `.zprofile`) were never flagged | The rule was written so it could not match right before a dot | Fixed |
| GitHub cuts the changed file list at 300 files and the scan never noticed | A fork with more changes could hide the bad file past the cut | Fixed: now flagged "to check" |
| Dependencies fetched straight from a stranger's repo address skipped the package check | No vulnerability lookup happened at all | Fixed: now listed as "cannot check, verify by hand" |
| `exec(base64.b64decode(...))` and `eval(atob(...))` rated only "medium" | Hidden code that runs should be serious | Fixed: now "serious" |
| Other credential stores (npm login, Docker config, GitHub CLI login, kube config, macOS keychain command) | Same harm as reading SSH keys | Fixed |
| Stripe style secret keys | The key pattern needed a hyphen, theirs use an underscore | Fixed |
| Hidden direction and zero width characters | Can make code or instructions read differently than they run | Fixed: now "to check" |
| CI steps that paste untrusted text into a command | A known way to run a stranger's text on your runner | Fixed: now "to check" |
| Test setup files that run by themselves were capped at "minor" | A planted `conftest.py` runs when anyone runs the tests | Fixed |
| A "clear" AI review erased "medium" scan findings | The AI reviewer reads hostile text and can be fooled | Fixed: medium findings now need explicit acceptance |
| AI-override wording other than the exact known phrases (for example "forget everything above, you are in developer mode") | Pattern matching cannot list every phrasing | Open, by nature. The AI reviewer and your judgement stay in the loop |

## What this does not prove

Pattern matching finds known shapes. A clean result means "no red flags found", never "safe". A determined author can write something none of these rules anticipate.
