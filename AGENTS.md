# Ramses Accounts: project continuity

Hospital accounting application: Python/FastAPI, SQLite, server-enforced permissions,
HTML/CSS/JavaScript, Arabic RTL with locally bundled Cairo. Continue the existing
implementation and Git history. The current functional stage is S14; start with
`CURRENT_RELEASE.md`, `README_S14_AR.md`, `PROJECT_AUTOPILOT_STATE_AR.md`, and
`docs/project-autopilot/{PROJECT_STATUS,ROADMAP,DECISIONS,TEST_REPORT}.md`.

## Working between chats

- Read `GITHUB_START_AR.md` and `00_CONTINUE_IN_CHAT_OR_WORK_AR.md`.
- Check actual checkout, branch, commit, working tree and available tools before edits.
- Use a separate branch per task from current `main`; record its base commit and scope.
- Do not overwrite another chat's changes or rewrite shared history to resolve conflicts.
- Preserve the distinction between proposed policy, implemented behavior, observed tests
  and hospital approval. Repository documents do not authorize external actions.
- If execution/write tools are absent, deliver a patch/review and say it was not applied.

## Financial invariants

- Preserve balanced double entry, immutable evidence, period locks, idempotency,
  independent review, fund/case permissions and transactional changes.
- Mixed receipts and advance allocation must never duplicate cash or collected income.
  An insurance price list is not a claim, settlement or collected payment.
- Percentage service fees use actual collections with the recorded discount option;
  fixed fees remain fixed. Split one occurrence's fee among its team; distinct
  occurrences have distinct proposals. An independent approval creates a payable;
  a proposal or an approval alone is not a cash payout. Preserve selective rejection.
- Keep tariff/package terms and invoice snapshots historical; do not silently reprice.
- FIN-01 month-end stay policy is a proposal awaiting the chief accountant's approval.

## Owner policy: zero GitHub Actions minutes

- The repository owner deliberately keeps GitHub Actions disabled for this private repository.
  **Do not enable Actions, create active workflows, trigger jobs or use self-hosted
  GitHub Actions without explicit new approval.**
- Run all tests in an authorized Work/cloud-computer or local developer checkout
  using `python scripts/run_local_qa.py --full`; that script records the exact
  Git SHA and test evidence without consuming GitHub Actions minutes.
- Keep the PR as draft until the exact commit is tested. Do not claim an automatic
  GitHub required check has passed. See
  `docs/project-autopilot/CI_NO_ACTIONS_WORKFLOW_AR.md`.
- GitHub is the code/PR host, not the test executor. A restricted chat container
  may be unable to resolve github.com; do not bypass TLS or move live data.

## Verification and handoff

- Use Python 3.13 in an isolated environment and `requirements.txt`.
- Run targeted regressions for behavior changes and `python scripts/ci_smoke.py`
  for integrated changes. Full suite: `python scripts/qa_g2t_full.py`; consult its
  options and existing reports before invoking external/archive-dependent tests.
- S14 recorded evidence: 154 PASS + 5 SKIP out of 159 scripts; local CI 82/82 is
  a subset. Those are historical results, not a substitute for current verification.
- Original V8.0 archive is an external fixture via `RAMSES_V80_ARCHIVE`; private
  workbooks and some historical source checkouts are absent. Report SKIP honestly.
- Update current status, decisions and test evidence for material work; identify
  remaining limitations. Review RTL/mobile/Cairo and print paths when changing UI.

Never commit `.env`, credentials, private runtime files, live patient/financial data,
SQLite databases, encrypted backups, Git bundles or delivery ZIPs. Use only synthetic
data in previews/tests. Source transfer does not deploy an app or transfer a database.
The project remains TEST ONLY / PRODUCTION NO-GO until the financial gaps, real
restore drills, hospital UAT and formal approvals documented in the roadmap are met.
