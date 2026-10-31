# Ramses Accounts — verified project state after G2X

- Source: local isolated branch `fix/g2x-restricted-shift-authorization`, based on G2W `35f22cd`; no hospital production deployment.
- Invariant: reviewer may read sensitive cashier-shift finance/evidence only with an active explicit restricted-fund grant; approval additionally requires `can_approve`. Owner unrestricted. Clerk access remains tied to station assignment and shift responsibility.
- Reproduced: G2W default reviewer leaks restricted shift in `GET /api/shifts` on synthetic TestClient. G2X regression denies and confirms live grant/revocation.
- Additional: GL viewer denied by prior G2W, release code/banner synchronized to G2X; test expectation repaired.
- Fresh final QA: 104 scripts = 98 PASS, 3 historical SKIP, 2 private-reference SKIP, 1 BLOCKED V8.0, 0 FAIL; CI smoke 32/32 PASS. Initial preview HTTP nondeterministic failure did not repeat in 2 independent runs or whole-suite rerun; investigate if recurring.
- Remaining gate: full reporting RBAC, patient clinical attestation, V8.0 historical migration, offsite restore, clinical/finance/IT sign-off.
- NO-GO; synthetic-only / unapproved rollout.

# Ramses Accounts — current source tracking

- Source baseline: `V8.1E-G2U` from matching SHA-256 ZIP. Git working branch: `fix/g2v-encrypted-upgrade` (local only).
- Current local slice: G2V migration rollback encryption, test-driven development. NO-GO for production.
- No live deployment, no cloud database alterations, no sensitive real employee/patient records.
- Verified prior G2U: 96 PASS / 3 historical SKIP / 1 V8.0 BLOCKED (100 scripts) as documented in G2U archive. Fresh G2V QA 97 PASS / 3 SKIP / 1 BLOCKED V8.0, 101 scripts; CI smoke 29/29 PASS. Tests are local synthetic only.
- Next actions: package checksum-verified G2V source, scope comprehensive read RBAC, and design clinician-signed service attestation. Offsite restore and historical V8.0 remain blocked.
