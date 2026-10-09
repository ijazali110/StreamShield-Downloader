# Shield Stream V2.2 On-Video Download Menu

Shield Stream V2.2 keeps the V2.0.1 preview reliability fixes and adds an IDM-style on-video quality menu in the Chrome companion. It keeps the clean desktop UI and Chrome companion while adding smart stream grouping, quality discovery, preview-before-download, refreshable browser captures, resumable transfers, history/duplicate protection and stronger privacy/security.

## Main workflow

**Play video -> On-video Download button -> Choose quality -> Shield Stream -> Preview -> Download**

The app is intended for standard non-DRM media and content you are authorized to download. It does not bypass Widevine, PlayReady, FairPlay, paywalls or other access controls.

## V2.2 feature set

### Smart stream resolver
- Browser candidates from the same page/player are grouped into one logical video card.
- Fresh captures replace/merge matching quality variants instead of creating endless duplicate rows.
- Browser candidates can include quality hints such as 1080p / 720p when the URL exposes them.
- Real yt-dlp format probing is used for HLS/DASH/direct streams when possible.

### Manifest / quality discovery
- HLS and DASH streams are probed for available formats.
- The card quality menu can populate with actual representations, bitrate/FPS/language-derived labels.
- Separate DASH video/audio tracks remain handled by yt-dlp/FFmpeg so compatible audio can be merged into the final output.

### Preview before download
- Every result card has a **Play / Preview** button.
- Headerless/local media uses the in-app Qt video preview window.
- Header-bound HLS/DASH/direct streams use `ffplay` when it is already available.
- **New in V2.0.1:** if `ffplay` is missing, Shield Stream automatically uses the bundled/system `ffmpeg` to create a short 30-second local compatibility preview with the required safe Referer/Origin/User-Agent headers, then opens that clip inside the app.
- The old "ffplay is not installed" hard-stop is therefore removed for normal preview verification.
- If a normal webpage result does not yet have a direct preview stream, Shield Stream resolves formats on demand before opening preview.

### Expiring URL refresh
- Browser captures are marked refreshable and timestamped.
- Old signed/CDN URLs trigger a fresh-stream warning instead of blindly failing.
- The app can queue a **Refresh from Chrome** request for the original browser tab.
- While the extension popup is connected, it can run a fresh capture and send matching candidates back; the desktop card merges the new stream.
- 403/404/expired-token failures automatically request a fresh capture when a browser-tab link is available.

### IDM-style on-video Download menu
- A small **Download** toggle appears on top of a playing HTML5 video instead of floating at the page corner.
- Works inside normal pages and accessible embedded/iframe players because the content script runs in all permitted frames.
- Click the toggle to open a compact quality menu directly over the player.
- The menu groups the strongest detected variants and shows labels such as **Best Available, 1080p, 720p, 480p, Audio** when those variants are exposed.
- VERIFIED network candidates are preferred automatically.
- During Power Scan, HLS master playlists are parsed for child resolution playlists; DASH manifests expose preferred resolution choices when representations are visible.
- Clicking a quality **does not start an uncontrolled browser download**. It securely sends that selected stream/preferred quality to Shield Stream, where the normal Preview and Download controls remain available.
- If Shield Stream later resolves a richer format list, the quality chosen in Chrome is automatically preselected in the desktop card.
- The on-video menu is enabled by default and can be disabled from the extension popup.

### Chrome companion V2
- Quick scan + **Power scan 30s**.
- Nested iframes, page DOM, open Shadow DOM, video/source tags, common data attributes.
- Fetch/XHR interception and small player/config response inspection.
- DevTools Network response headers/body capture during Power Scan.
- HLS `.m3u8`, DASH `.mpd`, direct video/audio and extensionless media responses.
- PerformanceObserver/live resource detection.
- Plain-text/small WebSocket message inspection for standard media URLs.
- False-positive filtering for segments, HTML errors, 403/404 responses and DRM/license endpoints.
- Optional **Auto-send VERIFIED streams**.
- Optional/on-by-default **IDM-style Download quality menu directly on playing videos**.
- Candidate data is removed when the tab closes.

### Reliable downloads
- Resume is enabled through `.part` files / yt-dlp continuation.
- HLS/DASH fragment concurrency.
- `Normal`, `Fast`, `Maximum` speed modes.
- Maximum mode can use optional `aria2c` for accelerated progressive HTTP transfers.
- Smart format fallback retries when an exact representation disappears.
- Existing FFmpeg merge and MP3 extraction support remains.
- Small HTML/text/security-error responses are rejected instead of being reported as successful videos.

### Subtitles
- Optional subtitle/caption download in Settings.
- User can provide preferred language patterns such as `en.*, ur.*, hi.*`.
- Compatible subtitles are embedded when supported by the output/container.

### Download history + duplicate protection
- Completed downloads can be stored in a local SQLite history database.
- History is restored into the Downloads page across restarts.
- If the same media is downloaded again, Shield Stream offers **Open Existing / Download Again / Cancel**.
- History can be disabled in Settings.
- Browser cookies, Authorization headers and session credentials are never stored in history.

### Filename intelligence
- Titles are used for human-readable filenames.
- Windows-illegal filename characters are sanitized by yt-dlp / direct-file logic.
- Generic direct-file URLs use Content-Disposition filenames when safely available.

### Privacy / security
- Chrome -> desktop writes use a random per-process pairing token.
- Local bridge binds to `127.0.0.1` only.
- Normal webpage Origins are rejected.
- Extension payload size is limited and URL schemes are validated.
- Cookie/Authorization headers are deliberately not copied by the extension.
- Browser candidate storage is removed when a tab closes.
- Local completed-download history can be disabled.

### Chromium browser support
The unpacked MV3 extension is designed for current Chromium-family browsers including Chrome, Edge, Brave, Opera and Vivaldi. Browser policies can vary by installation.

### Direct download-manager foundation
Pasted direct video/audio/HLS/DASH URLs remain supported. V2.2 also includes resumable HTTP handling for common direct files (for example PDF/ZIP/images) without cluttering the video-focused UI.

## Install / run

1. Extract V2.2 into a fresh folder.
2. Run `run_windows.bat`.
3. Install the extension from the `chrome_extension` folder using `chrome://extensions` -> Developer mode -> Load unpacked.
4. Refresh already-open video pages after installing/updating the extension.

Optional helpers:
- `install_ffmpeg_windows.bat` - full FFmpeg/ffplay support when needed.
- `install_aria2_windows.bat` - optional Maximum speed accelerator.
- `diagnose_windows.bat` - environment diagnostics.
- `build_exe.bat` - Windows PyInstaller build.

## Recommended browser capture flow

1. Play the video.
2. Quick scan.
3. If only a player is found, run **Power scan 30s** and keep playback active.
4. Prefer VERIFIED candidates.
5. Send to Shield Stream.
6. Use the **Play** button on the result card to verify the media before downloading.
7. Choose the quality and download.

## Important limitations

No tool can guarantee every website. Sites can use DRM, encrypted Media Source Extensions, short-lived signed URLs, browser-only authorization, anti-bot protections or custom protocols. Shield Stream deliberately does not bypass DRM/access controls. Its browser capture system focuses on standard media streams that the browser legitimately exposes during playback.
