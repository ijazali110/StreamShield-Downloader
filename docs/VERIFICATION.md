# Verification results — 2026-10-03

18 automated checks passed locally and on the Ubuntu VPS.

Live HTTPS smoke checks passed:
- Private login and cookie/CSRF flow
- Protected DASH fixture identified as Widevine Protected; download unavailable
- Direct MP4 analysis
- HLS master identified 360p and 720p
- Active download paused and retried/resumed
- Direct MP4 and selected 720p HLS downloaded and FFprobe-validated
- Final files retrieved over HTTPS; HTTP Range returned the correct 32 bytes
- Owned-media AES-GCM encryption and authenticated restoration matched exactly
- Wrong key rejected

Two synthetic sample jobs are left completed in the workspace so the user can inspect/save their files.

Nginx configuration passed. Service is active, bound to localhost and reverse-proxied at https://tool.vieapps.cloud/streamforge/. Runtime memory after tests was about 38 MB; configured maximum is 1 GB with one CPU quota and one active download.

Browser verification: the live private login page renders with its password field and Open workspace button. Full dashboard interaction was not checked through the cloud browser because credentials were not displayed. The actual authenticated workflow was checked by the in-process smoke script on the VPS.

Not yet verified: real live broadcasts, arbitrary production portals, subtitle embedding (sidecar downloads are implemented), split-track external sources, Windows executable build, browser extension interaction. Desktop/extension files are unchanged copies of V2.1. Standard resume behavior depends on the source supporting partial downloads; token expiry requires a manual refreshed URL.

A newly generated private dashboard password remains in the root-readable environment file. Automatic approval review blocked reading/displaying that password in this conversation; no credential is included in the ZIP.
