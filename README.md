# Shield Stream 3.4.1 — Direct YouTube video and MP3 transfers

The public homepage accepts one individual YouTube video/Shorts URL. Analyze reveals available clear direct HTTP media tracks, including split video/audio tracks, without a 720p, duration or file-size cap. Choose video quality or MP3 audio (real 192 kbps conversion). Batch belongs to the planned Personal tier. Free keeps the existing 10 downloads/day per observed IP; live and protected sources remain unavailable. Formats that require a segmented manifest downloader are not included in this streaming pilot.

Public downloads never create a media file, segment file or job directory on the VPS. Short-lived encrypted, guest-bound selection tokens hold URLs in the browser until submitted through a CSRF-protected POST. Guarded Python reads feed FFmpeg through bounded pipes; the output is streamed directly to the browser. Video is copied to fragmented MP4, audio is converted to AAC; MP3 is converted with libmp3lame. One public transfer at a time protects the VPS. There are no total duration/size limits, but idle connection timeouts and source access restrictions apply. No media or source URLs enter the public jobs database; daily abuse protection stores only hashed IP counters and timestamps. Nginx response buffering and disk temporary media files are disabled; small POST bodies fit in the configured memory buffer. Your device stores the completed download. Interrupted transfers require a fresh analysis/retry.

Existing private owner queue/download files remain available and use the legacy on-disk workflow. They were not deleted or converted. Personal/Studio subscriptions and their eventual direct transfer workflows are not implemented or being sold yet.

Validation: 42 tests passed locally and on the VPS. Operator HTTPS tests streamed and probed the original synthetic fixture as MP4 (4,169,206 bytes) and MP3 (193,245 bytes), with no new retained VPS media files. This verifies the relay/conversion pipeline, not successful YouTube extraction from the VPS.

Ads: empty labelled `home-banner` and `results` placements remain hidden until a provider/IDs are supplied. No click simulation, forced ad clicks, hidden ad frames or Analyze/Download ad navigation is present. Actual provider setup still needs consent/privacy handling, domain approval and provider-specific integration.

The logged-in owner workspace opens a dedicated YouTube Downloader tab, using the same single-link quality/MP3 direct-transfer form as the public homepage. The form is moved between containers on login/logout, so selections and event handlers are preserved without duplicate element IDs. Sources remains a separate tab for supported website/media analysis. Login does not resolve YouTube server verification.

Workspace login opens the existing private owner dashboard using the configured password. Paid plans, customer accounts, checkout, subscriptions and entitlements are not implemented. The current password grants owner access and should not be sold/shared as a customer subscription.

Install app controls start hidden and appear only with Chrome's install prompt outside standalone/minimal-ui/fullscreen mode. The appinstalled event and display-mode changes hide the controls immediately. Android physical device behavior remains to be checked by the owner.

YouTube extraction uses yt-dlp[default], the matching EJS component and Node 22+ if installed. YouTube can refuse requests from a VPS; availability is not guaranteed. No cookie import, proxies, fingerprint workarounds or account bypass are configured for free users. Native app playback does not reveal a downloadable URL to this server. Use the existing desktop companion for supported non-DRM website/network capture; protected service titles remain in the providers' official download flows.

Previous workspace details below describe the private dashboard.

# Shield Stream 3.2 — VPS media workspace + owned-media lab

Includes the uploaded V2.1 Windows desktop app and Chrome extension, with Shield Stream display branding, in `desktop_v2_1/`, plus a new private web companion in `server/`.

## Live test workspace

https://tool.vieapps.cloud/streamforge/

Use the private password supplied separately. Select **Public external video**, Analyze, then Add to queue. Open Downloads to save the final file to your device. For HLS qualities, analyze `https://tool.vieapps.cloud/streamforge/test/master.m3u8`. The protected manifest fixture at `/streamforge/test/protected.mpd` should report **Widevine Protected** and offer inspection only.

## Implemented in the web companion

