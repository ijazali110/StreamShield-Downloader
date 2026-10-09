let currentTab = null;
let candidates = [];
let appTimer = null;
let scanPoll = null;
let deepEndsAt = 0;

const connection = document.getElementById("connection");
const pageTitle = document.getElementById("pageTitle");
const pageUrl = document.getElementById("pageUrl");
const countText = document.getElementById("countText");
const empty = document.getElementById("empty");
const list = document.getElementById("list");
const sendAllBtn = document.getElementById("sendAllBtn");
const message = document.getElementById("message");
const deepScanBtn = document.getElementById("deepScanBtn");
const deepState = document.getElementById("deepState");
const autoSend = document.getElementById("autoSend");
const floatingButton = document.getElementById("floatingButton");

function setMessage(text, type = "") {
  message.textContent = text || "";
  message.className = `message ${type}`;
}

function shortHost(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch (_) { return "media"; }
}

function displayTitle(item) {
  if (item.kind === "player") return "Embedded player detected";
  if (item.kind === "hls") return "HLS video stream";
  if (item.kind === "dash") return "DASH video stream";
  if (item.kind === "audio") return "Audio stream";
  return item.title || "Detected video";
}

function sendableItems() {
  return candidates.filter((item) => item && ["video", "audio", "hls", "dash", "page"].includes(item.kind));
}

function render() {
  list.innerHTML = "";
  const sendable = sendableItems();
  const verified = sendable.filter((item) => item.verified).length;
  const players = candidates.filter((item) => item && item.kind === "player");
  const parts = [`${sendable.length} stream${sendable.length === 1 ? "" : "s"}`];
  if (verified) parts.push(`${verified} verified`);
  if (players.length) parts.push(`${players.length} player${players.length === 1 ? "" : "s"}`);
  countText.textContent = parts.join("  |  ");
  empty.style.display = candidates.length ? "none" : "block";
  sendAllBtn.disabled = !sendable.length;

  candidates.forEach((item) => {
    const row = document.createElement("div");
    row.className = `media-item ${item.kind === "player" ? "hint-item" : ""} ${item.verified ? "verified" : ""}`;
    const copy = document.createElement("div");
    copy.innerHTML = `
      <div class="media-title"></div>
      <div class="media-meta">
        <span class="chip"></span>
        <span class="verify-chip" style="display:none"></span>
        <span class="media-url"></span>
      </div>`;
    copy.querySelector(".media-title").textContent = displayTitle(item);
    copy.querySelector(".chip").textContent = item.quality_hint ? `${item.kind || "media"} • ${item.quality_hint}` : (item.kind || "media");
    if (item.verified) {
      const verifiedChip = copy.querySelector(".verify-chip");
      verifiedChip.style.display = "inline-block";
      verifiedChip.textContent = "verified";
    }
    const status = item.status_code ? ` • ${item.status_code}` : "";
    copy.querySelector(".media-url").textContent = `${shortHost(item.url)}${status}`;

    const button = document.createElement("button");
    if (item.kind === "player") {
      button.className = "send-one wait";
      button.textContent = "Hint";
      button.disabled = true;
      button.title = "This is a player frame, not a downloadable media stream.";
    } else {
      button.className = "send-one";
      button.textContent = "Send";
      button.addEventListener("click", () => sendPayload(item, button));
    }

    row.append(copy, button);
    list.appendChild(row);
  });

  if (!sendable.length && players.length) {
    setMessage("Player found, but no stream yet. Keep playback running and use Power scan 30s.");
  }
}

function getCandidates(delay = 0) {
  if (!currentTab || !currentTab.id) return;
  setTimeout(() => {
    chrome.runtime.sendMessage({ type: "GET_CANDIDATES", tabId: currentTab.id }, (response) => {
      candidates = (response && response.items) || [];
      render();
    });
  }, delay);
}

function checkApp() {
  chrome.runtime.sendMessage({ type: "CHECK_APP" }, (response) => {
    const ok = Boolean(response && response.ok);
    connection.textContent = ok ? "Connected" : "App closed";
    connection.className = `status ${ok ? "online" : "offline"}`;
  });
}

function updateDeepState(active) {
  if (!active) {
    deepScanBtn.disabled = false;
    deepScanBtn.classList.remove("active");
    deepScanBtn.textContent = "Power scan 30s";
    deepState.textContent = "";
    deepState.className = "deep-state";
    if (scanPoll) { clearInterval(scanPoll); scanPoll = null; }
    return;
  }
  const seconds = Math.max(0, Math.ceil((deepEndsAt - Date.now()) / 1000));
  deepScanBtn.disabled = true;
  deepScanBtn.classList.add("active");
  deepScanBtn.textContent = `Scanning ${seconds}s`;
  deepState.textContent = "Power capture is active across the page and embedded frames. Keep the video playing.";
  deepState.className = "deep-state active";
}

function sendPayload(payload, button = null) {
  if (payload && payload.kind === "player") {
    setMessage("That item is only an embedded player. Use Power scan while playback is running.", "error");
    return;
  }
  if (button) { button.disabled = true; button.textContent = "Sending..."; }
  chrome.runtime.sendMessage({ type: "SEND_TO_APP", payload, tabId: currentTab && currentTab.id }, (response) => {
    const ok = Boolean(response && response.ok && response.accepted > 0);
    if (button) { button.disabled = false; button.textContent = ok ? "Sent" : "Retry"; }
    const text = ok ? "Sent to Shield Stream." : ((response && response.error) || "Open Shield Stream on this PC, then retry.");
    setMessage(text, ok ? "ok" : "error");
    checkApp();
  });
}

