async function render() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.id) return;

  const domainEl = document.getElementById("domain");
  const bannerEl = document.getElementById("banner");
  const scoreEl = document.getElementById("score");
  const prefilterSection = document.getElementById("prefilter-section");
  const prefilterReasons = document.getElementById("prefilter-reasons");
  const visualSection = document.getElementById("visual-section");
  const visualDetails = document.getElementById("visual-details");

  let hostname = "";
  try {
    hostname = new URL(tab.url).hostname;
  } catch (e) {
    hostname = tab.url;
  }
  domainEl.textContent = hostname;

  const stored = await chrome.storage.session.get(`tab_${tab.id}`);
  const result = stored[`tab_${tab.id}`];

  if (!result) {
    bannerEl.textContent = "No data yet — reload the page to check it.";
    bannerEl.className = "verdict-banner unknown";
    return;
  }

  scoreEl.textContent = `${result.final_score}/100`;

  if (result.verdict === "phishing_suspected") {
    bannerEl.textContent = "⚠️ Likely phishing / lookalike site";
    bannerEl.className = "verdict-banner phishing";
  } else if (result.verdict === "suspicious") {
    bannerEl.textContent = "⚠️ Suspicious — proceed with caution";
    bannerEl.className = "verdict-banner suspicious";
  } else {
    bannerEl.textContent = "✓ Looks safe";
    bannerEl.className = "verdict-banner safe";
  }

  if (result.prefilter && result.prefilter.reasons) {
    prefilterSection.style.display = "block";
    prefilterReasons.innerHTML = "";
    result.prefilter.reasons.forEach((reason) => {
      const li = document.createElement("li");
      li.textContent = reason;
      prefilterReasons.appendChild(li);
    });
    if (result.prefilter.matched_brand) {
      const li = document.createElement("li");
      li.textContent = `Closest brand match: ${result.prefilter.matched_brand}`;
      prefilterReasons.appendChild(li);
    }
  }

  if (result.visual_analysis) {
    visualSection.style.display = "block";
    const v = result.visual_analysis;
    visualDetails.textContent = `${v.similarity_score}% visually similar to reference page "${v.closest_match}"`;
  }
}

render();
