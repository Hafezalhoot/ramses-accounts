# S2 technical/operational decisions

- Preserve G3N-S1 backend ledger, SQLite schema and permission guards; no unasked redesign or accounting migrations.
- Treat an independently accepted external shift as the source of custody for a **physical** treasury receipt. Destination must be the same receiver's open current-day central shift; another accountant approves shift closure.
- Use existing `voucher_request_keys` with `treasury-deposit:` namespace to atomically deduplicate retry keys; a replay returns previously approved voucher metadata before shift/period revalidation and causes no mutation.
- Keep `client_request_id` optional for historical scripts/existing clients, but always supply it from the S2 UI; document residual compatibility risk until all callers migrate.
- Block duplicate normalized physical `note` for the same source shift, even when submitted from a different tab/device/request key. Distinct partial deposits require distinct original envelope references. This guards accidental duplicate cash, not forged evidence or different descriptions of one envelope.
- Reuse the shift page and existing modal instead of another management dashboard. Expose button only from server-calculated receiver eligibility; view gating is helpful UX, not an authorization boundary.
- Keep current-page retry key while awaiting confirmed response; if a browser restart loses it, a repeated physical reference raises 409 and must be reconciled rather than silently posted twice. Do not persist sensitive finance notes across users in browser localStorage.
- Preserve Cairo typography, RTL, current palette and layouts. Fix schedule `end` metadata instead of manually writing a misleading fixed period.

---

## Historical project record — preserved from S1 source

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


## G3C decisions — nonproduction
- **D-14:** Reuse immutable G2T FIFO issue allocations, never compute cost from a new estimated price or manufacture an invoice from it. Show only approved case-linked costs with an explicit partial-scope notice. Require BOTH warehouse read and case-specific cashier point access.
- **D-15:** Without time-of-day in the G2T source, disallow NEW approvals dated strictly before an already-approved later-day issue of the same item; same-day approval order governs. This trades convenience for an immutable historical cost basis. Corrections need a future approved adjustment mechanism, not direct GL rewrites.
- **D-16:** Guard date ordering in SQL as well as API. The new triggers must be backed up before any historical G3B schema upgrade; old posted rows are never modified.
- **D-17:** Inventory case costing excludes unlinked issues, drug stock, staff costs, doctor fees, insurer contracts and historical opening inventory, and cannot be described as case profit. No patient identities appear in the payload.

## G3D decisions (local synthetic-data development)

- **D-18:** Return to the original approved receipt allocation, not a stock amount at today's average price. Preserve original issue and ledger; independent reviewer posts separate Dr1100/Cr5100 at original unit cost. No patient refund/invoice credit is inferred.
- **D-19:** Pending returns reserve their original issued quantity but cannot increase sellable stock. Approved returns increase inventory and reduce case consumables cost only as of physical return day; expired items rejected. Patient case grants apply also to replayed request IDs.
- **D-20:** Do not backdate stock issuance before actual physical return or insert a return before a later posted issue for the same item; source records remain immutable. Calendar-day chronology remains a known limitation of the G2T source model.
- **D-21:** Financial case closure and monthly closure both reject pending returns. A SQLite case-status trigger defends against a direct SQL close even with an approved clearance record. These conditions are tested with synthetic cases.
- **D-22:** Legacy tests need Cairo business date, not UTC/local OS date, and a fully completed day outside the shift grace window; repair test-clock assumptions only, not financial cutoff logic.
- **D-23:** No real hospital data, offsite file replication, medical reuse clearance, infection-control review, PO/AP vendor liability, or production authorization.
