# Changelog

## Unreleased

- Added: bad-fork regression suite (`tests/test_bad_forks.py`) and `TEST-REPORT.md`.
- Fixed: shell startup file edits are now flagged (the rule could not match before a dot).
- Fixed: a fork whose changed file list hit GitHub's 300 file cap is now flagged instead of silently half scanned.
- Fixed: `exec`/`eval` of decoded text is now serious; more credential stores, Stripe style keys, hidden characters and CI text injection are flagged; dependencies fetched from a raw address are listed as unchecked; auto-loaded test setup files are no longer capped at minor.
- Changed: medium scan findings now need `--accept-concerns` even when the reviewer says clear.

- Fixed: `snapshot.py` now copies every tracked file. It used `git archive`, which silently drops files a project marks export-ignore (often its tests). It also refuses links that point outside the project.

## 0.1.0

First public release.

- Browse the forks of a repo as a numbered, readable list. Search by repo, URL, topic, project name or `@person`, and filter forks by feature with `--find`.
- Forks ranked by recent activity, closeness to the original and real change, not by stars. Docs-only forks sink.
- Background security check on the forks you pick: pattern scan of what the fork added, workflow files, new packages checked against OSV, secret scan, author context.
- Independent reviewer brief and a recorded verdict, tied to the exact commit.
- A gate that stops copying unless the scan and review match the fork's current commit.
- Copy by adopting a fork (private snapshot, or GitHub fork) or by building on the original with chosen forks' features.
- Extras: compare forks, single-commit patches, watch for changes, draft pull request.