- URL analysis via yt-dlp; static embedded-media fallback; public HTTP(S) URLs only
- HLS/DASH manifest inspection; quality, codec, bitrate, language and subtitle metadata
- Select video format and separate audio track; FFmpeg merge; optional subtitle sidecars
- Browser-compatible direct-stream preview; sources needing request headers may require desktop preview
- One concurrent download; four fragment connections; persistent SQLite history and queue
- Pause/cancel, manual retry/resume of partial files, manual signed-URL replacement on retry
- Scheduling in local time; bandwidth limits; duration-limited clear MPEG-TS HLS live recording (DASH live and fragmented-MP4 live are unsupported; not validated against a real live broadcast)
- Duplicate protection for active URL/format selections; per-job 2 GB and total 10 GB limits
- FFprobe output validation; job files can be saved to your device with Range support
- Private password login, HttpOnly/Strict cookies, CSRF token, same-origin checks and login attempt limits
- Isolated network worker; every DNS result checked against private/local addresses
- Sanitized diagnostic JSON export; session headers stay in memory and are not stored in SQLite
- Service restarts mark unfinished work paused; re-supply authorization headers when retrying
- Custom owned-media AES-256-GCM lab: local uploads up to 32 MB, explicit user-supplied key, authenticated decrypt, wrong-key rejection. Keys/files in this lab are not persisted.

## What this version does not claim

- Third-party DRM/license/CDM extraction or protected streaming-service decryption
- Arbitrary encrypted HLS/DASH/CENC decryption: remote encrypted manifests are inspection-only
- Automatic signed-URL refresh, cloud access to your Chrome login, dynamic page/network capture in the VPS dashboard, Netflix/Prime download adapters
- Windows executable build: the included desktop source remains V2.1

Use the existing desktop + extension for local browser network capture, Power Scan, embedded iframe discovery and on-video controls. Its localhost bridge remains local and has not been exposed on the VPS. The new web workspace does not receive browser extension captures automatically.

The lab uses **a custom Shield Stream container, not a streaming-service DRM format**. On your dummy website, you may publish standard non-DRM MP4/HLS/DASH for downloader testing. The separate local-file lab tests explicit-key encryption round trips.

## Local web use

Install Python 3.10+ and FFmpeg/FFprobe on PATH. Install `server/requirements.txt`. Set `STREAMFORGE_PASSWORD` (at least 16 characters), `STREAMFORGE_DATA`, and optionally `STREAMFORGE_PORT` (default 8122). Run `python -m server.app` from this folder. For local HTTP testing only, set `STREAMFORGE_SECURE_COOKIE=0`. Use `http://127.0.0.1:8122/`.

The `run_web_local.bat` launcher provides this setup on Windows. Install FFmpeg/FFprobe first. Server deployment files are in `deploy/`. The live VPS process is Linux; Windows local mode uses the Python process termination fallback.

## Tests

`python -m unittest discover -s tests -v`

Run `python deploy/make_demo.py` to create synthetic media fixtures with FFmpeg. No stock or copyrighted videos are included.

## VPS operations

Service: `streamforge3.service` uses an isolated systemd DynamicUser; code: `/opt/streamforge3`; data: `/var/lib/streamforge3`; private environment: `/etc/streamforge3.env`; bind address: `127.0.0.1:8122`. Login password is not included in this ZIP. Edit the environment file and restart the service to change it. Existing services are preserved. Nginx routes only `/streamforge/` to the new app on the existing HTTPS subdomain.

The dashboard retains downloads until you delete the job. Resource caps: one CPU, 1 GB memory; media storage caps enforced separately. No new subdomain DNS entry was created because DNS management was not available in this session.

Live recordings restart when retried; ordinary file downloads resume supported partial files.

## 3.0.1 compatibility fix

OK.ru embedded metadata accepts both pre-decoded objects and legacy JSON strings through a scoped extractor registration. Both analysis and downloads use this registration. Manifest verification preserves extractor-provided request headers. Four regression checks cover the object response, legacy text, malformed JSON, and header-dependent manifests.

## 3.1 mobile and dashboard update

Professional responsive dashboard, Shield Stream branding, source quick tests, download controls and Android install/share manifest. In Android Chrome install from the dashboard or Chrome menu. Shared links populate the source field and require a deliberate Analyze tap. Copy/paste works without installation. The service worker uses network-only requests and stores no media or account information. Installation and share integration depend on device/browser support and have not been tested on a physical Android phone.

Netflix/Prime title links return official-app guidance. A phone app login does not transfer its session to this server; Netflix offline titles remain inside Netflix. Use Netflix's Download button for eligible titles (https://help.netflix.com/en/node/54816). Shield Stream downloads supported public or authorized non-DRM sources.

Legacy STREAMFORGE environment variable names, cookie names, paths, extension event identifiers and bridge protocol headers remain compatible. Windows build output is ShieldStream.exe; a Windows binary has not been built in this release.

## Public pages

Features: https://tool.vieapps.cloud/streamforge/features
Pricing: https://tool.vieapps.cloud/streamforge/pricing

Short homepage copy, shared navigation, three plan cards and reduced-motion-aware animated headings. Personal/Studio are planned, with launch pricing and billing still pending.
