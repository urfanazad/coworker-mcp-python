const out = document.getElementById("out");
const rootInput = document.getElementById("root");
const filePathInput = document.getElementById("filePath");
const webUrlInput = document.getElementById("webUrl");
const docContent = document.getElementById("docContent");
const pyCodeInput = document.getElementById("pyCode");

let lastPlanJobId = null;

// Tab management
document.getElementById("tabFiles").onclick = () => {
  document.getElementById("viewFiles").style.display = "block";
  document.getElementById("viewWeb").style.display = "none";
  document.getElementById("tabFiles").className = "tab active";
  document.getElementById("tabWeb").className = "tab";
};
document.getElementById("tabWeb").onclick = () => {
  document.getElementById("viewFiles").style.display = "none";
  document.getElementById("viewWeb").style.display = "block";
  document.getElementById("tabFiles").className = "tab";
  document.getElementById("tabWeb").className = "tab active";
};

async function getOptions() {
  const opts = await chrome.storage.local.get(["allowed_roots"]);
  return { allowed_roots: opts.allowed_roots || [] };
}

async function submitJob(type, params, approval_token = null) {
  const { allowed_roots } = await getOptions();
  const body = {
    dedupe_key: `${type}:${Date.now()}:${Math.random()}`, // Non-deduping for UI convenience
    type,
    allowed_roots,
    params
  };
  if (approval_token) body.approval_token = approval_token;

  const r = await chrome.runtime.sendMessage({ type: "SUBMIT_JOB", body });
  if (!r.ok) throw new Error(r.error);
  return r.data.job_id;
}

async function poll(jobId) {
  out.textContent = "Working on job " + jobId + "...";
  for (let i = 0; i < 60; i++) {
    const r = await chrome.runtime.sendMessage({ type: "GET_JOB", job_id: jobId });
    if (!r.ok) throw new Error(r.error);
    const j = r.data;
    if (j.status === 3) return j; // SUCCEEDED
    if (j.status === 4) throw new Error("Job failed: " + (j.error_message || "Unknown error"));
    await new Promise(res => setTimeout(res, 800));
  }
  throw new Error("Timeout waiting for job.");
}

async function getResult(jobId) {
  const r = await chrome.runtime.sendMessage({ type: "GET_RESULT", job_id: jobId });
  if (!r.ok) throw new Error(r.error);
  return r.data;
}

async function runTool(type, params, approvalToken = null) {
  try {
    const jobId = await submitJob(type, params, approvalToken);
    await poll(jobId);
    const res = await getResult(jobId);
    if (res.content_type === "application/json") {
      out.textContent = JSON.stringify(JSON.parse(atob(res.bytes_base64)), null, 2);
    } else {
      out.textContent = atob(res.bytes_base64);
    }
    return jobId;
  } catch (e) {
    out.textContent = "Error: " + e.message;
  }
}

// Event Listeners
document.getElementById("btnList").onclick = () => runTool(2, { root: rootInput.value });
document.getElementById("btnScan").onclick = () => runTool(1, { root: rootInput.value, hash_files: "false" });

document.getElementById("btnPlan").onclick = async () => {
  lastPlanJobId = await runTool(4, { root: rootInput.value, policy: "by_ext" });
};

document.getElementById("btnExecute").onclick = async () => {
  if (!lastPlanJobId) { out.textContent = "Submit a plan first."; return; }
  const approveResp = await chrome.runtime.sendMessage({
    type: "APPROVE",
    body: { plan_job_id: lastPlanJobId, ttl_seconds: 120 }
  });
  if (!approveResp.ok) { out.textContent = "Approval failed: " + approveResp.error; return; }
  await runTool(5, { plan_job_id: lastPlanJobId, workspace_root: rootInput.value }, approveResp.data.approval_token);
};

document.getElementById("btnRead").onclick = () => runTool(3, { path: filePathInput.value });

// New Tools
document.getElementById("btnBrowse").onclick = () => runTool(8, { url: webUrlInput.value });

document.getElementById("btnWord").onclick = () => {
  const path = filePathInput.value || (rootInput.value + "/document.docx");
  runTool(10, { path, content: docContent.value });
};

document.getElementById("btnPdf").onclick = () => {
  const path = filePathInput.value || (rootInput.value + "/document.pdf");
  runTool(11, { path, content: docContent.value });
};

document.getElementById("btnPy").onclick = () => runTool(12, { code: pyCodeInput.value });

document.getElementById("btnListen").onclick = () => {
  const duration = document.getElementById("recSecs").value || 10;
  runTool(15, { duration });
};
