#!/usr/bin/env python3
"""Make a private, fresh-history copy of the exact commit that was scanned and reviewed.

Usage: snapshot.py OWNER/FORK [--name NEW_NAME] [--keep-workflows] [--ignore-license]
                   [--accept-concerns] [--confirm]

Safer than a GitHub fork: it is private, it is not linked to a repo the author can keep
changing, it carries one commit and no history, and CI workflow files are stripped so
GitHub Actions has nothing to run. Files come from `git archive` of the scanned clone,
never the clone's .git folder. Refuses unless the scan and the reviewer's record match
the fork's current head, and the clone still sits on that commit. Without --confirm it
only prints the plan. The user's explicit yes is required before --confirm.
"""
import argparse
import importlib.util
import shutil
import subprocess
import sys
import tarfile
from datetime import date
from pathlib import Path

_spec = importlib.util.spec_from_file_location("fs_common", Path(__file__).resolve().parent / "common.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)


def git(*args, cwd=None):
    return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=cwd, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fork")
    ap.add_argument("--name")
    ap.add_argument("--keep-workflows", action="store_true")
    ap.add_argument("--ignore-license", action="store_true")
    ap.add_argument("--accept-concerns", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    a = ap.parse_args()
    a.fork = C.resolve(a.fork)

    rep = C.gate(a.fork, need_review=True, accept_concerns=a.accept_concerns)
    clone = Path(rep["clone"])
    head = git("-C", str(clone), "rev-parse", "HEAD").stdout.strip()
    if head != rep["head_sha"]:
        sys.exit("the scanned clone no longer matches the scanned commit: rescan")

    info = C.gh(f"repos/{a.fork}")
    lic = (info.get("license") or {}).get("spdx_id")
    if lic in (None, "NOASSERTION") and not a.ignore_license:
        sys.exit("the fork shows no licence, which means you have no right to copy it. Check the repo, or pass --ignore-license if you hold permission")

    me = C.gh("user")["login"]
    name = a.name or f"{a.fork.split('/')[1]}-{a.fork.split('/')[0]}-{head[:7]}"
    if C.gh(f"repos/{me}/{name}", die=False):
        sys.exit(f"{me}/{name} already exists: pick another --name")
    work = C.STATE / "snapshots" / name
    if work.exists():
        sys.exit(f"{work} already exists: pick another --name")

    print(f"Scan verdict: {rep['verdict']} (HIGH {rep['counts']['HIGH']}, MEDIUM {rep['counts']['MEDIUM']}); reviewer record present")
    print(f"Plan: private repo {me}/{name} holding one commit of {a.fork} @ {head[:10]}, licence {lic}.\n"
          f"      CI workflows {'kept' if a.keep_workflows else 'removed'}; GitHub Actions turned off; no history carried over.")
    if not a.confirm:
        print("Re-run with --confirm after the user says yes.")
        return

    work.mkdir(parents=True)
    p = subprocess.Popen(["git", "-C", str(clone), "archive", "--format=tar", "HEAD"], stdout=subprocess.PIPE)
    with tarfile.open(fileobj=p.stdout, mode="r|") as tf:
        tf.extractall(work, filter="data")  # refuses links and paths that escape the folder
    if p.wait():
        shutil.rmtree(work)
        sys.exit("git archive failed")
    if not a.keep_workflows:
        shutil.rmtree(work / ".github" / "workflows", ignore_errors=True)
    (work / "PROVENANCE.md").write_text(
        f"# Provenance\n\nSnapshot of {a.fork} at commit {head}\nUpstream: {rep['upstream']}\nLicence: {lic}\n"
        f"Taken: {date.today()} by fork-scout. Scan verdict: {rep['verdict']}. Reviewed by a read-only agent before copying.\n"
        f"CI workflows {'kept' if a.keep_workflows else 'removed'}. History intentionally not carried over.\n")
    for step in (["init", "-b", "main"], ["add", "-A"],
                 ["-c", "user.name=fork-scout", "-c", "user.email=fork-scout@users.noreply.github.com",
                  "commit", "-m", f"Snapshot of {a.fork} at {head[:10]}"]):
        r = git(*step, cwd=work)
        if r.returncode:
            sys.exit(f"git {step[0]} failed: {r.stderr[:200]}")
    subprocess.run(["gh", "repo", "create", f"{me}/{name}", "--private", "--source", str(work), "--push",
                    "--description", f"Private snapshot of {a.fork}"], check=True)
    subprocess.run(["gh", "api", "-X", "PUT", f"repos/{me}/{name}/actions/permissions", "-F", "enabled=false"], check=False)
    print(f"Created private repo {me}/{name}. GitHub Actions is off. Install by this commit only: {head}.")


if __name__ == "__main__":
    main()
