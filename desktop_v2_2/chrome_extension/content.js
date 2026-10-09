const CANDIDATE_EVENT = "streamforge-media-candidate-v19";
const DEEP_SCAN_EVENT = "streamforge-deep-scan-v19";
const DIRECT_RE = /\.(mp4|webm|mov|mkv|m4v|avi|wmv|flv|mp3|m4a|aac|ogg|opus|wav|flac)(?:$|[?#])/i;
const HLS_RE = /\.m3u8(?:$|[?#])/i;
const DASH_RE = /\.mpd(?:$|[?#])/i;
const MEDIA_TEXT_RE = /(?:https?:\/\/|\/\/|\/)[^\s"'<>\\]{1,1900}?\.(?:m3u8|mpd|mp4|webm|m4v|mov|mp3|m4a)(?:\?[^\s"'<>\\]{0,1900})?/gi;

function safeHttp(url) {
  return typeof url === "string" && /^https?:\/\//i.test(url);
}

function absolute(url, base = location.href) {
  if (!url || /^blob:|^data:/i.test(String(url))) return "";
  try {
    const value = new URL(String(url), base).href;
    return safeHttp(value) ? value : "";
  } catch (_) {
    return "";
  }
}

function classify(url, contentType = "") {
  const ct = String(contentType || "").toLowerCase();
  if (HLS_RE.test(url) || /mpegurl/.test(ct)) return "hls";
  if (DASH_RE.test(url) || ct.includes("application/dash+xml")) return "dash";
  if (/\.(mp3|m4a|aac|ogg|opus|wav|flac)(?:$|[?#])/i.test(url) || ct.startsWith("audio/")) return "audio";
  if (DIRECT_RE.test(url) || ct.startsWith("video/")) return "video";
  return "";
}


function decodeMediaBase64(value) {
  const text = String(value || "").trim();
  if (text.length < 20 || text.length > 4096 || !/^[A-Za-z0-9+/_=-]+$/.test(text)) return "";
  try {
    const normalized = text.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized + "=".repeat((4 - normalized.length % 4) % 4);
    const decoded = atob(padded);
    return /\.(?:m3u8|mpd|mp4|webm|m4v|mov|mp3|m4a)(?:[?#]|$)/i.test(decoded) ? decoded : "";
  } catch (_) { return ""; }
}

function baseCandidate(url, kind, extra = {}) {
  return {
    url,
    kind,
    frame_url: location.href,
    title: document.title || "Detected video",
    user_agent: navigator.userAgent,
    referer: location.href,
    origin: location.origin,
    ...extra
  };
}

function extractTextMedia(text, found) {
  if (!text || text.length > 1024 * 1024) return;
  const cleaned = text.replace(/\\u0026/gi, "&").replace(/\\\//g, "/").replace(/&amp;/gi, "&");
  const matches = cleaned.match(MEDIA_TEXT_RE) || [];
  matches.slice(0, 120).forEach((raw) => {
    const url = absolute(raw.startsWith("//") ? `${location.protocol}${raw}` : raw);
    const kind = url ? classify(url) : "";
    if (url && kind) found.set(`${kind}|${url}`, baseCandidate(url, kind, { detector: "inline-config" }));
  });
  const tokens = cleaned.match(/[A-Za-z0-9+/_=-]{24,2048}/g) || [];
  tokens.slice(0, 100).forEach((token) => {
    const decoded = decodeMediaBase64(token);
    if (!decoded) return;
    const url = absolute(decoded);
    const kind = url ? classify(url) : "";
    if (url && kind) found.set(`${kind}|${url}`, baseCandidate(url, kind, { detector: "base64-config" }));
  });
}

function collectPageMedia() {
  const found = new Map();
  const add = (rawUrl, kind = "", extra = {}) => {
    const url = absolute(rawUrl);
    if (!url) return;
    const resolvedKind = kind || classify(url, extra.content_type || "");
    if (!resolvedKind) return;
    found.set(`${resolvedKind}|${url}`, baseCandidate(url, resolvedKind, extra));
  };

  document.querySelectorAll("video, audio").forEach((media) => {
    add(media.currentSrc || media.src, media.tagName.toLowerCase() === "audio" ? "audio" : "video", {
      thumbnail: media.poster ? absolute(media.poster) : "",
      detector: "html-media"
    });
    media.querySelectorAll("source[src]").forEach((source) => add(source.src, "", { detector: "html-source" }));
  });

  document.querySelectorAll("source[src]").forEach((source) => add(source.src, "", { detector: "html-source" }));

  document.querySelectorAll("[data-src],[data-video],[data-file],[data-hls],[data-mpd],[data-stream],[data-url],[data-playlist],[data-manifest],[data-config]").forEach((node) => {
    ["data-src", "data-video", "data-file", "data-hls", "data-mpd", "data-stream", "data-url", "data-playlist", "data-manifest", "data-config"].forEach((attr) => {
      const raw = node.getAttribute(attr);
      if (!raw) return;
      let kind = "";
      if (attr === "data-hls") kind = "hls";
      else if (attr === "data-mpd") kind = "dash";
      else if (["data-video", "data-file", "data-stream"].includes(attr) && safeHttp(absolute(raw))) kind = classify(absolute(raw)) || "video";
      add(raw, kind, { detector: "data-attribute" });
    });
  });

  document.querySelectorAll("a[href]").forEach((link) => {
    const href = absolute(link.getAttribute("href"));
    if (href && classify(href)) add(href, "", { detector: "media-link" });
  });

  document.querySelectorAll("iframe[src]").forEach((frame) => {
    const url = absolute(frame.getAttribute("src"));
    if (!url) return;
    const allow = (frame.getAttribute("allow") || "").toLowerCase();
    const hint = `${url} ${frame.className || ""} ${frame.id || ""}`.toLowerCase();
    const looksLikePlayer = /player|embed|video|stream|youtube|youtu\.be|vimeo|dailymotion|jwplayer|plyr/.test(hint) || /autoplay|fullscreen/.test(allow);
    if (!looksLikePlayer) return;
    found.set(`player|${url}`, baseCandidate(url, "player", {
      title: frame.title || document.title || "Embedded player",
      detector: "iframe-hint"
    }));
  });

  // Open shadow roots are common in modern custom video components. Scan them
  // recursively without attempting to break closed shadow DOM boundaries.
  try {
    const roots = [];
    const queue = [document];
    const seenRoots = new Set();
    while (queue.length && roots.length < 80) {
      const root = queue.shift();
      if (!root || seenRoots.has(root)) continue;
      seenRoots.add(root);
      roots.push(root);
      root.querySelectorAll && root.querySelectorAll("*").forEach((node) => {
        if (node.shadowRoot && !seenRoots.has(node.shadowRoot)) queue.push(node.shadowRoot);
      });
    }
    roots.slice(1).forEach((root) => {
      root.querySelectorAll("video,audio").forEach((media) => {
        add(media.currentSrc || media.src, media.tagName.toLowerCase() === "audio" ? "audio" : "video", {
          thumbnail: media.poster ? absolute(media.poster) : "",
          detector: "shadow-media"
        });
        media.querySelectorAll("source[src]").forEach((source) => add(source.src, "", { detector: "shadow-source" }));
      });
      root.querySelectorAll("source[src]").forEach((source) => add(source.src, "", { detector: "shadow-source" }));
      root.querySelectorAll("[data-src],[data-video],[data-file],[data-hls],[data-mpd],[data-stream],[data-url],[data-playlist],[data-manifest]").forEach((node) => {
        ["data-src","data-video","data-file","data-hls","data-mpd","data-stream","data-url","data-playlist","data-manifest"].forEach((attr) => {
          const raw = node.getAttribute(attr);
          if (raw) add(raw, attr === "data-hls" ? "hls" : (attr === "data-mpd" ? "dash" : ""), { detector: "shadow-data" });
        });
      });
    });
  } catch (_) {}

  try {
    performance.getEntriesByType("resource").slice(-600).forEach((entry) => {
      const url = entry && entry.name;
      if (safeHttp(url) && classify(url)) add(url, "", { detector: "performance" });
    });
  } catch (_) {}

  try {
    let total = 0;
    for (const script of document.querySelectorAll("script:not([src])")) {
      const text = script.textContent || "";
      total += text.length;
      if (total > 1024 * 1024) break;
      extractTextMedia(text, found);
    }
  } catch (_) {}

  return Array.from(found.values());
}

let latestPlayableCandidate = null;
let floatingEnabled = true;
const overlayStates = new Map();
let overlayTick = null;
let scanTimer = null;

function setFloatingEnabled(value) {
  floatingEnabled = Boolean(value);
  if (!floatingEnabled) {
    for (const state of overlayStates.values()) {
      try { state.root.remove(); } catch (_) {}
    }
    overlayStates.clear();
  } else {
    scheduleOverlayRefresh(0);
  }
}

chrome.storage.local.get("sf_floating_button").then((data) => {
  if (typeof data.sf_floating_button === "undefined") {
    setFloatingEnabled(true);
    chrome.storage.local.set({ sf_floating_button: true }).catch(() => {});
  } else {
    setFloatingEnabled(Boolean(data.sf_floating_button));
  }
}).catch(() => setFloatingEnabled(true));

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.sf_floating_button) {
    setFloatingEnabled(Boolean(changes.sf_floating_button.newValue));
  }
});

function collectVideoElements() {
  const videos = [];
  const roots = [document];
  const seen = new Set();
  while (roots.length && seen.size < 80) {
    const root = roots.shift();
    if (!root || seen.has(root)) continue;
    seen.add(root);
    try {
      root.querySelectorAll("video").forEach((video) => videos.push(video));
      root.querySelectorAll("*").forEach((node) => {
        if (node.shadowRoot && !seen.has(node.shadowRoot)) roots.push(node.shadowRoot);
      });
    } catch (_) {}
  }
  return videos;
}

function videoEligible(video) {
  if (!video || !video.isConnected) return false;
  let rect;
  try { rect = video.getBoundingClientRect(); } catch (_) { return false; }
  if (!rect || rect.width < 180 || rect.height < 96) return false;
  if (rect.bottom < 0 || rect.right < 0 || rect.top > window.innerHeight || rect.left > window.innerWidth) return false;
  const started = (!video.paused && !video.ended) || Number(video.currentTime || 0) > 0.05;
  const hasMedia = Boolean(video.currentSrc || video.src || video.readyState >= 1);
  return started && hasMedia;
}

function style(node, values) {
  Object.assign(node.style, values);
  return node;
}

function makeOverlay(video) {
  const root = style(document.createElement("div"), {
    position: "fixed",
    zIndex: "2147483646",
    pointerEvents: "none",
    fontFamily: "system-ui,-apple-system,Segoe UI,Roboto,sans-serif",
    color: "#fff"
  });
  root.dataset.streamforgeOverlay = "1";

  const button = style(document.createElement("button"), {
    pointerEvents: "auto",
    minWidth: "116px",
    height: "36px",
    padding: "0 13px",
    border: "1px solid rgba(255,255,255,.22)",
    borderRadius: "10px",
    background: "linear-gradient(135deg,#4d8eff,#7027e8)",
    color: "#fff",
    boxShadow: "0 8px 24px rgba(0,0,0,.35)",
    cursor: "pointer",
    font: "700 13px system-ui,-apple-system,Segoe UI,sans-serif",
    letterSpacing: ".1px"
  });
  button.type = "button";
  button.textContent = "↓ Download";
  button.title = "Choose video quality and send it to Shield Stream";

  const menu = style(document.createElement("div"), {
    display: "none",
    pointerEvents: "auto",
    position: "absolute",
    right: "0",
    top: "42px",
    width: "260px",
    maxHeight: "330px",
    overflowY: "auto",
    padding: "8px",
    border: "1px solid rgba(255,255,255,.14)",
    borderRadius: "13px",
    background: "rgba(20,20,22,.97)",
    boxShadow: "0 16px 42px rgba(0,0,0,.48)",
    backdropFilter: "blur(14px)"
  });

  const title = style(document.createElement("div"), {
    padding: "7px 8px 8px",
    color: "#f5f4f7",
    fontSize: "12px",
    fontWeight: "800",
    borderBottom: "1px solid rgba(255,255,255,.08)",
    marginBottom: "6px"
  });
  title.textContent = "Download video";
  menu.appendChild(title);

  root.append(button, menu);
  (document.documentElement || document.body).appendChild(root);

  const state = { root, button, menu, video, open: false, loading: false };
  overlayStates.set(video, state);

  button.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (state.open) closeOverlayMenu(state);
    else openOverlayMenu(state);
  }, true);

  menu.addEventListener("click", (event) => event.stopPropagation(), true);
  return state;
}

function closeOverlayMenu(state) {
  if (!state) return;
  state.open = false;
  state.menu.style.display = "none";
}

function menuNotice(state, text, tone = "muted") {
  const row = style(document.createElement("div"), {
    padding: "10px 9px",
    borderRadius: "9px",
    color: tone === "error" ? "#ffb4ab" : (tone === "ok" ? "#86f7c0" : "#b8b8c3"),
    fontSize: "12px",
    lineHeight: "1.35"
  });
  row.textContent = text;
  state.menu.appendChild(row);
  return row;
}

function resetMenu(state) {
  while (state.menu.children.length > 1) state.menu.lastChild.remove();
}

function qualityRank(label) {
  const match = String(label || "").match(/(4320|2160|1440|1080|720|576|540|480|360|240)p/i);
  if (match) return Number(match[1]);
  if (/best/i.test(label)) return 10000;
  if (/audio/i.test(label)) return -1;
  return 0;
}

function renderQualityOptions(state, options) {
  resetMenu(state);
  const rows = Array.isArray(options) ? [...options] : [];
  rows.sort((a, b) => qualityRank(b.label) - qualityRank(a.label));
  if (!rows.length) {
    menuNotice(state, "No downloadable quality detected yet. Keep the video playing, then use Power scan in the extension.");
    return;
  }

  rows.slice(0, 16).forEach((option) => {
    const row = style(document.createElement("button"), {
      width: "100%",
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: "10px",
      padding: "10px 10px",
      margin: "2px 0",
      border: "0",
      borderRadius: "9px",
      background: "transparent",
      color: "#fff",
      cursor: "pointer",
      textAlign: "left",
      fontFamily: "inherit"
    });
    row.type = "button";
    row.addEventListener("mouseenter", () => { row.style.background = "rgba(108,92,231,.18)"; });
    row.addEventListener("mouseleave", () => { row.style.background = "transparent"; });

    const left = document.createElement("span");
    const label = style(document.createElement("strong"), { display: "block", fontSize: "13px", fontWeight: "800" });
    label.textContent = option.label || "Best Available";
    const meta = style(document.createElement("small"), { display: "block", color: "#9f9fab", fontSize: "10.5px", marginTop: "2px" });
    meta.textContent = [option.kind ? String(option.kind).toUpperCase() : "VIDEO", option.verified ? "VERIFIED" : ""].filter(Boolean).join(" • ");
    left.append(label, meta);

    const send = style(document.createElement("span"), {
      color: "#aebdff",
      fontSize: "15px",
      fontWeight: "900"
    });
    send.textContent = "→";
    row.append(left, send);

    row.addEventListener("click", () => sendOverlayOption(state, option, row));
    state.menu.appendChild(row);
  });
}

function requestOverlayOptions(state, retry = true) {
  if (!state || state.loading) return;
  state.loading = true;
  resetMenu(state);
  menuNotice(state, "Finding available qualities...");
  const mediaUrl = absolute(state.video.currentSrc || state.video.src || "");
  chrome.runtime.sendMessage({
    type: "GET_OVERLAY_OPTIONS",
    frame_url: location.href,
    media_url: mediaUrl,
    title: document.title || "Detected video"
  }, (response) => {
    state.loading = false;
    const options = (response && response.options) || [];
    if (options.length || !retry) {
      renderQualityOptions(state, options);
      return;
    }
    // Run a lightweight page scan once before telling the user to use Power scan.
    sendScan();
    setTimeout(() => requestOverlayOptions(state, false), 750);
  });
}

function openOverlayMenu(state) {
  for (const other of overlayStates.values()) {
    if (other !== state) closeOverlayMenu(other);
  }
  state.open = true;
  state.menu.style.display = "block";
  positionOverlay(state.video, state);
  requestOverlayOptions(state, true);
}

function sendOverlayOption(state, option, row) {
  if (!option || !option.payload) return;
  const original = row.innerHTML;
  row.disabled = true;
  row.textContent = "Sending to Shield Stream...";
  const payload = {
    ...option.payload,
    preferred_quality: option.label || option.payload.quality_hint || "Best",
    quality_hint: option.payload.quality_hint || option.label || ""
  };
  chrome.runtime.sendMessage({ type: "SEND_TO_APP", payload }, (response) => {
    const ok = Boolean(response && response.ok && Number(response.accepted || 0) > 0);
    resetMenu(state);
    if (ok) {
      menuNotice(state, `${option.label || "Video"} sent to Shield Stream.`, "ok");
      state.button.textContent = "✓ Sent";
      setTimeout(() => {
        state.button.textContent = "↓ Download";
        closeOverlayMenu(state);
      }, 1300);
    } else {
      menuNotice(state, (response && response.error) || "Open Shield Stream on this PC, then try again.", "error");
      state.button.textContent = "↓ Download";
      row.innerHTML = original;
    }
  });
}

function positionOverlay(video, state) {
  if (!state || !videoEligible(video)) {
    if (state) state.root.style.display = "none";
    return;
  }
  const rect = video.getBoundingClientRect();
  state.root.style.display = "block";
  // Stay inside the visible video rectangle and away from the browser edge.
  const left = Math.max(8, Math.min(window.innerWidth - 126, rect.right - 124));
  const top = Math.max(8, Math.min(window.innerHeight - 48, rect.top + 10));
  state.root.style.left = `${Math.round(left)}px`;
  state.root.style.top = `${Math.round(top)}px`;
}

function refreshVideoOverlays() {
  if (!floatingEnabled) return;
  const videos = collectVideoElements();
  const live = new Set(videos);

  for (const [video, state] of overlayStates.entries()) {
    if (!video.isConnected || !live.has(video)) {
      try { state.root.remove(); } catch (_) {}
      overlayStates.delete(video);
    }
  }

  videos.forEach((video) => {
    if (!videoEligible(video)) {
      const existing = overlayStates.get(video);
      if (existing) existing.root.style.display = "none";
      return;
    }
    const state = overlayStates.get(video) || makeOverlay(video);
    positionOverlay(video, state);
  });
}

function scheduleOverlayRefresh(delay = 60) {
  clearTimeout(overlayTick);
  overlayTick = setTimeout(refreshVideoOverlays, Math.max(0, delay));
}

function forwardCandidates(candidates) {
  if (!Array.isArray(candidates) || !candidates.length) return;
  const playable = candidates.find((item) => item && ["video", "audio", "hls", "dash"].includes(item.kind));
  if (playable) latestPlayableCandidate = playable;
  chrome.runtime.sendMessage({ type: "PAGE_MEDIA", candidates }).catch(() => {});
  scheduleOverlayRefresh(30);
}

function sendScan() {
  forwardCandidates(collectPageMedia());
  try { window.dispatchEvent(new CustomEvent(DEEP_SCAN_EVENT)); } catch (_) {}
  scheduleOverlayRefresh(20);
}

window.addEventListener(CANDIDATE_EVENT, (event) => {
  try {
    const raw = event && event.detail;
    const candidate = typeof raw === "string" ? JSON.parse(raw) : raw;
    if (!candidate || !candidate.url) return;
    candidate.user_agent = navigator.userAgent;
    candidate.referer = candidate.referer || location.href;
    candidate.origin = candidate.origin || location.origin;
    candidate.frame_url = candidate.frame_url || location.href;
    forwardCandidates([candidate]);
  } catch (_) {}
}, false);

function scheduleScan(delay = 350) {
  clearTimeout(scanTimer);
  scanTimer = setTimeout(sendScan, delay);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => { sendScan(); scheduleOverlayRefresh(0); }, { once: true });
} else {
  sendScan();
  scheduleOverlayRefresh(0);
}
setTimeout(sendScan, 1500);
setTimeout(sendScan, 5000);

// Keep the IDM-style toggle aligned with players as the page scrolls/resizes.
window.addEventListener("scroll", () => scheduleOverlayRefresh(0), true);
window.addEventListener("resize", () => scheduleOverlayRefresh(0), true);
document.addEventListener("fullscreenchange", () => scheduleOverlayRefresh(0), true);
document.addEventListener("play", () => { scheduleScan(180); scheduleOverlayRefresh(20); }, true);
document.addEventListener("playing", () => { scheduleScan(180); scheduleOverlayRefresh(20); }, true);
document.addEventListener("loadedmetadata", () => { scheduleScan(220); scheduleOverlayRefresh(20); }, true);
document.addEventListener("pause", () => scheduleOverlayRefresh(80), true);

document.addEventListener("pointerdown", (event) => {
  for (const state of overlayStates.values()) {
    if (!state.open) continue;
    if (state.root.contains(event.target)) continue;
    closeOverlayMenu(state);
  }
}, true);

const startObserver = () => {
  if (!document.documentElement) return;
  const observer = new MutationObserver(() => {
    scheduleScan(450);
    scheduleOverlayRefresh(90);
  });
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["src", "data-src", "data-video", "data-file", "data-hls", "data-mpd", "data-stream", "data-url", "data-playlist", "data-manifest", "data-config"]
  });
};
if (document.documentElement) startObserver();
else document.addEventListener("DOMContentLoaded", startObserver, { once: true });

try {
  const perfObserver = new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      const url = entry && entry.name;
      if (safeHttp(url) && classify(url)) scheduleScan(80);
    }
  });
  perfObserver.observe({ type: "resource", buffered: false });
} catch (_) {}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message && message.type === "SCAN_NOW") {
    sendScan();
    sendResponse({ ok: true, frame: location.href });
  }
});
