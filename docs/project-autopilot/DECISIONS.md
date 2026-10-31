# Ramses Accounts — engineering decisions (31 Oct 2026)

- G2V decision: preserve the installed architecture (Python/FastAPI/SQLite). No reset of financial records and no new external dependencies.
- Pre-upgrade archives are encrypted AES-GCM `.rbe` using existing G2M tooling, with an authenticated `pre_upgrade` purpose and authenticated restore; missing key blocks schema updates.
- Retain historical data unchanged and avoid silent V8.0 compatibility claims without its real source archive.
- Durable plaintext pre-upgrade SQLite snapshots are prohibited. Private transient scratch snapshots remain a documented disk-encryption dependency.
- Production publishing, privilege mutations, data deletion, money movements and key custody are outside this local development authorization.

- G2X decision (local only): owner keeps emergency/full oversight; reviewer may see restricted cash/bank/wallet shift evidence only with current `user_fund_grants` (`can_submit` OR `can_approve`), and authorize closing/variance decisions only with `can_approve`. Unrestricted cash shifts retain existing reviewer role. Revocation is checked on each request/within write transaction. No automatic live permission changes.
- G2X deliberately defers full-hospital GL/reports and clinical approval: neither a financial slice of balanced GL nor a clinician role can be safely inferred without chief-accountant/medical signoff.

- G2Y temporary least-privilege reporting: viewer cash-only restricted to visible vouchers and never shown hospital GL/payroll; reviewer may still see full-hospital GL pending accountant approval, but fund cash aggregates are granted only per current fund permissions. Never present reviewer partial cash minus global payroll as a reconciled margin. Clear prior-role DOM at logout.
