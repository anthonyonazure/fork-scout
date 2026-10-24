#!/usr/bin/env python3
"""Background security check for the forks the user chose. Reports a short summary.

Usage: check.py FORK_OR_NUMBER [FORK_OR_NUMBER ...]

Runs scan.py on each pick at the same time, then prints one short block per fork and
writes the reviewer brief for each. The assistant then hands each brief to a read-only
reviewer agent (in the background) and records its verdict with review.py. Nothing from
a fork is ever run. Run this only once someone is about to read code or copy a fork.
"""
import argparse
import importlib.util
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("fs_common", HERE / "common.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)


def run(script, *args):
    r = subprocess.run([sys.executable, "-I", str(HERE / script), *args], capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("picks", nargs="+")
    a = ap.parse_args()
    forks = [C.resolve(p) for p in a.picks]

    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(lambda f: (f, run("scan.py", f)), forks))
    for fork, (code, out) in results:
        if code:
            print(f"## {fork}: scan failed: {out[-200:]}\n")
            continue
        rep = json.loads(C.report_path(fork).read_text())
        t = rep["trust"]
        run("review.py", fork)  # writes the reviewer brief
        print(f"## {fork}: {rep['verdict']}")
        print(f"- Flags: {rep['counts']['HIGH']} serious, {rep['counts']['MEDIUM']} to check, {rep['counts']['LOW']} minor (tests count as minor)")
        print(f"- Author: account {t['account_age_days']} days old, {t['public_repos']} repos, {t['followers']} followers, "
              f"signed commits {t['verified_commits']}")
        if rep["new_domains"]:
            print("- New web addresses: " + ", ".join(rep["new_domains"]))
        if rep["dependencies"]:
            print("- New packages: " + ", ".join(d["package"] for d in rep["dependencies"][:8]))
        top = [x for x in rep["findings"] if x[0] in ("HIGH", "MEDIUM")][:5]
        for sev, label, name, i, why in top:
            print(f"- {sev}: {label} in {name}:{i}")
        print(f"- Reviewer brief: {C.STATE / 'briefs' / (C.slug(fork) + '.md')}\n")
    print("NEXT: give each brief to a read-only reviewer agent, then record with review.py FORK --record clear|concerns|unsafe --notes \"...\"")


if __name__ == "__main__":
    main()
