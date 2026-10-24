#!/usr/bin/env python3
"""Browse the interesting forks of a repo: a readable list the user can pick from.

Usage: scout.py REPO_OR_URL [--top 8] [--since-days N] [--min-ahead N] [--max-behind N]
                            [--stars-pages N] [--new-pages N]

Prints a numbered table and a card per fork (facts, recent changes, biggest files). The
assistant adds the plain-English explanation of each card. The numbers can be used in
place of fork names by check.py, snapshot.py, fork.py and build.py ("2" = second fork).
Read-only: no security scan runs here, because nobody is looking at code yet.
"""
import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("fs_common", HERE / "common.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)


def tier(r):
    """0 = recent and close to the original, 1 = recent-ish, 2 = old or far behind."""
    docs_only = r["files_total"] <= len(r["files"]) and all(n.lower().endswith((".md", ".txt", ".rst")) for n, _, _ in r["files"])
    if docs_only:
        return 2
    if r["days_idle"] <= 45 and (r["behind"] or 0) <= 300:
        return 0
    return 1 if r["days_idle"] <= 120 else 2


def activity(days):
    return "active" if days <= 30 else "quiet" if days <= 120 else "abandoned"


REPO_RE = r"(https?://github\.com/)?[\w.-]+/[\w.-]+(\.git)?/?"


def search(text):
    """Free-text search for repos to scout: a topic, keyword, project name, or `@person`."""
    import re
    q = text.strip()
    owner = None
    m = re.fullmatch(r"(?:@|user:)([\w.-]+)", q)
    if m:
        owner, q = m.group(1), ""
    words = q.split()
    hits = []
    while True:  # every word must match, so relax by dropping the last word until there are enough results
        cmd = ["gh", "search", "repos", *words, *(["--owner", owner] if owner else []),
               "--limit", "10", "--sort", "stars", "--json", "fullName,description,stargazersCount,forksCount,updatedAt"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"search failed: {r.stderr.strip()[:200]}")
        hits = json.loads(r.stdout)
        if len(hits) >= 3 or len(words) <= 1:
            break
        words = words[:-1]
    if words and " ".join(words) != q:
        print(f"(too few matches for all the words, so I searched for '{' '.join(words)}')\n")
    if not hits:
        sys.exit(f"nothing found for '{text}'. Try fewer or different words.")
    print(f"# Repos matching '{text}'  (most-starred first)\n")
    print("| # | Repo | Stars | Forks | Updated | What it is |\n| --- | --- | --- | --- | --- | --- |")
    for i, h in enumerate(hits, 1):
        print(f"| {i} | {h['fullName']} | {h['stargazersCount']} | {h['forksCount']} | {h['updatedAt'][:10]} "
              f"| {(h['description'] or '')[:90]} |")
    print("\nPick one and run scout.py on its name to see its interesting forks. "
          "A repo with few forks has little to find.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", help="OWNER/REPO, a github.com URL, or anything to search for (a topic, project name, @person)")
    ap.add_argument("--find", help="only forks that touch this (a feature word or phrase, e.g. reddit, auth)")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--since-days", type=int)
    ap.add_argument("--min-ahead", type=int)
    ap.add_argument("--max-behind", type=int)
    ap.add_argument("--stars-pages", type=int)
    ap.add_argument("--new-pages", type=int)
    a = ap.parse_args()
    import re
    if not re.fullmatch(REPO_RE, a.repo.strip()):
        return search(a.repo)
    repo = C.repo_name(a.repo)

    flags = ["--top", "200" if a.find else "40", "--json"]
    for name, val in (("--since-days", a.since_days), ("--min-ahead", a.min_ahead), ("--max-behind", a.max_behind),
                      ("--stars-pages", a.stars_pages), ("--new-pages", a.new_pages)):
        if val is not None:
            flags += [name, str(val)]
    r = subprocess.run([sys.executable, "-I", str(HERE / "forks.py"), repo, *flags], capture_output=True, text=True)
    if r.returncode:
        sys.exit(r.stdout + r.stderr)
    data = json.loads(r.stdout)
    pool = data["forks"]
    if a.find:
        words = [w.lower() for w in a.find.split()]
        pool = [x for x in pool if all(w in " ".join(x["titles"] + [n for n, _, _ in x["files"]] + [x["description"]]).lower() for w in words)]
    rows = sorted(pool, key=lambda x: (tier(x), -x["ahead"], x["days_idle"], -x["stars"]))[: a.top]
    if not rows:
        print(f"No fork of {repo} has changes of its own that pass the filters" + (f" and mention '{a.find}'." if a.find else "."))
        return

    C.LAST.parent.mkdir(parents=True, exist_ok=True)
    C.LAST.write_text(json.dumps({"upstream": repo, "forks": [x["fork"] for x in rows]}))

    print(f"# Forks of {data['upstream']}  ({data['stars']} stars, {data['total_forks']} forks)"
          + (f"  matching '{a.find}'" if a.find else ""))
    print(f"Looked at {data['checked']} of {data['total_forks']} (the most-starred and newest); "
          f"{data['with_own_commits']} have changes of their own. Showing the {len(rows)} most interesting.\n")
    print("| # | Fork | Stars | Last active | Ahead | Behind | Latest change |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for i, x in enumerate(rows, 1):
        print(f"| {i} | [{x['fork']}]({x['url']}) | {x['stars']} | {activity(x['days_idle'])}, {x['days_idle']}d ago "
              f"| {x['ahead']} | {x['behind']} | {(x['titles'] or [''])[-1][:80]} |")
    print("\nAhead = commits the fork added. Behind = commits of the original it is missing. "
          "Ranked by recent activity, closeness to the original and size of change, not stars.")
    for i, x in enumerate(rows, 1):
        print(f"\n## {i}. {x['fork']}")
        print(f"{activity(x['days_idle'])} (last push {x['pushed'][:10]}), {x['ahead']} ahead / {x['behind']} behind, "
              f"{x['files_total']} files changed, {x['stars']} stars")
        print("Recent commits: " + " | ".join(x["titles"][::-1][:6]))
        print("Biggest files: " + ", ".join(f"{n} (+{p}/-{m})" for n, p, m in x["files"][:8]))


if __name__ == "__main__":
    main()
