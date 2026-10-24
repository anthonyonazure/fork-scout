#!/usr/bin/env python3
"""Rank the forks of a GitHub repo by what they actually changed.

Usage: forks.py OWNER/REPO [--stars-pages 2] [--new-pages 2] [--top 20] [--json]

Needs the gh CLI, logged in. Read-only: only GET requests.
Candidates come from the most-starred forks plus the newest forks, because
the forks endpoint has no "recently pushed" sort and most forks never change.
Each candidate is compared against upstream to count commits ahead.
"""
import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone


def gh(path):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if r.returncode:
        return None
    return json.loads(r.stdout)


def days_since(iso):
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - t).days


def candidates(repo, sort, pages):
    out = []
    for p in range(1, pages + 1):
        page = gh(f"repos/{repo}/forks?sort={sort}&per_page=100&page={p}")
        if not page:
            break
        out += page
    return out


def inspect(fork, repo, base):
    owner = fork["owner"]["login"]
    head = f"{owner}:{fork['default_branch']}"
    cmp = gh(f"repos/{repo}/compare/{base}...{head}")
    row = {
        "fork": fork["full_name"],
        "url": fork["html_url"],
        "stars": fork["stargazers_count"],
        "pushed": fork["pushed_at"],
        "days_idle": days_since(fork["pushed_at"]),
        "description": fork["description"] or "",
        "ahead": None,
        "behind": None,
        "changes": [],
    }
    if cmp:
        row["ahead"], row["behind"] = cmp["ahead_by"], cmp["behind_by"]
        row["changes"] = [
            c["commit"]["message"].split("\n")[0][:90] for c in cmp["commits"][-4:]
        ]
        # fuller picture for browsing: recent commit titles and the biggest changed files
        row["titles"] = [c["commit"]["message"].split("\n")[0][:110] for c in cmp["commits"][-8:]]
        files = sorted(cmp.get("files", []), key=lambda x: -(x["additions"] + x["deletions"]))
        row["files"] = [[x["filename"], x["additions"], x["deletions"]] for x in files[:12]]
        row["files_total"] = len(cmp.get("files", []))
        row["head_sha"] = cmp["commits"][-1]["sha"] if cmp["commits"] else None
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--stars-pages", type=int, default=2)
    ap.add_argument("--new-pages", type=int, default=2)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--since-days", type=int, help="only forks pushed within this many days")
    ap.add_argument("--min-ahead", type=int, default=1, help="at least this many commits of their own")
    ap.add_argument("--max-behind", type=int, help="at most this many commits behind upstream")
    a = ap.parse_args()

    info = gh(f"repos/{a.repo}")
    if not info:
        sys.exit(f"cannot read {a.repo}")
    base = info["default_branch"]
    pool = {}
    for sort, n in (("stargazers", a.stars_pages), ("newest", a.new_pages)):
        for f in candidates(a.repo, sort, n):
            pool[f["full_name"]] = f
    with ThreadPoolExecutor(8) as ex:
        rows = list(ex.map(lambda f: inspect(f, a.repo, base), pool.values()))

    # a fork is interesting if it has its own commits; then stars, then freshness
    live_all = [r for r in rows if (r["ahead"] or 0) >= a.min_ahead
                and (a.since_days is None or r["days_idle"] <= a.since_days)
                and (a.max_behind is None or (r["behind"] or 0) <= a.max_behind)]
    live = sorted(live_all, key=lambda r: (-r["stars"], r["days_idle"], -r["ahead"]))[: a.top]

    if a.json:
        print(json.dumps({
            "upstream": info["full_name"],
            "stars": info["stargazers_count"],
            "total_forks": info["forks_count"],
            "checked": len(rows),
            "with_own_commits": len(live_all),
            "forks": live,
        }, indent=1))
        return
    print(f"{info['full_name']}: {info['stargazers_count']} stars, {info['forks_count']} forks. "
          f"Checked {len(rows)}; {len(live_all)} have commits of their own.\n")
    print("| Fork | Stars | Last push | Ahead | Behind | What changed |")
    print("| --- | --- | --- | --- | --- | --- |")
    for r in live:
        what = "; ".join(r["changes"]) or r["description"]
        print(f"| [{r['fork']}]({r['url']}) | {r['stars']} | {r['pushed'][:10]} ({r['days_idle']}d) "
              f"| {r['ahead']} | {r['behind']} | {what} |")


if __name__ == "__main__":
    main()
