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
# (severity, label, regex, why it matters)
RULES = [
    ("HIGH", "pipe to shell", r"(curl|wget)[^\n|]*\|\s*(sudo\s+)?(ba|z)?sh\b", "downloads and runs code in one step"),
    ("HIGH", "reverse shell", r"/dev/tcp/|\bnc\s+(-e|-c)\b|bash\s+-i\s+>&", "opens a remote control channel"),
    ("HIGH", "decode then run", r"(b64decode|base64\s+(-d|--decode)|atob)\(?[^\n]{0,80}(exec|eval|sh\b)", "hides code then runs it"),
    ("HIGH", "reads credential stores", r"(\.ssh/(id_|config)|\.aws/credentials|\.netrc|Login Data|Library/Keychains|\bop\s+(read|item\s+get))", "touches passwords or keys"),
    ("HIGH", "hides from user", r"(do not|don't|never)\s+(tell|inform|mention|show)[^\n]{0,30}(the )?user|without\s+(telling|informing)\s+the\s+user", "instruction aimed at an AI to keep a secret"),
    ("HIGH", "prompt override", r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|rules)|disregard\s+(your|the)\s+(instructions|rules)", "tries to override an AI's rules"),
    ("HIGH", "private key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "a private key is committed"),
    ("HIGH", "workflow runs outsider code", r"pull_request_target", "CI job that can run a stranger's code with your secrets"),
    ("MEDIUM", "possible secret", r"(ghp_|gho_|github_pat_)[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|xox[bp]-[A-Za-z0-9-]{10,}", "looks like a live key or token"),
    ("MEDIUM", "workflow uses moving version", r"uses:\s*\S+@(main|master|latest|v\d+)\s*$", "CI step pinned to a tag the author can change"),
    ("MEDIUM", "runs shell or programs", r"\b(os\.system|subprocess\.|child_process|execSync|spawnSync|Runtime\.getRuntime|popen\()", "launches other programs"),
    ("MEDIUM", "dynamic code", r"\b(eval|exec)\s*\(|new Function\(", "runs text as code"),
    ("MEDIUM", "persistence", r"\b(launchctl|crontab|systemctl|LaunchAgents|schtasks|\.bashrc|\.zshrc|\.zprofile)\b", "keeps running or edits startup files"),
    ("MEDIUM", "touches AI config", r"(\.claude/(settings|hooks|skills)|CLAUDE\.md|AGENTS\.md|\"hooks\"\s*:|SessionStart|PreToolUse|UserPromptSubmit)", "changes how your AI assistant behaves"),
    ("MEDIUM", "sends data out", r"(requests\.(post|put)|fetch\([^)]*method\s*:\s*['\"]POST|axios\.post|curl\s[^\n]*(-d|--data|-F)\b|webhook|discord\.com/api/webhooks|pastebin)", "uploads something somewhere"),
    ("MEDIUM", "install-time script", r"\"(preinstall|postinstall|prepare|install)\"\s*:", "runs when the package is installed"),
    ("MEDIUM", "obfuscation", r"(String\.fromCharCode|\\x[0-9a-fA-F]{2}(\\x[0-9a-fA-F]{2}){12,}|[A-Za-z0-9+/=]{300,})", "looks deliberately hard to read"),
    ("LOW", "environment secrets", r"(os\.environ|process\.env)[^\n]{0,40}(KEY|TOKEN|SECRET|PASSWORD)", "reads API keys from the environment"),
]
BINARY_EXT = {".exe", ".dll", ".so", ".dylib", ".node", ".jar", ".whl", ".pyc", ".bin", ".msi", ".pkg", ".dmg", ".app", ".apk"}
SAFE_HOSTS = {"github.com", "githubusercontent.com", "docs.python.org", "python.org", "pypi.org", "npmjs.com", "anthropic.com", "openai.com", "wikipedia.org", "example.com", "localhost", "w3.org", "shields.io"}
KNOWN_INSTALLERS = ("deb.nodesource.com", "astral.sh/uv", "sh.rustup.rs", "get.docker.com", "bun.sh/install", "deno.land/install", "raw.githubusercontent.com/Homebrew/install")
URL_RE = re.compile(r"https?://([A-Za-z0-9.-]+)")
TEST_RE = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]*$|\.test\.[jt]sx?$")


def is_test_path(name):
    return bool(TEST_RE.search(name))


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
