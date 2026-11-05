# Pricing and split-payment implementation plan

Goal: complete the usable S14 slice defined in S14_PRICING_DESIGN_AR.md, preserving S13 history and all ledger/clinical controls.
Architecture: additive immutable tariff/package/order/line-term tables; pricing domain calculates quotes; existing billing owns fulfillment, invoicing, collection and GL. A pricing API and owner workspace expose the actual integrated paths. FastAPI/SQLite/plain JS; no new dependencies.

- [x] Write real API regression for catalog, location/list prices, costs, rules, packages, rounding, snapshots, billed net and access; observe missing route failure.
- [x] Implement additive schema and pricing module with protected APIs and integer quote engine. Version snapshots, atomic orders and retry keys.
- [x] Connect existing case totals, fulfillment, draft/invoice and print readers to net amounts; reject legacy bypass and incomplete package billing/cancellation.
- [x] Owner pricing workspace and cashier priced-service/package modal; five payment methods per receipt and multiple receipts/advance scenarios. Browser acceptance.
- [x] Genuine frozen S13 migration and rollback preservation test; independent branch review; regressions and V8.0; protected preview and S14 delivery with honest remaining scope.

Review focus: stale tariffs, discount-cent rounding, cost secrecy, quote tampering, incomplete bundles, financial double posting, clinical evidence, negative authorization, legacy compatibility and partial migration.

- [x] Service fee slice (service_fees.py): projected versus collected basis, fixed per occurrence, shared performers, independent accept/reject, incremental proposals, immutable approved payable and reversal, no cash movement. Dedicated subagent owns this file and its tests; parent owns pricing and billing seams.
- [x] UI slice (pricing_ui.js/css): owner forms, package builder, cashier quote confirmation and service fee review. Dedicated subagent owns only these files; parent wires nav and runs real E2E. Independent task and whole-branch reviews follow.
