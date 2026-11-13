# K-Cosmetics EU — Live Heartbeat Digital Authenticity Seal

## Phase 1 technical proposal and operating cost estimate

Status: **PROTOTYPE — awaiting management approval. Nothing deployed or activated.**
Date: 13 November 2026

---

### 1. Phase 1 inspection findings (read-only)

| Item                                      | Finding                                                                                                                                                                       | Consequence                                                                                                                                                                          |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Connected Shopify store                   | `kjvtit-2p.myshopify.com` ("My Store 4"), Basic plan, EUR, CET, Spain                                                                                                         | —                                                                                                                                                                                    |
| Themes on that store                      | **Only one theme: "Horizon", role MAIN (live).** No unpublished development theme exists.                                                                                     | Nothing was written to Shopify. Theme code is delivered as files in this folder, ready to install in a development theme once one exists.                                            |
| Approved style brief (Drive, 05 Nov 2026) | Refers to a **different store**, `1gf1ui-rv.myshopify.com`, unpublished theme ID `197290787142`.                                                                              | Management must confirm which store is the target before installation.                                                                                                               |
| Seal artwork (Drive)                      | Only navy-and-gold seal found: `KC_seal_navy_gold_small_DRAFT.svg` (file ID `1Yi28XZFC46wi3vUjL057eFDez0KcG9lf`). The file name says **DRAFT**.                               | Used **byte-for-byte unchanged** (SHA-256 `5897d419c0a28893d2770fad554c0cf57d9e583252fd17b31356c35948e4f0f9`). Not redesigned. Management must confirm this is the approved version. |
| Brief guidance on the seal                | "Small NAVY circular authenticity seal at lower right… Seal is brand-design element, NOT proof of third-party certification or supplier authentication unless substantiated." | Small badge lower right; explicit "digital record only" wording.                                                                                                                     |
| Existing theme styling                    | `kc-pages-premium.css` backup: ivory/champagne/gold hairlines, Playfair Display + Jost via theme font variables.                                                              | Seal CSS reuses the same palette, fonts and hairline style.                                                                                                                          |

### 2. Recommended architecture (safest option)

```
 Customer browser on the official domain  (/pages/authenticity?seal=KC-…  or the product-page badge)
   │  every 60 s: GET /apps/kc-seal/heartbeat?seal_id=…&nonce=<random>
   ▼
 Shopify storefront (same origin) ── App Proxy, HMAC-signed by Shopify ──►  Verification backend (EU region)
                                                                           • checks Shopify proxy signature
                                                                           • looks up record (PostgreSQL)
                                                                           • signs response, Ed25519 key in KMS/HSM
                                                                           • hash-chained audit log
                                                                           • pseudonymised 30-day access log
   ◄──────────── signed envelope {alg, kid, payload, sig} ────────────────┘
 Browser verifies signature with the public key pinned in the theme, checks nonce, seal ID, origin and freshness,
 then shows Verified Record / Verification Unavailable / Verification Suspended + last verified date, time and zone.
```

Why this is the safest option:

- **No change to the live theme, products, prices, inventory, checkout, payments or apps.** The feature is seven new theme files (section, block, snippet, page template, JS, CSS, seal SVG), installed only in an unpublished development theme. No existing theme file is modified. Nothing renders unless a page uses the `authenticity` template, or a merchant adds the block and the product has a `kc_seal.record_id` metafield.
- **Official domain via Shopify App Proxy.** The verification page and its API live on the store's own domain; the backend accepts only requests carrying Shopify's HMAC signature (`KC_SEAL_REQUIRE_APP_PROXY=1`). An App Proxy needs a free _custom app_ — creating it is a store configuration change that needs approval.
- **Separate backend** holds all records and keys; Shopify holds only the public key and record IDs.
- **Signing keys never leave the server.** Prototype: key file with 0600 permissions (refuses to start otherwise). Production: non-exportable Ed25519 key in a cloud KMS/HSM.

### 3. How each requirement is met

