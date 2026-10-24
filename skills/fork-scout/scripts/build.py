#!/usr/bin/env python3
"""Fork the ORIGINAL repo and add the chosen forks' features on a separate branch.

Usage: build.py FORK_OR_NUMBER [FORK_OR_NUMBER ...] [--confirm] [--accept-concerns]

Each pick's own commits are copied (keeping the original author) onto a fresh copy of
the original's main branch, one whole fork at a time. If a fork's changes clash with
the original or with an earlier pick, that fork is skipped entirely and the clash is
reported, so nothing is half-applied. The merge happens on this machine first, so the
preview already shows what would work. Only --confirm touches GitHub: it forks the
original under the user's account if needed (default branch only, GitHub Actions turned
off), then pushes the new branch there. The main branch of that fork is never changed.
Every pick needs a scan and a reviewer record matching its current head. The user's
explicit yes is required before --confirm.
"""
import argparse
import importlib.util
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_spec = importlib.util.spec_from_file_location("fs_common", Path(__file__).resolve().parent / "common.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)

IDENT = ["-c", "user.name=fork-scout", "-c", "user.email=fork-scout@users.noreply.github.com"]


def git(cwd, *args, check=True):
    r = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *IDENT, *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"git {args[0]} failed: {(r.stderr or r.stdout).strip()[:300]}")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("picks", nargs="+")
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--accept-concerns", action="store_true")
    a = ap.parse_args()
    forks = [C.resolve(p) for p in a.picks]
    ups = {C.upstream_of(f) for f in forks}
    if len(ups) != 1:
        sys.exit("the picks come from different original repos")
    up = ups.pop()
    for f in forks:
        C.gate(f, need_review=True, accept_concerns=a.accept_concerns)

    upinfo = C.gh(f"repos/{up}")
    base = upinfo["default_branch"]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    work = C.STATE / "builds" / f"{C.slug(up)}-{stamp}"
    work.parent.mkdir(parents=True, exist_ok=True)
    git(None, "clone", "--depth", "1", "--no-tags", "--branch", base, upinfo["clone_url"], str(work))
    branch = "features-" + "-".join(f.split("/")[0] for f in forks)[:40] + "-" + stamp[:8]
    git(work, "checkout", "-b", branch)

    applied, skipped = [], []
    for f in forks:
        info = C.gh(f"repos/{f}")
        cmp = C.gh(f"repos/{up}/compare/{base}...{info['owner']['login']}:{info['default_branch']}")
        commits = [c for c in cmp["commits"] if len(c["parents"]) == 1]  # merges cannot be copied; their content arrives via the commits
        if cmp["ahead_by"] > 250:
            skipped.append((f, "more than 250 commits ahead: too many to copy safely"))
            continue
        git(work, "remote", "add", info["owner"]["login"], info["clone_url"])
        r = git(work, "fetch", "--no-tags", "--depth", str(min(1000, cmp["ahead_by"] * 2 + 50)), info["owner"]["login"], info["default_branch"], check=False)
        if r.returncode:
            skipped.append((f, f"could not fetch: {r.stderr.strip()[:120]}"))
            continue
        before = git(work, "rev-parse", "HEAD").stdout.strip()
        failed = None
        for c in commits:
            r = git(work, "cherry-pick", "-x", "--empty=drop", c["sha"], check=False)
            if r.returncode:
                clash = git(work, "diff", "--name-only", "--diff-filter=U", check=False).stdout.split()
                git(work, "cherry-pick", "--abort", check=False)
                failed = (c["sha"][:7], c["commit"]["message"].splitlines()[0][:70], clash)
                break
        if failed:
            git(work, "reset", "--hard", before)
            skipped.append((f, f"clashes at {failed[0]} \"{failed[1]}\" in {', '.join(failed[2][:4]) or 'unknown files'}"))
        else:
            applied.append((f, len(commits)))

    print(f"# Build on {up}@{base}  (branch {branch})")
    for f, n in applied:
        print(f"- ADDED   {f}: {n} commits applied cleanly")
    for f, why in skipped:
        print(f"- SKIPPED {f}: {why}")
    stat = git(work, "diff", "--shortstat", f"origin/{base}..HEAD", check=False).stdout.strip()
    print(f"Result vs the original: {stat or 'no changes'}")
    print(f"Local copy (not on GitHub): {work}")
    if not applied:
        sys.exit("nothing could be applied")
    if not a.confirm:
        print("Nothing was created or pushed. Re-run with --confirm after the user says yes: it forks "
              f"{up} into the user's account if needed (public, since the original is public) and pushes the branch there.")
        return

    me = C.gh("user")["login"]
    name = up.split("/")[1]
    existing = C.gh(f"repos/{me}/{name}", die=False)
    if existing and existing.get("parent", {}).get("full_name") != up:
        sys.exit(f"{me}/{name} exists and is not a fork of {up}: refusing")
    if not existing:
        subprocess.run(["gh", "repo", "fork", up, "--clone=false", "--default-branch-only"], check=True)
    subprocess.run(["gh", "api", "-X", "PUT", f"repos/{me}/{name}/actions/permissions", "-F", "enabled=false"], check=False)
    git(work, "remote", "add", "mine", f"https://github.com/{me}/{name}.git")
    git(work, "push", "mine", branch)
    print(f"Pushed. See https://github.com/{me}/{name}/tree/{branch}  (main branch untouched, GitHub Actions off)")


if __name__ == "__main__":
    main()
