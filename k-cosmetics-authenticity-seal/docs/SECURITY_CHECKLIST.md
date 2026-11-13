# Security and privacy checklist

Legend: ✅ done and tested in the prototype · 🟡 designed, needs production configuration · ⬜ to do before go-live

## Cryptography and keys

- ✅ Every heartbeat response signed with Ed25519 over the exact payload bytes (no canonicalisation ambiguity).
- ✅ Browser verifies the signature with a **pinned** public key from the theme settings (not fetched at run time on the storefront).
- ✅ Response bound to a fresh 144-bit browser nonce, to the seal ID and to the official origin; issued-at checked (±5 min).
- ✅ Private key file must be mode 0600; service refuses to start otherwise; refuses to start if the key is missing (unless dev flag).
- ✅ Private key never served (`/api/v1/keys` returns public JWK only — tested).
- 🟡 Production key in a non-exportable HSM-backed KMS key; service account limited to `sign` only.
- 🟡 Key rotation by `kid`: publish new public key in theme first, then switch signing key; old key retired.
- ⬜ Key-compromise runbook: remove compromised `kid` from theme pins, rotate, re-verify, notify.

## Seal copying / counterfeit sites (requirement 7)

- ✅ Seal artwork contains no data; codes are 120-bit random (not guessable or enumerable).
- ✅ Copied page claiming official origin → Unavailable (tested).
- ✅ Copied page on its own domain → blocked by CORS → Unavailable (tested).
- ✅ Copied page relaying genuine signed responses → origin mismatch → Unavailable (tested).
- ✅ Forged signature, tampered status, stale/replayed response → Unavailable (tested).
- ✅ Page cannot be framed (`X-Frame-Options: DENY`, CSP `frame-ancestors 'none'`); script also refuses to verify inside a frame.
- ✅ Customer wording: "A seal image on another website or a screenshot cannot be verified."

## API protection

- ✅ Production path via Shopify App Proxy with HMAC-SHA256 signature and 5-minute timestamp window; direct endpoint can be closed (`KC_SEAL_REQUIRE_APP_PROXY=1`) — tested.
- ✅ Strict input validation (seal ID regex, nonce regex, length limits); unknown fields rejected on admin API.
- ✅ Per-client rate limiting (public 20/min, burst 10; admin 60/min) — tested.
- ✅ Admin API: bearer token, only its SHA-256 stored, constant-time comparison, failed attempts audited (token never logged).
- ✅ Admin body size limit 64 KB.
- ✅ Security headers: CSP, X-Frame-Options, nosniff, Referrer-Policy no-referrer, Permissions-Policy, HSTS on HTTPS, `Cache-Control: no-store` on API.
- ✅ CORS allowlist, GET only, no credentials.
- ✅ OpenAPI docs and demo routes disabled unless demo mode.
- 🟡 Edge rate limiting / WAF (Cloudflare or Cloud Armor) in front of the backend; firewall backend to Shopify egress.
- ⬜ Replace single admin token with SSO (OIDC) + role separation (record editor vs approver) and 4-eyes approval for revocation.
- ⬜ Independent penetration test.

## Revocation and integrity

- ✅ Suspend / reinstate / revoke; revocation is permanent (409 on reinstate) — tested.
- ✅ Status change reaches open customer pages at the next heartbeat (≤ 60 s) — tested in browser.
- ✅ Signed revocation list `/api/v1/revocations`.
- ✅ Supplier approval pending/withdrawn or review overdue automatically yields "Verification Suspended".
- ✅ Atomic record writes; version counter; full status history per record.

## Audit logging

- ✅ All admin actions, auth failures, fault injection and service start logged.
- ✅ Hash-chained JSONL; edit or deletion detected (`/api/v1/admin/audit/verify`) — tested.
- ✅ Chain head signed with the server key for external anchoring.
- 🟡 Daily export of signed head + log to WORM object storage (retention lock, e.g. 6 years).

## Privacy (GDPR)

- ✅ No cookies, no accounts, no customer personal data collected.
- ✅ IP addresses never written; daily-rotating salted HMAC pseudonym; salt discarded each day — tested.
- ✅ User-Agent and Referer not stored; widget sends `referrerPolicy: no-referrer`, `credentials: omit`.
- ✅ Access log retention 30 days with purge — tested.
- ✅ Public response limited to non-personal product facts; supplier identity and documents never published — tested.
- ⬜ Update Privacy Policy (purpose: fraud/abuse prevention; legal basis: legitimate interest; retention 30 days).
- ⬜ Record of processing activity entry; DPA with hosting provider; EU-only hosting region.

## Claims and wording

- ✅ Verified Record never claims physical authenticity; "digital record only" in UI and payload.
- ✅ No third-party certification implied; TEST RECORD label on all prototype records.
- ⬜ Legal review of final wording and translations before publication.

## Operations

- ⬜ Uptime monitoring and alerting on heartbeat error rate; on-call contact.
- ⬜ Database backups (point-in-time recovery) and restore drill.
- ⬜ Dependency and container vulnerability scanning in CI.
