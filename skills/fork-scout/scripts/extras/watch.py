#!/usr/bin/env python3
"""Keep an eye on forks you have adopted or are considering. Local notes only.

Usage:
  watch.py add OWNER/FORK       remember the scanned commit (needs a scan report)
  watch.py list
  watch.py check                see which forks moved; rescan those and show the new verdict
  watch.py remove OWNER/FORK

Not a scheduler. For a recurring check, ask the assistant to run `watch.py check` with
/loop or /schedule. A rescan makes any earlier reviewer record stale, so review again
before snapshot, fork, pr or cherry --apply.
"""
import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("fs_common", Path(__file__).resolve().parent.parent / "common.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)

STORE = C.STATE / "watch.json"


def load():
    return json.loads(STORE.read_text()) if STORE.exists() else {}


def save(d):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(d, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["add", "list", "check", "remove"])
    ap.add_argument("fork", nargs="?")
    a = ap.parse_args()
    w = load()

    if a.cmd == "add":
        if not a.fork or not C.report_path(a.fork).exists():
            sys.exit("give a fork that has a scan report (run scan.py first)")
        rep = json.loads(C.report_path(a.fork).read_text())
        w[a.fork] = {"head_sha": rep["head_sha"], "verdict": rep["verdict"]}
        save(w)
        print(f"watching {a.fork} at {rep['head_sha'][:10]} ({rep['verdict']})")
    elif a.cmd == "remove":
        w.pop(a.fork, None)
        save(w)
        print(f"stopped watching {a.fork}")
    elif a.cmd == "list":
        for fk, v in w.items():
            print(f"- {fk}  scanned {v['head_sha'][:10]}  {v['verdict']}")
        if not w:
            print("nothing watched")
    else:
        for fk, v in w.items():
            sha, _ = C.live_head(fk)
            if sha == v["head_sha"]:
                print(f"- {fk}: unchanged since the scan")
                continue
            print(f"- {fk}: CHANGED ({v['head_sha'][:7]} -> {sha[:7]}). Rescanning...")
            r = subprocess.run([sys.executable, "-I", str(Path(__file__).resolve().parent / "scan.py"), fk],
                               capture_output=True, text=True)
            head = "\n".join(r.stdout.splitlines()[:3]) if r.returncode == 0 else r.stdout + r.stderr
            print("  " + head.replace("\n", "\n  "))
            if r.returncode == 0:
                rep = json.loads(C.report_path(fk).read_text())
                print(f"  verdict was {v['verdict']}, now {rep['verdict']}. Earlier review is now stale: review again before using it.")
                w[fk] = {"head_sha": rep["head_sha"], "verdict": rep["verdict"]}
        save(w)
        if not w:
            print("nothing watched")


if __name__ == "__main__":
    main()
