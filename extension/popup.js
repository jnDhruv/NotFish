// ---------------------------------------------------------------------
// Theme handling
// ---------------------------------------------------------------------
const SUN_ICON = `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="1.7"/>
  <path d="M12 2.5V4.5M12 19.5V21.5M4.22 4.22L5.64 5.64M18.36 18.36L19.78 19.78M2.5 12H4.5M19.5 12H21.5M4.22 19.78L5.64 18.36M18.36 5.64L19.78 4.22"
        stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>
</svg>`;

const MOON_ICON = `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a6.8 6.8 0 0 0 10.5 10.5Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>
</svg>`;

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const btn = document.getElementById("theme-toggle");
  btn.innerHTML = theme === "dark" ? SUN_ICON : MOON_ICON;
  btn.setAttribute("aria-label", theme === "dark" ? "Switch to light theme" : "Switch to dark theme");
}

async function initTheme() {
  let theme = "light";
  try {
    const stored = await chrome.storage.local.get("theme");
    if (stored.theme === "dark" || stored.theme === "light") {
      theme = stored.theme;
    } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      theme = "dark";
    }
  } catch (e) {
    // storage unavailable — fall back to light
  }
  applyTheme(theme);

  document.getElementById("theme-toggle").addEventListener("click", async () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    applyTheme(next);
    try {
      await chrome.storage.local.set({ theme: next });
    } catch (e) {
      // ignore — theme still applies for this session
    }
  });
}

// ---------------------------------------------------------------------
// Gauge (signature element): radial arc that fills to the score out of 100
// ---------------------------------------------------------------------
const GAUGE_RADIUS = 42;
const GAUGE_CIRCUMFERENCE = 2 * Math.PI * GAUGE_RADIUS;

function setGauge(score, colorVar) {
  const clamped = Math.max(0, Math.min(100, Number(score) || 0));
  const filled = (clamped / 100) * GAUGE_CIRCUMFERENCE;
  const progress = document.getElementById("gauge-progress");
  progress.style.strokeDasharray = `${filled} ${GAUGE_CIRCUMFERENCE}`;
  progress.style.stroke = colorVar;
  document.getElementById("gauge-score").textContent = Number.isFinite(score) ? Math.round(score) : "—";
}

// ---------------------------------------------------------------------
// Verdict presentation
// ---------------------------------------------------------------------
const VERDICT_CONFIG = {
  phishing_suspected: {
    pillClass: "phishing",
    pillLabel: "Phishing suspected",
    color: "var(--danger)",
    copy: "Multiple strong indicators of phishing were found on this domain. Avoid entering credentials or personal information."
  },
  suspicious: {
    pillClass: "suspicious",
    pillLabel: "Suspicious",
    color: "var(--warn)",
    copy: "Some indicators on this page are unusual. Double-check the address bar before entering any sensitive information."
  },
  safe: {
    pillClass: "safe",
    pillLabel: "Looks safe",
    color: "var(--safe)",
    copy: "No phishing indicators were detected for this domain."
  }
};

function renderResult(result) {
  const cfg = VERDICT_CONFIG[result.verdict] || {
    pillClass: "safe",
    pillLabel: "Looks safe",
    color: "var(--safe)",
    copy: "No phishing indicators were detected for this domain."
  };

  setGauge(result.final_score, cfg.color);

  const pill = document.getElementById("pill");
  pill.textContent = cfg.pillLabel;
  pill.className = `pill ${cfg.pillClass}`;

  document.getElementById("verdict-copy").textContent = cfg.copy;

  // Domain analysis section
  const prefilterSection = document.getElementById("prefilter-section");
  const prefilterReasons = document.getElementById("prefilter-reasons");
  const brandMatch = document.getElementById("brand-match");

  if (result.prefilter && (result.prefilter.reasons?.length || result.prefilter.matched_brand)) {
    prefilterSection.classList.remove("hidden");
    prefilterReasons.innerHTML = "";
    (result.prefilter.reasons || []).forEach((reason) => {
      const li = document.createElement("li");
      li.textContent = reason;
      prefilterReasons.appendChild(li);
    });
    if (result.prefilter.matched_brand) {
      brandMatch.classList.remove("hidden");
      brandMatch.innerHTML = `Closest brand match: <strong>${escapeHtml(result.prefilter.matched_brand)}</strong>`;
    } else {
      brandMatch.classList.add("hidden");
    }
  } else {
    prefilterSection.classList.add("hidden");
  }

  // Visual similarity section
  const visualSection = document.getElementById("visual-section");
  if (result.visual_analysis) {
    visualSection.classList.remove("hidden");
    const v = result.visual_analysis;
    document.getElementById("visual-figure").textContent = `${v.similarity_score}%`;
    document.getElementById("visual-caption").innerHTML =
      `visually similar to <strong>${escapeHtml(v.closest_match)}</strong>`;
  } else {
    visualSection.classList.add("hidden");
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = String(str);
  return div.innerHTML;
}

// ---------------------------------------------------------------------
// Main render
// ---------------------------------------------------------------------
async function render() {
  await initTheme();

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.id) return;

  const domainEl = document.getElementById("domain");
  let hostname = "";
  try {
    hostname = new URL(tab.url).hostname;
  } catch (e) {
    hostname = tab.url || "";
  }
  domainEl.textContent = hostname;
  domainEl.title = hostname;

  const stored = await chrome.storage.session.get(`tab_${tab.id}`);
  const result = stored[`tab_${tab.id}`];

  const resultView = document.getElementById("result-view");
  const emptyState = document.getElementById("empty-state");

  if (!result) {
    resultView.classList.add("hidden");
    emptyState.classList.remove("hidden");
    return;
  }

  resultView.classList.remove("hidden");
  emptyState.classList.add("hidden");
  renderResult(result);
}

render();
