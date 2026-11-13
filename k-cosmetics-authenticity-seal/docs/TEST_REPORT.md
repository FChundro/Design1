# Phase 3 test report

Run on 13 November 2026 against the local prototype (TEST records only, throw-away data folder).
No Shopify store was touched.

| Suite                                                               | Result                                       |
| ------------------------------------------------------------------- | -------------------------------------------- |
| Backend API, security and privacy (`backend/kc_seal_tests`, pytest) | **30 / 30 passed**                           |
| Browser end-to-end (`e2e/run-e2e.cjs`, Chromium via Playwright)     | **19 / 19 passed** (`docs/e2e-results.json`) |
| Lint / format / types (ruff, ty — the repository's CI tools)        | clean                                        |

## Coverage by requirement

| Area             | Tests                                                                                                                                                                                                                                                                 |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Heartbeat (60 s) | No request at 30 s, exactly one at 60 s, timestamp updates (controlled browser clock).                                                                                                                                                                                |
| Date/time/zone   | Format `13 November 2026 at 17:17:24 CET (Europe/Madrid)` asserted; compact form on badge.                                                                                                                                                                            |
| Three statuses   | Verified, Suspended (suspended, revoked, supplier pending), Unavailable (unknown code, malformed code, outage, refused connection, forged signature, tampered payload, stale response).                                                                               |
| Signatures       | Signed envelope verified; tampered payload rejected; response from attacker key rejected; nonces unique.                                                                                                                                                              |
| Copied seal      | Counterfeit page claiming official origin, counterfeit with own origin (CORS), counterfeit relaying genuine responses — all Unavailable. Framing blocked. Screenshot: `screenshots/counterfeit-copy-rejected.png`.                                                    |
| Revocation       | Suspend → reinstate → revoke lifecycle; revoke permanent; live page switches Verified → Suspended at next heartbeat; signed revocation list.                                                                                                                          |
| Server failures  | 503 outage, connection refused, forged signature, stale clock: page shows Unavailable, keeps the last successful time, recovers automatically.                                                                                                                        |
| API protection   | Admin auth required and audited; unknown fields rejected; input validation; rate limiting (429); App Proxy HMAC valid/invalid/expired; direct endpoint closed when proxy required; demo routes and docs disabled outside demo mode; security headers; CORS allowlist. |
| Audit            | Hash chain valid and signed; edited line detected at the exact line.                                                                                                                                                                                                  |
| Privacy          | No raw IP in logs; 30-day purge; no cookies; public payload contains no supplier identity, document references or hashes.                                                                                                                                             |
| Keys             | Key file must be 0600; missing key blocks start-up; private key never served.                                                                                                                                                                                         |
| Mobile           | iPhone 13 (390 px), tablet 768 px, desktop 1440 px: no horizontal scroll, ≥ 44 px tap targets, badge positioned lower right opposite "Complete Your Routine".                                                                                                         |
| Accessibility    | Status changes announced through an `aria-live` region; focus styles; reduced motion respected.                                                                                                                                                                       |

## Screenshots (`docs/screenshots/`)

`desktop-1440-verified.png`, `desktop-1440-suspended.png`, `desktop-1440-unavailable-outage.png`, `desktop-1440-product-badge.png`, `tablet-768-verified.png`, `tablet-768-product-badge.png`, `iphone-390-verified.png`, `iphone-390-product-badge.png`, `counterfeit-copy-rejected.png`.

## Not yet tested (needs an approved development theme / environment)

- Real Shopify preview of the Liquid files (Horizon theme context, App Proxy round trip, theme editor settings).
- Safari/WebKit and Firefox (the demo was tested in Chromium only; the widget uses standard WebCrypto Ed25519, available in current Safari, Firefox and Chrome).
- Load test and penetration test of a deployed backend.
