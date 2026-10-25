/* fork-scout page UI: a button on GitHub repo pages that opens a short ranked list of the repo's forks, each with a safety scan.
 * The full results page (AI review, forking) opens in its own tab. Everything that comes from a fork (names, commit titles,
 * file names) is inserted as plain text, never as HTML. */
(function () {
  const Scan = self.ForkScoutScan;
  const Core = self.ForkScoutCore;
  let R = null;
  let host = null;
  let lastHref = "";

  const el = (tag, props = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) (k === "class" ? (n.className = v) : n.setAttribute(k, v));
    for (const k of kids) n.append(k);
    return n;
  };

  function repoOnThisPage() {
    const meta = document.querySelector('meta[name="octolytics-dimension-repository_nwo"]');
    const parts = location.pathname.split("/").filter(Boolean);
    if (!meta || parts.length !== 2 || meta.content.toLowerCase() !== parts.join("/").toLowerCase()) return null;
    return { owner: parts[0], repo: parts[1] };
  }

  const CSS = `
    :host { all: initial; }
    * { box-sizing: border-box; font-family: system-ui, sans-serif; }
    .btn { position: fixed; right: 16px; bottom: 16px; z-index: 2147483000; padding: 10px 14px; border-radius: 999px; border: 1px solid #1f6feb; background: #1f6feb; color: #fff; font-size: 14px; cursor: pointer; box-shadow: 0 4px 14px rgba(0,0,0,.3); }
    .panel { position: fixed; right: 16px; bottom: 64px; z-index: 2147483000; width: min(720px, calc(100vw - 32px)); max-height: 75vh; overflow: auto; border-radius: 10px; border: 1px solid #d1d9e0; background: #fff; color: #1f2328; padding: 14px 16px; box-shadow: 0 8px 30px rgba(0,0,0,.35); font-size: 14px; line-height: 1.45; }
    @media (prefers-color-scheme: dark) { .panel { background: #0d1117; color: #e6edf3; border-color: #3d444d; } .muted { color: #9198a1 !important; } .row { border-color: #3d444d !important; } }
    h2 { margin: 0 0 4px; font-size: 16px; } .muted { color: #59636e; font-size: 13px; }
    .top { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
    .open { border: 1px solid #1f6feb; background: transparent; color: #1f6feb; border-radius: 6px; padding: 4px 10px; cursor: pointer; font-size: 13px; }
    .row { border-top: 1px solid #d1d9e0; padding: 10px 0; } .head { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
    a { color: #0969da; } .badge { padding: 1px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; }
    .ok { background: #dafbe1; color: #116329; } .check { background: #fff8c5; color: #7d4e00; } .bad { background: #ffebe9; color: #a40e26; }
    ul { margin: 4px 0 0 18px; padding: 0; } details summary { cursor: pointer; }
    .note { margin-top: 10px; padding-top: 8px; border-top: 1px solid #d1d9e0; }
  `;

  function badge(verdict) {
    const [cls, text] = verdict === "DO NOT FORK" ? ["bad", "Serious flags"]
      : verdict === "REVIEW BEFORE FORKING" ? ["check", "Check before copying"] : ["ok", "No red flags found"];
    return el("span", { class: `badge ${cls}` }, text);
  }

  function renderRow(r) {
    const a = el("a", { href: r.fork.html_url, target: "_blank", rel: "noopener noreferrer" });
    a.textContent = r.fork.full_name;
    const head = el("div", { class: "head" }, a, badge(r.scan.verdict),
      el("span", { class: "muted" }, `${r.fork.stargazers_count} stars · ${r.daysIdle} days since last push · ${r.cmp.ahead_by} ahead, ${r.cmp.behind_by} behind`));
    const list = el("ul");
    r.cmp.titles.slice(0, 3).forEach((x) => list.append(el("li", {}, x)));
    const row = el("div", { class: "row" }, head,
      el("div", { class: "muted" }, `Changes ${r.cmp.files.length}${r.cmp.fileListCut ? "+" : ""} files. Latest commits:`), list);
    const flags = r.scan.findings.filter((f) => f[0] !== "LOW").slice(0, 8);
    if (flags.length || Object.keys(r.scan.domains).length) {
      const d = el("details", {}, el("summary", {}, `${r.scan.counts.HIGH} serious, ${r.scan.counts.MEDIUM} to check, ${r.scan.counts.LOW} minor`));
      const ul = el("ul");
      flags.forEach(([sev, label, file, line]) => ul.append(el("li", {}, `${sev}: ${label} in ${file}${line ? ":" + line : ""}`)));
      Object.keys(r.scan.domains).slice(0, 5).forEach((dom) => ul.append(el("li", {}, `New web address: ${dom}`)));
      d.append(ul);
      row.append(d);
    }
    return row;
  }

  function mount(target) {
    host = el("div", { id: "fork-scout-host" });
    const root = host.attachShadow({ mode: "open" });
    const style = el("style");
    style.textContent = CSS;
    const btn = el("button", { class: "btn" }, "Forks worth copying");
    let panel = null;
    btn.addEventListener("click", () => {
      if (panel) { panel.remove(); panel = null; return; }
      const body = el("div");
      const status = el("div", { class: "muted" }, "Loading forks...");
      const open = el("button", { class: "open" }, "Open full results");
      open.addEventListener("click", () => chrome.runtime.sendMessage({ type: "open-results", repo: `${target.owner}/${target.repo}` }));
      panel = el("div", { class: "panel" },
        el("div", { class: "top" }, el("h2", {}, `Forks of ${target.owner}/${target.repo}`), open), status, body,
        el("div", { class: "note muted" }, "Pattern scan only, no AI review. A clean result means no red flags found, not that a fork is safe. Nothing from a fork is run. AI review and forking are on the full results page."));
      root.append(panel);
      Core.loadForks({
        owner: target.owner, repo: target.repo, R,
        onRows: (rows) => body.replaceChildren(...rows.map(renderRow)),
        onStatus: (t) => (status.textContent = t),
      }).catch(() => (status.textContent = "Something went wrong reading GitHub."));
    });
    root.append(style, btn);
    document.documentElement.append(host);
  }

  async function refresh() {
    if (location.href === lastHref) return;
    lastHref = location.href;
    host?.remove();
    host = null;
    const target = repoOnThisPage();
    if (!target) return;
    if (!R) R = Scan.prepare(await (await fetch(chrome.runtime.getURL("rules.json"))).json());
    mount(target);
  }

  refresh();
  setInterval(refresh, 800); // GitHub swaps pages without a reload, so watch the address
})();
