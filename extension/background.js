/* The only part of the extension that talks to the network or holds keys.
 * - GitHub reads are limited to the address shapes in policy.js.
 * - The one GitHub write (forking) and the AI call are accepted only from this extension's own pages, never from a GitHub page.
 * - Keys never leave this file: pages ask for an action and get a result back. */
importScripts("scanlib.js", "policy.js", "review.js");

const Scan = self.ForkScoutScan;
const Policy = self.ForkScoutPolicy;
const Review = self.ForkScoutReview;

let rulesPromise = null;
const rules = () => (rulesPromise ||= fetch(chrome.runtime.getURL("rules.json")).then((r) => r.json()).then(Scan.prepare));

async function github(path, { method = "GET", body, write = false } = {}) {
  const { githubToken, githubWriteToken } = await chrome.storage.local.get(["githubToken", "githubWriteToken"]);
  const token = write ? githubWriteToken : githubToken;
  if (write && !token) return { ok: false, error: "Add a GitHub token that can create forks in the extension settings first." };
  const headers = { Accept: "application/vnd.github+json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(`https://api.github.com${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  } catch (e) {
    return { ok: false, error: "Could not reach GitHub. Check your connection." };
  }
  if ((res.status === 403 || res.status === 429) && res.headers.get("x-ratelimit-remaining") === "0") {
    const reset = Number(res.headers.get("x-ratelimit-reset")) * 1000;
    const mins = reset ? Math.max(1, Math.ceil((reset - Date.now()) / 60000)) : null;
    return {
      ok: false, rateLimited: true,
      error: `GitHub's hourly limit is used up${mins ? `; it resets in about ${mins} minutes` : ""}. Add a read-only GitHub token in the extension settings to raise the limit.`,
    };
  }
  if (res.status === 401) return { ok: false, error: "GitHub rejected the token. Check it in the extension settings." };
  if (!res.ok) return { ok: false, error: `GitHub answered ${res.status}.` };
  return { ok: true, data: await res.json(), remaining: res.headers.get("x-ratelimit-remaining") };
}

async function aiReview(msg) {
  const { anthropicKey, aiModel } = await chrome.storage.local.get(["anthropicKey", "aiModel"]);
  if (!anthropicKey) return { ok: false, error: "No AI key is set. Add one in the extension settings." };
  const model = Policy.modelOrDefault(aiModel);
  const built = Review.buildReviewInput({ forkName: msg.fork, upstream: msg.upstream, cmp: msg.cmp, scan: msg.scan });
  // The API treats any request from a browser extension as a browser request and refuses it without the last header.
  // The key is the user's own, stored only in this browser, which is the case the header exists to acknowledge.
  const headers = {
    "content-type": "application/json", "x-api-key": anthropicKey, "anthropic-version": "2023-06-01",
    "anthropic-dangerous-direct-browser-access": "true",
  };
  const body = {
    model, max_tokens: 16000, output_config: { effort: "medium" },
    system: Review.SYSTEM, messages: [{ role: "user", content: built.text }],
  };
  // A safety filter can decline security work. Where the platform supports it, let it retry on a recommended model.
  if (Policy.MODELS.find((m) => m.id === model).fallback) { headers["anthropic-beta"] = "server-side-fallback-2026-07-01"; body.fallbacks = "default"; }
  let res;
  try {
    res = await fetch("https://api.anthropic.com/v1/messages", { method: "POST", headers, body: JSON.stringify(body) });
  } catch (e) {
    return { ok: false, error: "Could not reach the AI service. Check your connection." };
  }
  if (res.status === 401 || res.status === 403) {
    const why = await res.json().then((j) => (j && j.error && j.error.message) || "", () => "");
    return { ok: false, error: `The AI service refused the request (${res.status}). ${String(why).slice(0, 200)} Check the key in the extension settings.`.replace("  ", " ") };
  }
  if (res.status === 429) return { ok: false, error: "The AI service is rate limiting this key. Try again in a minute." };
  if (!res.ok) return { ok: false, error: `The AI service answered ${res.status}.` };
  const data = await res.json();
  if (data.stop_reason === "refusal") return { ok: false, error: "The AI declined to review this code (its safety filter). Treat this fork as having no AI review." };
  if (data.stop_reason === "max_tokens") return { ok: false, error: "The AI ran out of room before finishing. Try again." };
  const text = (data.content || []).filter((b) => b.type === "text").map((b) => b.text).join("");
  const parsed = Review.parseReview(text, built.truncated);
  if (!parsed.ok) return parsed;
  return { ok: true, review: { ...parsed.review, fingerprint: msg.fingerprint, model: data.model || model } };
}

