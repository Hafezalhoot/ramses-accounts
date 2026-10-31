# G3E -- inventory case visibility and reviewer authorization (2026-11-01)

**Intent:** A warehouse assignment must never grant access to unrelated patient cases. This is the next previously recorded P0 follow-up from G3D; it is not a new, unapproved patient-access policy.

**Scope:** Existing SQLite/FastAPI app, synthetic test database, one local feature branch only. No deployment, no real patient data, no live DB migration. Preserve existing owner-wide visibility and warehouse-only unlinked issue visibility.

**Security rule:** For a non-owner stock user, an issue or return with `case_id` is visible only while that same active user also has a currently active `billing_point_access` grant for the case's `default_point_id`. Read and approval must use equivalent server-side checks; already-decided or pending unrelated documents may not reveal their status via a distinct 409 before the 403 authorization gate. Revoking the patient grant must take effect without login/logout; an inventory grant alone is insufficient.

**Behavior:** `/api/inventory/overview` must return only allowed case-linked issues and returns, while global inventory quantities and standalone supplier stock documents retain their current behavior. `/api/inventory/issues/{id}/decision` must forbid a reviewer without case access before altering a posted or pending case-linked issue. `/api/inventory/issues/{id}/returnable`, return submission/review and case-cost access already check point permission and must stay intact.

**Approaches:** (A) Hide rows in browser (rejected: API leak persists); (B) filter SQL on server and verify reviewer inside the write transaction (selected: follows the existing `case_scope` guard and SQL filter used for returns); (C) introduce a new case-specific warehouse ACL schema (rejected: unnecessary and changes the existing permission model).

**Acceptance:** Direct HTTP negative tests for two billing points, owner visibility, stock staff without patient grant, allowed staff, revocation without relogin, and blocked approval with no financial or inventory side effects. Verify inventory and returns operations still work in existing G3D tests. No unverified claims of operational readiness.
