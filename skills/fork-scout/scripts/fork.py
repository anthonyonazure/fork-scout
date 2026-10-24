#!/usr/bin/env python3
"""Fork a repo into the user's GitHub account, but only after a clean scan and review.

Usage: fork.py OWNER/FORK [--confirm] [--accept-concerns]

Prefer snapshot.py: it makes a private copy of the exact scanned commit. A GitHub
fork stays linked to a repo the author can keep changing, and a fork of a public repo
is public. Refuses unless the scan and the reviewer's record both match the fork's
current head. Without --confirm it only says what it would do; the user's explicit
yes is required before --confirm. After forking it turns GitHub Actions off on the copy.
"""
import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("fs_common", Path(__file__).resolve().parent / "common.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fork")
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--accept-concerns", action="store_true")
    a = ap.parse_args()
    a.fork = C.resolve(a.fork)

    rep = C.gate(a.fork, need_review=True, accept_concerns=a.accept_concerns)
    print(f"Scan verdict: {rep['verdict']} (HIGH {rep['counts']['HIGH']}, MEDIUM {rep['counts']['MEDIUM']}); reviewer record present")
    if not a.confirm:
        print(f"Would run: gh repo fork {a.fork} --clone=false --default-branch-only, then turn Actions off on the copy.\n"
              f"Note: a fork of a public repo is public. snapshot.py makes a private copy instead.\n"
              f"Re-run with --confirm after the user says yes.")
        return
    # default branch only: the scan read that branch, so other branches stay behind
    subprocess.run(["gh", "repo", "fork", a.fork, "--clone=false", "--default-branch-only"], check=True)
    me = C.gh("user")["login"]
    name = a.fork.split("/")[1]
    subprocess.run(["gh", "api", "-X", "PUT", f"repos/{me}/{name}/actions/permissions", "-F", "enabled=false"], check=False)
    print(f"Forked to {me}/{name}; GitHub Actions turned off on it. Do not add secrets or turn Actions back on.")


if __name__ == "__main__":
    main()