/** Re-checks everything fresh, then forks. The page's own view is only used to detect that the fork has moved. */
async function forkCreate(msg) {
  if (typeof msg.fork !== "string" || !/^[\w.-]+\/[\w.-]+$/.test(msg.fork)) return { ok: false, error: "Not a repository name." };
  const R = await rules();
  const info = await github(`/repos/${msg.fork}`);
  if (!info.ok) return info;
  const upstream = info.data.parent && info.data.parent.full_name;
  if (!upstream) return { ok: false, error: "That repository is not a fork of anything, so there is nothing to compare." };
  const up = await github(`/repos/${upstream}`);
  if (!up.ok) return up;
  const branch = info.data.default_branch;
  const cmp = await github(`/repos/${upstream}/compare/${encodeURIComponent(up.data.default_branch)}...${info.data.owner.login}:${encodeURIComponent(branch)}`);
  if (!cmp.ok) return cmp;
  const scan = Scan.scanCompare(R, cmp.data.files || []);
  const verdict = Scan.gate({
    scan, ai: msg.ai || null, shownFingerprint: msg.shownFingerprint, nowFingerprint: Scan.fingerprint(cmp.data), accept: msg.accept === true,
  });
  if (!verdict.ok) return { ok: false, error: verdict.reason, needsAccept: !!verdict.needsAccept };
  const path = `/repos/${msg.fork}/forks`;
  if (!Policy.isForkPath(path)) return { ok: false, error: "That request is not allowed." };
  const made = await github(path, { method: "POST", body: { default_branch_only: true }, write: true });
  if (!made.ok) return made;
  return { ok: true, url: made.data.html_url, name: made.data.full_name };
}

const fromOwnPage = (sender) => !!sender.url && sender.url.startsWith(chrome.runtime.getURL(""));

const handlers = {
  async "github-get"(msg) {
    return Policy.isAllowedGet(msg.path) ? github(msg.path) : { ok: false, error: "That request is not allowed." };
  },
  async "open-results"(msg) {
    const q = typeof msg.repo === "string" && /^[\w.-]+\/[\w.-]+$/.test(msg.repo) ? `?repo=${encodeURIComponent(msg.repo)}` : "";
    await chrome.tabs.create({ url: chrome.runtime.getURL(`results.html${q}`) });
    return { ok: true };
  },
  async "capabilities"() {
    const s = await chrome.storage.local.get(["githubWriteToken", "anthropicKey", "aiModel"]);
    return { ok: true, canFork: !!s.githubWriteToken, aiOn: !!s.anthropicKey, model: Policy.modelOrDefault(s.aiModel) };
  },
  async "whoami"() {
    const r = await github("/user", { write: true });
    return r.ok ? { ok: true, login: r.data.login } : r;
  },
  "ai-review": aiReview,
  "fork-create": forkCreate,
};
const OWN_PAGE_ONLY = new Set(["capabilities", "whoami", "ai-review", "fork-create"]);

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || sender.id !== chrome.runtime.id || !Object.hasOwn(handlers, msg.type)) return false;
  if (OWN_PAGE_ONLY.has(msg.type) && !fromOwnPage(sender)) {
    sendResponse({ ok: false, error: "Not allowed from this page." });
    return false;
  }
  handlers[msg.type](msg).then(sendResponse, () => sendResponse({ ok: false, error: "Something went wrong." }));
  return true;
});

chrome.action.onClicked.addListener(async (tab) => {
  const m = /^https:\/\/github\.com\/([\w.-]+)\/([\w.-]+?)(?:\/|$)/.exec(tab.url || "");
  await handlers["open-results"]({ repo: m ? `${m[1]}/${m[2]}` : null });
});
