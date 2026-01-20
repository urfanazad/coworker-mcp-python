const API = "http://127.0.0.1:8765";

async function ensureSession() {
  const data = await chrome.storage.local.get(["session_id", "token"]);
  if (data.session_id && data.token) return data;

  const r = await fetch(`${API}/handshake`, { method: "POST" });
  if (!r.ok) throw new Error("Handshake failed");
  const j = await r.json();
  await chrome.storage.local.set({ session_id: j.session_id, token: j.token });
  return j;
}

async function apiFetch(path, options = {}) {
  const s = await ensureSession();
  const headers = Object.assign({}, options.headers || {}, {
    "X-Coworker-Session": s.session_id,
    "X-Coworker-Token": s.token,
    "Content-Type": "application/json"
  });
  return fetch(`${API}${path}`, { ...options, headers });
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    try {
      if (msg.type === "TOOLS") {
        const r = await apiFetch("/tools");
        sendResponse({ ok: true, data: await r.json() });
        return;
      }
      if (msg.type === "SUBMIT_JOB") {
        const r = await apiFetch("/jobs", { method: "POST", body: JSON.stringify(msg.body) });
        sendResponse({ ok: true, data: await r.json() });
        return;
      }
      if (msg.type === "GET_JOB") {
        const r = await apiFetch(`/jobs/${msg.job_id}`);
        sendResponse({ ok: true, data: await r.json() });
        return;
      }
      if (msg.type === "GET_RESULT") {
        const r = await apiFetch(`/jobs/${msg.job_id}/result`);
        sendResponse({ ok: true, data: await r.json() });
        return;
      }
      if (msg.type === "APPROVE") {
        const r = await apiFetch("/approve", { method: "POST", body: JSON.stringify(msg.body) });
        sendResponse({ ok: true, data: await r.json() });
        return;
      }

      sendResponse({ ok: false, error: "Unknown message type" });
    } catch (e) {
      sendResponse({ ok: false, error: String(e) });
    }
  })();
  return true;
});
