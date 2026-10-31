# G3B clinical source-document fingerprint: test-only design

Goal: connect a clinician's service attestation to a reproducible fingerprint of the exact PDF/JPEG/PNG source they inspected, WITHOUT archiving private medical bytes in the finance database.

- Keep `billing_clinical_attestations` append-only. Add nullable SHA-256/size/media columns; pre-G3B evidence remains intact with NULL source fingerprint.
- A clinician may attest using the existing reference-only endpoint for a department that has not opted into the stronger source-document rule. A new multipart endpoint hashes a supplied source file in memory, validates format and <=6 MiB cap, and atomically stores digest/size/media with the clinical attestation. Uploaded source content and original name are discarded. No patient file is stored, served, logged or synchronized in finance.
- Owner can irreversibly opt a protected department into mandatory source-document fingerprints, confirming password and checking no earlier unbilled, reference-only attestation that would become impossible to invoice. No silent toggle-off.
- Enforce the department rule at API, invoice-issue, and SQLite BEFORE INSERT trigger boundaries, including direct SQL bypass. The clinical role remains isolated and revocation works immediately. A clinician with a current department grant may re-upload original source to compare its digest; this check never persists the bytes.
- Old cases, invoices and medical witness rows remain untouched. Migration from a genuine G3A schema first creates a verifiable encrypted rollback; refusing to migrate without key. All tests use synthetic documents and isolated databases; no production access.
- `sha256` proves byte-level comparison against the submitted file, not clinical validity, doctor signature, authority or external EHR archival. Multipart spool and possible OS temp files require encrypted host filesystem and secure operating policy for future production.

Acceptance: RED->GREEN API tests for optional and required policy, forged direct SQL/legacy witness rejection, wrong file/no docs/size/auth/revocation; real G3A migration+encrypted restore; UI response with local file upload, responsive browser smoke; full regression and source package QA; production remains NO-GO.
