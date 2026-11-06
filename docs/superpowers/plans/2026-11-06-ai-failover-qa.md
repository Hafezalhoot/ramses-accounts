# Provider-independent AI QA failover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Any authorized coding assistant can implement, safely test, publish an authentic QA result, and merge approved source changes into Ramses `main` without depending on another model or GitHub Actions.

**Architecture:** Keep GitHub as source of truth. Use installed Mac Local QA as primary; provide an alternate trusted-main QA launcher on a second Mac/Linux machine, executing untrusted PR sources in networkless Docker while preserving GitHub credentials only on the host. Leave production migrations and protected branch settings untouched until verified.

**Tech Stack:** Python 3.13, Git, GitHub CLI, Docker, Playwright/Chromium, GitHub commit statuses.

**Spec:** `docs/project-autopilot/AI_FAILOVER_AND_MERGE_AR.md`.

## Global Constraints
- The authorized repository is `Hafezalhoot/ramses-accounts`, private.
- Keep GitHub Actions disabled; no Work reliance; no auto-merge.
- Use only synthetic data, never a live hospital DB, patient data, secrets or external financial mirror.
- Main history must be preserved; no force push, no direct production effects.
- Published QA PASS requires exact PR SHA and complete approved test results; SKIP is never counted as PASS.
- No dependency on another AI's quota or approval.

## Review Focus
- Fork or unauthorized bot PR: reject **before executing** its source.
- Branch SHA moves during fetch or during tests: refuse stale report publication.
- Docker network, credentials, socket: tests must not receive these.
- Missing V8.0 source, unexpected SKIP, duplicate/absent rows, timeout: fail closed.
- Mac unavailable and no second trusted device: preserve PR pending, never invent successful QA.

---

### Task 1: Trusted-source fallback safety and report gate

**Files:** `scripts/qa_fallback.py`, `tests/test_qa_fallback.py`, `tools/qa/trusted_pr_authors.txt`

- [x] Create regression tests of trust checks, container argv, forbidden paths, TSV status handling.
- [x] Observe RED before implementation (import failure), then GREEN after minimal implementation.
- [x] Syntax-check fallback in Python 3.13.
- [x] Commit files to draft PR #6, read them back from GitHub.
- [ ] Re-run new tests from the exact remote PR checkout in Docker on a trusted machine.
- [ ] Negative integration: unauthorized fork PR must never execute a container.
- [ ] Negative integration: mutated PR head must never receive stale PASS.

### Task 2: Consistent isolated QA image and real full test

**Files:** `tools/qa/Dockerfile`, `tools/qa/requirements.lock`, the existing `scripts/ci_smoke.py` and `scripts/qa_g2t_full.py`.

- [x] Add image recipe including Python 3.13, Node, current project Python dependencies and matching Chromium/Playwright.
- [ ] Build image with Docker on a trusted secondary machine and prove Chromium opens without a network at runtime.
- [ ] Run complete suite on a real authorized PR SHA with original V8.0 SOURCE ZIP; record counts and logs.
- [ ] Check clean host files, no secret mount, no external network, no hospital database use.
- [ ] Use `--publish` only after checking the real evidence; verify GitHub status/comment tied to exact SHA.

### Task 3: AI handoff and protection

**Files:** `AGENTS.md`, `CLAUDE.md`, `docs/project-autopilot/AI_FAILOVER_AND_MERGE_AR.md`.

- [x] Standardize independent agent takeover instructions and source of truth.
- [x] Document alternate runner, no-actions policy, owner-approved PR identity allowlist and recovery limits.
- [ ] Explicitly approve and safely add future non-owner GitHub identities to Mac and alternate allowlists when required.
- [ ] Inspect the repository GitHub subscription and actual ruleset eligibility.
- [ ] Only after alternate is proven, enable protection of main: PR required, 0 compulsory reviews, real QA status required, block deletion/force push; confirm owner recovery path.
- [ ] Verify a second authorized assistant can run QA and merge a **non-production**, test-only PR from latest SHA under the real protection rules.

### Evidence / current limit

Local isolated code-level checks: `tests/test_qa_fallback.py` PASS; Python `py_compile` PASS; CLI help displayed. The exact uploaded source and config were read back from GitHub. This **does not** prove a real Docker image builds, complete QA runs, or ruleset/merge works. The existing Mac watcher reported historic PASS on other PRs but not this new fallback. PR #6 remains DRAFT / NOT MERGED; Ramses is still TEST ONLY / PRODUCTION NO-GO.


### Task 4: Verified merge with private GitHub Free limitation

**Files:** `scripts/qa_checked_merge.py`, `tests/test_qa_checked_merge.py`, `docs/project-autopilot/AI_FAILOVER_QUICKSTART_AR.md`.

- [x] RED test on missing checked-merge module, then GREEN after implementation, Python 3.13 syntax check.
- [x] Reject wrong PR author, Draft PR, mergeability failure, SHA mismatch, missing/blocked QA, and stale main base in synthetic tests.
- [x] Require explicit `--merge`; GitHub merge API is SHA constrained to reject a moved head.
- [x] Confirm actual private GitHub API responds 403 requiring Pro for rulesets, while main remains unprotected.
- [ ] Test the actual precheck and an authorized, non-production merge on a real disposable PR once the fallback QA has passed.
- [ ] Reassess paid private-repo GitHub branch protection with the owner if desired. Never make the repo public.
