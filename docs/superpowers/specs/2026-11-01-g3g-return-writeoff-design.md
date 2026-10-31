# G3G — Accounted disposal of rejected return stock (test only)

## Intent and boundary
Continue G3F without changing original FIFO returns or medical decisions. A hospital-owned but clinically rejected return remains quarantined until a separately reviewed disposal voucher removes its quantity and book value. G3G is an accounting prototype only: not evidence of real-world destruction, infection control certification, or approval for use with actual patients.

## Chosen design
Use a new immutable SQLite document per rejected original return line, with partial quantities supported. Existing inventory grants authorize prepare/approve, but the same person cannot perform both acts; clinicians cannot post journals. The preparer supplies a physical-loss document, date, reason and a declared physical removal; independent approval atomically creates Dr 5195 (loss of rejected supplies) / Cr 1100 (inventory) at original lot cost, then finalizes the voucher. Rejecting a proposal does not affect stock or GL. Keep original RETURN Dr 1100 / Cr 5100 and patient case net cost untouched.

Alternatives rejected: automatically expense a medical rejection (no financial segregation); edit original return journal (destroys traceability); expose patient case details in disposal worklist (privacy risk). No new permission role, no supplier settlement and no pharmaceutical/UDI workflow.

## Invariants
- Only financially approved, clinically rejected return lines are eligible; unreleased and medically released lines cannot be written off.
- Pending plus approved disposals cannot exceed the rejected quantity. Each document is immutable after decision; approval is one-time and transactional.
- Block historical G3E lots which show unverified reissues beyond supplied lot units plus medically released returns; do not fabricate historical clearance or inventory balance.
- Preparation and approval recheck current warehouse permissions in write transactions. Closed accounting months reject writeoff posting. No patient IDs or protected clinical notes in the disposal API or audit payload.
- Inventory reporting subtracts only approved writeoffs from physical/financial quantity, including the quarantine subtotal; reconciliation proves inventory 1100 balance against source documents including writeoffs.
- Existing G3F database upgrades add new tables/triggers and the 5195 expense account after an encrypted pre-upgrade snapshot; no backfilled approved disposal data.
- Technical verification uses synthetic fixtures, negative tests, migration check, CI, complete suite and optional offline Chromium screens. Production remains NO-GO.
