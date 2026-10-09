# Shield Stream 3.1 release

Live workspace: https://tool.vieapps.cloud/streamforge/

Shield Stream branding, teal dashboard with dark navigation, responsive Sources/Downloads/Media lab/Mobile guide/System views. Desktop and Chrome companion display names updated; bridge protocol and environment names preserved.

Android Chrome install manifest and GET share target populate a link for explicit analysis. No offline account/media caching. Physical phone installation/share integration remains to be tested on the user's device.

Quick tests: real external Blender Sintel trailer MP4, clear HLS with 360p/720p qualities, local synthetic MP4. Existing non-DRM extraction/download engine, quality/audio/subtitle selection, pause/resume, scheduling and file saving are integrated into the dashboard. Netflix/Prime title-page links return official-app instructions.

Verification on 2026-10-04: 27 unit/API regressions passed locally. Server initially passed 26; final additional direct-media error regression protects error reporting. Deployed HTTPS login, branding/version, manifest/SW/icon assets and share entry checked. Clear HLS quality analysis and protected-manifest rejection passed. Real external Sintel MP4 downloaded and validated: 4,372,373 bytes; attachment and HTTP Range save response passed. Windows source compiled for syntax; a Windows executable was not built.

The initial W3C quick-test source intermittently refused extraction with an anti-bot response. The quick test now uses Blender's public Sintel trailer. Direct-media errors retain the original source error instead of trying to parse binary media as HTML. Arbitrary services and actual live broadcasts have not been verified.

Mobile test: open the live dashboard in Chrome, sign in with the existing password, choose Public external video, Analyze, Add to queue, Downloads, Save to device. Install from Chrome if supported; copy/paste works without installation. Netflix: use the Netflix app's Download button for eligible titles and watch them in Netflix Downloads.
