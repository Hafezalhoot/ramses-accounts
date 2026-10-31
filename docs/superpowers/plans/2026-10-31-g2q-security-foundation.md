# G2Q security foundation — executable implementation plan

**Source:** G2P SHA-256 `f83baf274fe5df1a3cd68190eb87a5d254539af449dfc94ac37ac0035d0454a7`.
**Intent:** Fix four confirmed security gaps F-012, F-013, F-015, F-016 without altering posted transactions, patient data, or historical closing logic. Test with synthetic SQLite databases, preserve backward-compatible schema upgrades. No production deploy.
**Alternative rejected:** wholesale auth rewrite + cloud DB migration—too risky for current tested ledger. Preferred: additive SQLite security controls and existing secure-backup interface.

## Task A / F-012: block source-bound abuse, not a username across all networks
1. Add synthetic failing test `tests/test_v82_g2q_security.py` asserting an unrelated source can log into an account after 5 bad attempts from another source and the attacking source hits its own per-user/overall limit.
2. Schema: new `login_rate_events` table with `username`, hashed socket-source key, `occurred_at` plus indexes; old `login_attempts` preserved historically.
3. App login: derive source from `Request.client.host` (no trust in caller-controlled headers); count only failures; cap 5 per source/user and 40 per source/15 minutes; invalidate matching failures on success. Document shared NAT / distributed IP limitations and deploy proxy trust review.
4. Run test RED then GREEN; run authentication regressions.

## Task B / F-013: scope employee directory
1. In the same synthetic test assert clerk and viewer cannot get employees via `GET /api/lookups`; owner and reviewer retain the employee roster for financial review.
2. Modify the `employees` property centrally to return empty for other roles, no new endpoint or data contract.
3. Verify account/voucher/payroll tests.

## Task C / F-015: fail closed on plaintext backup paths
1. Write a failing test ensuring the old `backup.py` and `scripts/backup_local.sh` only produce/use authenticated AES-GCM `.rbe` backups and fail without a configured strong passphrase; test no `.sqlite3` artifact left behind. Preserve `scripts/secure_backup.py` implementation.
2. Make `backup.py` a compatibility CLI forwarding to encrypted routine; make shell wrapper call `backup_encrypted_docker.sh`; update systemd/README/free-preview instructions to demand passphrase and off-device copy.
3. Verify G2M recovery tests and new CLI tests.

## Task D / F-016: protect app audit trail against ordinary SQL mutation
1. Test updating/deleting `audit_log` with raw SQL fails on fresh and upgraded SQLite, while append remains possible.
2. Add `BEFORE UPDATE/DELETE` triggers; clearly state that privileged DB file owner can still drop triggers (needs external append-only audit store for tamper evidence).
3. Verify no existing application updates/deletes audit log.

## Task E / M0: CI / handoff
1. Add GitHub Actions smoke workflow (fast real tests + static `compileall` + Node syntax, no historical archive as false success); no live GitHub push, secrets, or deployment.
2. Update CURRENT_RELEASE/RELEASE_GATE/master plan and record precise file changes, test commands/results, remaining blocker statuses.
3. Assemble new G2Q ZIP with manifest, executable Mac launcher, no secrets/databases, `unzip -t`, checksum, source count and report. Keep G2P source immutable.

## Release gates
* Authentication cannot lock out remote owner solely due to other-source attempts.
* Lookup privilege test for all roles; DB `audit_log` trigger negative tests.
* Old backup routes refuse plaintext; secure backup create→verify→restore succeeds.
* Full existing test suite: count success/skip/fail individually and disclose the missing V8.0 archive.
* `NO-GO` for real hospital money/patient records until full modules, off-device backup and independent UAT.
