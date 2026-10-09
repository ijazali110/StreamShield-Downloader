# Shield Stream 3.2 design and release notes

User goal: a no-login free YouTube homepage with single/multiple links; private advanced workspace remains behind login, followed by paid plans in a future phase. Fix installed PWA showing an install action.

Frontend: free homepage, single/bulk input (up to five), quality selection and download-all queue action, visitor's job list and file save. Existing owner workspace stays intact. Installed-mode checks and install lifecycle events control both install buttons.

Backend: /api/free routes issue a signed 24-hour guest cookie, bind opaque guest IDs to persistent job specs, isolate history/files/actions, restrict requests to canonical YouTube individual video links and enforce CSRF/origin. Private /api routes retain their existing password boundary. Free quota records survive job deletion; cleanup removes expired free history/files and prunes old quota entries. One existing worker processes all jobs; free byte/time/quality caps are verified in the worker. Node 22 and matching EJS dependency enable current yt-dlp YouTube support.

Future paid plans require per-customer accounts, validated payment webhooks and server-side entitlements; the existing owner password is not a premium customer account. This release does not implement billing.

Tests cover public homepage without premium access, independent guest jobs/files, non-YouTube rejection, CSRF, restricted options, quota retention after deletion, plus the existing download/protection/authentication suite. Device install/share and arbitrary YouTube titles are not guaranteed by these tests.

## Verification outcome

32 unit/API tests pass locally and on the VPS. Public homepage rendered in the browser, bulk mode checked, private API login boundary and guest source restrictions checked over HTTPS. Existing owner password login succeeds. Install eligibility checks cover no prompt, prompt available, standalone and iOS standalone states; physical Android installation is not directly tested.

The retired yt-dlp sample BaW_jenozKc was unavailable. The live Sintel YouTube video eRsGyueVLvQ asked this VPS to sign in to confirm it is not a bot. Actual YouTube download/save is therefore NOT verified; extraction was refused by YouTube. No proxies, impersonation or cookie-transfer workarounds were attempted. Public UI reports source verification failures in plain language. Existing direct external MP4/HLS verification from 3.1 still describes the private engine; it is not evidence of a successful YouTube download.
