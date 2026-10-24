<p align="center">
  <img src="assets/logo.png" alt="fork-scout logo" width="128">
</p>

<h1 align="center">fork-scout</h1>

<p align="center"><b>Find the forks worth copying.</b><br>
A <a href="https://claude.com/claude-code">Claude Code</a> skill that browses the forks of a GitHub repo, explains what each one adds in plain English, vets the ones you pick, and helps you copy them.</p>

<p align="center">
  <a href="https://github.com/anthonyonazure/fork-scout/actions/workflows/test.yml"><img alt="tests" src="https://github.com/anthonyonazure/fork-scout/actions/workflows/test.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="MIT licence" src="https://img.shields.io/badge/licence-MIT-2dd4bf"></a>
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-fbbf24">
</p>

---

## Why

A popular repo can have thousands of forks. Almost all are untouched copies, but a few add something real: a bug fix the author never merged, a feature, a security hardening. Finding those by hand means clicking through pages of near-identical repos.

fork-scout does the digging. It compares every candidate fork with the original, drops the copies and the abandoned ones, and shows you the rest with a readable explanation of each.

## What it does

1. **Browse.** Give it a repo, or just search for a topic, a project name or `@person`. You get a numbered list of the interesting forks with: what each adds, why it might be better, and the catch (how far behind the original it is, what it depends on).
2. **Choose.** Pick by number. "Adopt 2", "build with 2 and 4" or "look at the code of 3".
3. **Vet, quietly.** Once you pick something, the security checks run in the background and report back in a few lines. Browsing alone never runs them.
4. **Copy.** Two ways, both previewed before anything is created:
   - **Adopt a fork as it is.** A private one-commit snapshot of the reviewed version, or a normal GitHub fork of that fork.
   - **Build on the original.** Fork the original repo and add the chosen forks' features on a separate branch, keeping each author's name. A fork that clashes is skipped whole, and the clash is explained.

## Example

The names below are made up, to show the shape of the output.

```
# Forks of example/research-tool  (12,400 stars, 980 forks)
Looked at 347 of 980 (the most-starred and newest); 17 have changes of their own.

| # | Fork            | Stars | Last active    | Ahead | Behind | Latest change                      |
| 1 | alice/research  | 3     | active, 4d ago | 12    | 8      | Merge: harden handling of web text |
| 2 | bob/research    | 1     | active, 9d ago | 6     | 25     | fix(reddit): fallback after a 403  |
| 3 | carol/research  | 0     | abandoned      | 2     | 610    | docs: update README                |
```

Then, for each fork, a short card in plain English: what it adds, why it might matter, and the catch.

## Install

fork-scout is a Claude Code [skill](https://docs.claude.com/en/docs/claude-code/skills). Copy the folder into your skills directory:

```sh
git clone https://github.com/anthonyonazure/fork-scout.git
cp -R fork-scout/skills/fork-scout ~/.claude/skills/
```

**Requirements:** Python 3.10 or newer, `git`, and the [GitHub CLI](https://cli.github.com/) (`gh`) signed in with `gh auth login`. The optional [gitleaks](https://github.com/gitleaks/gitleaks) tool adds a secret scan when it is installed. The scripts use only the Python standard library.

## Use

In Claude Code, ask in plain words:

- "What are the interesting forks of github.com/owner/repo?"
- "Search for forks of research skills that touch Reddit."
- "Adopt fork 2." / "Build on the original with forks 2 and 4."

Or run the scripts yourself:

```sh
python3 -I ~/.claude/skills/fork-scout/scripts/scout.py owner/repo
python3 -I ~/.claude/skills/fork-scout/scripts/scout.py "research skill"          # search by topic
python3 -I ~/.claude/skills/fork-scout/scripts/scout.py owner/repo --find reddit  # forks touching a feature
python3 -I ~/.claude/skills/fork-scout/scripts/check.py 2 4                       # background security check
python3 -I ~/.claude/skills/fork-scout/scripts/build.py 2 4                       # preview a combined build
```

| Script | Purpose |
| --- | --- |
| `scout.py` | Search, browse and rank forks. Read-only. |
| `check.py` | Security scan of the forks you picked, plus a brief for a reviewer. |
| `snapshot.py` | Private one-commit copy of a vetted fork. |
| `fork.py` | GitHub fork of a vetted fork (default branch only). |
| `build.py` | Fork the original and add the chosen forks' features on a branch. |
| `extras/` | Side-by-side compare, single-commit patches, watch for changes, draft pull request. |

Picks can be numbers from your last list or `owner/repo` names. Every script that creates something previews first and only acts with `--confirm`.

## How the safety works

Forks are written by strangers, so nothing from a fork is ever run, installed or imported. fork-scout only reads it.

- **Scan.** A shallow clone with git hooks off, then pattern checks on exactly what the fork added: commands piped to a shell, hidden decode-and-run, credential reads, data sent out, startup-file edits, changes to AI assistant settings, install-time scripts, obfuscation, binaries, workflow files, instructions aimed at an AI, new web addresses and packages. New packages are checked against the [OSV](https://osv.dev) vulnerability database. Secrets are checked with built-in patterns and gitleaks. Test files count for less.
- **Author context.** Account age, repo count and signed commits are shown. They never change the verdict.
- **Independent review.** A read-only reviewer agent reads the changed code in its own context, so a malicious fork cannot talk to your main session. Its verdict is recorded against the exact commit.
- **A hard gate.** `snapshot.py`, `fork.py` and `build.py` refuse unless the scan and the review match the fork's current commit. If the fork changes, both must be redone.
- **Smallest blast radius.** Copies are made from the exact reviewed commit. Forks take the default branch only, GitHub Actions is switched off on new copies, and a snapshot is private and strips workflow files.

**What it cannot do.** Pattern matching and one reviewer cannot prove code is safe. "No red flags found" is not "secure". Read the diff of anything you plan to depend on. Forking is also not installing: copying a skill into your own skills folder runs its instructions in every session, which deserves its own decision.

Forking a public repo creates a public repo under your account. fork-scout says so and asks first.

## Repository layout

```
skills/fork-scout/       the skill (SKILL.md and scripts)
tests/                   unit tests for the scan rules, the gate and the helpers
assets/                  logo and social preview
```

## Development

```sh
python3 -m unittest discover -s tests -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md). Security issues: see [SECURITY.md](SECURITY.md).

## Licence

[MIT](LICENSE)
