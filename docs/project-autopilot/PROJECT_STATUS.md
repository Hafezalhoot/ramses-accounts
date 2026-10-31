# G3A Project Autopilot state — 2026-10-31

- Source baseline: G2Z frozen commit `a17aeec`.
- Local feature branch: `feat/g3a-clinician-isolated-access` — no shared repo push, no production deployment or live database changes.
- IMPLEMENTED locally: separate medical role, owner manual professional review plus password re-entry, department grants, deny-by-default finance API access, SQLite verified encrypted rollback and historical preservation, suspension of G2Z viewer grants, old viewer attestation not usable for new invoices, identity-revocation on password reset/disable, mobile-friendly owner review.
- TESTED locally: FastAPI/SQLite, frozen G2Z historical migration+restore, role denial, Chromium stub UI; full **103 PASS/5 SKIP/1 BLOCKED** from 109 scripts. CI: 37/37 PASS في تشغيل منفصل (31 أكتوبر 2026).
- Remaining blockers: real medical licensing/signature check and medical leadership approval; no off-device restore; missing V8.0 and some historical sources; procurement and doctor remuneration; complete hospital UAT and authorization certification.
- Production gate: NO-GO.

## Top next three actions

1. Authoritative medical credential validation + clinical approval workflow and source document hash (with human policy sign-off); no invented legal status.
2. Approved remediation for old G2Z viewer-attested service lines without new invoices + clinical/financial audit trail.
3. Full authorized cross-department workflows and case-level supply consumption, supplier AP, doctors fees and acceptance/offsite restore checks.
