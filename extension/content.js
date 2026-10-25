/* fork-scout page UI: a button on GitHub repo pages that opens a ranked list of the repo's forks, each with a safety scan.
 * Everything that comes from a fork (names, commit titles, file names) is inserted as plain text, never as HTML. */
(function () {
  const Scan = self.ForkScoutScan;
  const MAX_FORKS = 12;
  let R = null;
  let host = null;
  let lastHref = "";

  const el = (tag, props = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) (k === "class" ? (n.className = v) : n.setAttribute(k, v));
    for (const k of kids) n.append(k);
    return n;
  };

  const ask = (path) => chrome.runtime.sendMessage({ type: "github-get", path });
  const daysSince = (iso) => Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);

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

  function rowFor(fork, cmp) {
    const res = Scan.scanCompare(R, cmp.files || []);
    const daysIdle = daysSince(fork.pushed_at);
    const t = Scan.tier({ daysIdle, behind: cmp.behind_by, filesTotal: (cmp.files || []).length, files: (cmp.files || []).map((f) => f.filename) });
    const titles = (cmp.commits || []).slice(-3).reverse().map((c) => c.commit.message.split("\n")[0].slice(0, 100));
    const head = el("div", { class: "head" },
      Object.assign(el("a", { href: fork.html_url, target: "_blank", rel: "noopener noreferrer" }), { textContent: fork.full_name }),
      badge(res.verdict),
      el("span", { class: "muted" }, `${fork.stargazers_count} stars · ${daysIdle} days since last push · ${cmp.ahead_by} ahead, ${cmp.behind_by} behind`));
    const changed = el("div", { class: "muted" }, `Changes ${(cmp.files || []).length}${(cmp.files || []).length >= R.fileCap ? "+" : ""} files. Latest commits:`);
    const list = el("ul");
    titles.forEach((x) => list.append(el("li", {}, x)));
    const row = el("div", { class: "row" }, head, changed, list);
    const flags = res.findings.filter((f) => f[0] !== "LOW").slice(0, 8);
    if (flags.length || Object.keys(res.domains).length) {
      const d = el("details", {}, el("summary", {}, `${res.counts.HIGH} serious, ${res.counts.MEDIUM} to check, ${res.counts.LOW} minor`));
      const ul = el("ul");
      flags.forEach(([sev, label, file, line]) => ul.append(el("li", {}, `${sev}: ${label} in ${file}${line ? ":" + line : ""}`)));
      Object.keys(res.domains).slice(0, 5).forEach((dom) => ul.append(el("li", {}, `New web address: ${dom}`)));
      d.append(ul);
      row.append(d);
    }
    return { row, tier: t, daysIdle };
  }

  async function load(owner, repo, body, status) {
    const info = await ask(`/repos/${owner}/${repo}`);
    if (!info.ok) return void (status.textContent = info.error);
    const base = info.data.default_branch;
    const forksRes = await ask(`/repos/${owner}/${repo}/forks?sort=stargazers&per_page=100`);
    if (!forksRes.ok) return void (status.textContent = forksRes.error);
    const forks = forksRes.data.filter((f) => new Date(f.pushed_at) > new Date(f.created_at))
      .sort((a, b) => new Date(b.pushed_at) - new Date(a.pushed_at)).slice(0, MAX_FORKS);
    if (!forks.length) return void (status.textContent = "No fork has changes of its own yet.");
    const rows = [];
    let done = 0;
    const queue = [...forks];
    const render = () => {
      rows.sort((a, b) => a.tier - b.tier || a.daysIdle - b.daysIdle);
      body.replaceChildren(...rows.map((r) => r.row));
      status.textContent = `Looked at ${done} of ${forks.length} recent forks (${forksRes.data.length} listed). Favours recent, close to the original, real code over stars.`;
    };
    const worker = async () => {
      while (queue.length) {
        const f = queue.shift();
        const c = await ask(`/repos/${owner}/${repo}/compare/${encodeURIComponent(base)}...${f.owner.login}:${encodeURIComponent(f.default_branch)}`);
        done++;
        if (!c.ok) { status.textContent = c.error; if (c.rateLimited) queue.length = 0; continue; }
        if (c.data.ahead_by > 0) rows.push(rowFor(f, c.data));
        render();
      }
    };
    await Promise.all([worker(), worker(), worker()]);
    if (!rows.length) status.textContent = "None of the recent forks add anything beyond the original.";
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
      panel = el("div", { class: "panel" },
        el("h2", {}, `Forks of ${target.owner}/${target.repo}`), status, body,
        el("div", { class: "note muted" }, "Pattern scan only, no AI review. A clean result means no red flags found, not that a fork is safe. Nothing from a fork is run."));
      root.append(panel);
      load(target.owner, target.repo, body, status).catch(() => (status.textContent = "Something went wrong reading GitHub."));
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
