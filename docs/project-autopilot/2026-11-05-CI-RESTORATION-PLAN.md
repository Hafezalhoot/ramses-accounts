# Zero-GitHub-Actions QA Implementation Plan

> For engineering collaborators: use test-driven-development and verification-before-completion. Test exact committed source, report incomplete gates, and never claim real-hospital certification.

**Goal:** Run repeatable Ramses financial/security regression tests without enabling GitHub Actions or using its private-repository minutes.

**Implementation:** Keep the independent `ci_audit_gate.py` and synthetic test suite; use `scripts/run_local_qa.py` on a full-history local/Work checkout. Run in detached temporary Git worktree and record the tested SHA, step exit codes, and synthetic QA reports outside the repository. Keep `.github/workflows/` empty on `main` and the QA PR.

**Constraints:** No production database, no patient data, no external payment, no Github-hosted actions, Python 3.13, Node.js, Git. Source remains TEST ONLY.

## Verified isolated work

- [x] Local regression RED when runner did not exist; GREEN after implementation.
- [x] Separate synthetic test rejects active `RAMSES_DB_PATH`.
- [x] Separate synthetic test rejects uncommitted source.
- [x] Separate synthetic test rejects reporting to a folder within source checkout (RED then GREEN).
- [x] Local existing `ci_audit_gate.py` tests exercise pass, failure, blocked fixture and report spoofing.
- [x] Run all isolated tests and syntax checks; record exit codes in discussion.

## Before merging PR

- [ ] Ensure no active workflow remains in `.github/workflows/` after changes.
- [ ] Checkout CI PR on Work or trusted machine with full Git history and Python 3.13 installed.
- [ ] Run `python scripts/run_local_qa.py --full` and inspect `run.json`, smoke/full logs, and `audit.md`.
- [ ] Fix any genuine FAIL/TIMEOUT; distinguish historical SKIP and BLOCKED from PASS.
- [ ] Independent review; merge only after verified evidence; keep GitHub Actions disabled.
- [ ] Bring S15 branch up to validated base and repeat full QA on that exact commit before financial merge.

## Operation

- Tests run **on demand** in a user-controlled compute environment. GitHub connector handles read/write/PR, not execution.
- The one-line runner intentionally refuses a shallow or dirty checkout or an environment with active live database/mirror variables.
- CI-style enforcement without Actions or another always-on runner is **not automatic**; preserve PR review discipline and SHA evidence.
