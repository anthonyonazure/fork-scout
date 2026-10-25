/* Shared by the GitHub page panel and the full results page: asks GitHub (through the background worker),
 * compares each recent fork with the original, scans what changed, and ranks the results. */
(function (root) {
  const Scan = root.ForkScoutScan;
  const MAX_FORKS = 12;

  const ask = (path) => chrome.runtime.sendMessage({ type: "github-get", path });
  const daysSince = (iso) => Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);

  function makeRow(R, fork, cmp) {
    const files = cmp.files || [];
    const scan = Scan.scanCompare(R, files);
    const daysIdle = daysSince(fork.pushed_at);
    const tier = Scan.tier({ daysIdle, behind: cmp.behind_by, filesTotal: files.length, files: files.map((f) => f.filename) });
    return {
      fork, scan, tier, daysIdle,
      fingerprint: Scan.fingerprint(cmp),
      cmp: {
        ahead_by: cmp.ahead_by, behind_by: cmp.behind_by,
        files: files.map((f) => ({ filename: f.filename, status: f.status, changes: f.changes, patch: f.patch })),
        fileListCut: files.length >= R.fileCap,
        titles: (cmp.commits || []).slice(-20).reverse().map((c) => c.commit.message.split("\n")[0].slice(0, 100)),
      },
    };
  }

  const byRank = (a, b) => a.tier - b.tier || a.daysIdle - b.daysIdle;

  /** Loads and scans the most recently active forks. Calls onRow(rows) as results arrive and onStatus(text) for messages. */
  async function loadForks({ owner, repo, R, onRows, onStatus, limit = MAX_FORKS }) {
    const info = await ask(`/repos/${owner}/${repo}`);
    if (!info.ok) return void onStatus(info.error);
    const base = info.data.default_branch;
    const list = await ask(`/repos/${owner}/${repo}/forks?sort=stargazers&per_page=100`);
    if (!list.ok) return void onStatus(list.error);
    const forks = list.data.filter((f) => new Date(f.pushed_at) > new Date(f.created_at))
      .sort((a, b) => new Date(b.pushed_at) - new Date(a.pushed_at)).slice(0, limit);
    if (!forks.length) return void onStatus("No fork has changes of its own yet.");
    const rows = [];
    let done = 0;
    const queue = [...forks];
    const report = () => {
      rows.sort(byRank);
      onRows(rows);
      onStatus(`Looked at ${done} of ${forks.length} recent forks (${list.data.length} listed). Favours recent, close to the original, real code over stars.`);
    };
    const worker = async () => {
      while (queue.length) {
        const f = queue.shift();
        const c = await ask(`/repos/${owner}/${repo}/compare/${encodeURIComponent(base)}...${f.owner.login}:${encodeURIComponent(f.default_branch)}`);
        done++;
        if (!c.ok) { onStatus(c.error); if (c.rateLimited) queue.length = 0; continue; }
        if (c.data.ahead_by > 0) rows.push(makeRow(R, f, c.data));
        report();
      }
    };
    await Promise.all([worker(), worker(), worker()]);
    if (!rows.length) onStatus("None of the recent forks add anything beyond the original.");
  }

  root.ForkScoutCore = { ask, daysSince, loadForks, MAX_FORKS };
})(typeof self !== "undefined" ? self : this);
