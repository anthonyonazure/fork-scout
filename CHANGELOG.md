# Changelog

## 0.1.0

First public release.

- Browse the forks of a repo as a numbered, readable list. Search by repo, URL, topic, project name or `@person`, and filter forks by feature with `--find`.
- Forks ranked by recent activity, closeness to the original and real change, not by stars. Docs-only forks sink.
- Background security check on the forks you pick: pattern scan of what the fork added, workflow files, new packages checked against OSV, secret scan, author context.
- Independent reviewer brief and a recorded verdict, tied to the exact commit.
- A gate that stops copying unless the scan and review match the fork's current commit.
- Copy by adopting a fork (private snapshot, or GitHub fork) or by building on the original with chosen forks' features.
- Extras: compare forks, single-commit patches, watch for changes, draft pull request.
