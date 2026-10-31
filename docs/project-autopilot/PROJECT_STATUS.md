# Ramses Accounts — current source tracking

- Source baseline: `V8.1E-G2U` from matching SHA-256 ZIP. Git working branch: `fix/g2v-encrypted-upgrade` (local only).
- Current local slice: G2V migration rollback encryption, test-driven development. NO-GO for production.
- No live deployment, no cloud database alterations, no sensitive real employee/patient records.
- Verified prior G2U: 96 PASS / 3 historical SKIP / 1 V8.0 BLOCKED (100 scripts) as documented in G2U archive. New G2V tests to be recorded from actual fresh runs, not inherited results.
- Next actions: complete G2V full suite, freeze signed build manifest; scope comprehensive read RBAC; design medical attestation source.
