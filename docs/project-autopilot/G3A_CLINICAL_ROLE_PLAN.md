# G3A Clinician Isolation — Implementation Plan (TEST ONLY)

**Goal:** Remove the insecure G2Z `viewer` clinical witness workaround by adding a distinct `clinician` login role, manual credential review, department-scoped attestations, and fail-closed upgrade behavior.

**Scope and limits:** All operations on synthetic databases in a local feature branch. No real license-registry integration, legal e-signature, production role changes, or publication. Existing historical attestation rows and issued invoices are not edited. Viewer clinical grants are suspended during upgrade, not silently converted to physician status; already activated department policies remain enforced.

**Approach:** Preserve SQLite IDs and all foreign-key references during an encrypted, transaction-protected users table rebuild. Restrict the clinician's authenticated API routes centrally. Require owner password re-entry and a recorded manual credential review before granting clinical permissions. Extend the existing medical attestation module and UI instead of new architecture. Test old G2Z data migration, positive medical flow, revocation, and negative finance API access.

**Task 1:** Tests for isolated clinician login and credential review, plus negative financial access; confirm failures before implementation.
**Task 2:** Add users CHECK migration, clinical profile storage and clinical trigger; preserve legacy data and prove rollback with frozen G2Z schema.
**Task 3:** Implement approved clinical identity lifecycle and owner-only grants in API; suspend G2Z viewer grants without deleting historical attestations; change old G2Z regression scripts to clinician role.
**Task 4:** Update UI role selection, clinical-only navigation and admin credential review; browser checks with synthetic API.
**Task 5:** Run focused tests and full suite, CI smoke, source review, independent ZIP verify; record exact limitations and commit local branch.

## Acceptance gates
- A clinician never sees accounting, funds, payroll, vouchers, employees, reports, billing patients, or general lookups, even with a guessed URL.
- A generic viewer, owner, reviewer, or cashier cannot file clinical evidence even if assigned an old viewer grant.
- A clinician cannot sign unless the owner manually reviewed their registration, the department grant is live, and its policy was explicitly activated.
- Revoking clinical credential approval OR department grant blocks the next attestation. No backdated evidence is forged.
- G2Z source schema migrates without losing existing foreign keys, users, sessions, vouchers, case lines, or old attestations. Encrypted rollback is verified before destructive table rebuild; without passphrase, no table mutation.
- Browser medical workflow works at 320,375,1440px; disabled screens are unavailable server-side, not just hidden.
- Financial and clinical human approval remain outstanding; output TEST ONLY / NO-GO.
