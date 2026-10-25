/* The full results page: ranked forks with scan details, optional AI review, and optional forking after a confirmation.
 * All text that comes from a fork or from the AI is inserted as plain text, never as HTML. */
(async function () {
  const Scan = self.ForkScoutScan;
  const Core = self.ForkScoutCore;
  const $ = (id) => document.getElementById(id);
  const R = Scan.prepare(await (await fetch("rules.json")).json());
  let caps = { canFork: false, aiOn: false, model: "" };
  let current = null; // { owner, repo }
  let cards = new Map();

  const el = (tag, props = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) (k === "class" ? (n.className = v) : n.setAttribute(k, v));
    for (const k of kids) n.append(k);
    return n;
  };
  const link = (href, text) => { const a = el("a", { href, target: "_blank", rel: "noopener noreferrer" }); a.textContent = text; return a; };

  async function refreshCaps() {
    caps = await chrome.runtime.sendMessage({ type: "capabilities" });
    const model = self.ForkScoutPolicy.MODELS.find((m) => m.id === caps.model);
    $("modes").replaceChildren(
      el("span", { class: "chip on" }, "Pattern scan: always on"),
      el("span", { class: caps.aiOn ? "chip on" : "chip" }, caps.aiOn ? `AI review: on (${model ? model.label : caps.model})` : "AI review: off, add a key in Settings"),
      el("span", { class: caps.canFork ? "chip on" : "chip" }, caps.canFork ? "Forking: on, asks you each time" : "Forking: off, add a token in Settings"));
  }

  function badge(verdict) {
    const [cls, text] = verdict === "DO NOT FORK" ? ["bad", "Serious flags"]
      : verdict === "REVIEW BEFORE FORKING" ? ["check", "Check before copying"] : ["ok", "No red flags found"];
    return el("span", { class: `badge ${cls}` }, text);
  }
  const aiBadge = (v) => el("span", { class: `badge ${v === "clear" ? "ok" : v === "concerns" ? "check" : "bad"}` }, `AI: ${v}`);

  function aiBox(row) {
    if (row.aiError) return el("div", { class: "err" }, row.aiError);
    if (!row.ai) return null;
    const a = row.ai;
    const box = el("div", { class: "ai" }, el("h3", {}, "AI review "), el("div", { class: "muted" }, `Model: ${a.model}. Pattern scan plus AI review.`));
    box.firstChild.append(aiBadge(a.verdict));
    if (a.summary) box.append(el("p", {}, a.summary));
    if (a.why_better) box.append(el("div", {}, el("strong", {}, "Why it might be better: "), a.why_better));
    if (a.catch) box.append(el("div", {}, el("strong", {}, "Catch: "), a.catch));
    if (a.concerns.length) {
      const ul = el("ul");
      a.concerns.forEach((c) => ul.append(el("li", {}, `${c.file}${c.line ? ":" + c.line : ""} ${c.issue}`.trim())));
      box.append(el("div", {}, el("strong", {}, "Concerns:")), ul);
    }
    return box;
  }

  function card(row) {
    const f = row.fork;
    const head = el("div", { class: "head" }, el("strong", {}, link(f.html_url, f.full_name)), badge(row.scan.verdict),
      el("span", { class: "muted" }, `${f.stargazers_count} stars · ${row.daysIdle} days since last push · ${row.cmp.ahead_by} ahead, ${row.cmp.behind_by} behind`));
    const titles = el("ul");
    row.cmp.titles.slice(0, 5).forEach((t) => titles.append(el("li", {}, t)));
    const c = el("div", { class: "card" }, head,
      el("div", { class: "muted" }, `Changes ${row.cmp.files.length}${row.cmp.fileListCut ? "+ (GitHub cut the list short)" : ""} files. Latest commits:`), titles);

    const flags = row.scan.findings.filter((x) => x[0] !== "LOW");
    const doms = Object.keys(row.scan.domains);
    if (flags.length || doms.length) {
      const d = el("details", {}, el("summary", {}, `Scan: ${row.scan.counts.HIGH} serious, ${row.scan.counts.MEDIUM} to check, ${row.scan.counts.LOW} minor`));
      const ul = el("ul");
      flags.slice(0, 25).forEach(([sev, label, file, line, why]) => ul.append(el("li", {}, `${sev}: ${label} in ${file}${line ? ":" + line : ""}. ${why}`.slice(0, 260))));
      doms.slice(0, 8).forEach((dom) => ul.append(el("li", {}, `New web address: ${dom} (${row.scan.domains[dom].slice(0, 3).join(", ")})`)));
      d.append(ul);
      c.append(d);
    }
    const ai = aiBox(row);
    if (ai) c.append(ai);

    const actions = el("div", { class: "actions" });
    const aiBtn = el("button", { class: "secondary" }, row.aiBusy ? "Reviewing..." : row.ai ? "Run AI review again" : "AI review");
    aiBtn.disabled = !!row.aiBusy;
    aiBtn.title = caps.aiOn ? "Sends this fork's changed code to Anthropic using your key" : "Add an AI key in Settings to turn this on";
    aiBtn.addEventListener("click", () => (caps.aiOn ? runAi(row) : chrome.runtime.openOptionsPage()));
    const blocked = row.scan.verdict === "DO NOT FORK";
    const forkBtn = el("button", {}, row.forkedUrl ? "Forked" : row.forkBusy ? "Forking..." : "Fork a copy");
    forkBtn.disabled = blocked || !!row.forkedUrl || !!row.forkBusy;
    forkBtn.title = blocked ? "Blocked: the scan found serious flags" : caps.canFork ? "Create a public fork in your GitHub account (asks first)" : "Add a fork token in Settings to turn this on";
    forkBtn.addEventListener("click", () => (caps.canFork ? startFork(row) : chrome.runtime.openOptionsPage()));
    actions.append(aiBtn, forkBtn);
    if (row.forkedUrl) actions.append(el("span", { class: "good" }, "Created: "), link(row.forkedUrl, row.forkedName));
    if (row.forkError) actions.append(el("span", { class: "err" }, row.forkError));
    c.append(actions);
    return c;
  }

  function redraw(row) {
    const old = cards.get(row);
    const fresh = card(row);
    cards.set(row, fresh);
    if (old && old.isConnected) old.replaceWith(fresh);
  }

  function showRows(rows) {
    const live = new Set(rows);
    for (const k of [...cards.keys()]) if (!live.has(k)) cards.delete(k);
    for (const r of rows) if (!cards.has(r)) cards.set(r, card(r));
    $("list").replaceChildren(...rows.map((r) => cards.get(r)));
  }

  async function runAi(row) {
    row.aiBusy = true; row.aiError = null; redraw(row);
    const res = await chrome.runtime.sendMessage({
      type: "ai-review", fork: row.fork.full_name, upstream: `${current.owner}/${current.repo}`,
      cmp: row.cmp, scan: row.scan, fingerprint: row.fingerprint,
    });
    row.aiBusy = false;
    if (res.ok) row.ai = res.review; else row.aiError = res.error;
    redraw(row);
  }

  function confirmFork(row, login) {
    return new Promise((resolve) => {
      const preview = Scan.gate({ scan: row.scan, ai: row.ai || null, shownFingerprint: row.fingerprint, nowFingerprint: row.fingerprint, accept: false });
      const needsAccept = !!preview.needsAccept;
      const close = (v) => { overlay.remove(); resolve(v); };
      const box = el("input", { type: "checkbox", id: "accept" });
      const ok = el("button", {}, "Create public fork");
      const cancel = el("button", { class: "secondary" }, "Cancel");
      ok.disabled = needsAccept || !preview.ok && !needsAccept;
      box.addEventListener("change", () => (ok.disabled = !box.checked));
      ok.addEventListener("click", () => close({ accept: box.checked }));
      cancel.addEventListener("click", () => close(null));
      const lines = el("ul");
      lines.append(el("li", {}, `Pattern scan: ${row.scan.verdict === "NO RED FLAGS" ? "no red flags found" : row.scan.verdict.toLowerCase()} (${row.scan.counts.HIGH} serious, ${row.scan.counts.MEDIUM} to check).`));
      lines.append(el("li", {}, row.ai ? `AI review (${row.ai.model}): ${row.ai.verdict}.` : "No AI review was run for this fork."));
      const dialog = el("div", { class: "dialog", role: "dialog", "aria-modal": "true" },
        el("h2", {}, "Create a public fork?"),
        el("p", {}, `This copies ${row.fork.full_name} into your GitHub account${login ? ` (${login})` : ""} as a public fork of its default branch. Nothing is installed or run.`),
        lines);
      if (needsAccept) dialog.append(el("label", {}, box, " I have read the flagged items above and accept them."));
      if (!preview.ok && !needsAccept) dialog.append(el("p", { class: "err" }, preview.reason));
      dialog.append(el("div", { class: "buttons" }, cancel, ok));
      const overlay = el("div", { class: "overlay" }, dialog);
      document.body.append(overlay);
      (needsAccept ? box : cancel).focus();
    });
  }

  async function startFork(row) {
    row.forkError = null;
    const who = await chrome.runtime.sendMessage({ type: "whoami" });
    if (!who.ok) { row.forkError = who.error; return redraw(row); }
    const choice = await confirmFork(row, who.login);
    if (!choice) return;
    row.forkBusy = true; redraw(row);
    const res = await chrome.runtime.sendMessage({
      type: "fork-create", fork: row.fork.full_name, shownFingerprint: row.fingerprint, accept: choice.accept,
      ai: row.ai ? { verdict: row.ai.verdict, fingerprint: row.ai.fingerprint } : null,
    });
    row.forkBusy = false;
    if (res.ok) { row.forkedUrl = res.url; row.forkedName = res.name; } else row.forkError = res.error;
    redraw(row);
  }

  async function load(text) {
    const m = /^(?:https?:\/\/github\.com\/)?([\w.-]+)\/([\w.-]+?)(?:\.git)?(?:\/.*)?$/.exec(text.trim());
    if (!m) return void ($("status").textContent = "Type a repository like owner/name.");
    current = { owner: m[1], repo: m[2] };
    $("repo").value = `${m[1]}/${m[2]}`;
    $("list").replaceChildren();
    cards = new Map();
    $("status").textContent = "Loading forks...";
    await refreshCaps();
    Core.loadForks({ owner: m[1], repo: m[2], R, onRows: showRows, onStatus: (t) => ($("status").textContent = t) })
      .catch(() => ($("status").textContent = "Something went wrong reading GitHub."));
  }

  $("form").addEventListener("submit", (e) => { e.preventDefault(); load($("repo").value); });
  $("settings").addEventListener("click", () => chrome.runtime.openOptionsPage());
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshCaps(); });
  await refreshCaps();
  const start = new URLSearchParams(location.search).get("repo");
  if (start) load(start);
})();
