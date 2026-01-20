const rootsEl = document.getElementById("roots");
const statusEl = document.getElementById("status");

async function load() {
  const { allowed_roots } = await chrome.storage.local.get(["allowed_roots"]);
  rootsEl.value = (allowed_roots || []).join("\n");
}
load();

document.getElementById("save").onclick = async () => {
  const roots = rootsEl.value.split("\n").map(s => s.trim()).filter(Boolean);
  await chrome.storage.local.set({ allowed_roots: roots });
  statusEl.textContent = "Saved.";
};
