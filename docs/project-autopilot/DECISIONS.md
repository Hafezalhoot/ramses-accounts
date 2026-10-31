# G3A Decisions — test-only

- **D-01:** Prefer a real `clinician` SQLite login role, not a custom viewer grant or client-side flag. This requires rebuilding the users table with SQLite FKs temporarily disabled *only* inside a single transaction, backed by verified encrypted snapshot and followed by `foreign_key_check`.
- **D-02:** Legacy `viewer` clinical grants are suspended at upgrade; historical clinical attestations and active department policies remain. Cost: protected departments cannot issue additional invoices until owners provision/review proper clinical accounts; this is intentionally fail-closed, not a seamless automatic privilege transfer.
- **D-03:** Owner's password re-entry and registration reference represent a local *manual review record*, not independent registry verification. Do not call it a licensed medical signature.
- **D-04:** Clinical users have a narrowly allowlisted server API surface. Finance lookups are never downloaded by clinical UI. Never rely on hidden navigation as authorization.
- **D-05:** No live migration, public deploy, actual patient data, cloud approval, or secret values. Separate IT/medical/finance validation remains a release gate.

- **D-06:** Historical viewer-signed G2Z attestations are audit records only. Require a clinician-origin attestation for *new* protected invoices; preserve old records/invoices. Unbilled legacy viewer-signed service needs an independently approved financial+medical remediation workflow. No automatic backfill.
- **D-07:** Clinician password rotation or deactivation revokes earlier manual credential approval in the *same* SQLite transaction. Reactivation needs a new professional review; immutable historical attestations stay untouched.
- **D-08:** Make the existing full-height sidebar independently scrollable so lower admin actions remain reachable on small displays. Verify owner credential-review modal in real Chromium at 375/1440; no navigation reordering.

## G3B decisions (test-only)
- **D-09:** Keep actual patient/clinical document bytes out of accounting DB entirely. Hash the uploaded synthetic PDF/JPEG/PNG at the request boundary; retain only SHA-256/size/media and a separate reference; original must remain in an approved medical document repository. Note that multipart may use temporary OS disk files.
- **D-10:** Owner opt-in is one-way per department and requires password confirmation; don't silently activate the stricter condition for earlier evidence, and reject opt-in with legacy unbilled reference-only witnesses that would become impossible to invoice.
- **D-11:** Add SQLite BEFORE INSERT guard and invoice issue guard in addition to FastAPI checks, preserving old NULL hashes. A SHA digest is not an external signature or proof of medical correctness.
- **D-12:** Preserve original G3A users/session IDs and proofs through additive columns and encrypted `.rbe` pre-DDL rollback; no real database migrations authorized.
- **D-13:** Correct suite status classification for historical `SKIP` stdout without colon; never count unexecuted predecessor tests as PASS.
