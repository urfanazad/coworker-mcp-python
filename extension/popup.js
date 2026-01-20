const out = document.getElementById("out");
const rootInput = document.getElementById("root");
const filePathInput = document.getElementById("filePath");

let lastPlanJobId = null;

async function getOptions() {
  const opts = await chrome.storage.local.get(["allowed_roots"]);
  return { allowed_roots: opts.allowed_roots || [] };
}

async function submitJob(type, params, approval_token = null) {
  const { allowed_roots } = await getOptions();
  const body = {
    dedupe_key: `${type}:${JSON.stringify(params)}:${allowed_roots.join(",")}:${approval_token ? "w" : "r"}`,
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
  for (let i = 0; i < 60; i++) {
    const r = await chrome.runtime.sendMessage({ type: "GET_JOB", job_id: jobId });
    if (!r.ok) throw new Error(r.error);
    const j = r.data;
    if (j.status === 3 || j.status === 4) return j; // SUCCEEDED/FAILED
    await new Promise(res => setTimeout(res, 500));
  }
  throw new Error("Timeout waiting for job");
}

async function getResult(jobId) {
  const r = await chrome.runtime.sendMessage({ type: "GET_RESULT", job_id: jobId });
  if (!r.ok) throw new Error(r.error);
  return r.data;
}

document.getElementById("btnList").onclick = async () => {
  try {
    const root = rootInput.value.trim();
    const jobId = await submitJob(2, { root });
    const job = await poll(jobId);
    const res = await getResult(jobId);
    out.textContent = JSON.stringify({ job, result: res }, null, 2);
  } catch (e) { out.textContent = String(e); }
};

document.getElementById("btnScan").onclick = async () => {
  try {
    const root = rootInput.value.trim();
    const jobId = await submitJob(1, { root, hash_files: "false" });
    const job = await poll(jobId);
    const res = await getResult(jobId);
    out.textContent = JSON.stringify({ job, result: res }, null, 2);
  } catch (e) { out.textContent = String(e); }
};

document.getElementById("btnPlan").onclick = async () => {
  try {
    const root = rootInput.value.trim();
    const jobId = await submitJob(4, { root, policy: "by_ext" });
    lastPlanJobId = jobId;
    const job = await poll(jobId);
    const res = await getResult(jobId);
    out.textContent = JSON.stringify({ lastPlanJobId, job, result: res }, null, 2);
  } catch (e) { out.textContent = String(e); }
};

document.getElementById("btnExecute").onclick = async () => {
  try {
    if (!lastPlanJobId) throw new Error("Run 'Propose organize plan' first.");

    const approveResp = await chrome.runtime.sendMessage({
      type: "APPROVE",
      body: { plan_job_id: lastPlanJobId, ttl_seconds: 120 }
    });
    if (!approveResp.ok) throw new Error(approveResp.error);

    const approval_token = approveResp.data.approval_token;
    const root = rootInput.value.trim();

    const execJobId = await submitJob(
      5,
      { plan_job_id: lastPlanJobId, workspace_root: root },
      approval_token
    );

    const job = await poll(execJobId);
    const res = await getResult(execJobId);
    out.textContent = JSON.stringify({ approved: approveResp.data, execJobId, job, result: res }, null, 2);
  } catch (e) { out.textContent = String(e); }
};

document.getElementById("btnRead").onclick = async () => {
  try {
    const path = filePathInput.value.trim();
    const jobId = await submitJob(3, { path, max_bytes: "1000000" });
    const job = await poll(jobId);
    const res = await getResult(jobId);
    out.textContent = JSON.stringify({ job, result: res }, null, 2);
  } catch (e) { out.textContent = String(e); }
};
