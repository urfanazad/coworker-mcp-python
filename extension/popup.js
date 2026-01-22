const out = document.getElementById("out");
const overlay = document.getElementById("overlay");
const timerEl = document.getElementById("timer");
const toggleBtn = document.getElementById("btnToggle");
const toggleText = document.getElementById("toggleText");
const eyeIcon = document.getElementById("eyeIcon");
const micBtn = document.getElementById("btnListen");

// --- State Management ---
const state = {
  isListening: false,
  isHidden: false,
  liveText: "",
  aiContent: "",
  status: "Ready",
  silentCount: 0
};

// --- Rendering ---
function renderApp() {
  // 1. Update Buttons
  if (state.isListening) {
    micBtn.style.background = "#ef4444";
    micBtn.style.boxShadow = "0 0 35px rgba(239, 68, 68, 0.6)";
  } else {
    micBtn.style.background = "var(--accent)";
    micBtn.style.boxShadow = "0 0 25px var(--accent-glow)";
  }

  // 2. Update Content
  if (state.isHidden) {
    out.classList.add('hidden');
    toggleText.textContent = 'SHOW';
    eyeIcon.innerHTML = '<path d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/>';
  } else {
    out.classList.remove('hidden');
    toggleText.textContent = 'HIDE';
    eyeIcon.innerHTML = '<path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/>';
  }

  let html = "";

  // Status Header
  if (state.isListening) {
    html += `<div style="color:var(--accent); font-weight:600; margin-bottom:10px;">🔴 Auto-Pilot Engaged <span style="font-weight:400; color:var(--text-dim); font-size:12px;">(${state.status})</span></div>`;
  } else {
    html += `<div style="color:var(--text-dim); font-size:13px; margin-bottom:10px;">Ready to assist.</div>`;
  }

  // Live Buffer (what is currently being heard)
  if (state.liveText) {
    html += `<div style="margin-bottom: 20px; border-left: 3px solid var(--accent); padding-left: 10px; background: rgba(56, 189, 248, 0.05); padding: 8px; border-radius: 0 8px 8px 0;">
                  <div style="color:var(--accent); font-size: 10px; text-transform: uppercase; letter-spacing: 1px; margin-bottom:4px;">Live Audio Buffer</div>
                  <div style="color: var(--text); font-style: italic;">"${state.liveText}"</div>
               </div>`;
  }

  // Main AI Content
  if (state.aiContent) {
    html += state.aiContent;
  } else if (!state.liveText) {
    html += `<div style="color:var(--text-dim); text-align: center; margin-top: 40px; opacity: 0.5;">
          Click the mic to start Auto-Pilot
      </div>`;
  }

  out.innerHTML = html;
}

// Toggle Visibility Handler
toggleBtn.onclick = () => {
  state.isHidden = !state.isHidden;
  renderApp();
};

async function getOptions() {
  const opts = await chrome.storage.local.get(["allowed_roots"]);
  return { allowed_roots: opts.allowed_roots || [] };
}

async function submitJob(type, params) {
  const { allowed_roots } = await getOptions();
  const body = {
    dedupe_key: `job_${Date.now()}_${Math.random()}`,
    type,
    allowed_roots,
    params
  };

  const r = await chrome.runtime.sendMessage({ type: "SUBMIT_JOB", body });
  if (!r.ok) throw new Error(r.error);
  return r.data.job_id;
}

async function poll(jobId) {
  for (let i = 0; i < 150; i++) {
    const r = await chrome.runtime.sendMessage({ type: "GET_JOB", job_id: jobId });
    if (!r.ok) throw new Error(r.error);
    const j = r.data;
    if (j.status === 3) return j;
    if (j.status === 4) throw new Error(j.error_message || "Processing failed");
    await new Promise(res => setTimeout(res, 200)); // Standard poll 200ms
  }
  throw new Error("Job timed out.");
}

async function getResult(jobId) {
  const r = await chrome.runtime.sendMessage({ type: "GET_RESULT", job_id: jobId });
  if (!r.ok) throw new Error(r.error);
  return r.data;
}

