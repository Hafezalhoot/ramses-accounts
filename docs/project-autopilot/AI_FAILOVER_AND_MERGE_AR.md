# Ramses AI Failover and Merge Protocol — proposed / 2026-11-06

**Scope:** source development and TEST-ONLY validation. This document does **not** grant production access, install a local runner, change repository permissions/rulesets, turn on GitHub Actions, or approve hospital financial policies.

## Intent

The owner may switch between ChatGPT, Codex, Claude, or any future coding assistant **at any point**, including before testing and before merging to `main`. The new assistant must be able to continue without a quota, conversation, or account session from the previous assistant. No particular AI vendor and **no second AI reviewer** is a mandatory dependency.

The source of truth is `Hafezalhoot/ramses-accounts` Git history, the current PR, the exact commit SHA, and checked-in project docs — not a previous model's memory or claim. Each assistant requires its **own legitimate GitHub read/write and merge permissions**; no shared secret or copied token.

## Standard handoff for any assistant

1. Read `AGENTS.md`, `CURRENT_RELEASE.md`, `PROJECT_AUTOPILOT_STATE_AR.md`, `docs/project-autopilot/ROADMAP.md`, the active PRs and this document. Run `git status`, `git fetch`, and inspect the exact HEAD SHA.
2. Select a distinct branch from current `main` (or explicitly stack a branch onto an existing PR); do not overwrite concurrent work or force-push `main`.
3. Implement with synthetic fixtures, focused regression tests, and independent permission/accounting checks. Explain changed files, the previous and new commit SHA, uncovered risks, and what was actually executed.
4. Open/update the PR. Read the recorded `ramses/mac-local-qa` status **for this exact commit**, not an older green status. Do not treat `SKIP` as a pass, and do not treat successful synthetic QA as production certification.
5. Review the diff and rebase/retarget on latest `main` where necessary; check integration conflicts. Re-run tests on the updated commit/merge candidate before merge. If the user's delegated merge rights and repository rules allow it, **the same assistant** may merge the verified PR. A separate AI assistant is optional, not required.
6. After merge, record the merge SHA, source status, tests and limitations in project status/handoff docs. Keep GitHub Actions disabled per owner policy.

## QA: primary and fallback, without GitHub Actions

- **Primary:** the Mac's `Ramses Local QA` agent scans supported same-repository PR commits approximately every ten minutes while the Mac is awake, Colima/Docker and the network work, and GitHub authentication is valid. It publishes `ramses/mac-local-qa` and a PR summary. A status is evidence of a test report, not a signature of production readiness.
- **Fallback:** if the Mac is asleep, offline, over capacity or unavailable, a suitably authorized assistant can use **another trusted local computer/runtime** with repository access, Python 3.13, Node.js and the same pinned test environment. Use the isolated `scripts/run_local_qa.py --full` **where that file exists** (currently PR #4, not on historical `main`), or run the equivalent source-owned `scripts/ci_smoke.py` and `scripts/qa_g2t_full.py` with the audit gate on a clean full-history checkout. Never execute these against a hospital production database.
- Only a trusted reporter with explicitly granted status-write permission may publish a replacement QA status for the exact tested SHA and environment version, with a link or path to sanitized evidence. Do **not** forge/mark success to get around a missing Mac check. Without an authorized alternate reporter, keep the PR pending until verified status is available.
- The current local watcher deliberately filters PR creators to the repository owner's identity and ignores bot/fork PRs. Before a distinct Claude/bot account authors PRs, **review and explicitly extend** this safe allowlist to the intended identities, while still blocking untrusted forks and credentials. Merely granting GitHub access does not automatically change the Mac watcher's filter.

## Merge policy without an AI bottleneck

- Preferred path: task branch → PR → verified latest-commit QA + reviewed diff → authorized merge into `main`.
- Do not require Codex to approve ChatGPT or Claude to approve Codex. The owner may authorize any one capable assistant to finish the full source-code lifecycle (including tests and merge) within repository controls.
- Recommended `main` protection: no force pushes/deletions, verified QA required for current commit, no default direct pushes. **Do not** configure a mandatory human/AI reviewer that nobody can supply, or a check dependent exclusively on one unavailable Mac. Before enabling any protection, test the owner-managed recovery/fallback and permissions.
- No automatic merge based on `PASS` alone. A synthetic test cannot authorize hospital go-live. Financial-policy decisions, production migrations, opening balances, sensitive patient/employee access, and actual disbursements still require the relevant human approvals and backups.

## Failure scenarios and honest limitations

- **One AI provider's quota runs out:** stop using that session; another assistant reads GitHub and continues from the latest branch/PR independently. No previous assistant approval required.
- **Mac unavailable:** use the trusted alternate QA route above, preserving version, SHA, logs and status provenance.
- **GitHub unavailable or credentials expired:** local work can continue in a full checkout, but pushing, PR updates and merging are blocked until authorized GitHub connectivity returns.
- **Tests fail:** keep the PR unmerged, identify root cause, create/re-run focused tests, then repeat the full gate. Never bypass by fabricating green status.
- **Merge conflicts or outdated QA status:** synchronize/retest, do not reuse a previous green result.

**Current state:** proposal only. The actual Mac installation, distinct-bot filtering, `main` branch protection and authorized alternate reporter must be separately inspected/configured and verified. Project status remains TEST ONLY / PRODUCTION NO-GO.
