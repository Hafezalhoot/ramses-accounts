# Ramses S11 independent security, database and operational architecture review

Reviewed baseline `49167d9` (S10), branch `stabilization/s11-operational-review`, and the corresponding current implementation while the parent implements unrelated S11 fixes. Read-only checkout review; all probes used disposable synthetic databases outside the repository. Reviewed FastAPI and browser JavaScript security guidance, application/session/RBAC boundaries, SQLite connection/bootstrap/schema handling, encrypted backup and recovery, Google mirror, Docker/Compose/systemd and local launch paths. No production service or hospital data was accessed. No full test suite was run by this reviewer.

## Executive assessment

The current system has substantially stronger controls than several historical audit documents describe. No unauthenticated data-read, SQL-injection, direct financial authorization bypass or executable stored-XSS path was established in the reviewed scope. Four reproducible availability/audit-integrity defects remain. Two should be resolved before operational acceptance; the proxy-source issue also requires verification in the actual chosen deployment. This review does not certify production readiness or replace the existing physical recovery/UAT/financial policy gates.

## Strengths and stale findings avoided

- Session secrets are random opaque cookies, stored as SHA-256 hashes server-side, with expiry, `HttpOnly`, `SameSite=Strict`, configurable `Secure`, CSRF checks on protected writes, and session deletion on disabling users/password resets (`app.py:114`, `app.py:568`, `app.py:3348`, `app.py:3371`). Passwords use a salted PBKDF2 KDF rather than plaintext or fast hashes.
- Clinician identities have a central deny-by-default route allowlist, separate role and professional identity/grant checks, with financial and patient-file endpoints unavailable to the clinical role (`app.py:124`; `billing.py:322`). Older warnings that the clinical actor is just a finance viewer are stale.
- Bank/wallet/restricted-cash grants are applied before voucher/report aggregation, not merely by hiding UI rows. Bank import and inventory review recheck current grants after obtaining a write lock (`app.py:742`, `app.py:1885`; `inventory.py:585`). Historical generic bank/RBAC warnings should not be blindly repeated.
- Most financial mutations use `BEGIN IMMEDIATE`; integer piastres avoid floating-point money; posted journals and audit/evidence rows have immutability guards. The three creation exceptions are finding SEC-02 below.
- Pre-DDL rollback is encrypted and verified, and no-clobber AES-GCM/scrypt restore authenticates both archive metadata and ciphertext and checks SQLite/FKs, posted GL balance, selected evidence checksums and essential guards (`bootstrap.py:148`; `scripts/secure_backup.py:72`, `scripts/secure_backup.py:224`, `scripts/secure_backup.py:279`). Old claims that routine backups are plaintext or that restore overwrites live files are stale.
- Google mirroring requires explicit sensitive-data approval outside synthetic preview, uses literal cell strings, and makes atomic remote replacement batches (`google_sync.py:116`). This is not automatic off-site backup, and the current documentation says so.
- API responses are `no-store`; upload downloads use attachment/octet-stream; public docs are disabled; Docker runs non-root with read-only application filesystem, dropped capabilities and a loopback host port.

## Findings

### SEC-01 — High / P1: Bound the request stream before multipart parsing/spooling

**Rule:** FASTAPI deployment/input resource limits.
**Locations:** `app.py:842-852`; equivalent multipart handlers in `billing.py:429-447`, `app.py:1847`; `compose.yaml:25-26`; `Dockerfile:16`.

**Evidence:** `UploadFile = File(...)` makes FastAPI/Starlette parse the multipart request before `get_user`/the handler. The handler only later calls `file.file.read(MAX_EVIDENCE_BYTES + 1)`. There is no total body/stream cap in app middleware or the supplied Uvicorn/Compose origin configuration. The container's spool target is `/tmp`, a 32 MiB tmpfs.

**Reproduction:** A focused TestClient probe instrumented `starlette.formparsers.SpooledTemporaryFile.write`, then anonymously POSTed a single 8 MiB file to `/api/vouchers/1/attachments`. The response was **401**, but the parser had already accepted **8,388,608 bytes** and the spool had rolled onto disk. The advertised 6 MiB cap therefore does not protect parsing; unauthenticated requests can consume much more, and multiple files/requests multiply it. Only an externally configured smaller origin cap could mitigate this; none is supplied or tested here.

**Impact:** A network client reaching the origin can exhaust temporary storage/CPU and disrupt shared hospital accounting. Cloudflare Access reduces the set of reachable attackers when actually enabled; it does not establish an application body-size bound.

