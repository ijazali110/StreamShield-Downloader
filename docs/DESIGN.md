# StreamForge 3.0 VPS companion

Goal: give the owner a private HTTPS dashboard for testing media analysis and downloads while keeping the uploaded V2.1 Windows app and extension unchanged. The dummy streaming website is supplied by the owner.

Architecture: standard-library HTTP server bound to localhost behind existing Nginx TLS, one isolated downloader process at a time, SQLite queue/history, yt-dlp extraction and FFmpeg merging. Browser extension and desktop remain local; their existing localhost bridge is never exposed publicly. Web sessions cannot read cookies from a user's Chrome profile. Optional per-request headers are supplied explicitly, remain in memory, and are redacted in reports.

Web flows: login; analyze URL; display selectable video/audio qualities and subtitles; preview an accessible direct URL; enqueue; schedule; throttle; cancel/pause; retry/resume; download final files; export sanitized report; clear finished downloads. Persistent jobs survive restart as paused; authorization must be re-supplied. Live recordings require explicit duration. Worker timeout, disk quotas, queue limits and single concurrency bound VPS load.

Protection: scan manifests and yt-dlp format metadata. Protected/encrypted remote streams are inspection-only in this web version. The owned-media lab accepts only its own authenticated AES-256-GCM container and an explicit user-supplied key; no license discovery, CDM integration, CENC key extraction, or third-party protection circumvention. This is a custom test format, not Netflix-compatible DRM.

Scope limits: the web scanner handles URLs and statically linked media; existing desktop extension remains the solution for browser network capture and dynamic/iframe pages. Automatic signed-URL refresh, cloud browser cookies, remote browser capture, automatic portal adapters and arbitrary encrypted HLS/DASH decryption are not claimed. URLs may be refreshed manually on retry.

Verification: manifest protection inheritance, encrypted HLS, query redaction, public-only network access, wrong-key lab rejection, authentication, CSRF, actual demo extraction/download, pause/retry, report sanitization, service restart recovery, Nginx config test and HTTPS live smoke checks. Ship a full versioned source ZIP, including the unchanged desktop project.
