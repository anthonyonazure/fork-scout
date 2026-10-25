"""Shared pieces for fork-scout: GitHub calls, scan rules, and the safety gate.

Loaded by path from the other scripts (they run under `python3 -I`, which does not
put this folder on the import path). Read-only except where a script says otherwise.
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE = Path.home() / ".cache" / "fork-scout"


def gh(path, die=True, accept=None):
    cmd = ["gh", "api"] + (["-H", f"Accept: {accept}"] if accept else []) + [path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        if die:
            sys.exit(f"gh api {path} failed: {r.stderr.strip()[:200]}")
        return None
    return r.stdout if accept else json.loads(r.stdout)


LAST = STATE / "last_browse.json"


def repo_name(arg):
    """Accept OWNER/REPO or a github.com URL."""
    s = arg.strip().rstrip("/")
    s = re.sub(r"^https?://github\.com/", "", s)
    return re.sub(r"\.git$", "", s)


def resolve(arg):
    """'2' or '#2' means the 2nd fork of the last list shown; anything else is a repo name."""
    m = re.fullmatch(r"#?(\d+)", arg.strip())
    if not m:
        return repo_name(arg)
    if not LAST.exists():
        sys.exit("no list to pick from yet: run scout.py on a repo first")
    forks = json.loads(LAST.read_text())["forks"]
    n = int(m.group(1))
    if not 1 <= n <= len(forks):
        sys.exit(f"pick a number from 1 to {len(forks)}")
    return forks[n - 1]


def days_since(iso):
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - t).days


def slug(fork):
    return fork.replace("/", "__")


def live_head(fork):
    """Current head commit of the fork's default branch, and that branch name."""
    info = gh(f"repos/{fork}")
    sha = gh(f"repos/{fork}/commits/{info['default_branch']}")["sha"]
    return sha, info["default_branch"]


def upstream_of(fork, given=None):
    up = given or (gh(f"repos/{fork}").get("parent") or {}).get("full_name")
    if not up:
        sys.exit("not a fork and no --upstream given")
    return up


# ---------------------------------------------------------------- scan rules
# The rules live in rules.json beside the scripts so the browser extension can read the same file.
_R = json.loads((Path(__file__).resolve().parent.parent / "rules.json").read_text())
RULES = [(r["severity"], r["label"], r["pattern"], r["why"]) for r in _R["rules"]]  # (severity, label, regex, why it matters)
BINARY_EXT = set(_R["binary_extensions"])
SAFE_HOSTS = set(_R["safe_hosts"])
KNOWN_INSTALLERS = tuple(_R["known_installers"])
GITHUB_FILE_CAP = _R["github_file_cap"]  # GitHub's compare call lists at most this many files; past it the list is cut short
AUTO_RUN_TEST_FILES = set(_R["auto_run_test_files"])  # test tools load these by themselves
URL_RE = re.compile(r"https?://([A-Za-z0-9.-]+)")
TEST_RE = re.compile(_R["test_path_pattern"])


def is_test_path(name):
    return bool(TEST_RE.search(name)) and Path(name).name not in AUTO_RUN_TEST_FILES


def added_lines(patch):
    return [l[1:] for l in (patch or "").splitlines() if l.startswith("+") and not l.startswith("+++")]


def scan_lines(name, lines):
    """Return (findings, domains) for one file's added lines. Tests cap at LOW."""
    findings, domains = [], set()
    test = is_test_path(name)
    for i, line in enumerate(lines, 1):
        for sev, label, rx, why in RULES:
            if re.search(rx, line, re.I):
                if label == "pipe to shell" and any(h in line for h in KNOWN_INSTALLERS):
                    sev, why = "MEDIUM", "well-known vendor installer, but still an unpinned download that runs at once"
                findings.append(("LOW" if test and sev != "HIGH" else sev, label, name, i, f"{why}: {line.strip()[:140]}"))
        if not test:
            for h in URL_RE.findall(line):
                if "." in h and not any(h == s or h.endswith("." + s) for s in SAFE_HOSTS):
                    domains.add(h)
    return findings, domains


# ---------------------------------------------------------------- the gate
def report_path(fork):
    return STATE / "reports" / f"{slug(fork)}.json"


def review_path(fork):
    return STATE / "reviews" / f"{slug(fork)}.json"


def gate(fork, need_review=True, accept_concerns=False):
    """Refuse (exit) unless a scan and a reviewer's record both match the fork's live head."""
    rp = report_path(fork)
    if not rp.exists():
        sys.exit("no scan report: run scan.py on this fork first")
    rep = json.loads(rp.read_text())
    sha, _ = live_head(fork)
    if rep.get("head_sha") != sha:
        sys.exit(f"fork changed since the scan ({str(rep.get('head_sha'))[:7]} then, {sha[:7]} now): rescan")
    if rep["verdict"] == "DO NOT FORK":
        sys.exit("scan verdict is DO NOT FORK: refusing")
    medium = [x for x in rep.get("findings", []) if x[0] == "MEDIUM"]
    if need_review and medium and not accept_concerns:
        sys.exit(f"scan raised {len(medium)} item(s) to check: a reviewer's 'clear' does not erase them. Read them to the user, and pass --accept-concerns only if they accept")
    if need_review:
        vp = review_path(fork)
        if not vp.exists():
            sys.exit("no review record: run review.py, hand the brief to a read-only reviewer agent, then record the result")
        rev = json.loads(vp.read_text())
        if rev.get("head_sha") != sha:
            sys.exit("review is for an older version of the fork: review again")
        if rev["verdict"] == "unsafe":
            sys.exit("reviewer verdict is unsafe: refusing")
        if rev["verdict"] == "concerns" and not accept_concerns:
            sys.exit("reviewer raised concerns: read them, and pass --accept-concerns only if the user accepts them")
    return rep