async function init() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  currentTab = tabs[0] || null;
  pageTitle.textContent = (currentTab && currentTab.title) || "Current page";
  pageUrl.textContent = (currentTab && currentTab.url) || "";
  checkApp();
  chrome.storage.local.get(["sf_auto_send_verified", "sf_floating_button"]).then((data) => {
    autoSend.checked = Boolean(data.sf_auto_send_verified);
    const firstRun = typeof data.sf_floating_button === "undefined";
    floatingButton.checked = firstRun ? true : Boolean(data.sf_floating_button);
    if (firstRun) chrome.storage.local.set({ sf_floating_button: true }).catch(() => {});
  }).catch(() => {});
  getCandidates();
  appTimer = setInterval(checkApp, 1800);
  if (currentTab && currentTab.id) {
    chrome.runtime.sendMessage({ type: "GET_DEEP_SCAN_STATE", tabId: currentTab.id }, (response) => {
      if (response && response.active) {
        deepEndsAt = Date.now() + 30000;
        updateDeepState(true);
        scanPoll = setInterval(() => { getCandidates(); updateDeepState(true); }, 1000);
      }
    });
  }
}

document.getElementById("scanBtn").addEventListener("click", () => {
  if (!currentTab || !currentTab.id) return;
  setMessage("Scanning page and embedded frames...");
  chrome.runtime.sendMessage({ type: "SCAN_TAB", tabId: currentTab.id }, (response) => {
    if (!response || !response.ok) {
      setMessage("Could not scan this page. Refresh the page and try again.", "error");
      return;
    }
    getCandidates(300);
    getCandidates(1000);
    setTimeout(() => {
      if (!sendableItems().length) setMessage("No stream yet. Keep playback running, then use Power scan 30s.");
    }, 1300);
  });
});

deepScanBtn.addEventListener("click", () => {
  if (!currentTab || !currentTab.id) return;
  setMessage("Starting deep network capture...");
  chrome.runtime.sendMessage({ type: "DEEP_SCAN_TAB", tabId: currentTab.id, duration_ms: 30000 }, (response) => {
    if (!response || !response.ok) {
      const detail = (response && response.error) || "Power scan could not start.";
      setMessage(`${detail} Close DevTools for this tab if it is open, then retry.`, "error");
      return;
    }
    deepEndsAt = Date.now() + Number(response.duration_ms || 30000);
    updateDeepState(true);
    if (scanPoll) clearInterval(scanPoll);
    scanPoll = setInterval(() => {
      getCandidates();
      if (Date.now() >= deepEndsAt) {
        updateDeepState(false);
        getCandidates(250);
        if (!sendableItems().length) setMessage("Power scan finished. No standard non-DRM stream was exposed by the browser.");
      } else {
        updateDeepState(true);
      }
    }, 850);
  });
});

chrome.runtime.onMessage.addListener((msg) => {
  if (!currentTab || !msg || msg.type !== "DEEP_SCAN_STATE" || msg.tabId !== currentTab.id) return;
  if (!msg.active) {
    updateDeepState(false);
    getCandidates(150);
  }
});

document.getElementById("sendPageBtn").addEventListener("click", () => {
  if (!currentTab || !currentTab.url || !/^https?:\/\//i.test(currentTab.url)) return;
  sendPayload({
    url: currentTab.url,
    page_url: currentTab.url,
    title: currentTab.title || "Current page",
    kind: "page",
    source: "chrome-extension"
  });
});

document.getElementById("clearBtn").addEventListener("click", () => {
  if (!currentTab || !currentTab.id) return;
  chrome.runtime.sendMessage({ type: "CLEAR_CANDIDATES", tabId: currentTab.id }, () => {
    candidates = [];
    render();
    setMessage("");
  });
});

sendAllBtn.addEventListener("click", () => {
  const sendable = sendableItems();
  if (!sendable.length) return;
  sendAllBtn.disabled = true;
  sendAllBtn.textContent = "Sending...";
  chrome.runtime.sendMessage({ type: "SEND_TO_APP", payload: sendable }, (response) => {
    const accepted = Number((response && response.accepted) || 0);
    const ok = Boolean(response && response.ok && accepted > 0);
    const text = ok
      ? `${accepted} item${accepted === 1 ? "" : "s"} sent to Shield Stream.`
      : ((response && response.error) || "Open Shield Stream on this PC, then retry.");
    setMessage(text, ok ? "ok" : "error");
    sendAllBtn.disabled = false;
    sendAllBtn.textContent = "Send all streams to Shield Stream";
    checkApp();
  });
});

window.addEventListener("unload", () => {
  if (appTimer) clearInterval(appTimer);
  if (scanPoll) clearInterval(scanPoll);
});

init();


autoSend.addEventListener("change", () => {
  chrome.storage.local.set({ sf_auto_send_verified: Boolean(autoSend.checked) }).catch(() => {});
  setMessage(autoSend.checked ? "Verified streams will be sent automatically while this option is enabled." : "Auto-send disabled.", "ok");
});


floatingButton.addEventListener("change", () => {
  chrome.storage.local.set({ sf_floating_button: Boolean(floatingButton.checked) }).catch(() => {});
  setMessage(floatingButton.checked ? "On-video Download menu enabled for playing videos." : "On-video Download menu disabled.", "ok");
});
