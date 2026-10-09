const BRIDGE_URL = "http://127.0.0.1:8765";
const MAX_PER_TAB = 120;
const MAX_BODY_BYTES = 2 * 1024 * 1024;
const DIRECT_EXT_RE = /\.(mp4|webm|mov|mkv|m4v|avi|wmv|flv|mp3|m4a|aac|ogg|opus|wav|flac)(?:$|[?#])/i;
const HLS_RE = /\.m3u8(?:$|[?#])/i;
const DASH_RE = /\.mpd(?:$|[?#])/i;
const SEGMENT_RE = /\.(ts|m4s|cmfv|cmfa|aac)(?:$|[?#])/i;
const MEDIA_BODY_RE = /(?:https?:\/\/|\/\/|\/)[^\s"'<>\\]{1,1900}?\.(?:m3u8|mpd|mp4|webm|m4v|mov|mp3|m4a)(?:\?[^\s"'<>\\]{0,1900})?/gi;
const BODY_HINT_RE = /(player|config|source|stream|manifest|master|media|video|playlist|hls|dash|m3u8|mpd|jwplayer|plyr)/i;
const BLOCKED_SENSITIVE_RE = /(?:widevine|playready|fairplay|drm|license(?:s|server)?)(?:[/?#._=-]|$)/i;
const requestContext = new Map();
const deepSessions = new Map();
const autoSent = new Map();
let bridgeToken = "";

function tabKey(tabId) { return `sf_candidates_${tabId}`; }
function safeHttpUrl(url) { return typeof url === "string" && /^https?:\/\//i.test(url); }
function now() { return Date.now(); }

function qualityHint(url = "", contentType = "", disposition = "") {
  const text = `${url} ${contentType} ${disposition}`;
  const explicit = text.match(/(?:^|[^0-9])(2160|1440|1080|720|576|540|480|360|240)p?(?:[^0-9]|$)/i);
  if (explicit) return `${explicit[1]}p`;
  const dims = text.match(/(?:^|[^0-9])(3840x2160|2560x1440|1920x1080|1280x720|854x480|640x360)(?:[^0-9]|$)/i);
  if (dims) {
    const height = dims[1].split("x")[1];
    return `${height}p`;
  }
  return "";
}

function groupIdFor(tabId, candidate = {}) {
  const page = candidate.page_url || candidate.frame_url || "";
  const title = String(candidate.title || "").replace(/\s+/g, " ").trim().toLowerCase();
  return `${tabId}|${page}|${title}`.slice(0, 1200);
}

function qualityNumber(label = "") {
  const match = String(label || "").match(/(4320|2160|1440|1080|720|576|540|480|360|240)p/i);
  return match ? Number(match[1]) : 0;
}

function optionLabel(item = {}) {
  const hinted = String(item.quality_hint || "").trim();
  if (hinted) return hinted;
  if (item.kind === "audio") return "Audio";
  if (item.kind === "hls" || item.kind === "dash") return "Best Available";
  return "Video";
}

function overlayOptionPayload(item, label = "") {
  return {
    ...item,
    quality_hint: String(label || item.quality_hint || "").trim(),
    preferred_quality: String(label || item.preferred_quality || item.quality_hint || "Best").trim()
  };
}

async function fetchManifestOverlayOptions(item) {
  if (!item || !["hls", "dash"].includes(item.kind) || !safeHttpUrl(item.url)) return [];
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 2600);
  try {
    const options = {
      cache: "no-store",
      credentials: "omit",
      signal: controller.signal
    };
    const response = await fetch(item.url, options);
    if (!response.ok) return [];
    const contentLength = Number(response.headers.get("content-length") || 0);
    if (contentLength > 1024 * 1024) return [];
    const text = await response.text();
    if (!text || text.length > 1024 * 1024) return [];

    if (item.kind === "hls" && text.trimStart().startsWith("#EXTM3U")) {
      const lines = text.split(/\r?\n/);
      const rows = [];
      for (let i = 0; i < lines.length && rows.length < 16; i += 1) {
        const line = String(lines[i] || "").trim();
        if (!line.startsWith("#EXT-X-STREAM-INF:")) continue;
        const attrs = line.slice(line.indexOf(":") + 1);
        const resolution = attrs.match(/RESOLUTION=(\d+)x(\d+)/i);
        const fps = attrs.match(/FRAME-RATE=([0-9.]+)/i);
        const bandwidth = attrs.match(/(?:AVERAGE-)?BANDWIDTH=(\d+)/i);
        let uri = "";
        for (let j = i + 1; j < lines.length; j += 1) {
          const next = String(lines[j] || "").trim();
          if (!next || next.startsWith("#")) continue;
          uri = next;
          break;
        }
        const url = absoluteUrl(uri, item.url);
        if (!url || isSensitiveUrl(url)) continue;
        const height = resolution ? Number(resolution[2]) : 0;
        const label = height ? `${height}p` : `HLS ${rows.length + 1}`;
        rows.push({
          label,
          kind: "hls",
          verified: Boolean(item.verified),
          height,
          payload: overlayOptionPayload({
            ...item,
            url,
            quality_hint: label,
            width: resolution ? Number(resolution[1]) : 0,
            height,
            fps: fps ? Number(fps[1]) : 0,
            bitrate: bandwidth ? Number(bandwidth[1]) : 0,
            detector: `${item.detector || "manifest"}+quality-menu`
          }, label)
        });
      }
      return rows;
    }

    if (item.kind === "dash" && /<MPD(?:\s|>)/i.test(text.slice(0, 65536))) {
      const rows = [];
      const seen = new Set();
      const repRe = /<Representation\b([^>]*)>/gi;
      let match;
      while ((match = repRe.exec(text)) && rows.length < 20) {
        const attrs = match[1] || "";
        const heightMatch = attrs.match(/\bheight=["'](\d+)["']/i);
        const bandwidthMatch = attrs.match(/\bbandwidth=["'](\d+)["']/i);
        const fpsMatch = attrs.match(/\bframeRate=["']([0-9.]+)["']/i);
        const height = heightMatch ? Number(heightMatch[1]) : 0;
        if (!height) continue;
        const label = `${height}p`;
        if (seen.has(label)) continue;
        seen.add(label);
        rows.push({
          label,
          kind: "dash",
          verified: Boolean(item.verified),
          height,
          payload: overlayOptionPayload({
            ...item,
            quality_hint: label,
            preferred_quality: label,
            height,
            fps: fpsMatch ? Number(fpsMatch[1]) : 0,
            bitrate: bandwidthMatch ? Number(bandwidthMatch[1]) : 0,
            detector: `${item.detector || "manifest"}+quality-menu`
          }, label)
        });
      }
      return rows;
    }
  } catch (_) {
    return [];
  } finally {
    clearTimeout(timer);
  }
  return [];
}

async function getOverlayOptions(tabId, frameUrl = "", mediaUrl = "") {
  let items = (await getCandidates(tabId)).filter((item) => item && ["video", "audio", "hls", "dash"].includes(item.kind));
  if (!items.length) return [];

  const exactMedia = mediaUrl ? items.filter((item) => item.url === mediaUrl) : [];
  const byFrame = frameUrl ? items.filter((item) => item.frame_url === frameUrl || item.referer === frameUrl) : [];
  if (exactMedia.length) items = [...exactMedia, ...byFrame.filter((x) => !exactMedia.includes(x))];
  else if (byFrame.length) items = byFrame;

  const options = [];

  // On demand, try to read standard public/signed manifests without browser
  // credentials. This often exposes the same 1080p/720p/480p menu the player
  // already knows, even before a full Power Scan has captured every child URL.
  const manifestItems = items.filter((item) => ["hls", "dash"].includes(item.kind)).slice(0, 4);
  const manifestRows = (await Promise.all(manifestItems.map((item) => fetchManifestOverlayOptions(item)))).flat();
  options.push(...manifestRows);

  const add = (label, item, extra = {}) => {
    const cleanLabel = String(label || optionLabel(item)).trim() || "Best Available";
    options.push({
      label: cleanLabel,
      kind: item.kind,
      verified: Boolean(item.verified),
      score: candidateScore(item),
      height: Number(extra.height || item.height || qualityNumber(cleanLabel) || 0),
      payload: overlayOptionPayload({ ...item, ...extra }, cleanLabel)
    });
  };

  for (const item of items) {
    const manifestQualities = Array.isArray(item.manifest_qualities) ? item.manifest_qualities : [];
    if (manifestQualities.length && item.kind === "dash") {
      for (const q of manifestQualities.slice(0, 16)) {
        const label = String(q.label || (q.height ? `${q.height}p` : "Best Available"));
        add(label, item, { height: Number(q.height || 0), bitrate: Number(q.bitrate || 0), fps: Number(q.fps || 0) });
      }
    } else {
      add(optionLabel(item), item);
    }
  }

  const bestByLabel = new Map();
  for (const option of options) {
    const key = `${option.kind}|${option.label.toLowerCase()}`;
    const existing = bestByLabel.get(key);
    const optionWeight = (option.height || 0) * 1000 + (option.verified ? 100 : 0) + option.score;
    const existingWeight = existing ? (existing.height || 0) * 1000 + (existing.verified ? 100 : 0) + existing.score : -1;
    if (!existing || optionWeight > existingWeight) bestByLabel.set(key, option);
  }

  const deduped = [...bestByLabel.values()];
  deduped.sort((a, b) => {
    if (a.kind === "audio" && b.kind !== "audio") return 1;
    if (b.kind === "audio" && a.kind !== "audio") return -1;
    return (b.height || 0) - (a.height || 0) || Number(b.verified) - Number(a.verified) || b.score - a.score;
  });

  return deduped.slice(0, 16).map(({ score, height, ...row }) => row);
}

async function ensureBridgeToken() {
  if (bridgeToken) return bridgeToken;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 1500);
  try {
    const response = await fetch(`${BRIDGE_URL}/health?t=${Date.now()}`, { cache: "no-store", signal: controller.signal });
    const data = await response.json().catch(() => ({}));
    if (response.ok && data.token) bridgeToken = String(data.token);
    return bridgeToken;
  } finally { clearTimeout(timer); }
}

async function sendToBridge(payload) {
  let token = await ensureBridgeToken();
  if (!token) throw new Error("Shield Stream companion token is unavailable. Restart the desktop app.");
  let response = await fetch(`${BRIDGE_URL}/add-media`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-StreamForge-Token": token },
    body: JSON.stringify(payload),
    cache: "no-store"
  });
  if (response.status === 401) {
    bridgeToken = "";
    token = await ensureBridgeToken();
    response = await fetch(`${BRIDGE_URL}/add-media`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-StreamForge-Token": token },
      body: JSON.stringify(payload),
      cache: "no-store"
    });
  }
  const data = await response.json().catch(() => ({}));
  return { ok: response.ok, ...data };
}


async function pollBridgeCommands() {
  const token = await ensureBridgeToken();
  if (!token) return;
  try {
    const response = await fetch(`${BRIDGE_URL}/commands?t=${Date.now()}`, {
      cache: "no-store",
      headers: { "X-StreamForge-Token": token }
    });
    if (!response.ok) return;
    const data = await response.json().catch(() => ({}));
    const commands = Array.isArray(data.commands) ? data.commands : [];
    for (const command of commands.slice(0, 10)) {
      if (!command || command.type !== "refresh_stream") continue;
      const tabId = Number(command.tab_id || 0);
      if (!Number.isInteger(tabId) || tabId <= 0) continue;
      const tab = await chrome.tabs.get(tabId).catch(() => null);
      if (!tab) continue;
      try {
        await startDeepScan(tabId, 15000);
        setTimeout(async () => {
          try {
            const items = await getCandidates(tabId);
            let matches = items.filter((item) => item && !["player", "page"].includes(item.kind));
            if (command.group_id) {
              const grouped = matches.filter((item) => item.group_id === command.group_id);
              if (grouped.length) matches = grouped;
            } else if (command.page_url) {
              const byPage = matches.filter((item) => item.page_url === command.page_url);
              if (byPage.length) matches = byPage;
            }
            const verified = matches.filter((item) => item.verified);
            await sendToBridge((verified.length ? verified : matches).slice(0, 12));
          } catch (_) {}
        }, 15500);
      } catch (_) {}
    }
  } catch (_) {}
}


function safeOrigin(url) {
  try { return new URL(url).origin; } catch (_) { return ""; }
}

function absoluteUrl(raw, base = "") {
  if (!raw || /^blob:|^data:/i.test(String(raw))) return "";
  try {
    const value = new URL(String(raw), base || undefined).href;
    return safeHttpUrl(value) ? value : "";
  } catch (_) { return ""; }
}

function headerValue(headers = [], name = "") {
  const target = name.toLowerCase();
  const header = headers.find((h) => (h.name || "").toLowerCase() === target);
  return (header && header.value) || "";
}

function contentTypeFromHeaders(headers = []) {
  return headerValue(headers, "content-type").split(";", 1)[0].trim().toLowerCase();
}

function dispositionFilename(headers = []) {
  const value = headerValue(headers, "content-disposition");
  if (!value) return "";
  const match = value.match(/filename\*?=(?:UTF-8''|["']?)([^"';]+)/i);
  if (!match) return "";
  try { return decodeURIComponent(match[1].replace(/["']/g, "").trim()); }
  catch (_) { return match[1].replace(/["']/g, "").trim(); }
}

function isSensitiveUrl(url) {
  return BLOCKED_SENSITIVE_RE.test(String(url || ""));
}

function classify(url, contentType = "", requestType = "", disposition = "") {
  if (!safeHttpUrl(url) || SEGMENT_RE.test(url) || isSensitiveUrl(url)) return "";
  const ct = String(contentType || "").toLowerCase();
  const filename = String(disposition || "");
  const combined = `${url} ${filename}`;

  if (HLS_RE.test(combined) || /(?:application|audio)\/(?:vnd\.apple\.)?mpegurl|application\/x-mpegurl/.test(ct)) return "hls";
  if (DASH_RE.test(combined) || ct.includes("application/dash+xml")) return "dash";
  if (/\.(mp3|m4a|aac|ogg|opus|wav|flac)(?:$|[?#\s])/i.test(combined) || ct.startsWith("audio/")) return "audio";
  if (DIRECT_EXT_RE.test(combined) || ct.startsWith("video/")) return "video";

  // A Chrome request whose resource type is literally media is a strong signal,
  // even when a CDN uses extensionless URLs or application/octet-stream.
  if (String(requestType).toLowerCase() === "media" && !/(?:text\/html|application\/(?:json|javascript|xml))/.test(ct)) return "video";
  return "";
}

function candidateScore(item) {
  if (!item) return 0;
  let score = { hls: 100, dash: 98, video: 90, audio: 72, player: 5, page: 1 }[item.kind] || 0;
  if (item.verified) score += 30;
  if (item.detector === "devtools-response") score += 18;
  if (item.detector === "response-headers") score += 14;
  if (item.detector === "manifest-body" || item.detector === "devtools-body") score += 12;
  if (item.status_code >= 200 && item.status_code < 300) score += 8;
  return score;
}

async function getCandidates(tabId) {
  const key = tabKey(tabId);
  const result = await chrome.storage.local.get(key);
  const items = Array.isArray(result[key]) ? result[key] : [];
  const cutoff = now() - 20 * 60 * 1000;
  return items.filter((item) => !item.detected_at || item.detected_at >= cutoff);
}

async function setCandidates(tabId, items) {
  const key = tabKey(tabId);
  const sorted = [...items]
    .sort((a, b) => candidateScore(b) - candidateScore(a) || (b.detected_at || 0) - (a.detected_at || 0))
    .slice(0, MAX_PER_TAB);
  await chrome.storage.local.set({ [key]: sorted });
  const streamCount = sorted.filter((item) => !["player", "page"].includes(item.kind)).length;
  const badge = Math.min(streamCount, 99);
  await chrome.action.setBadgeText({ tabId, text: badge ? String(badge) : "" }).catch(() => {});
  if (badge) await chrome.action.setBadgeBackgroundColor({ tabId, color: "#6C5CE7" }).catch(() => {});
}

async function addCandidate(tabId, candidate) {
  if (!Number.isInteger(tabId) || tabId < 0 || !candidate || !safeHttpUrl(candidate.url)) return;
  if (isSensitiveUrl(candidate.url)) return;
  const kind = candidate.kind || classify(
    candidate.url,
    candidate.content_type || "",
    candidate.request_type || "",
    candidate.content_disposition || ""
  );
  if (!kind && candidate.kind !== "player" && candidate.kind !== "page") return;

  const normalized = {
    url: candidate.url,
    page_url: candidate.page_url || "",
    frame_url: candidate.frame_url || candidate.referer || candidate.page_url || "",
    title: candidate.title || "Detected video",
    thumbnail: candidate.thumbnail || "",
    kind: kind || candidate.kind,
    source: candidate.source || "chrome-extension",
    user_agent: candidate.user_agent || navigator.userAgent || "",
    referer: candidate.referer || candidate.frame_url || candidate.page_url || "",
    origin: candidate.origin || "",
    content_type: candidate.content_type || "",
    content_length: Number(candidate.content_length || 0),
    status_code: Number(candidate.status_code || 0),
    verified: Boolean(candidate.verified),
    detector: candidate.detector || "browser-network",
    detected_at: Number(candidate.detected_at || now()),
    tab_id: tabId,
    group_id: candidate.group_id || groupIdFor(tabId, candidate),
    quality_hint: candidate.quality_hint || qualityHint(candidate.url, candidate.content_type || "", candidate.content_disposition || ""),
    preferred_quality: candidate.preferred_quality || "",
    width: Number(candidate.width || 0),
    height: Number(candidate.height || 0),
    fps: Number(candidate.fps || 0),
    bitrate: Number(candidate.bitrate || 0),
    manifest_qualities: Array.isArray(candidate.manifest_qualities) ? candidate.manifest_qualities.slice(0, 24) : []
  };

  const current = await getCandidates(tabId);
  const signature = `${normalized.kind}|${normalized.url}`;
  const existing = current.find((item) => `${item.kind}|${item.url}` === signature);
  let next = current.filter((item) => `${item.kind}|${item.url}` !== signature);
  if (existing) {
    const merged = {
      ...existing,
      ...normalized,
      verified: Boolean(existing.verified || normalized.verified),
      status_code: normalized.status_code || existing.status_code || 0,
      content_type: normalized.content_type || existing.content_type || "",
      content_length: normalized.content_length || existing.content_length || 0,
      referer: normalized.referer || existing.referer || "",
      origin: normalized.origin || existing.origin || "",
      preferred_quality: normalized.preferred_quality || existing.preferred_quality || "",
      width: normalized.width || existing.width || 0,
      height: normalized.height || existing.height || 0,
      fps: normalized.fps || existing.fps || 0,
      bitrate: normalized.bitrate || existing.bitrate || 0,
      manifest_qualities: normalized.manifest_qualities.length ? normalized.manifest_qualities : (existing.manifest_qualities || []),
      detected_at: Math.max(existing.detected_at || 0, normalized.detected_at || 0)
    };
    next.push(merged);
  } else {
    next.push(normalized);
  }
  await setCandidates(tabId, next);

  // Optional live companion mode. It is OFF by default and only sends verified
  // standard media streams. Browser pages/player hints are never auto-sent.
  if (normalized.verified && !["player", "page"].includes(normalized.kind)) {
    try {
      const setting = await chrome.storage.local.get("sf_auto_send_verified");
      if (setting.sf_auto_send_verified) {
        const sig = `${normalized.kind}|${normalized.url}`;
        const sent = autoSent.get(tabId) || new Set();
        if (!sent.has(sig)) {
          sent.add(sig);
          autoSent.set(tabId, sent);
          await sendToBridge(normalized);
        }
      }
    } catch (_) {}
  }
}

async function removeCandidate(tabId, url, kind = "") {
  if (!Number.isInteger(tabId) || tabId < 0 || !url) return;
  const current = await getCandidates(tabId);
  const next = current.filter((item) => {
    if (item.url !== url) return true;
    if (kind && item.kind !== kind) return true;
    return false;
  });
  await setCandidates(tabId, next);
}

function strongManifestMime(kind, mime) {
  const ct = String(mime || "").toLowerCase();
  if (kind === "hls") return /mpegurl/.test(ct);
  if (kind === "dash") return ct.includes("application/dash+xml");
  return true;
}

function bodyLooksLikeManifest(kind, text) {
  const value = String(text || "").trimStart();
  if (kind === "hls") return value.startsWith("#EXTM3U");
  if (kind === "dash") return /<MPD(?:\s|>)/i.test(value.slice(0, 65536));
  return false;
}

function bodyLooksLikeErrorText(text) {
  const value = String(text || "").trim().toLowerCase();
  if (!value) return false;
  return [
    "security error", "access denied", "forbidden", "unauthorized",
    "permission denied", "invalid token", "expired", "not found",
    "<!doctype html", "<html", "error 403", "error 404"
  ].some((marker) => value.includes(marker));
}

async function frameInfo(details) {
  try { return await chrome.webNavigation.getFrame({ tabId: details.tabId, frameId: details.frameId }); }
  catch (_) { return null; }
}

async function addNetworkCandidate(details, kind, contentType = "", disposition = "", detector = "webRequest", verified = false) {
  if (!kind || details.tabId < 0) return;
  try {
    const [tab, frame] = await Promise.all([
      chrome.tabs.get(details.tabId).catch(() => null),
      frameInfo(details)
    ]);
    const context = requestContext.get(details.requestId) || {};
    const pageUrl = (tab && tab.url) || "";
    const frameUrl = (frame && frame.url) || context.referer || details.initiator || pageUrl;
    await addCandidate(details.tabId, {
      url: details.url,
      page_url: pageUrl,
      frame_url: frameUrl,
      title: (tab && tab.title) || "Detected video",
      kind,
      content_type: contentType,
      content_disposition: disposition,
      content_length: Number(details.content_length || 0),
      status_code: Number(details.statusCode || 0),
      request_type: details.type,
      referer: context.referer || frameUrl || pageUrl,
      origin: context.origin || details.initiator || safeOrigin(frameUrl),
      user_agent: context.user_agent || navigator.userAgent || "",
      detector,
      verified
    });
  } catch (_) {}
}

function decodeBase64Text(value) {
  const text = String(value || "").trim();
  if (text.length < 20 || text.length > 4096 || !/^[A-Za-z0-9+/_=-]+$/.test(text)) return "";
  try {
    const normalized = text.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized + "=".repeat((4 - normalized.length % 4) % 4);
    const decoded = atob(padded);
    if (!/\.(?:m3u8|mpd|mp4|webm|m4v|mov|mp3|m4a)(?:[?#]|$)/i.test(decoded)) return "";
    return decoded;
  } catch (_) { return ""; }
}

function extractCandidatesFromText(text, baseUrl, detector = "devtools-body") {
  const results = [];
  if (typeof text !== "string" || !text || text.length > MAX_BODY_BYTES) return results;
  const cleaned = text.replace(/\\u0026/gi, "&").replace(/\\\//g, "/").replace(/&amp;/gi, "&");
  const seen = new Set();

  function push(raw, forcedKind = "", extra = {}) {
    let candidate = raw;
    if (raw && raw.startsWith("//")) {
      try { candidate = `${new URL(baseUrl).protocol}${raw}`; } catch (_) { candidate = `https:${raw}`; }
    }
    const url = absoluteUrl(candidate, baseUrl);
    if (!url || isSensitiveUrl(url)) return;
    const kind = forcedKind || classify(url);
    if (!kind) return;
    const signature = `${kind}|${url}|${String(extra.quality_hint || "")}`;
    if (seen.has(signature)) return;
    seen.add(signature);
    results.push({ url, kind, detector, verified: false, ...extra });
  }

  const trimmed = cleaned.trimStart();
  if (trimmed.startsWith("#EXTM3U")) {
    push(baseUrl, "hls", { quality_hint: "Best Available" });
    const lines = cleaned.split(/\r?\n/);
    for (let i = 0; i < lines.length; i += 1) {
      const line = String(lines[i] || "").trim();
      if (!line.startsWith("#EXT-X-STREAM-INF:")) continue;
      const attrs = line.slice(line.indexOf(":") + 1);
      const resolution = attrs.match(/RESOLUTION=(\d+)x(\d+)/i);
      const fps = attrs.match(/FRAME-RATE=([0-9.]+)/i);
      const bandwidth = attrs.match(/(?:AVERAGE-)?BANDWIDTH=(\d+)/i);
      let uri = "";
      for (let j = i + 1; j < lines.length; j += 1) {
        const next = String(lines[j] || "").trim();
        if (!next || next.startsWith("#")) continue;
        uri = next;
        break;
      }
      if (!uri) continue;
      const height = resolution ? Number(resolution[2]) : 0;
      push(uri, "hls", {
        quality_hint: height ? `${height}p` : "HLS",
        width: resolution ? Number(resolution[1]) : 0,
        height,
        fps: fps ? Number(fps[1]) : 0,
        bitrate: bandwidth ? Number(bandwidth[1]) : 0,
        verified: true
      });
    }
  }
  if (/<MPD(?:\s|>)/i.test(trimmed.slice(0, 65536))) {
    const qualities = [];
    const repRe = /<Representation\b([^>]*)>/gi;
    let match;
    while ((match = repRe.exec(cleaned)) && qualities.length < 24) {
      const attrs = match[1] || "";
      const heightMatch = attrs.match(/\bheight=["'](\d+)["']/i);
      const widthMatch = attrs.match(/\bwidth=["'](\d+)["']/i);
      const bandwidthMatch = attrs.match(/\bbandwidth=["'](\d+)["']/i);
      const fpsMatch = attrs.match(/\bframeRate=["']([0-9.]+)["']/i);
      const height = heightMatch ? Number(heightMatch[1]) : 0;
      if (!height) continue;
      qualities.push({
        label: `${height}p`,
        height,
        width: widthMatch ? Number(widthMatch[1]) : 0,
        bitrate: bandwidthMatch ? Number(bandwidthMatch[1]) : 0,
        fps: fpsMatch ? Number(fpsMatch[1]) : 0
      });
    }
    const unique = [];
    const used = new Set();
    qualities.sort((a, b) => b.height - a.height || b.bitrate - a.bitrate).forEach((q) => {
      if (used.has(q.label)) return;
      used.add(q.label);
      unique.push(q);
    });
    push(baseUrl, "dash", { quality_hint: "Best Available", manifest_qualities: unique.slice(0, 16) });
  }

  const matches = cleaned.match(MEDIA_BODY_RE) || [];
  matches.slice(0, 120).forEach((raw) => push(raw));

  // Some ordinary player configs store a relative media path as base64. This
  // decodes only values that visibly become a standard media URL/path. It does
  // not inspect DRM/license material.
  const base64Tokens = cleaned.match(/[A-Za-z0-9+/_=-]{24,2048}/g) || [];
  base64Tokens.slice(0, 120).forEach((token) => {
    const decoded = decodeBase64Text(token);
    if (decoded) push(decoded);
  });

  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      const data = JSON.parse(cleaned);
      let budget = 0;
      const walk = (value, path = "", depth = 0) => {
        if (depth > 8 || budget++ > 1800) return;
        if (typeof value === "string") {
          const lowerPath = path.toLowerCase();
          const decoded = decodeBase64Text(value);
          if (decoded) push(decoded);
          const url = absoluteUrl(value, baseUrl);
          if (url) {
            let forced = "";
            if (/(?:^|\.)(?:hls|m3u8|master|manifest|playlist)(?:_url)?$/.test(lowerPath)) forced = "hls";
            else if (/(?:^|\.)(?:dash|mpd)(?:_url)?$/.test(lowerPath)) forced = "dash";
            else if (/(?:^|\.)(?:video|stream|source|file|media)(?:_url)?$/.test(lowerPath)) forced = classify(url) || "video";
            push(url, forced);
          }
          return;
        }
        if (Array.isArray(value)) return value.slice(0, 400).forEach((item, i) => walk(item, `${path}.${i}`, depth + 1));
        if (value && typeof value === "object") {
          Object.entries(value).slice(0, 400).forEach(([key, item]) => walk(item, path ? `${path}.${key}` : key, depth + 1));
        }
      };
      walk(data);
    } catch (_) {}
  }
  return results;
}

function debuggerAttach(target) {
  return new Promise((resolve, reject) => {
    chrome.debugger.attach(target, "1.3", () => {
      const err = chrome.runtime.lastError;
      if (err) reject(new Error(err.message)); else resolve();
    });
  });
}

function debuggerDetach(target) {
  return new Promise((resolve) => chrome.debugger.detach(target, () => resolve()));
}

function debuggerCommand(target, method, params = {}) {
  return new Promise((resolve, reject) => {
    chrome.debugger.sendCommand(target, method, params, (result) => {
      const err = chrome.runtime.lastError;
      if (err) reject(new Error(err.message)); else resolve(result || {});
    });
  });
}

async function stopDeepScan(tabId, reason = "finished") {
  const session = deepSessions.get(tabId);
  if (!session) return;
  deepSessions.delete(tabId);
  if (session.timer) clearTimeout(session.timer);
  await debuggerDetach({ tabId }).catch(() => {});
  chrome.runtime.sendMessage({ type: "DEEP_SCAN_STATE", tabId, active: false, reason }).catch(() => {});
}

async function startDeepScan(tabId, durationMs = 15000) {
  if (!Number.isInteger(tabId) || tabId < 0) throw new Error("No active browser tab.");
  if (deepSessions.has(tabId)) return { active: true, duration_ms: deepSessions.get(tabId).durationMs };

  const target = { tabId };
  await debuggerAttach(target);
  try {
    await debuggerCommand(target, "Network.enable", {
      maxTotalBufferSize: 8 * 1024 * 1024,
      maxResourceBufferSize: 2 * 1024 * 1024,
      maxPostDataSize: 0
    });
  } catch (error) {
    await debuggerDetach(target).catch(() => {});
    throw error;
  }

  const session = {
    target,
    durationMs,
    requests: new Map(),
    sniff: new Set(),
    pendingManifest: new Map(),
    timer: setTimeout(() => stopDeepScan(tabId, "finished"), durationMs)
  };
  deepSessions.set(tabId, session);
  chrome.runtime.sendMessage({ type: "DEEP_SCAN_STATE", tabId, active: true }).catch(() => {});
  return { active: true, duration_ms: durationMs };
}

chrome.debugger.onEvent.addListener(async (source, method, params) => {
  const tabId = source && source.tabId;
  const session = Number.isInteger(tabId) ? deepSessions.get(tabId) : null;
  if (!session) return;

  if (method === "Network.requestWillBeSent") {
    const req = params.request || {};
    const headers = req.headers || {};
    session.requests.set(params.requestId, {
      url: req.url || "",
      method: req.method || "GET",
      referer: headers.Referer || headers.referer || "",
      origin: headers.Origin || headers.origin || "",
      user_agent: headers["User-Agent"] || headers["user-agent"] || navigator.userAgent || "",
      frame_id: params.frameId || "",
      initiator_url: (params.initiator && params.initiator.url) || ""
    });
    return;
  }

  if (method === "Network.responseReceived") {
    const response = params.response || {};
    const url = response.url || "";
    const status = Number(response.status || 0);
    const mime = String(response.mimeType || "").toLowerCase();
    const requestType = String(params.type || "").toLowerCase();
    const req = session.requests.get(params.requestId) || {};
    const kind = status >= 200 && status < 400 ? classify(url, mime, requestType) : "";

    if (kind) {
      const tab = await chrome.tabs.get(tabId).catch(() => null);
      const pageUrl = (tab && tab.url) || req.initiator_url || req.referer || "";
      const manifestNeedsBodyCheck = ["hls", "dash"].includes(kind) && !strongManifestMime(kind, mime);
      await addCandidate(tabId, {
        url,
        page_url: pageUrl,
        frame_url: req.referer || req.initiator_url || pageUrl,
        title: (tab && tab.title) || "Detected video",
        kind,
        content_type: mime,
        status_code: status,
        content_length: Number(response.encodedDataLength || 0),
        referer: req.referer || req.initiator_url || pageUrl,
        origin: req.origin || safeOrigin(req.referer || req.initiator_url || pageUrl),
        user_agent: req.user_agent || navigator.userAgent || "",
        detector: "devtools-response",
        verified: !manifestNeedsBodyCheck
      });
      if (manifestNeedsBodyCheck) session.pendingManifest.set(params.requestId, { kind, url, pageUrl, req, mime, status });
    }

    const bodyType = /(?:json|text|javascript|mpegurl|dash\+xml|xml)/.test(mime);
    const hinted = BODY_HINT_RE.test(url);
    if (status >= 200 && status < 400 && (bodyType || hinted)) {
      session.sniff.add(params.requestId);
    }
    return;
  }

  if (method === "Network.loadingFinished" && session.sniff.has(params.requestId)) {
    session.sniff.delete(params.requestId);
    if (Number(params.encodedDataLength || 0) > MAX_BODY_BYTES) return;
    const req = session.requests.get(params.requestId) || {};
    try {
      const bodyResult = await debuggerCommand(session.target, "Network.getResponseBody", { requestId: params.requestId });
      let body = String(bodyResult.body || "");
      if (bodyResult.base64Encoded) {
        try { body = atob(body); } catch (_) { return; }
      }
      if (!body || body.length > MAX_BODY_BYTES) return;

      const pendingManifest = session.pendingManifest.get(params.requestId);
      if (pendingManifest) {
        session.pendingManifest.delete(params.requestId);
        if (bodyLooksLikeManifest(pendingManifest.kind, body)) {
          const tab = await chrome.tabs.get(tabId).catch(() => null);
          const pageUrl = (tab && tab.url) || pendingManifest.pageUrl || pendingManifest.req.referer || "";
          await addCandidate(tabId, {
            url: pendingManifest.url,
            page_url: pageUrl,
            frame_url: pendingManifest.req.referer || pageUrl,
            title: (tab && tab.title) || "Detected video",
            kind: pendingManifest.kind,
            content_type: pendingManifest.mime,
            status_code: pendingManifest.status,
            referer: pendingManifest.req.referer || pageUrl,
            origin: pendingManifest.req.origin || safeOrigin(pendingManifest.req.referer || pageUrl),
            user_agent: pendingManifest.req.user_agent || navigator.userAgent || "",
            detector: "manifest-body",
            verified: true
          });
        } else if (bodyLooksLikeErrorText(body)) {
          await removeCandidate(tabId, pendingManifest.url, pendingManifest.kind);
        }
      }

      const baseUrl = req.url || req.referer || "";
      const extracted = extractCandidatesFromText(body, baseUrl, "devtools-body");
      const tab = await chrome.tabs.get(tabId).catch(() => null);
      const pageUrl = (tab && tab.url) || req.referer || "";
      await Promise.all(extracted.map((candidate) => addCandidate(tabId, {
        ...candidate,
        page_url: pageUrl,
        frame_url: req.referer || pageUrl,
        title: (tab && tab.title) || "Detected video",
        referer: req.referer || pageUrl,
        origin: req.origin || safeOrigin(req.referer || pageUrl),
        user_agent: req.user_agent || navigator.userAgent || "",
        detector: "devtools-body"
      })));
    } catch (_) {}
    return;
  }

  if (method === "Network.loadingFailed") {
    session.sniff.delete(params.requestId);
    session.pendingManifest.delete(params.requestId);
    session.requests.delete(params.requestId);
  }
});

chrome.debugger.onDetach.addListener((source, reason) => {
  if (source && Number.isInteger(source.tabId) && deepSessions.has(source.tabId)) {
    const session = deepSessions.get(source.tabId);
    if (session.timer) clearTimeout(session.timer);
    deepSessions.delete(source.tabId);
    chrome.runtime.sendMessage({ type: "DEEP_SCAN_STATE", tabId: source.tabId, active: false, reason: reason || "detached" }).catch(() => {});
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message && message.type === "PAGE_MEDIA") {
    const tabId = sender.tab && sender.tab.id;
    const topPage = (sender.tab && sender.tab.url) || "";
    const frameUrl = sender.url || "";
    const candidates = Array.isArray(message.candidates) ? message.candidates : [];
    Promise.all(candidates.map((candidate) => addCandidate(tabId, {
      ...candidate,
      page_url: topPage || candidate.page_url || "",
      frame_url: frameUrl || candidate.frame_url || candidate.page_url || "",
      referer: candidate.referer || frameUrl || candidate.page_url || topPage || "",
      origin: candidate.origin || safeOrigin(frameUrl || candidate.page_url || topPage)
    }))).then(() => sendResponse({ ok: true }));
    return true;
  }

  if (message && message.type === "SCAN_TAB") {
    const tabId = message.tabId;
    chrome.webNavigation.getAllFrames({ tabId }).then(async (frames) => {
      const results = await Promise.all((frames || []).map((frame) =>
        chrome.tabs.sendMessage(tabId, { type: "SCAN_NOW" }, { frameId: frame.frameId }).catch(() => null)
      ));
      sendResponse({ ok: true, frames: results.filter(Boolean).length });
    }).catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }

  if (message && message.type === "DEEP_SCAN_TAB") {
    startDeepScan(message.tabId, Math.min(30000, Math.max(5000, Number(message.duration_ms || 15000))))
      .then((state) => sendResponse({ ok: true, ...state }))
      .catch((error) => sendResponse({ ok: false, error: String(error.message || error) }));
    return true;
  }

  if (message && message.type === "STOP_DEEP_SCAN") {
    stopDeepScan(message.tabId, "stopped").then(() => sendResponse({ ok: true }));
    return true;
  }

  if (message && message.type === "GET_DEEP_SCAN_STATE") {
    sendResponse({ ok: true, active: deepSessions.has(message.tabId) });
    return false;
  }

  if (message && message.type === "GET_OVERLAY_OPTIONS") {
    const tabId = sender.tab && sender.tab.id;
    const frameUrl = String(message.frame_url || sender.url || "");
    const mediaUrl = String(message.media_url || "");
    getOverlayOptions(tabId, frameUrl, mediaUrl)
      .then((options) => sendResponse({ ok: true, options }))
      .catch((error) => sendResponse({ ok: false, options: [], error: String(error) }));
    return true;
  }

  if (message && message.type === "GET_CANDIDATES") {
    getCandidates(message.tabId).then((items) => sendResponse({ ok: true, items }));
    return true;
  }

  if (message && message.type === "CLEAR_CANDIDATES") {
    setCandidates(message.tabId, []).then(() => sendResponse({ ok: true }));
    return true;
  }

  if (message && message.type === "SEND_TO_APP") {
    const rawPayload = Array.isArray(message.payload) ? message.payload : [message.payload];
    const payload = rawPayload.filter((item) => item && item.kind !== "player" && !isSensitiveUrl(item.url));
    if (!payload.length) {
      sendResponse({ ok: false, accepted: 0, error: "No direct media stream has been detected yet." });
      return false;
    }
    const body = Array.isArray(message.payload) ? payload : payload[0];
    const senderTabId = Number(message.tabId || (sender.tab && sender.tab.id) || 0);
    const enriched = Array.isArray(body)
      ? body.map((item) => ({ ...item, tab_id: senderTabId || item.tab_id || 0, group_id: item.group_id || groupIdFor(senderTabId || item.tab_id || 0, item), quality_hint: item.quality_hint || qualityHint(item.url, item.content_type || "", ""), preferred_quality: item.preferred_quality || item.quality_hint || "" }))
      : ({ ...body, tab_id: senderTabId || body.tab_id || 0, group_id: body.group_id || groupIdFor(senderTabId || body.tab_id || 0, body), quality_hint: body.quality_hint || qualityHint(body.url, body.content_type || "", ""), preferred_quality: body.preferred_quality || body.quality_hint || "" });
    sendToBridge(enriched)
      .then((data) => sendResponse(data))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }

  if (message && message.type === "CHECK_APP") {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 1200);
    fetch(`${BRIDGE_URL}/health?t=${Date.now()}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const data = await response.json().catch(() => ({}));
        if (response.ok && data.token) bridgeToken = String(data.token);
        if (response.ok) pollBridgeCommands().catch(() => {});
        sendResponse({ ok: response.ok, ...data });
      })
      .catch((error) => { bridgeToken = ""; sendResponse({ ok: false, error: String(error) }); })
      .finally(() => clearTimeout(timer));
    return true;
  }
});

chrome.webRequest.onBeforeSendHeaders.addListener(
  (details) => {
    if (details.tabId < 0) return;
    const headers = details.requestHeaders || [];
    // Deliberately do not retain Cookie, Authorization, or other credential
    // headers. The desktop app has a separate user-controlled browser-session
    // option for authorized sites.
    requestContext.set(details.requestId, {
      referer: headerValue(headers, "referer"),
      origin: headerValue(headers, "origin"),
      user_agent: headerValue(headers, "user-agent")
    });
    setTimeout(() => requestContext.delete(details.requestId), 120000);
  },
  { urls: ["<all_urls>"], types: ["media", "xmlhttprequest", "other", "object"] },
  ["requestHeaders", "extraHeaders"]
);

chrome.webRequest.onHeadersReceived.addListener(
  (details) => {
    if (details.tabId < 0) return;
    const status = Number(details.statusCode || 0);
    if (status < 200 || status >= 400) return;
    const headers = details.responseHeaders || [];
    const contentType = contentTypeFromHeaders(headers);
    const disposition = dispositionFilename(headers);
    const kind = classify(details.url, contentType, details.type, disposition);
    if (!kind) return;
    details.content_length = Number(headerValue(headers, "content-length") || 0);
    const verified = !["hls", "dash"].includes(kind) || strongManifestMime(kind, contentType);
    addNetworkCandidate(details, kind, contentType, disposition, "response-headers", verified);
  },
  { urls: ["<all_urls>"], types: ["media", "xmlhttprequest", "other", "object"] },
  ["responseHeaders", "extraHeaders"]
);

chrome.webRequest.onCompleted.addListener(
  (details) => {
    requestContext.delete(details.requestId);
  },
  { urls: ["<all_urls>"] }
);

chrome.webRequest.onErrorOccurred.addListener(
  (details) => {
    requestContext.delete(details.requestId);
  },
  { urls: ["<all_urls>"] }
);

chrome.webNavigation.onCommitted.addListener((details) => {
  if (details.frameId !== 0 || details.tabId < 0) return;
  setCandidates(details.tabId, []).catch(() => {});
  autoSent.delete(details.tabId);
  if (deepSessions.has(details.tabId)) stopDeepScan(details.tabId, "navigation").catch(() => {});
});

chrome.tabs.onRemoved.addListener((tabId) => {
  chrome.storage.local.remove(tabKey(tabId)).catch(() => {});
  autoSent.delete(tabId);
  if (deepSessions.has(tabId)) stopDeepScan(tabId, "tab-closed").catch(() => {});
});
