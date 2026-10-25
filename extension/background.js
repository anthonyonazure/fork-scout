/* Makes the GitHub calls for the page. Only read-only GET requests to api.github.com are allowed,
 * so a compromised page script cannot use this to write to a GitHub account. */
const ALLOWED = /^\/(repos\/[\w.-]+\/[\w.-]+(\/(forks|compare\/[^?]+))?|rate_limit)(\?[\w=&.-]*)?$/;

async function githubGet(path) {
  if (!ALLOWED.test(path)) return { ok: false, error: "That request is not allowed." };
  const { githubToken } = await chrome.storage.local.get("githubToken");
  const headers = { Accept: "application/vnd.github+json" };
  if (githubToken) headers.Authorization = `Bearer ${githubToken}`;
  let res;
  try {
    res = await fetch(`https://api.github.com${path}`, { headers });
  } catch (e) {
    return { ok: false, error: "Could not reach GitHub. Check your connection." };
  }
  if (res.status === 403 || res.status === 429) {
    const reset = Number(res.headers.get("x-ratelimit-reset")) * 1000;
    const mins = reset ? Math.max(1, Math.ceil((reset - Date.now()) / 60000)) : null;
    return {
      ok: false,
      rateLimited: true,
      error: `GitHub's hourly limit for anonymous use is used up${mins ? `; it resets in about ${mins} minutes` : ""}. Add a read-only GitHub token in the extension settings to raise the limit.`,
    };
  }
  if (!res.ok) return { ok: false, error: `GitHub answered ${res.status}.` };
  return { ok: true, data: await res.json(), remaining: res.headers.get("x-ratelimit-remaining") };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "github-get" && typeof msg.path === "string" && sender.id === chrome.runtime.id) {
    githubGet(msg.path).then(sendResponse);
    return true;
  }
  return false;
});
