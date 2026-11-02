# S2 cashier stabilization - acceptance brief (synthetic only)

Starting point: committed G3N-S1 (1c35cb5). No real hospital data.

Goal: prove one business day with 3 separate external cashier shifts (night, morning, evening),
internal central treasury custody, independent handovers and reviews, physical deposits,
GL reconciliation, and prevention of duplicate movements.

Constraints:
- No new hospital modules, no broad rewrite and no production DB migration or deployment.
- Real FastAPI TestClient and disposable SQLite, plus a browser-visible treasury deposit path.
- Clerk A must never review their own shift, receive their own cash, or post another user's deposit.
- Cash transferred to the internal vault cannot be counted as new revenue.
- All physical receipts carry a stable retry key; once-posted money cannot move twice after retries.
- Fail safely on insufficient funds, a missing independent handover or an unassigned clerk.
- Do not represent in-process tests as real network/TLS validation.

Acceptance:
1. 3 external shifts, one internal shift, different cashiers, distinct accounting reviewer.
2. External cash 100+200+300 EGP -> central 600 EGP, central expense 50 EGP -> central 550 EGP; external zero.
3. 4 closed shifts; no unsettled variance; GL balanced, only 600 EGP credited to medical revenue.
4. Browser cash receiver can use the actual treasury deposit endpoint via the shifts UI.
5. Duplicate request with same key returns same transfer without booking twice; mismatched payload fails.
6. Existing shift, transfer and full CI regressions pass or failures documented.
