#!/usr/bin/env python3
"""Take just a few commits from a fork as patch files, instead of adopting the whole fork.

Usage:
  cherry.py OWNER/FORK --commits SHA[,SHA...]                    write patches, scan them, apply nothing
  cherry.py OWNER/FORK --commits SHA[,SHA...] --into DIR         also dry-run them against a local repo
  cherry.py OWNER/FORK --commits ... --into DIR --apply --confirm [--accept-concerns]

The smallest attack surface: you read the patch, it touches only what it touches, and
there is nothing to keep in sync. Making the patches is read-only. Applying needs a
scan and a reviewer record matching the fork's head, and the user's yes.
"""
import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("fs_common", Path(__file__).resolve().parent.parent / "common.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fork")
    ap.add_argument("--commits", required=True)
    ap.add_argument("--into")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    ap.add_argument("--accept-concerns", action="store_true")
    a = ap.parse_args()

    out_dir = C.STATE / "patches"
    out_dir.mkdir(parents=True, exist_ok=True)
    patches = []
    for sha in [s.strip() for s in a.commits.split(",") if s.strip()]:
        text = C.gh(f"repos/{a.fork}/commits/{sha}", accept="application/vnd.github.patch")
        path = out_dir / f"{C.slug(a.fork)}__{sha[:7]}.patch"
        path.write_text(text)
        added = [l[1:] for l in text.splitlines() if l.startswith("+") and not l.startswith("+++")]
        names = [l.split(" b/")[-1] for l in text.splitlines() if l.startswith("diff --git")]
        findings = C.scan_lines("patch", added)[0]
        print(f"## {sha[:7]}  {len(names)} file(s): {', '.join(names)[:150]}\n   saved: {path}")
        for sev, label, _, i, why in findings:
            print(f"   {sev} {label}: {why}")
        patches.append(path)

    if not a.into:
        print("\nRead the patches, then re-run with --into DIR (a local repo) to dry-run them.")
        return
    for p in patches:
        r = subprocess.run(["git", "-C", a.into, "apply", "--check", str(p)], capture_output=True, text=True)
        print(f"dry run {p.name}: {'applies cleanly' if r.returncode == 0 else 'DOES NOT APPLY: ' + r.stderr.strip()[:150]}")
    if not a.apply:
        return
    C.gate(a.fork, need_review=True, accept_concerns=a.accept_concerns)
    if not a.confirm:
        print(f"\nWould run: git -C {a.into} am <patches>. Re-run with --confirm after the user says yes.")
        return
    for p in patches:
        subprocess.run(["git", "-C", a.into, "am", str(p)], check=True)
    print("Applied. The commits keep the original author's name.")


if __name__ == "__main__":
    main()
