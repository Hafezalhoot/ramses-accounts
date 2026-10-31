# G3D stock returns to original approved FIFO allocations (local development only)

**Scope:** Non-drug consumables physically returned from an approved issue. Only usable/non-expired items, original patient case still open, current accounting month open. No supplier credit, invoice adjustment, clinical authorization, stock quarantine, or cash movement is inferred.

**Design:** An immutable, separate return document holds the original issue and per-allocation returned quantities. A different authorized reviewer approves it, producing a posted balanced journal Dr inventory 1100 / Cr consumption 5100 at the original allocation unit cost, dated the return. Pending/rejected returns affect neither inventory nor GL. A return approved on a day earlier than an already-approved *later-day* issue for that item is rejected to protect historical FIFO decisions. No original issue or allocation is mutated. Current-period corrections are standalone journals.

**Invariants:** Source is approved; original issue and case remain accessible and (when case-linked) open; every allocation belongs to the source, return quantity >0 and approved+pending returns never exceed original allocation; serialized BEGIN IMMEDIATE and idempotency key; no self-approval; approved returns immutable; no expired stock returned; no closed-month return or approval; direct SQLite writes must not bypass capacity/dated/policy checks; GL, available stock, per-case cost and reconciliation move atomically; unauthorized roles cannot see patient costs or create returns; existing historical records remain untouched. The FIFO policy is deliberately calendar-day based as in G3C.

**Release gate:** Test RED/GREEN with real FastAPI TestClient + SQLite, frozen real G3C fixture upgraded behind encrypted pre-DDL backup, restoration and no extra backups on retry; include prior regression/CI. Not production/UAT approval.

**Financial case closure invariant (G3D addition):** If any return linked to the case
is still pending, neither ordinary financial clearance nor no-charge clearance may
close the case. An SQLite BEFORE UPDATE guard also denies a direct status update
even when an approved clearance record is present. The reviewer must resolve the
pending return first; no automatic approval or deletion of immutable evidence.
