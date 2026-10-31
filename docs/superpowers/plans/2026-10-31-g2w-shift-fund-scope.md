# G2W — Shift fund scope for financial reviewers

**Baseline:** V8.1E-G2V (local only), current G2U/G2V fund grants apply.
**Goal:** No read, attachment, summary, export or close/review of a restricted cash or wallet shift by an ungranted reviewer. The owner is authorized; unrestricted cash workflows remain unchanged. Revocation takes effect on the next request.
**Risk:** API scoping is a privilege change, so test entirely on synthetic SQLite before any UAT. No production deployment.
**Approach:** Reuse `user_fund_grants` and `fund_grant_rights` (no new schema). Apply a single correlated SQL predicate for collection reads and a single fund guard for object reads/review; keep `can_approve` for review actions. No new permission framework.

- [x] Reproduce unscoped shift list and document reads by a synthetic reviewer without grants.
- [x] Add current-grant visibility to collection/summary/variance routes before `LIMIT` and aggregation.
- [x] Deny object-level movements/count history/daily report/attachments and shift review without current grant.
- [x] Verify positive owner/authorized reviewer/unrestricted cases, then revoke and verify immediate denial.
- [x] Run G2W regression, existing affected shifts/review/authorization tests, full suite and CI smoke.
- [x] Update project status, source diff, checksum and test evidence; package development-only artifact.

**Remaining after this slice:** hospital-wide GL and personnel report authorization need an approved global reporting policy. Clinical service attestation remains unfinished.
