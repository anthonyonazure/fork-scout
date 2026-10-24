#!/usr/bin/env python3
"""Offer a fork's good change back to the original project as a DRAFT pull request.

Usage: pr.py OWNER/FORK --commits SHA[,SHA...] --title "..." [--confirm] [--accept-concerns]

This writes to a stranger's repository in the user's name, the most outward-facing thing
in fork-scout. Without --confirm it only drafts the description and prints the plan.
With --confirm (after the user's explicit yes) it forks the upstream under the user's
account if needed, cherry-picks the commits (keeping the original author), pushes a
branch, and opens a DRAFT pull request. Needs a scan and a reviewer record matching the
fork's head. The live path has not been exercised against a real repository.
"""
import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("fs_common", Path(__file__).resolve().parent.parent / "common.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)


def run(*cmd, cwd=None):
    r = subprocess.run(list(cmd), cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"{' '.join(cmd[:3])} failed: {r.stderr.strip()[:300]}")
    return r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fork")
    ap.add_argument("--commits", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--accept-concerns", action="store_true")
    a = ap.parse_args()

    rep = C.gate(a.fork, need_review=True, accept_concerns=a.accept_concerns)
    up = rep["upstream"]
    shas = [s.strip() for s in a.commits.split(",") if s.strip()]
    titles = [C.gh(f"repos/{a.fork}/commits/{s}")["commit"]["message"].splitlines()[0] for s in shas]
    body = (f"Draft contribution, originally written in {a.fork}.\n\nCommits (original authorship kept):\n"
            + "\n".join(f"- {s[:7]} {t}" for s, t in zip(shas, titles))
            + "\n\nOpened as a draft for the maintainers to review. Not tested by the submitter beyond the source fork's own tests.\n")
    draft = C.STATE / "prs" / f"{C.slug(a.fork)}.md"
    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text(f"# {a.title}\n\n{body}")
    print(f"Draft saved: {draft}\n\n# {a.title}\n{body}")
    me = C.gh("user")["login"]
    branch = f"fork-scout/{C.slug(a.fork)}-{shas[0][:7]}"
    print(f"Plan: ensure {me} has a fork of {up}; cherry-pick {len(shas)} commit(s) onto branch {branch}; push; open a DRAFT PR to {up}.")
    if not a.confirm:
        print("Nothing was sent. Re-run with --confirm after the user says yes.")
        return

    name = up.split("/")[1]
    if not C.gh(f"repos/{me}/{name}", die=False):
        run("gh", "repo", "fork", up, "--clone=false", "--default-branch-only")
    work = C.STATE / "prs" / "work" / f"{C.slug(a.fork)}-{shas[0][:7]}"
    if work.exists():
        sys.exit(f"{work} exists: remove it or choose different commits")
    work.parent.mkdir(parents=True, exist_ok=True)
    g = ["git", "-c", "core.hooksPath=/dev/null"]
    run(*g, "clone", "--depth", "100", f"https://github.com/{me}/{name}.git", str(work))
    run(*g, "remote", "add", "src", f"https://github.com/{a.fork}.git", cwd=work)
    run(*g, "fetch", "--depth", "100", "src", cwd=work)
    run(*g, "checkout", "-b", branch, cwd=work)
    run(*g, "cherry-pick", *shas, cwd=work)
    run(*g, "push", "origin", branch, cwd=work)
    out = run("gh", "pr", "create", "--repo", up, "--head", f"{me}:{branch}", "--title", a.title, "--body", body, "--draft")
    print(f"Draft pull request opened: {out.strip()}")


if __name__ == "__main__":
    main()
