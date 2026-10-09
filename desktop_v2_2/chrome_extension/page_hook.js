(() => {
  "use strict";

  const CANDIDATE_EVENT = "streamforge-media-candidate-v19";
  const DEEP_SCAN_EVENT = "streamforge-deep-scan-v19";
  const DIRECT_RE = /\.(mp4|webm|mov|mkv|m4v|avi|wmv|flv|mp3|m4a|aac|ogg|opus|wav|flac)(?:$|[?#])/i;
  const HLS_RE = /\.m3u8(?:$|[?#])/i;
  const DASH_RE = /\.mpd(?:$|[?#])/i;
  const URL_HINT_RE = /(manifest|master|playlist|hls|dash|stream|video|source|player|index)/i;
  const MAX_TEXT = 1024 * 1024;

  function safeHttp(url) {
    return typeof url === "string" && /^https?:\/\//i.test(url);
  }

  function absolute(raw, base = location.href) {
    if (!raw || /^blob:|^data:/i.test(String(raw))) return "";
    try {
      const value = new URL(String(raw), base).href;
      return safeHttp(value) ? value : "";
    } catch (_) {
      return "";
    }
  }

  function classify(url, contentType = "") {
    const ct = String(contentType || "").toLowerCase();
    if (HLS_RE.test(url) || /(?:application|audio)\/(?:vnd\.apple\.)?mpegurl|application\/x-mpegurl/.test(ct)) return "hls";
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

  function emit(rawUrl, kind = "", extra = {}) {
    const url = absolute(rawUrl, extra.base_url || location.href);
    if (!url) return;
    const resolvedKind = kind || classify(url, extra.content_type || "");
    if (!resolvedKind) return;
    const payload = {
      url,
      kind: resolvedKind,
      frame_url: location.href,
      title: document.title || "Detected video",
      content_type: String(extra.content_type || ""),
      detector: String(extra.detector || "page-hook")
    };
    try {
      window.dispatchEvent(new CustomEvent(CANDIDATE_EVENT, { detail: JSON.stringify(payload) }));
    } catch (_) {}
  }

  function emitFromJson(value, baseUrl, path = "", depth = 0, budget = { count: 0 }) {
    if (depth > 7 || budget.count > 1200) return;
    budget.count += 1;

    if (typeof value === "string") {
      const decoded = decodeMediaBase64(value);
      if (decoded) emit(decoded, "", { base_url: baseUrl, detector: "base64-json-config" });
      const url = absolute(value, baseUrl);
      if (!url) return;
      let kind = classify(url);
      const key = path.toLowerCase();
      if (!kind) {
        if (/(^|\.)(hls|hls_url|m3u8|master|master_url|playlist|playlist_url)$/.test(key)) kind = "hls";
        else if (/(^|\.)(dash|dash_url|mpd|mpd_url)$/.test(key)) kind = "dash";
        else if (/(^|\.)(video|video_url|stream|stream_url|file|file_url|media|media_url)$/.test(key)) kind = "video";
      }
      if (kind) emit(url, kind, { base_url: baseUrl, detector: "json-config" });
      return;
    }

    if (Array.isArray(value)) {
      value.slice(0, 300).forEach((item, index) => emitFromJson(item, baseUrl, `${path}.${index}`, depth + 1, budget));
      return;
    }

    if (value && typeof value === "object") {
      Object.entries(value).slice(0, 300).forEach(([key, item]) => {
        const next = path ? `${path}.${key}` : key;
        emitFromJson(item, baseUrl, next, depth + 1, budget);
      });
    }
  }

  function extractUrlsFromText(text, baseUrl) {
    if (typeof text !== "string" || !text || text.length > MAX_TEXT) return;
    const cleaned = text.replace(/\\u0026/gi, "&").replace(/\\\//g, "/").replace(/&amp;/gi, "&");
    const trimmed = cleaned.trimStart();

    if (trimmed.startsWith("#EXTM3U")) emit(baseUrl, "hls", { detector: "manifest-body" });
    if (/<MPD(?:\s|>)/i.test(trimmed.slice(0, 32768))) emit(baseUrl, "dash", { detector: "manifest-body" });

    const mediaUrlRe = /(?:https?:\/\/|\/\/|\/)[^\s"'<>\\]{1,1900}?\.(?:m3u8|mpd|mp4|webm|m4v|mov|mp3|m4a)(?:\?[^\s"'<>\\]{0,1900})?/gi;
    const matches = cleaned.match(mediaUrlRe) || [];
    matches.slice(0, 120).forEach((raw) => emit(raw.startsWith("//") ? `${location.protocol}${raw}` : raw, "", { base_url: baseUrl, detector: "text-config" }));

    const tokens = cleaned.match(/[A-Za-z0-9+/_=-]{24,2048}/g) || [];
    tokens.slice(0, 100).forEach((token) => {
      const decoded = decodeMediaBase64(token);
      if (decoded) emit(decoded, "", { base_url: baseUrl, detector: "base64-text-config" });
    });

    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      try {
        emitFromJson(JSON.parse(cleaned), baseUrl);
      } catch (_) {}
    }
  }

  function shouldSniff(url, contentType, contentLength) {
    const ct = String(contentType || "").toLowerCase();
    const length = Number(contentLength || 0);
    if (length > MAX_TEXT) return false;
    if (/json|text|javascript|mpegurl|dash\+xml/.test(ct)) return true;
    if (/octet-stream/.test(ct) && URL_HINT_RE.test(url)) return true;
    if (!ct && URL_HINT_RE.test(url)) return true;
    return false;
  }

  async function inspectFetchResponse(response, requestedUrl) {
    try {
      const responseUrl = response.url || absolute(requestedUrl) || "";
      if (!responseUrl) return;
      const contentType = response.headers.get("content-type") || "";
      const contentLength = response.headers.get("content-length") || "";
      const kind = classify(responseUrl, contentType);
      if (kind) emit(responseUrl, kind, { content_type: contentType, detector: "fetch-response" });
      if (!shouldSniff(responseUrl, contentType, contentLength)) return;
      const clone = response.clone();
      const text = await clone.text();
      extractUrlsFromText(text, responseUrl);
    } catch (_) {}
  }

  try {
    const nativeFetch = window.fetch;
    if (typeof nativeFetch === "function" && !nativeFetch.__streamforgeWrapped) {
      const wrappedFetch = function (...args) {
        const requestUrl = args[0] && typeof args[0] === "object" ? args[0].url : args[0];
        return nativeFetch.apply(this, args).then((response) => {
          inspectFetchResponse(response, requestUrl);
          return response;
        });
      };
      try { Object.defineProperty(wrappedFetch, "__streamforgeWrapped", { value: true }); } catch (_) {}
      window.fetch = wrappedFetch;
    }
  } catch (_) {}

  try {
    const proto = XMLHttpRequest.prototype;
    const nativeOpen = proto.open;
    const nativeSend = proto.send;

    proto.open = function (method, url, ...rest) {
      try { this.__streamforgeUrl = absolute(url); } catch (_) {}
      return nativeOpen.call(this, method, url, ...rest);
    };

    proto.send = function (...args) {
      if (!this.__streamforgeBound) {
        this.__streamforgeBound = true;
        this.addEventListener("loadend", () => {
          try {
            const url = this.responseURL || this.__streamforgeUrl || "";
            const contentType = this.getResponseHeader("content-type") || "";
            const kind = classify(url, contentType);
            if (kind) emit(url, kind, { content_type: contentType, detector: "xhr-response" });

            if (this.responseType === "" || this.responseType === "text") {
              const text = this.responseText || "";
              if (text.length <= MAX_TEXT) extractUrlsFromText(text, url);
            } else if (this.responseType === "blob" && this.response && this.response.size <= MAX_TEXT && shouldSniff(url, contentType, this.response.size)) {
              this.response.text().then((text) => extractUrlsFromText(text, url)).catch(() => {});
            } else if (this.responseType === "arraybuffer" && this.response && this.response.byteLength <= MAX_TEXT && shouldSniff(url, contentType, this.response.byteLength)) {
              try {
                const text = new TextDecoder("utf-8", { fatal: false }).decode(this.response);
                extractUrlsFromText(text, url);
              } catch (_) {}
            }
          } catch (_) {}
        }, { once: false });
      }
      return nativeSend.apply(this, args);
    };
  } catch (_) {}


  // Some player frameworks receive signed stream URLs through WebSocket
  // messages. Observe plain text/small Blob messages and scan only for standard
  // media URLs; credentials and DRM/license endpoints are not captured.
  try {
    const NativeWebSocket = window.WebSocket;
    if (typeof NativeWebSocket === "function" && !NativeWebSocket.__streamforgeWrapped) {
      const WrappedWebSocket = function (...args) {
        const socket = new NativeWebSocket(...args);
        socket.addEventListener("message", (event) => {
          try {
            if (typeof event.data === "string" && event.data.length <= MAX_TEXT) {
              extractUrlsFromText(event.data, socket.url || location.href);
            } else if (event.data instanceof Blob && event.data.size <= MAX_TEXT) {
              event.data.text().then((text) => extractUrlsFromText(text, socket.url || location.href)).catch(() => {});
            }
          } catch (_) {}
        });
        return socket;
      };
      WrappedWebSocket.prototype = NativeWebSocket.prototype;
      Object.setPrototypeOf(WrappedWebSocket, NativeWebSocket);
      try { Object.defineProperty(WrappedWebSocket, "__streamforgeWrapped", { value: true }); } catch (_) {}
      window.WebSocket = WrappedWebSocket;
    }
  } catch (_) {}

  try {
    const perfObserver = new PerformanceObserver((list) => {
      list.getEntries().forEach((entry) => {
        const url = entry && entry.name;
        const kind = safeHttp(url) ? classify(url) : "";
        if (kind) emit(url, kind, { detector: "performance-observer" });
      });
    });
    perfObserver.observe({ type: "resource", buffered: false });
  } catch (_) {}

  function scanPerformance() {
    try {
      performance.getEntriesByType("resource").slice(-600).forEach((entry) => {
        const url = entry && entry.name;
        const kind = safeHttp(url) ? classify(url) : "";
        if (kind) emit(url, kind, { detector: "performance" });
      });
    } catch (_) {}
  }

  window.addEventListener(DEEP_SCAN_EVENT, scanPerformance, false);
  setTimeout(scanPerformance, 1200);
  setTimeout(scanPerformance, 4500);
})();
