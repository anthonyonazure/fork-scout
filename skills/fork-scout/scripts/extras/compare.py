#!/usr/bin/env python3
"""Put several forks side by side: what each touches, where they overlap, what the scan said.

Usage: compare.py OWNER/FORK OWNER/FORK [OWNER/FORK ...] [--upstream OWNER/REPO]

Read-only. Overlapping files mean two forks fixed the same area, so they compete or
conflict. The judgement of which one to prefer is left to the reader (or the model).
"""
import argparse
import importlib.util
import itertools
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location("fs_common", Path(__file__).resolve().parent.parent / "common.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("forks", nargs="+")
    ap.add_argument("--upstream")
    a = ap.parse_args()
    up = C.upstream_of(a.forks[0], a.upstream)
    base = C.gh(f"repos/{up}")["default_branch"]

    rows = {}
    for fk in a.forks:
        info = C.gh(f"repos/{fk}")
        cmp = C.gh(f"repos/{up}/compare/{base}...{info['owner']['login']}:{info['default_branch']}")
        rp = C.report_path(fk)
        scan = json.loads(rp.read_text())["verdict"] if rp.exists() else "not scanned"
        rows[fk] = {"ahead": cmp["ahead_by"], "behind": cmp["behind_by"], "idle": C.days_since(info["pushed_at"]),
                    "files": {x["filename"] for x in cmp.get("files", [])}, "scan": scan,
                    "titles": [c["commit"]["message"].splitlines()[0][:70] for c in cmp["commits"][-3:]]}

    print(f"| Fork | Ahead | Behind | Idle days | Files | Scan |\n| --- | --- | --- | --- | --- | --- |")
    for fk, r in rows.items():
        print(f"| {fk} | {r['ahead']} | {r['behind']} | {r['idle']} | {len(r['files'])} | {r['scan']} |")
    print("\n## Latest commits")
    for fk, r in rows.items():
        print(f"- {fk}: " + "; ".join(r["titles"]))
    print("\n## Overlap (same files changed by both)")
    found = False
    for x, y in itertools.combinations(rows, 2):
        both = sorted(rows[x]["files"] & rows[y]["files"])
        if both:
            found = True
            print(f"- {x} and {y}: {len(both)} shared file(s): {', '.join(both[:6])}")
    if not found:
        print("- none: the forks change different parts, so they can be combined.")


if __name__ == "__main__":
    main()
