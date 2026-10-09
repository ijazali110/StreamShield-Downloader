# 3.0.1 embedded-player fix — 2026-10-04 Pakistan time

The reported JSON/dict error was reproduced on the submitted movie-page path. The installed yt-dlp 2026.08.19 OK.ru extractor called its JSON text decoder on an object-valued flashvars.metadata field. An instance-scoped extractor accepts the pre-decoded dictionary while preserving legacy string decoding and rejection of invalid JSON. Installed dependency files are not modified.

A second observed issue was resolved: manifest reinspection dropped extractor-provided headers, producing HTTP 400 and Protection Unknown. Inspection now merges the extraction result's headers, format headers and explicit user overrides.

22 unit/API tests passed locally and on the VPS, including four new regression checks. Both analysis and download workers use the compatibility registration. Version endpoint reports 3.0.1. Existing desktop V2.1 sources are unchanged. No third-party movie was downloaded during verification.

Deployment keeps backups of server/worker.py and server/core.py under /opt/streamforge3/backups/3.0.0. The service was restarted after tests. Existing browser sessions need login again with the same password.
