#!/usr/bin/env python3
"""Static security scan of what a fork changed. Never runs the fork's code.

Usage: scan.py OWNER/FORK [--upstream OWNER/REPO]

Steps: compare the fork with upstream through the GitHub API, make a shallow clone
with git hooks off into a fresh folder, read the changed files as text only, and
look for risky patterns on lines the fork added. Also checks CI workflow files, new
dependencies against the OSV vulnerability database, leaked secrets (built-in
patterns plus gitleaks when installed), and who the author is (surfaced, never
used to change the verdict). Writes a report that the other scripts check before
they will fork, snapshot, apply or open a pull request. A clean result means "no red
flags found by pattern matching", never "proven safe".
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

_spec = importlib.util.spec_from_file_location("fs_common", Path(__file__).resolve().parent / "common.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)

DEP_FILES = ("requirements", "package.json", "pyproject.toml")


def new_dependencies(name, lines):
    """(ecosystem, package, pinned_version_or_None) from added lines of a dependency file."""
    base = Path(name).name
    out = []
    for line in lines:
        s = line.strip()
        if base.startswith("requirements") and base.endswith(".txt"):
            m = re.match(r"([A-Za-z0-9_.-]+)\s*(==\s*([\w.]+))?", s)
            if m and not s.startswith(("#", "-")):
                out.append(("PyPI", m.group(1), m.group(3)))
        elif base == "package.json":
            m = re.match(r'"(@?[\w./-]+)"\s*:\s*"([~^]?)(\d[\w.\-+]*)"', s)
            if m and m.group(1) not in ("version", "name"):
                out.append(("npm", m.group(1), m.group(3) if not m.group(2) else None))
        elif base == "pyproject.toml":
            for m in re.finditer(r'"([A-Za-z0-9_.-]+)\s*(==\s*([\w.]+))?[^"]*"', s):
                if "==" in s or ">=" in s or "~=" in s:
                    out.append(("PyPI", m.group(1), m.group(3)))
    return out


def osv_lookup(deps):
    """Check pinned versions against osv.dev. Unpinned ones cannot be checked."""
    result = []
    for eco, pkg, ver in deps[:30]:
        if not ver:
            result.append({"package": pkg, "ecosystem": eco, "note": "unpinned: version unknown, cannot check; verify by hand"})
            continue
        body = json.dumps({"package": {"name": pkg, "ecosystem": eco}, "version": ver}).encode()
        try:
            req = urllib.request.Request("https://api.osv.dev/v1/query", body, {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                vulns = json.loads(r.read()).get("vulns", [])
            note = f"{len(vulns)} known vulnerabilities: " + ", ".join(v["id"] for v in vulns[:4]) if vulns else "no known vulnerabilities"
        except Exception as e:  # network down, rate limit: say so, never fake a pass
            note = f"lookup failed ({type(e).__name__}); verify by hand"
        result.append({"package": pkg, "ecosystem": eco, "version": ver, "note": note})
    return result


def trust_block(owner, commits):
    u = C.gh(f"users/{owner}", die=False) or {}
    verified = sum(1 for c in commits if (c["commit"].get("verification") or {}).get("verified"))
    return {
        "owner": owner,
        "account_age_days": C.days_since(u["created_at"]) if u.get("created_at") else None,
        "public_repos": u.get("public_repos"),
        "followers": u.get("followers"),
        "verified_commits": f"{verified} of {len(commits)}",
    }


def gitleaks_changed(dest, changed):
    """Run gitleaks if installed; keep only hits in files the fork changed."""
    if not shutil.which("gitleaks"):
        return None
    with tempfile.TemporaryDirectory() as td:
        rp = Path(td) / "r.json"
        subprocess.run(["gitleaks", "dir", str(dest), "--no-banner", "--redact", "-f", "json", "-r", str(rp), "--exit-code", "0"],
                       capture_output=True, text=True)
        try:
            hits = json.loads(rp.read_text() or "[]")
        except (OSError, ValueError):
            return None
    rows = []
    for h in hits:
        rel = os.path.relpath(h.get("File", ""), dest)
        if rel in changed:
            rows.append(("LOW" if C.is_test_path(rel) else "MEDIUM", "gitleaks", rel, h.get("StartLine", 0), f"{h.get('RuleID')}: possible secret (value hidden)"))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fork")
    ap.add_argument("--upstream")
    a = ap.parse_args()
    a.fork = C.resolve(a.fork)

    f = C.gh(f"repos/{a.fork}")
    up = C.upstream_of(a.fork, a.upstream)
    base = C.gh(f"repos/{up}")["default_branch"]
    cmp = C.gh(f"repos/{up}/compare/{base}...{f['owner']['login']}:{f['default_branch']}")
    if not cmp["commits"]:
        sys.exit("fork has no commits beyond upstream: nothing to scan, nothing to gain")
    files = cmp.get("files", [])
    head_sha, branch = C.live_head(a.fork)

    # shallow clone, hooks off, no submodules, no LFS download: files are only read as text
    dest = C.STATE / "clones" / f"{C.slug(a.fork)}__{head_sha[:7]}"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1", GIT_TERMINAL_PROMPT="0")
        r = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "clone", "--depth", "1",
             "--no-tags", "--single-branch", "--branch", branch, f["clone_url"], str(dest)],
            capture_output=True, text=True, env=env)
        if r.returncode:
            sys.exit(f"clone failed: {r.stderr[:200]}")
    cloned = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if cloned != head_sha:
        sys.exit(f"fork moved while cloning ({cloned[:7]} vs {head_sha[:7]}): run the scan again")

    findings, domains, dep_rows = [], {}, []
    changed = set()
    for x in files:
        name = x["filename"]
        changed.add(name)
        p = dest / name
        if Path(name).suffix.lower() in C.BINARY_EXT:
            findings.append(("HIGH", "binary added", name, 0, "compiled file that cannot be read as code"))
        if name.startswith(".github/workflows/") and x["status"] != "removed":
            findings.append(("MEDIUM", "workflow file changed", name, 0, "CI that can run with your secrets if Actions is on"))
        if x["status"] != "removed" and p.is_symlink():
            findings.append(("HIGH", "symlink", name, 0, "link can point outside the project"))
            continue
        patch = x.get("patch")
        if patch is None and p.is_file():
            try:
                lines = p.read_text(errors="replace").splitlines()
            except OSError:
                lines = []
            if not lines and p.stat().st_size > 0:
                findings.append(("MEDIUM", "unreadable file", name, 0, "no text to review"))
        else:
            lines = C.added_lines(patch)
        fnd, doms = C.scan_lines(name, lines)
        findings += fnd
        for d in doms:
            domains.setdefault(d, set()).add(name)
        if Path(name).name.startswith(DEP_FILES) or Path(name).name in DEP_FILES:
            dep_rows += new_dependencies(name, lines)

    gl = gitleaks_changed(dest, changed)
    findings += gl or []
    deps = osv_lookup(dep_rows)
    vulnerable = [d for d in deps if "known vulnerabilities:" in d["note"]]
    for d in vulnerable:
        findings.append(("MEDIUM", "vulnerable dependency", d["package"], 0, d["note"]))
    trust = trust_block(f["owner"]["login"], cmp["commits"])
    if trust["account_age_days"] is not None and trust["account_age_days"] < 180:
        trust["note"] = "account is under 6 months old"

    sev_count = {s: sum(1 for x in findings if x[0] == s) for s in ("HIGH", "MEDIUM", "LOW")}
    verdict = "DO NOT FORK" if sev_count["HIGH"] else ("REVIEW BEFORE FORKING" if sev_count["MEDIUM"] or domains or deps else "NO RED FLAGS")
    report = {"fork": a.fork, "upstream": up, "head_sha": head_sha, "verdict": verdict, "counts": sev_count,
              "new_domains": {k: sorted(v) for k, v in domains.items()}, "dependencies": deps, "trust": trust,
              "gitleaks": "not installed" if gl is None else f"{len(gl)} hit(s) in changed files",
              "changed_files": sorted(changed), "clone": str(dest), "findings": [list(x) for x in findings]}
    (C.STATE / "reports").mkdir(parents=True, exist_ok=True)
    out = C.report_path(a.fork)
    out.write_text(json.dumps(report, indent=1))

    print(f"# Scan: {a.fork} @ {head_sha[:10]} vs {up}")
    print(f"Verdict (pattern matching only): {verdict}")
    print(f"Files changed: {len(files)}   HIGH {sev_count['HIGH']}  MEDIUM {sev_count['MEDIUM']}  LOW {sev_count['LOW']}")
    print(f"Author: {trust['owner']}, account {trust['account_age_days']} days old, {trust['public_repos']} repos, "
          f"{trust['followers']} followers, verified commits {trust['verified_commits']}" + (f" ({trust['note']})" if trust.get("note") else ""))
    print(f"Secret scan: built-in patterns + gitleaks {report['gitleaks']}")
    if deps:
        print("\nNew dependencies:")
        for d in deps:
            print(f"- {d['package']} ({d['ecosystem']}{' ' + d['version'] if d.get('version') else ''}): {d['note']}")
    if domains:
        print("\nNew web addresses in added lines:")
        for d, fs in sorted(domains.items()):
            print(f"- {d}  ({', '.join(sorted(fs))[:100]})")
    for sev in ("HIGH", "MEDIUM", "LOW"):
        rows = [x for x in findings if x[0] == sev]
        if rows:
            print(f"\n## {sev}")
            for _, label, name, i, why in rows[:40]:
                print(f"- {label} in {name}:{i}  {why}")
    print(f"\nReport saved: {out}\nClone for reading (do not run anything in it): {dest}")


if __name__ == "__main__":
    main()
