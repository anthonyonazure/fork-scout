const FIELDS = { githubToken: "token", anthropicKey: "aikey", githubWriteToken: "writetoken" };
const model = document.getElementById("model");
const saved = document.getElementById("saved");

for (const m of self.ForkScoutPolicy.MODELS) model.append(Object.assign(document.createElement("option"), { value: m.id, textContent: m.label }));

chrome.storage.local.get([...Object.keys(FIELDS), "aiModel"]).then((s) => {
  for (const [key, id] of Object.entries(FIELDS)) if (s[key]) document.getElementById(id).value = s[key];
  model.value = self.ForkScoutPolicy.modelOrDefault(s.aiModel);
});

document.getElementById("save").addEventListener("click", async () => {
  for (const [key, id] of Object.entries(FIELDS)) {
    const v = document.getElementById(id).value.trim();
    if (v) await chrome.storage.local.set({ [key]: v });
    else await chrome.storage.local.remove(key);
  }
  await chrome.storage.local.set({ aiModel: model.value });
  saved.textContent = "Saved";
  setTimeout(() => (saved.textContent = ""), 1500);
});
