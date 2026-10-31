# Ramses Accounts — current source tracking

- Source baseline: `V8.1E-G2U` from matching SHA-256 ZIP. Git working branch: `fix/g2v-encrypted-upgrade` (local only).
- Current local slice: G2V migration rollback encryption, test-driven development. NO-GO for production.
- No live deployment, no cloud database alterations, no sensitive real employee/patient records.
- Verified prior G2U: 96 PASS / 3 historical SKIP / 1 V8.0 BLOCKED (100 scripts) as documented in G2U archive. Fresh G2V QA 97 PASS / 3 SKIP / 1 BLOCKED V8.0, 101 scripts; CI smoke 29/29 PASS. Tests are local synthetic only.
- Next actions: package checksum-verified G2V source, scope comprehensive read RBAC, and design clinician-signed service attestation. Offsite restore and historical V8.0 remain blocked.