function decodeUTF8(base64) {
  const binaryString = atob(base64);
  const bytes = new Uint8Array(binaryString.length);
  for (let i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return new TextDecoder().decode(bytes);
}

function isValidTranscript(text) {
  // Filter out gibberish/low quality transcripts
  if (!text || text.length < 5) return false;
  if (text.includes("No speech detected")) return false;
  if (text.includes("Error")) return false;

  // Check if it's mostly single characters or nonsense
  const words = text.split(/\s+/);
  if (words.length < 2) return false;

  return true;
}

// --- Core Logic ---

// --- Time Tracker Helper ---
function formatDuration(ms) {
  return (ms / 1000).toFixed(1) + "s";
}

async function processAudioChunk() {
  const duration = 3;
  const tStart = Date.now();

  try {
    state.status = "Listening...";
    renderApp();

    const jobId = await submitJob(15, { duration: String(duration) });

    state.status = "Processing Audio...";
    renderApp();

    await poll(jobId);

    const tEnd = Date.now();
    const cycleTime = tEnd - tStart;

    const res = await getResult(jobId);
    let text = decodeUTF8(res.bytes_base64);

    const match = text.match(/Transcript \(\d+s\): (.+)/);
    if (match && match[1]) {
      const transcriptChunk = match[1];

      // Skip heavy validation for speed - just check length
      if (transcriptChunk.length < 3 || transcriptChunk.includes("No speech")) {
        state.silentCount++;
        state.status = `Silence (${formatDuration(cycleTime)})`;
        renderApp();
        return false;
      }

      state.silentCount = 0;
      state.liveText += (state.liveText ? " " : "") + transcriptChunk;
      state.status = `Received (${formatDuration(cycleTime)})`;
      renderApp();
      return true;
    }
  } catch (e) {
    console.error("Audio chunk error", e);
    // Show actual error to help user debug
    state.status = "Error: " + (e.message || "Unknown");
    renderApp();

    // If error, wait a bit so we don't spam
    await new Promise(r => setTimeout(r, 1000));
  }
  return false;
}

async function runAutoPilot() {
  while (state.isListening) {
    // Run audio processing
    const gotSpeech = await processAudioChunk();

    // Check triggers for analysis
    const wordCount = state.liveText.split(/\s+/).length;
    const shouldAnalyze = state.isListening && (wordCount >= 20 || (state.silentCount >= 1 && wordCount > 5));

    if (shouldAnalyze) {
      // ⚡ FIRE AND FORGET - Do not await!
      // Let analysis happen in background while we keep listening
      state.status = "🧠 Analyzing (Background)...";
      renderApp();

      // Capture current text snapshot for analysis
      const textToAnalyze = state.liveText;
      state.liveText = ""; // Reset buffer immediately so we can capture new speech

      analyzeText(textToAnalyze).then(() => {
        // specific callback if needed, but analyzeText updates UI directly
        console.log("Analysis finished for:", textToAnalyze.substring(0, 10) + "...");
      });
    }

    if (!state.isListening) break;
    // Minimal pause to yield back to event loop
    await new Promise(r => setTimeout(r, 100));
  }
}

async function analyzeText(text) {
  const tStart = Date.now();
  try {
    const jobId = await submitJob(16, { transcript: text });
    await poll(jobId);
    const res = await getResult(jobId);
    const rawAI = decodeUTF8(res.bytes_base64);

    const tEnd = Date.now();
    const aiTime = tEnd - tStart;

    const formatted = rawAI
      .replace(/STRATEGIC INSIGHT:/g, '<br><strong style="color:#a855f7">🧠 STRATEGIC INSIGHT:</strong>')
      .replace(/POWER QUESTIONS:/g, '<br><br><strong style="color:#ec4899">❓ POWER QUESTIONS:</strong>')
      .replace(/PERFECT RESPONSE:/g, '<br><br><strong style="color:#22c55e">💬 PERFECT RESPONSE:</strong>')
      .replace(/•/g, '<br>&nbsp;&nbsp;•');

    state.aiContent = formatted;
    state.status = `Analysis Complete (${formatDuration(aiTime)})`;
    renderApp();

  } catch (e) {
    console.error("Analysis Error", e);
    state.status = "AI Error: " + e.message;
    renderApp();
  }
}

// --- Event Listeners ---

micBtn.onclick = () => {
  state.isListening = !state.isListening;

  if (state.isListening) {
    state.silentCount = 0;
    state.liveText = "";

    // Auto-show if hidden
    if (state.isHidden) {
      state.isHidden = false;
    }

    renderApp();
    runAutoPilot();
  } else {
    state.status = "Stopped";
    renderApp();
  }
};

document.getElementById("btnOptions").onclick = () => chrome.runtime.openOptionsPage();
document.getElementById("btnStop").onclick = () => micBtn.click(); // Reuse toggle

// Initial Render
renderApp();
