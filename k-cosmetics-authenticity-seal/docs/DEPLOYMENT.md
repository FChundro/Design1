# Demonstration and deployment instructions

> **Do not perform any step in Part B without written management approval.**
> Part A runs entirely on a local machine and touches no Shopify store.

## Part A — Local demonstration (safe)

Requirements: Python 3.12+, Node 18+ with Playwright and Chromium (for the automated tests only).

```bash
cd k-cosmetics-authenticity-seal/backend
python -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"

# throw-away data folder, TEST records, demo mode
export KC_SEAL_DATA_DIR=$PWD/var-demo KC_SEAL_DEMO_MODE=1 KC_SEAL_DEV_GENERATE_KEY=1
export KC_SEAL_OFFICIAL_ORIGIN=http://127.0.0.1:8787
export KC_SEAL_ADMIN_TOKEN_SHA256=$(printf 'choose-a-long-demo-token' | python -m kc_seal hash-token)
python -m kc_seal seed
python -m kc_seal serve --port 8787
```

Open:

- Verification page: <http://127.0.0.1:8787/demo/index.html?seal=KC-TEST-VERI-FIED-AAAA-AAAA-AAA2>
- Product page mock with small seal: <http://127.0.0.1:8787/demo/product.html>

TEST codes:

| Code                               | Shows                                              |
| ---------------------------------- | -------------------------------------------------- |
| `KC-TEST-VERI-FIED-AAAA-AAAA-AAA2` | Verified Record                                    |
| `KC-TEST-SUSP-ENDE-DAAA-AAAA-AAA3` | Verification Suspended (record suspended)          |
| `KC-TEST-REVO-KEDA-AAAA-AAAA-AAA4` | Verification Suspended (record revoked)            |
| `KC-TEST-PEND-INGA-AAAA-AAAA-AAA5` | Verification Suspended (supplier approval pending) |
| `KC-AAAA-BBBB-CCCC-DDDD-EEEE-FFFF` | Verification Unavailable (no record)               |

Live demonstrations (in a second terminal, `T=choose-a-long-demo-token`):

```bash
H="Authorization: Bearer $T"; U=http://127.0.0.1:8787/api/v1/admin
# server failure -> page shows Verification Unavailable within 60 s, keeps last verified time
curl -sX POST $U/demo/fault -H "$H" -H 'Content-Type: application/json' -d '{"mode":"outage"}'
curl -sX POST $U/demo/fault -H "$H" -H 'Content-Type: application/json' -d '{"mode":"forged_signature"}'
curl -sX POST $U/demo/fault -H "$H" -H 'Content-Type: application/json' -d '{"mode":"none"}'
# live suspension / revocation of the verified TEST record
curl -sX POST $U/records/KC-TEST-VERI-FIED-AAAA-AAAA-AAA2/suspend -H "$H" -H 'Content-Type: application/json' -d '{"reason":"TEST demo"}'
curl -sX POST $U/records/KC-TEST-VERI-FIED-AAAA-AAAA-AAA2/reinstate -H "$H" -H 'Content-Type: application/json' -d '{"reason":"TEST demo"}'
# audit chain check
curl -s $U/audit/verify -H "$H"
```

Automated tests:

```bash
cd backend && pytest                       # 30 API/security tests
cd .. && node e2e/run-e2e.cjs              # 19 browser tests, writes docs/screenshots + docs/e2e-results.json
```

## Part B — Production deployment (only after approval)

1. **Backups first.** Export the live theme and the development theme (ZIP), products/collections CSV. Store in Drive.
2. **Development theme.** In the approved store, _Online Store → Themes → … → Duplicate_ the live theme. Keep it **unpublished**. Never edit the live theme.
3. **Backend** (EU region):
   - Build from `backend/` (`pip install .`; run `uvicorn` via `python -m kc_seal serve --host 0.0.0.0` behind HTTPS).
   - Create the Ed25519 signing key in KMS/HSM (non-exportable). Until the KMS signer adapter is added, mount a 0600 key file from Secret Manager. Never set `KC_SEAL_DEV_GENERATE_KEY` or `KC_SEAL_DEMO_MODE` in production.
   - Environment: `KC_SEAL_ENVIRONMENT=production`, `KC_SEAL_OFFICIAL_ORIGIN=https://<official domain>`, `KC_SEAL_ALLOWED_ORIGINS=https://<official domain>`, `KC_SEAL_REQUIRE_APP_PROXY=1`, `KC_SEAL_APP_PROXY_SECRET` (from Secret Manager), `KC_SEAL_ADMIN_TOKEN_SHA256`, `KC_SEAL_KEY_ID=kc-seal-2026-11`, `KC_SEAL_DATA_DIR` on persistent storage (or PostgreSQL adapter).
   - Put Cloudflare / Cloud Armor in front with rate limiting.
4. **Shopify custom app** (Settings → Apps → Develop apps): enable an **App Proxy**: prefix `apps`, subpath `kc-seal`, proxy URL `https://<backend>/proxy`. The storefront URL `https://<official domain>/apps/kc-seal/heartbeat` then reaches `/proxy/heartbeat` with Shopify's signature.
5. **Theme files** into the _unpublished_ theme only (Theme editor → Edit code, or Shopify CLI `shopify theme push --theme <dev-theme-id> --only ...`):
   `assets/kc-seal-heartbeat.js`, `assets/kc-seal.css`, `assets/kc-seal-navy-gold.svg`, `snippets/kc-seal-heartbeat.liquid`, `sections/kc-authenticity-verify.liquid`, `blocks/kc-seal-badge.liquid`, `templates/page.authenticity.json`.
6. **Pin the public key**: copy the `keys` array from `GET https://<backend>/api/v1/keys` into the section/block setting "Pinned public keys (JSON)".
7. **Metafield definition** (product, `kc_seal.record_id`, single line text) and records created through the admin API by compliance staff; set the metafield on chosen TEST products only.
8. **Preview** the development theme: `/pages/authenticity?preview_theme_id=<id>` (create the page as hidden/unpublished, template `authenticity`). Re-run the checks in docs/TEST_REPORT.md against the preview at 1440/768/390 px.
9. **Go-live** (separate approval): remove the test banner setting, replace TEST records with real ones, publish translations reviewed by legal, then publish the theme in a planned window.

### Rollback

Theme: re-publish the previous theme or delete the 7 added files from the development theme (no existing file is modified). Backend: disable the App Proxy in the custom app; the widget then shows "Verification Unavailable" and nothing else on the site changes.
