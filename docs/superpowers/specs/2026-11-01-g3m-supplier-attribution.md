# G3M — Evidence-based attribution of historic AP control journals (TEST ONLY)

G3L intentionally shows unassigned 2200 journals. G3M allows independently reviewed, evidence-backed mapping of ONE already-posted MANUAL journal containing exactly one 2200 ledger line to ONE existing supplier. It **never creates or changes a GL journal, opening balance or cashbook payment**. Attribution is a *classification* at the review date, not proof of opening balance or supplier receipt.

## Constraints
- Only posted original, non-source-backed `manual` GL journal, with exactly one line on account 2200 and nonzero signed amount; no automatic detection based on memo or name. Reject any system-linked/receipt journal. Do not split a mixed supplier journal; flag it for a separate human-governed process.
- Require evidence reference and justification, active supplier, warehouse preparation grant, and independent financial reviewer role plus current explicit approval grant. Maker and original journal creator/reviewer cannot approve. Failed/rejected mapping stays immutable; a new proposal may replace a rejected one.
- SQLite guards must reject forged approved inserts, same-user approval, changed final decisions, duplicate open/approved mapping, and changes to journal/vendor/proof after creation. Recheck rights on a locked write transaction.
- Existing G3L report continues to show GL balance unchanged and unassigned journals until approval; `as_of` shows attribution only from the Cairo date of approval onward. Negative/credit-direction journals remain sign-accurate; abnormal negative balances are flagged.
- Only synthetic data in tests. Add a small RTL form, a reviewer queue that displays evidence and signed GL amount, no patient identifiers, preserve Cairo and 320/375/1440. No deployment or real financial changes.
- NO-GO real operations until financial owner defines the document evidence, delegation, signoffs, source archive and complete opening balance policy.
