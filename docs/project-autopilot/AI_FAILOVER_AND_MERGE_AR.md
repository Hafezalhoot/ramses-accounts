# Ramses AI failover / merge protocol — active6 November2026

Owner approved Public after full-history/content audit and attested that evidence is synthetic. Actions and strict main Rulesets are authorized. The current policy is [PUBLIC_CI_AI_WORKFLOW_AR.md](PUBLIC_CI_AI_WORKFLOW_AR.md). Earlier no-Actions/private-only instructions are historical Git versions, not the active policy.

Any legitimately authorized ChatGPT, Codex, Claude or another assistant can read current Git/PR/checks, implement on a separate branch, run tests and perform an authorized checked merge. Each uses its own legitimate GitHub access; no token sharing and no mandatory named AI reviewer.

## Checks and merge

Public core CI requires `ramses-security` and `ramses-core-ci`. Python3.13 financial/permission/UI/Playwright tests run inside networkless non-root Docker. Only counts/SHA/step outcomes are uploaded; no archives, raw logs, TSV or live data. Public core reports the exact missing historical V8.0 test as BLOCKED, never PASS, and preserves five known SKIPs. This is not historical-complete certification.

From clean, current, reviewed main: `python3.13 scripts/qa_checked_merge.py --pr N` is read-only preflight; `--merge` acts explicitly. It requires an approved or GitHub-confirmed writer author, same-repo PR, Ready/mergeable status, current-main ancestry and latest completed successful exact-head checks from GitHub Actions app15368. REST merge constrains the head SHA. Strict no-bypass server Ruleset is also required to protect a concurrent main change; the helper alone cannot atomically bind the base SHA. No `--admin`, direct main writes or force pushes.

Ruleset activation and the tested merge must be verified live before the final completion report. No particular AI vendor is an integration ID or required reviewer. Default token is read-only and cannot approve PR reviews; forks receive no Secrets through this workflow.

## Complementary historical QA

Retain PR6's portable fallback and Mac Local QA. From reviewed clean full-history main on a trusted Mac/Linux host with Docker/gh/Python3.13 and the owner's original source ZIP: `python3.13 scripts/qa_fallback.py --pr N --v80-archive /absolute/path/original.zip --publish`. Original archive/schema digests are pinned. Missing/changed fixture refuses historical success. A fixed runtime image ID is used throughout each job, Docker API transfer has no host bind, and stale/symlink reports are refused. Source runs in Docker only.

Mac's timer remains paused by owner request. Its actual original-migration results are additional evidence; they never impersonate Actions checks to bypass server protection. GitHub/Actions outage can defer merges; changing protection is an explicit owner recovery action. An AI quota outage can be handled by any other assistant with the required legitimate permissions.

The Docker recipe currently refreshes a mutable Python base/tag, apt packages and some transitive ranges. The inspected image ID makes a single execution immutable and recorded; rebuilding a commit is not promised bit-for-bit reproducible. New runtime builds are tested again.

## Remaining acceptance

Issue7 tracks independent-host/fallback proof and the disposable tested merge. GitHub-hosted Ubuntu supplies independent public-core execution; private historical fixtures are not published to satisfy a checkbox. Record separately what actually ran on Mac versus Ubuntu, including SHA, runtime ID and counts. Never claim the original V8 archive ran on a second physical machine if it did not.

TEST ONLY /PRODUCTION NO-GO. No real hospital DB/records, financial disbursements, policy approvals or production deployment.
