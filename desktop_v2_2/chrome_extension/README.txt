Shield Stream Companion 2.1
=========================

Install
1. Start Shield Stream V2.2 on Windows.
2. Open chrome://extensions in Chrome / Edge / Brave / Opera / Vivaldi.
3. Enable Developer mode.
4. Choose Load unpacked and select this chrome_extension folder.
5. Refresh any already-open video page once.

Recommended capture flow
1. Start playback.
2. Open the Shield Stream extension.
3. Use Quick scan first.
4. If the stream is embedded/dynamic, use Power scan 30s and keep playback running.
5. VERIFIED HLS/DASH/VIDEO/AUDIO candidates are the strongest choices.
6. Send one stream, Send All, or enable Auto-send verified streams.

V2.2 additions
- 30-second deep network capture across nested frames.
- Fetch/XHR/player config, response-header and DevTools response-body inspection.
- Open Shadow DOM and live PerformanceObserver scanning.
- Plain-text/small WebSocket message scanning for standard media URLs.
- HLS/DASH/direct video/audio detection, extensionless media detection and false-positive filtering.
- Quality hints and logical grouping metadata sent to the desktop app.
- Secure per-session localhost pairing token.
- Optional auto-send of VERIFIED streams.
- IDM-style Download button appears directly over playing HTML5 video players.
- Clicking the button opens a quality menu (Best/1080p/720p/480p/etc. when detected).
- Choosing a quality sends that exact stream/preferred quality to the desktop app; it does not auto-download.
- HLS master playlists discovered during Power Scan expose child quality variants; DASH manifests can expose selectable preferred qualities.
- Tab candidate data is automatically forgotten when the tab closes.

Safety / limitations
- Standard non-DRM media only. The extension deliberately ignores DRM/license endpoints.
- It does not collect Cookie or Authorization request headers.
- Use browser-session support in the desktop app only for content you are authorized to access.
- Chrome may show a debugger permission warning during Power Scan because the official chrome.debugger Network API is used.
- Close DevTools on the same tab if Power Scan cannot attach.
