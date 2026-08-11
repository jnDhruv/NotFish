// Background service worker: runs the check whenever the active tab navigates,
// calls the backend, and updates the toolbar badge color/text with the verdict.
//
// NOTE ON SCOPE: this MVP calls the backend on every navigation for simplicity
// and to make the demo obvious. The documented production design adds a Tier 1
// local list check in front of this (see README) so most page loads resolve
// instantly without a network call at all. Wiring that in is a small addition
// once this end-to-end flow is working.

const BACKEND_URL = "http://127.0.0.1:8000/check";

// Simple in-memory cache so repeat visits in the same browser session don't
// re-hit the backend every time (a lightweight stand-in for Tier 2 caching).
const verdictCache = {};

function extractDomain(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch (e) {
    return null;
  }
}

async function checkDomain(domain) {
  if (verdictCache[domain]) {
    return verdictCache[domain];
  }
  try {
    const response = await fetch(`${BACKEND_URL}?domain=${encodeURIComponent(domain)}`);
    if (!response.ok) throw new Error(`Backend returned ${response.status}`);
    const data = await response.json();
    verdictCache[domain] = data;
    return data;
  } catch (err) {
    console.error("Phishing check failed:", err);
    return null;
  }
}

function updateBadge(tabId, result) {
  if (!result) {
    chrome.action.setBadgeText({ tabId, text: "?" });
    chrome.action.setBadgeBackgroundColor({ tabId, color: "#888888" });
    return;
  }

  let color, text;
  if (result.verdict === "phishing_suspected") {
    color = "#D32F2F"; // red
    text = "!";
  } else if (result.verdict === "suspicious") {
    color = "#F9A825"; // yellow
    text = "?";
  } else {
    color = "#2E7D32"; // green
    text = "✓";
  }

  chrome.action.setBadgeText({ tabId, text });
  chrome.action.setBadgeBackgroundColor({ tabId, color });
}

async function handleTabUpdate(tabId, url) {
  const domain = extractDomain(url);
  if (!domain || url.startsWith("chrome://") || url.startsWith("about:")) return;

  chrome.action.setBadgeText({ tabId, text: "…" });
  chrome.action.setBadgeBackgroundColor({ tabId, color: "#888888" });

  const result = await checkDomain(domain);
  // store the latest result for this tab so the popup can read it
  chrome.storage.session.set({ [`tab_${tabId}`]: result });
  updateBadge(tabId, result);
}

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "loading" && tab.url) {
    handleTabUpdate(tabId, tab.url);
  }
});

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  const tab = await chrome.tabs.get(tabId);
  if (tab.url) handleTabUpdate(tabId, tab.url);
});