**Minimal fix:** Enforce an ASGI receive-stream byte limit before form/JSON parsing and return 413. Reject excessive declared `Content-Length` early, but also count actual streamed bytes so chunked requests cannot bypass it. Add an appropriate edge cap in the selected deployment. Keep existing per-file count/type/size checks. Prove over-limit authenticated and anonymous uploads cannot spool the full body and that legitimate uploads still work.

### SEC-02 — High / P1: Entity creation can commit while its audit record fails

**Rule:** Atomic security/financial mutations and audit integrity.
**Locations:** `bootstrap.py:71`; `app.py:2132-2136` (`create_fund`), `app.py:2422-2425` (`employee_add`), `app.py:3339-3342` (`add_user`). These are current line numbers after the concurrent S11 day-summary insertion; baseline equivalents start at `app.py:2118`, `app.py:2409`, `app.py:3326`.

**Evidence:** `connect()` sets `isolation_level=None` (autocommit). `with c:` does not start a transaction in this mode. Those three handlers insert the entity and then audit it without `BEGIN IMMEDIATE`, unlike the financial handlers. Fund creation additionally inserts the GL account/mapping separately.

**Reproduction:** On a disposable database, a test-only `BEFORE INSERT ON audit_log` trigger rejected actions `create_user`, `create_employee`, `create_fund`. Each HTTP request returned **400**, while querying a new connection found **one persisted entity** for each allegedly failed request. No corresponding audit row existed. An operational audit-write failure (for example storage/constraint failure) likewise cannot roll back earlier autocommits. The broad IntegrityError catch also reports these failures as an existing username/code, misleading the operator.

**Impact:** Privileged accounts, employee records and financial fund/GL setup can be changed without the required audit evidence; the user sees failure although the mutation took effect. A fund/GL later-step failure can leave a partial configuration.

**Minimal fix:** Explicitly begin a transaction in each of the three existing `with c:` blocks so entity, related GL configuration and audit are one commit. Distinguish uniqueness violations from unrelated integrity/storage errors. Add an injected audit-failure regression that asserts entity, GL mapping and audit are all absent after failure, then prove the normal path remains intact.

### SEC-03 — Medium / P2: A runtime request recreates a disappeared ledger as an empty database

**Rule:** Fail-closed database access / recovery integrity.
**Locations:** `bootstrap.py:67-74`; `app.py:95-100`; compare intentional read-only readiness behavior at `app.py:553-565`.

**Evidence:** Every request-scoped `db()` calls the bootstrap `connect()`. It creates the parent directory and uses SQLite's create-if-missing default. The health endpoint deliberately checks `DB.is_file()` and opens `mode=ro`, but ordinary request dependencies do not.

**Reproduction:** After initializing/closing a disposable database, rename its database file to simulate missing storage. An anonymous `GET /api/me` returns **401**, yet creates a new **4,096-byte empty SQLite database** at the live path before authentication. A subsequent login/query fails due to missing tables; on restart the nonempty, unrecognized file can cause bootstrap's existing-database safeguard to reject startup.

**Impact:** Storage/mount/operator failures get mixed with accidental new-database creation and confusing authentication/startup failures. A public request can modify the missing-ledger path during recovery. This is not demonstrated destruction of the renamed original, but it breaks the intended fail-closed recovery behavior.

**Minimal fix:** Separate explicit first-install/bootstrap creation from runtime opens. Runtime connections should require an existing regular ledger and open SQLite with a safely encoded URI and `mode=rw`, returning a controlled 503 when unavailable. Keep intentional database creation only in the initialization path. Regression should assert no file/directory is created by anonymous/authenticated requests when the configured ledger is missing.

### SEC-04 — Medium / P2, deployment-dependent: Proxy clients can share a login lockout bucket

**Rule:** Trustworthy source identity and abuse/availability controls.
**Locations:** `app.py:571-582`; `Dockerfile:16`; `compose.yaml:13-19`; `scripts/free_preview.py:159-170`.

**Evidence:** Rate limits are keyed to `request.client.host`: five failed attempts against a username or 40 total per source deny all later logins for 15 minutes, including a correct password. The supplied Docker deployment routes a host Cloudflare tunnel through a loopback-published container port and does not configure/document a verified trusted proxy identity chain. If the ASGI source is the Docker/tunnel peer rather than the actual remote client, users share one bucket. Uvicorn may process forwarding headers depending on its trust configuration, so this must be measured in the actual topology, not guessed from browser IPs.

**Reproduction of the failure condition:** Two TestClient browser identities with the same proxy socket host and distinct claimed `CF-Connecting-IP` headers were used. After one made five incorrect owner-password attempts, the second browser's **correct password returned 429**. This is conditional deployment proof; no real Cloudflare/Docker proxy route was available to prove which peer it presents.

