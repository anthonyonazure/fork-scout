const tokenBox = document.getElementById("token");
const saved = document.getElementById("saved");

chrome.storage.local.get("githubToken").then(({ githubToken }) => {
  if (githubToken) tokenBox.value = githubToken;
});

document.getElementById("save").addEventListener("click", async () => {
  const token = tokenBox.value.trim();
  if (token) await chrome.storage.local.set({ githubToken: token });
  else await chrome.storage.local.remove("githubToken");
  saved.textContent = "Saved";
  setTimeout(() => (saved.textContent = ""), 1500);
});
