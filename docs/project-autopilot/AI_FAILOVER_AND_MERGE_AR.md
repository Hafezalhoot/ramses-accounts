## Active owner policy — 2026-11-06

The owner approved Public visibility after full-history/content audit and attested that published evidence is synthetic. GitHub Actions is now authorized for isolated TEST-ONLY CI. Use `docs/project-autopilot/PUBLIC_CI_AI_WORKFLOW_AR.md`. Historical no-Actions/private-repo instructions below are superseded by this explicit policy. No production deployment or real hospital data. Any legitimately authorized assistant may complete implementation, read CI, and perform a permitted SHA-checked merge; no particular AI reviewer is required.

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

**State (2026-11-06):** portable fallback code is in draft PR #6; Mac installation details are external. Bot filtering, fallback end-to-end behavior, and branch protection still require explicit verification. TEST ONLY / PRODUCTION NO-GO.


## Portable fallback now implemented in this PR (not yet merged or end-to-end verified)

A second trusted Mac/Linux machine can use a reviewed `main` checkout, Docker, Python 3.13, GitHub CLI (`gh`), and the **original V8.0 source ZIP** to test any authorized same-repo PR. The launcher MUST come from reviewed, updated `main`; never execute an unreviewed PR's copy of the launcher on the host.

```bash
gh auth status
docker info
git checkout main
git pull --ff-only
python3.13 tests/test_qa_fallback.py
python3.13 scripts/qa_fallback.py --pr PR_NUMBER \
  --v80-archive "/path/to/original/Ramses_Accounts_V8_0_Double_Entry_Decision_Foundation.zip"
```

Inspect the local report directory outside Git. To intentionally post **a new, actually executed** result and a sanitized comment, repeat the same call with `--publish`. No secret, patient information, V8.0 archive, or raw log is published to GitHub.

The fallback validates PR author against `tools/qa/trusted_pr_authors.txt`, same-repository source, exact SHA before and after tests, clean trusted `main`, and a full-history checkout; rejects tracked private/DB files; runs in a disposable Docker container with networking off, dropped Linux capabilities, no host credentials or Docker socket; and audits all test statuses. Known historical SKIP remains a SKIP; missing V8.0 is BLOCKED and **cannot produce a green result**. This runner deliberately publishes to the **existing** `ramses/mac-local-qa` status context for compatibility, with the description `fallback Docker` identifying the reporter. Do not run the Mac watcher and fallback reporter simultaneously on the same SHA; most recent GitHub commit status wins.

Allowlist today: only `Hafezalhoot`. A separately authenticated bot/Claude identity needs explicit owner approval, an allowlist commit to trusted `main`, and a distinct approval for the Mac watcher's own allowlist. The model provider does not grant GitHub credentials or approval by itself.

Authorized merge after matching SHA success, review of code and base compatibility, and GitHub permissions is independent of any single AI: `gh pr merge PR_NUMBER --repo Hafezalhoot/ramses-accounts --merge`. No `--admin` bypass, no force pushes, and no production effects.

**Do not activate a required-check ruleset yet.** First verify the fallback end-to-end on a second trusted device, using the real V8.0 source fixture, and confirm it can post a status accepted by the repository. Private repository rulesets require an eligible GitHub plan; check availability before configuring. Preferred future rules: PRs required, **0 mandatory reviewer approvals** (AI provider failover), status `ramses/mac-local-qa` from any authorized source, no force push/deletion, and upstream-current integration verification. The connected GitHub app in this chat has no action to change rulesets, so no repository protection was modified here.

**Actual verification so far:** portable runner Python syntax and local safety/audit regression tests; GitHub upload read-back. **Not yet verified:** Docker image build, full historical suite on a second machine, fallback status publishing, and branch protection. Project remains TEST ONLY / PRODUCTION NO-GO.


## Checked merge implementation; actual GitHub plan limitation (6 Nov 2026)

`scripts/qa_checked_merge.py --pr PR_NUMBER` checks an open Ready PR from an approved same-repo author targeting current `main`, the exact current head SHA, the latest successful `ramses/mac-local-qa` status with zero BLOCKED, and that the PR branch contains current `main`. `--merge` repeats checks and invokes GitHub's SHA-constrained merge API; without it no merge occurs. The same authorized AI may run both commands; no mandatory second AI.

GitHub's live API returned **HTTP 403** for the private repository rulesets list: **"Upgrade to GitHub Pro or make this repository public to enable this feature."** The `main` branch was **unprotected** when inspected. Do **not** make the hospital repository public. The checked merge helper cannot enforce policy against direct push by an account with write access; private-repo branch protection needs an eligible GitHub subscription. No GitHub protections were enabled or changed in this turn.

See [Arabic Quickstart](AI_FAILOVER_QUICKSTART_AR.md) and [Implementation Plan](../superpowers/plans/2026-11-06-ai-failover-qa.md). The new fallback and checked-merge scripts are in **draft PR #6**, pending real Docker/PR integration and review. TEST ONLY / PRODUCTION NO-GO.

## Owner decision: temporary public visibility during development (2026-11-06)

The owner has explicitly requested **temporary Public visibility** to use GitHub Free rulesets during development and then return to Private. This supersedes the earlier blanket "never make public" recommendation. The visibility change itself has NOT been executed from ChatGPT; the connected GitHub app has no repository visibility mutation action.

**Irreversibility warning:** returning to Private later cannot recall clones, downloaded commit history, detached public forks or other copies; do not imply that Public can be undone for confidentiality.

**Publication gate before owner changes visibility:** 
- On a trusted full clone: `git fetch --all --tags`, then run `gitleaks git --redact --log-opts="--all"` and inspect findings locally (do not upload secret values or unredacted reports).
- Inspect all Git branches and historical commits, issues/PR comments, screenshots/PDFs and any test-fixture files for credentials, real patient/staff details, bank details, sensitive hospital documents, internal URLs or commercially confidential information. A scan limited to today's main tree is not enough.
- If leaks are found, **rotate/revoke real credentials first** and keep this repository Private; history rewriting may still not eliminate all accessible copies. Consider a clean-history Public development mirror if the original history is not publishable.
- Owner may switch visibility from repository GitHub Settings → General → Danger Zone → Change repository visibility → Public. Verify `visibility=public`, that GitHub Actions are still disabled, and then configure supported rulesets carefully (no AI-vendor bottleneck; preserve a verified QA recovery path).
- Before the eventual Private switch, document that public forks persist, that public-repo rulesets may become unavailable on GitHub Free, and choose a private-safe fallback for merges/tests.

**Preliminary read-only inspection in ChatGPT (not certification):** current main tree: 808 tracked files, including 74 PDF/image assets and 107 data/report files; no obvious committed `.env`, database, ZIP backup, key or secret-file paths at 12 branch tips. Selected text files showed no obvious credential-token patterns, but complete history, screenshots, PDF and Issue/PR content have NOT been fully scanned. Keep `Private` until preflight succeeds.
