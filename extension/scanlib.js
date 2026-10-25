/* fork-scout scan rules in JavaScript. Mirrors skills/fork-scout/scripts/common.py and reads the same rules.json.
 * Pure functions only (no network, no page access) so they run in the browser and under node. */
(function (root) {
  const SEVERITY = { LOW: 1, MEDIUM: 2, HIGH: 3 };

  function prepare(rulesJson) {
    return {
      rules: rulesJson.rules.map((r) => ({ ...r, re: new RegExp(r.pattern, "i") })),
      binaryExt: new Set(rulesJson.binary_extensions),
      safeHosts: rulesJson.safe_hosts,
      installers: rulesJson.known_installers,
      testRe: new RegExp(rulesJson.test_path_pattern),
      autoRun: new Set(rulesJson.auto_run_test_files),
      fileCap: rulesJson.github_file_cap,
    };
  }

  const baseName = (name) => name.split("/").pop();
  const isTestPath = (R, name) => R.testRe.test(name) && !R.autoRun.has(baseName(name));

  function addedLines(patch) {
    return (patch || "").split("\n").filter((l) => l.startsWith("+") && !l.startsWith("+++")).map((l) => l.slice(1));
  }

  /** Findings and new web addresses for one file's added lines. Test files cap at LOW, except HIGH. */
  function scanLines(R, name, lines) {
    const findings = [];
    const domains = new Set();
    const test = isTestPath(R, name);
    lines.forEach((line, idx) => {
      for (const rule of R.rules) {
        if (!rule.re.test(line)) continue;
        let sev = rule.severity;
        let why = rule.why;
        if (rule.label === "pipe to shell" && R.installers.some((h) => line.includes(h))) {
          sev = "MEDIUM";
          why = "well-known vendor installer, but still an unpinned download that runs at once";
        }
        if (test && sev !== "HIGH") sev = "LOW";
        findings.push([sev, rule.label, name, idx + 1, `${why}: ${line.trim().slice(0, 140)}`]);
      }
      if (!test) {
        for (const m of line.matchAll(/https?:\/\/([A-Za-z0-9.-]+)/g)) {
          const h = m[1];
          if (h.includes(".") && !R.safeHosts.some((s) => h === s || h.endsWith("." + s))) domains.add(h);
        }
      }
    });
    return { findings, domains };
  }

  /** Scan a GitHub compare result (its `files` list). Returns the same shape of report the Python scan writes. */
  function scanCompare(R, files) {
    const findings = [];
    const domains = {};
    if (files.length >= R.fileCap) {
      findings.push(["MEDIUM", "file list cut short", "(whole fork)", 0,
        `GitHub lists at most ${R.fileCap} changed files and this fork changes at least that many, so some were not scanned`]);
    }
    for (const f of files) {
      const name = f.filename;
      const ext = name.includes(".") ? "." + name.split(".").pop().toLowerCase() : "";
      if (R.binaryExt.has(ext)) findings.push(["HIGH", "binary added", name, 0, "compiled file that cannot be read as code"]);
      if (name.startsWith(".github/workflows/") && f.status !== "removed") {
        findings.push(["MEDIUM", "workflow file changed", name, 0, "CI that can run with your secrets if Actions is on"]);
      }
      if (f.patch == null) {
        if (f.status !== "removed" && f.changes > 0 && !R.binaryExt.has(ext)) {
          findings.push(["MEDIUM", "no readable change", name, 0, "GitHub gave no text for this file (too large or binary), so it was not scanned"]);
        }
        continue;
      }
      const res = scanLines(R, name, addedLines(f.patch));
      findings.push(...res.findings);
      for (const d of res.domains) (domains[d] = domains[d] || new Set()).add(name);
    }
    const counts = { HIGH: 0, MEDIUM: 0, LOW: 0 };
    for (const x of findings) counts[x[0]]++;
    const verdict = counts.HIGH ? "DO NOT FORK"
      : counts.MEDIUM || Object.keys(domains).length ? "REVIEW BEFORE FORKING" : "NO RED FLAGS";
    return { verdict, counts, findings, domains: Object.fromEntries(Object.entries(domains).map(([k, v]) => [k, [...v].sort()])) };
  }

  /** 0 = recent and close to the original, 1 = recent-ish, 2 = old, far behind or docs only (same as scout.py). */
  function tier(r) {
    const docsOnly = r.filesTotal <= r.files.length && r.files.every((n) => /\.(md|txt|rst)$/i.test(n));
    if (docsOnly) return 2;
    if (r.daysIdle <= 45 && (r.behind || 0) <= 300) return 0;
    return r.daysIdle <= 120 ? 1 : 2;
  }

  /** A short stamp of exactly what GitHub says this fork changed. If it differs later, the fork moved. */
  function fingerprint(cmp) {
    const parts = [cmp.ahead_by, ...(cmp.files || []).map((f) => `${f.filename}:${f.sha || ""}:${f.changes}`).sort()];
    let h = 2166136261;
    for (const ch of parts.join("|")) { h ^= ch.charCodeAt(0); h = Math.imul(h, 16777619) >>> 0; }
    return `${cmp.ahead_by}-${(cmp.files || []).length}-${h.toString(16)}`;
  }

  /**
   * The copy gate, same rules as the Python skill. The scan is never optional: a serious finding blocks whatever the AI says.
   * `ai` is null when no AI review was run, which is allowed but labelled as such in the screen.
   */
  function gate({ scan, ai, shownFingerprint, nowFingerprint, accept }) {
    if (shownFingerprint !== nowFingerprint) return { ok: false, reason: "This fork changed since you looked at it. Reload the results and look again." };
    if (ai && ai.fingerprint !== nowFingerprint) return { ok: false, reason: "The AI review is for an older version of this fork. Run it again." };
    if (scan.verdict === "DO NOT FORK") return { ok: false, reason: "The scan found serious flags, so copying is blocked whatever the AI says." };
    if (ai && ai.verdict === "unsafe") return { ok: false, reason: "The AI review says this fork is unsafe, so copying is blocked." };
    const medium = scan.findings.filter((f) => f[0] === "MEDIUM").length;
    const concerns = !!ai && ai.verdict === "concerns";
    if ((medium || concerns) && !accept) {
      return { ok: false, needsAccept: true, reason: `${medium ? `The scan raised ${medium} item(s) to check. ` : ""}${concerns ? "The AI raised concerns. " : ""}Read them, and tick the box only if you accept them.` };
    }
    return { ok: true };
  }

  const api = { SEVERITY, prepare, isTestPath, addedLines, scanLines, scanCompare, tier, fingerprint, gate };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ForkScoutScan = api;
})(typeof self !== "undefined" ? self : this);