**Impact:** An origin-reachable client or one allowed staff identity can deny a specific account (or all accounts after 40 attempts) when the proxy collapses sources. Existing unit tests use different artificial socket peers and therefore do not validate the deployed proxy behavior.

**Fix/acceptance:** Establish the exact trusted proxy chain and forward authoritative client identity only from allowlisted/authenticated proxy hops. Never trust arbitrary client-supplied forwarding headers. Test two independent external users over the selected HTTPS tunnel: one reaches the throttle while the other can still log in correctly. Until that evidence exists, carry this as an operational readiness blocker rather than declaring source-scoped lockout solved in production.

## Additional operational limitations, not new proven vulnerabilities

- Backup and recovery preserve the exact database, including the historical `sessions` and account state. A cutover procedure should explicitly invalidate restored sessions and review accounts/password changes that happened after the snapshot. The current drill purposely does not perform a real cutover.
- The main `initialize()` body uses autocommit and `executescript()` without a versioned all-or-nothing migration transaction (`bootstrap.py:281-304`). Individual clinician/shift rebuilds are transactional and encrypted rollback exists. A broader future migration failure can leave a partial additive upgrade requiring deliberate rollback. No production failure was reproduced here, so this is an architecture/operational recommendation rather than a fifth confirmed defect.
- Encrypted local archives and systemd timers are not independently controlled off-device storage, retention, failure alerting or a signed restore exercise. Existing S7/current-release gates state this correctly. Recovery, actual financial close policy and licensed clinical signoff remain external acceptance obligations.
- The provided dependency ranges are broad and currently resolve substantially newer FastAPI/Starlette versions than older guidance assumes. No vulnerability advisory scan/lockfile reproducibility audit was performed here; parent test runs cover the installed environment, not every future resolution.

## Validation artifact and limitations

Focused executable probe: `/private/tmp/ramses_security_probes.py`. It performed only synthetic upload parsing, injected audit failure, proxy-source throttling and missing-ledger checks. Observed output:

```json
{"probe":"unauthenticated_upload","status":401,"parsed_bytes":8388608,"spooled_to_disk":true}
{"probe":"create_not_atomic_with_audit","endpoint":"/api/users","http_status":400,"entity_persisted_despite_failure":1}
{"probe":"create_not_atomic_with_audit","endpoint":"/api/employees","http_status":400,"entity_persisted_despite_failure":1}
{"probe":"create_not_atomic_with_audit","endpoint":"/api/funds","http_status":400,"entity_persisted_despite_failure":1}
{"probe":"shared_proxy_source_lockout","victim_correct_password_status":429}
{"probe":"missing_runtime_db","status":401,"new_empty_db_created":true,"new_db_bytes":4096}
```

Actual hospital LAN/HTTPS/tunnel, Cloudflare policies, external identity, secret rotation, production database, original V8.0 archive, off-site media and clinical/bank source documents were not available or accessed. Browser rendering was reviewed statically; no independent browser run or full suite was performed by this reviewer to avoid duplicating the parent's validation.

## Declined to judge

- Clinical licensing/tax/accounting/legal correctness: requires authorized institutional professionals and local applicable policy; no invented signoff.
- Full financial workflow numerical correctness and all historical schema fixtures: assigned to the other review seats and parent's full suite; inspected shared DB/security boundaries only.
- Real proxy trust chain, MFA/Access enforcement and hospital WAN/LAN exposure: unavailable external deployment; reported a conditional finding and concrete acceptance check.
- Physical recovery/off-site redundancy and real V8.0 migration: no genuine source/media/device provided; existing NO-GO remains.
- Root/host administrator changing SQLite/triggers deliberately: outside the ordinary application RBAC threat boundary; current docs already acknowledge SQLite guards cannot secure a compromised host.

## Verdict

**Ready for real hospital operations: No.** Resolve SEC-01/SEC-02 and preferably SEC-03, verify SEC-04 against the selected secure deployment, and retain the documented recovery/UAT/financial policy gates. **Ready to continue development: With fixes and focused regressions.**


## Coordinator completion addendum — 2026-11-04

SEC-02 is fixed in S11 with genuine SQLite audit-failure RED/GREEN and real local HTTP. SEC-01/03/04 remain open. Dependency audit subsequently found19 advisory records across2 packages (duplicates included); cryptography50.0.2 and pip26.3 resolved the observed installed-environment findings. Final audit reports no known vulnerabilities; old46.0.7 encrypted archives restore with identical logical rows under50.0.2.

See TEST_REPORT.md and evidence/S11/ for exact scope and limitations. Hospital production remains NO-GO.
