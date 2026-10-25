/* What the extension is allowed to ask GitHub for, and which AI models it offers.
 * Kept in one small file so it can be tested and so a reader can audit every network request shape in one place. */
(function (root) {
  const NAME = "[\\w.-]+";
  const GET_RE = new RegExp(`^/(repos/${NAME}/${NAME}(/(forks|commits/[^?]+|compare/[^?]+))?|rate_limit)(\\?[\\w=&.-]*)?$`);
  const FORK_RE = new RegExp(`^/repos/${NAME}/${NAME}/forks$`);

  const noTraversal = (path) => !path.split("?")[0].split("/").includes("..");

  /** Read-only GitHub requests the page may ask for. */
  const isAllowedGet = (path) => typeof path === "string" && GET_RE.test(path) && noTraversal(path);
  /** The single write the extension can make: forking a repo into the token owner's account. */
  const isForkPath = (path) => typeof path === "string" && FORK_RE.test(path) && noTraversal(path);

  const MODELS = [
    { id: "claude-opus-5-5", label: "Claude Opus 5.5 (most capable)", fallback: true },
    { id: "claude-sonnet-5-5", label: "Claude Sonnet 5.5 (cheaper)", fallback: true },
    { id: "claude-haiku-5-5", label: "Claude Haiku 5.5 (cheapest)", fallback: false },
  ];
  const DEFAULT_MODEL = MODELS[0].id;
  const modelOrDefault = (id) => (MODELS.some((m) => m.id === id) ? id : DEFAULT_MODEL);

  const api = { isAllowedGet, isForkPath, MODELS, DEFAULT_MODEL, modelOrDefault };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ForkScoutPolicy = api;
})(typeof self !== "undefined" ? self : this);
