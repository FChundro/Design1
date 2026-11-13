# K-Cosmetics EU — Live Heartbeat Digital Authenticity Seal (PROTOTYPE)

> **Prototype for management approval. Not deployed, not activated, no Shopify store modified.**
> All verification records are clearly labelled TEST records.

A customer opens the official verification page (or sees the small navy seal on a product page). Every
60 seconds the page asks the K-Cosmetics server about the record, checks the server's digital signature,
and shows one of **Verified Record**, **Verification Unavailable** or **Verification Suspended**, with the
date, time and time zone of the last successful verification. A Verified Record confirms the digital
record only — never that a physical item is authentic.

| Folder     | Contents                                                                                                                                                                                                 |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `backend/` | Verification service (Python/FastAPI): signing, records, revocation, audit log, privacy, App Proxy check. Tests in `backend/kc_seal_tests/`.                                                             |
| `theme/`   | Shopify Online Store 2.0 files for an **unpublished** theme: section, block, snippet, page template, JS, CSS, seal SVG (unchanged from Drive).                                                           |
| `demo/`    | Local demo pages mirroring the theme output (served by the backend in demo mode only).                                                                                                                   |
| `e2e/`     | Browser tests (heartbeat, failures, revocation, counterfeit pages, mobile).                                                                                                                              |
| `docs/`    | [Technical proposal & costs](docs/TECHNICAL_PROPOSAL.md) · [Security checklist](docs/SECURITY_CHECKLIST.md) · [Demo & deployment](docs/DEPLOYMENT.md) · [Test report](docs/TEST_REPORT.md) · screenshots |

Quick demo: see [docs/DEPLOYMENT.md, Part A](docs/DEPLOYMENT.md#part-a--local-demonstration-safe).

Open decisions before any installation are listed in the proposal, §6 (target store, approved seal file,
official domain, custom app, hosting budget, packaging codes).
