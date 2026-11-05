# Safe GitHub CI Restoration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove dependence on this chat container's unavailable GitHub DNS by running source regressions in a secure GitHub-hosted Python 3.13 runner.

**Architecture:** GitHub Actions PR/push/manual workflow on the maintained branch, with read-only token and full Git history, plus a stdlib TSV integrity gate for historically unavailable fixtures. Repository-level Actions enablement and branch-protection are separate owner actions.

**Tech Stack:** GitHub Actions, Python 3.13, SQLite ephemeral tests, pytest/unittest, YAML, GitHub branch checks.

**Spec:** `docs/project-autopilot/CI_SAFE_ENABLEMENT_AR.md`

## Global constraints

- Existing S14 `main` base `682b8338ef1e24eace67c01c86af5f1133e92dd5`; do not rewrite history or merge S15.
- No hospital data, .env, private/, SQLite, financial payments, hosted deploy or new credentials.
- Actions disabled at repository level until owner changes it; no claim of GitHub-hosted PASS prior to actual run.
- Expected missing original V8.0 and private workbooks are not treated as PASS or production acceptance.

## Review focus

1. Privilege abuse by PR from untrusted branch: permissions read only, no `pull_request_target` or secrets.
2. Historical S13 sources unavailable through shallow checkout: `fetch-depth: 0` mandatory.
3. Unknown silent SKIP/BLOCKED: fail gate on unexpected names or states.
4. False-green when QA file absent/stale: delete report before run, reject missing/duplicate/too-short report.
5. Sensitive artifacts: allow only sanitized status summary, seven-day retention.

### Task 1: Reproduce and isolate failure

- [x] Try `getent hosts github.com`/`curl -I https://github.com` in this container; observe DNS failure.
- [x] Inspect `main`, Actions and historical branch workflow locations through GitHub connector.
- [x] Confirm no active `.github/workflows/` on `main`; observe zero prior runs and legacy old workflow mismatch.

### Task 2: Add fixture-aware report gate

**Files:** `scripts/ci_audit_gate.py`, `tests/test_ci_audit_gate.py`.

- [x] Write failing synthetic unittest first; observe missing module.
- [x] Implement gate, run 11 positive/negative unittest cases (including skip reason integrity); check Python compilation.
- [ ] Run those tests from checked-out actual S14 CI branch; compare full-QA report counts.

### Task 3: Add branch-scoped workflow

**Files:** `.github/workflows/finance-ci.yml`, `scripts/ci_smoke.py`.

- [x] Create `pull_request/main`, `push/main`, and manual-only job choice.
- [x] Pin GitHub-owned actions using reviewed SHAs; Python 3.13; full history; read-only token.
- [x] Add synthetic full audit and clear SKIP/BLOCKED result summary.
- [x] Parse YAML locally and inspect security invariant fields.
- [ ] Observe actual workflow run and status for open PR; diagnose failures.

### Task 4: Restore repository policy and verify S15

**Files:** `docs/project-autopilot/CI_SAFE_ENABLEMENT_AR.md`.

- [x] Write precise UI/runbook for GitHub owner without sharing secrets.
- [ ] Repository owner enables trusted GitHub-owned actions / read-only token.
- [ ] Rerun PR checks, inspect run logs, fix any real failures.
- [ ] Merge CI-only PR after review, require both checks on main.
- [ ] Sync S15 branch with main, re-run its checks, then review separately.

**Outcome rule:** Infrastructure is **prepared** until a real GitHub Actions run succeeds; project is still TEST ONLY / PRODUCTION NO-GO.
