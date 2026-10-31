# Ramses Accounts — engineering decisions (31 Oct 2026)

- G2V decision: preserve the installed architecture (Python/FastAPI/SQLite). No reset of financial records and no new external dependencies.
- Pre-upgrade archives are encrypted AES-GCM `.rbe` using existing G2M tooling, with an authenticated `pre_upgrade` purpose and authenticated restore; missing key blocks schema updates.
- Retain historical data unchanged and avoid silent V8.0 compatibility claims without its real source archive.
- Durable plaintext pre-upgrade SQLite snapshots are prohibited. Private transient scratch snapshots remain a documented disk-encryption dependency.
- Production publishing, privilege mutations, data deletion, money movements and key custody are outside this local development authorization.
