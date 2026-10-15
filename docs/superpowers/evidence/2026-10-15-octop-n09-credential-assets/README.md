# Current credential and asset access

Continuing f7aac71 on codex/octop-integration. The functional block is accepted within the recorded native HTTP, current identity UI, encrypted storage, maintenance rotation and isolated runtime scope. Initial .pending snapshots and reproduction remain historical preparation, not the current runtime source.

## Available implementation

Original asset/keychain/group HTTP routes check current native Tenant/member facts before admission and delivery. Writes use the original tenant coordination and Tenant/member lock order. Credential/group references must belong to the current tenant and user. Referenced records cannot be deleted into dangling asset bindings. Inline password creation and asset writes share one transaction; a failed asset insert rolls back its credential.

New and updated Keychain values use the original strict encryption functions and require the existing encryption configuration. No credential value appears in response DTOs. Passwords that look like ciphertext are literal input and are encrypted once. Original password/key/ssh_key types remain usable. Existing plaintext rows retain current-owner SSH use and can be sealed through the original maintenance rotation; no unrequested live database is migrated.

The original SSH builder checks credential ownership and purpose and decrypts only at consumption. Wrong/missing keys fail closed. Connection probes verify current membership and credential facts during waits and before delivery, inherit only a small explicit environment, limit output, and terminate their owned local process group on withdrawal or failure. Local transport interruption does not claim remote side effects were undone.

The original maintenance rotation now includes Keychain in the same commit/rollback transaction, supports dry-run and environment key references, and rejects wrong old keys. This is a maintenance operation: quiesce writers and update configured keys under the existing operational boundary; online cross-service key rotation is not claimed. No production key, live database or deployment was changed.

Original asset dialogs now await confirmed saves, retain rejected input and block direct replay of unknown outcomes, including closing/reopening. Group creation remembers its confirmed ID. Identity guards reject stale mutations; cached lists discard late responses, hide data from previous identity, clear refused data and close old transports. An explicit fresh connection is required after access becomes available again. Readiness and known encryption-setup failures are distinguished from unknown publication.

A route-level dependency also keeps the legacy unscoped provisioner API disabled behind ASGI root prefixes; it supplements the middleware verified in the previous block.

## Evidence and precise boundaries

The original isolated HTTP reproduction proves withdrawn-identity writes, plaintext persistence and foreign references before the fix. Only synthetic identities/credentials and an owned temporary SQLite database were used. The first launcher had an incorrect cwd and never spawned its child; its incomplete receipt is not acceptance.

Related checks passed for original Terminal compatibility, current HTTP authorization, reference integrity, strict encryption, actual local child-process termination, and original ticket Secret behavior. Isolated PostgreSQL 16.15 ran all 23 new asset/rotation tests against the original schema and constraints, exit 0, with the owned loopback/tmpfs container removed. The original runner's generic schema description is retained in postgres.json; selected tests here concern assets/Keychain, not TenantSkill.

Backend/runtime and frontend inputs are frozen separately. This permits UI work without repeating an unchanged backend gate. Final acceptance must reconcile both snapshots, actual subprocess exits, immutable images, strict frontend build/route checks, NFT traces and upgrade/rollback. Source/external/inventory receipts from f7aac71 are reused only for explicitly unchanged pinned source/distribution input hashes. New tracked content still runs the brand gate without new waivers.

Real SSH, Kubernetes execution/mapping/termination, models, external tools and ticket counts remain pending where environment references are absent. Protocol substitutes and local process probes do not count as those real calls. Generic Secret purposes for the remaining domains, expert/delegation, independent Office and external runtime retain their exits. M1 has not exited and N08 has not started. All N01–N15, O01–O42/F01–F12 and original PrismOS goals/gates remain. No push, release or deployment.

The final whitespace check found one trailing ASCII space in the added JSX key line. The original 504-file frontend snapshot, 277 full tests, strict build and completed upgrade are retained. format-only-proof.json proves exactly that one-byte cleanup and identical emitted JavaScript; current TypeScript checking and all six dependent component tests are repeated afterward. The other 503 frontend files and all 1510 backend/runtime inputs are byte-identical. No complete-backend restart is needed for this frontend formatting change.

## Accepted results

- Complete backend: 2157 passed, 18 skipped, exit 0; all 1510 frozen backend/runtime inputs unchanged.
- Targeted native runtime/Terminal/remote compatibility: 113 passed at its checkpoint. Strict credential lifecycle and original ticket Secret compatibility: 87 passed. PostgreSQL: 23 passed, exit 0, owned container removed. Final default-privilege/no-network image runtime: 109 passed, with owned container removed.
- Backend image sha256:3aab8ec073dba150addc1807e152b24685d2ca9798c7a63a19a4d4e983e98aa5; provisioner sha256:906a3160c276f564306bdf709fa07c4c24bd9c218227556184e439b528f7e37c. Twelve image/source inputs match. Actual service-image HTTP admission passed; no cluster was exercised.
- Frontend: 277 full tests passed, strict generated-route/type/production build passed, 50 traces with no missing inputs. After the one-space cleanup, current typecheck and six dependent tests passed; emitted JavaScript is identical, as recorded above.
- Upgrade/rollback b5/b6/b5: 95 passed per phase, all exit 0, 130 host inputs unchanged during the probe. The later frontend formatting adjustment preserves emitted JavaScript and every backend test input.
- Final 2014 source inputs reconcile both scopes. Pinned source, external distribution and O/F inventory evidence from f7aac71 is reused only for the matching hashes in validation.json. Brand allowances remain unchanged. Logs are checked against staged and committed blobs.
