# Contributing

Thanks for helping. The project is small on purpose: browse forks, explain them, vet the ones you pick, copy them. Changes that keep it that way are the easiest to merge.

## Ground rules

- **Never run anything from a fork.** No `exec`, no `import`, no installing, no building. fork-scout only reads other people's code.
- **Anything that creates or sends something stays behind a preview and `--confirm`.** New write actions must go through the gate in `common.py` (`gate()`).
- **Standard library only.** No third-party Python packages.
- **Prose in plain English.** The skill's output is read by people who may not read code.

## Setup

You need Python 3.10 or newer. Run the tests:

```sh
python3 -m unittest discover -s tests -v
```

The tests do not call GitHub. Keep it that way: mock `gh` calls.

## Adding a scan rule

Rules live in the `RULES` list in `skills/fork-scout/scripts/common.py`. Each is a severity, a label, a regular expression and a plain-English reason. Add a test in `tests/test_rules.py` with one line the rule should catch and one it should leave alone.

## Pull requests

Describe what changed and why in a few sentences, and say how you tested it. CI runs the unit tests.