| #   | Requirement                                              | Implementation                                                                                                                                                                                                                                                                                                                                                                        |
| --- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Live heartbeat, 60-second refresh                        | `kc-seal-heartbeat.js` polls every 60 s (hard floor of 60 s on the storefront), re-checks when a tab becomes visible again, 10 s timeout. Browser test with a controlled clock: no request at 30 s, exactly one at 60 s.                                                                                                                                                              |
| 2   | Date, time and time zone of last successful verification | Server timestamp from the signed payload: "Last successful server verification: 13 November 2026 at 17:17:24 CET (Europe/Madrid) · just now". Compact on the badge ("Last verified 13 Nov 2026, 17:18:15 CET"). Kept visible during outages.                                                                                                                                          |
| 3   | Signed records, keys on server                           | Ed25519 over the exact payload bytes; public JWKS endpoint; key ID for rotation; audit-log head also signed.                                                                                                                                                                                                                                                                          |
| 4   | Three statuses                                           | **Verified Record**: active record, supplier approved, review not overdue. **Verification Suspended**: record suspended or revoked, or supplier approval pending/withdrawn/overdue. **Verification Unavailable**: server unreachable, forged or tampered signature, stale/replayed response, wrong origin, unknown or malformed code, rate limited.                                   |
| 5   | Secure verification page on official domain              | `templates/page.authenticity.json` + `sections/kc-authenticity-verify.liquid` → `/pages/authenticity`; data via App Proxy; CSP, no framing, no cookies.                                                                                                                                                                                                                               |
| 6   | Data model                                               | See §4.                                                                                                                                                                                                                                                                                                                                                                               |
| 7   | Copied seal image cannot produce a valid response        | The artwork carries no data. A valid result needs a 120-bit random code plus a fresh response signed by the private key, bound to a browser nonce and the official origin. Tested: copied page claiming the official origin, copied page on its own domain, copied page relaying genuine signed responses, forged signatures, tampered responses — all show Verification Unavailable. |
| 8   | No claim of physical authenticity                        | Verified message: "This confirms the record only – it does not by itself prove that a physical product is authentic." Page explains what it does and does not mean; payload `"scope": "digital_record_only"`.                                                                                                                                                                         |
| 9   | Audit, revocation, API protection, privacy               | See `SECURITY_CHECKLIST.md`.                                                                                                                                                                                                                                                                                                                                                          |
| 10  | Premium, discreet, mobile-friendly, consistent           | Brief palette and fonts; small badge; tested at 1440 / 768 / 390 px, no horizontal scroll, 44 px tap targets; reduced-motion respected; screen-reader announcements.                                                                                                                                                                                                                  |

### 4. Data model (one record per batch or per product listing)

```
SealRecord
  seal_id              KC-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX   server-generated, 120 bits
  is_test              bool (all prototype records = true; shown as "TEST RECORD")
  product_sku, product_title, manufacturer_batch, manufactured_on, best_before
  supplier             { supplier_id, supplier_name, approval_status: approved|pending|withdrawn,
                         approved_on, review_due, approved_by_role }
  evidence[]           { evidence_id, type: supplier_invoice | authorised_distributor_letter |
                         certificate_of_analysis | cpnp_notification | import_customs_document |
                         goods_receipt_inspection | other, reference, sha256, received_on, verified_by_role }
  logistics            { integration_status: not_integrated|pending|synced, provider, provider_lot_ref,
                         warehouse_code, received_into_stock_on, last_synced_at }      ← future 3PL hook
  status               active | suspended | revoked (revoked is permanent)
  status_reason, history[{at, status, reason, actor}], created_at, updated_at, version
```

Public responses expose only: product title, SKU, batch, best-before, supplier approval status and date, the count and types of evidence held, 3PL integration status, last update. Never: supplier identity, document references or hashes, history, or anything about customers.

Shopify link: product metafield `kc_seal.record_id`. Packaging link: the code (or a QR code of `https://<domain>/pages/authenticity?seal=<code>`) printed per batch — an operational decision.

### 5. Estimated operating costs (EU hosting, per month, excl. VAT)

Assumption: 5,000 product-page views/day with the badge + 1,000 verification-page views/day, ~3 heartbeats per view ⇒ ~18,000 signed responses/day (~550,000/month).

| Item                            | Option                                                                   | €/month                  |
| ------------------------------- | ------------------------------------------------------------------------ | ------------------------ |
| Backend hosting                 | Google Cloud Run, europe-southwest1 (Madrid), 1 always-on small instance | 15 – 30                  |
| Database                        | Managed PostgreSQL, small tier (Cloud SQL / Neon / Supabase Pro)         | 10 – 30                  |
| Signing key                     | HSM-backed KMS Ed25519 key + ~550k sign operations                       | 5 – 20                   |
| Secrets                         | Secret Manager                                                           | < 1                      |
| Edge protection                 | Cloudflare free/Pro or Cloud Armor rate limiting                         | 0 – 25                   |
| Logs, monitoring, uptime alerts |                                                                          | 0 – 15                   |
| Audit-log archive               | Object storage with retention lock, 6 years                              | 1 – 3                    |
| Shopify                         | Custom app with App Proxy — no charge on the current Basic plan          | 0                        |
| **Total**                       |                                                                          | **≈ €35 – €125 / month** |

One-off, recommended before go-live: independent penetration test (≈ €2,000–5,000); legal review of customer wording and Privacy Policy update; reviewed translations for the other 7 in-scope languages.
Ongoing staff time: record entry and evidence checks per batch, quarterly supplier reviews, yearly key rotation.

Cheaper alternative: one EU VPS (≈ €5–15/month) with local PostgreSQL and a key file. Lower cost, weaker key protection and more maintenance; not recommended for a customer-trust feature.

### 6. Decisions needed from management

1. Confirm the target store (`kjvtit-2p`, connected here, vs `1gf1ui-rv`, named in the brief) and authorise creating an **unpublished** copy of the theme.
2. Confirm `KC_seal_navy_gold_small_DRAFT.svg` is the approved seal, or supply the approved file.
3. Confirm the official customer-facing domain.
4. Approve a Shopify custom app (App Proxy only).
5. Choose hosting/KMS provider and approve the budget.
6. Decide how codes reach customers (per-batch label, QR) and who may create, suspend and revoke records.
