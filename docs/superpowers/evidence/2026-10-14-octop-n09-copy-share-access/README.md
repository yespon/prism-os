# N09 copy/share and current configuration authority

2026-10-15, continuing `codex/octop-integration` at `38073b1`. **Copy/share configuration functional block accepted locally. M1 and later milestones remain open.**

The existing Agent gallery now has a copy dialog. A copy identifies the exact original Agent row and content revision, creates a distinct original CustomAgent, resolves target Skill IDs through the original resolver, and keeps source identity in ordinary metadata. Sharing cannot inherit fixed personal resources. A stale source, foreign owner/tenant, withdrawn membership, and duplicate target are rejected. Discovery keeps labels while redacting another member's private configuration and revision. CRUD, profile and source confirmation use current DB membership and canonical original admin/owner aliases. Original Policy/Approval/Action/Audit and runtime revocation gates remain in force.

[Scope audit](scope-audit.md) distinguishes private configuration, target resource authorization, provenance and actual execution.

## Final verification

| Gate | Actual result / scope |
| --- | --- |
| Related backend | 149 passed; current source/target, private discovery, CRUD and role confirmation |
| Complete backend | 2005 passed, 18 skipped, 417 warnings; actual pytest summary retained; initial cross-shell wrapper exit capture unusable |
| PostgreSQL 16.15 | 92 passed, subprocess exit 0; owned loopback/tmpfs container removed |
| Production backend image | `sha256:8e6a118e06b7f6a12f93817c6ccef38c6899a24d955976f62c650016fbce55a2`; nine changed/runtime/test inputs match; 92 passed, exit 0, default privileges/no network, owned container removed |
| Frontend | Full single-worker run: 58 files / 258 passed with original 5s test deadline. A later test-only mandatory-field repair passed six API cases and final strict typecheck; the other 252 unchanged cases are reused explicitly |
| Production frontend | Strict route typegen/typecheck and production build exit 0; 50 trace manifests, no missing references |
| Upgrade/rollback | Retained broader changed-block b5/b6/b5: 86 tests per stage. Final frontend runtime inputs then pinned and verified with 11 copy cases per b5/b6/b5 stage, all exit 0, complete=true, host_changed=false. Frontend behavior is separately tested; backend source switching does not establish browser/model execution |
| Source/static gates | Raw 902 members; four external packages/seven artifacts; all O42/F12 inventory, original brand 526 allowances; original CI Ruff range and changed frontend ESLint pass |
| Input/log tracking | 1997 final source inputs unchanged; [validation receipt](validation.json), [build traces](frontend-build-traces.json), and raw SHA256s retained |

Original two HTTP privacy/role failures, newly reproduced network-loss and wrong-target failures, intermediate full frontend timing failures and the test-only TypeScript error remain archived. Two old UI files passed isolated, then the complete single-worker suite passed without raising deadlines. No intermediate failed run is relabeled as successful. Backend/PostgreSQL/image inputs stayed unchanged through UI fixes; those accepted results are reused within that scope.

## Execution tracking

The resumed host is Windows with the original WSL worktree. `/tmp` evidence from the interrupted run disappeared; retained repository evidence and code were preserved. Current raw logs are written directly into this directory. Initial cross-shell wrappers did not preserve their requested shell exit-code variables; their pytest/build summaries and embedded PostgreSQL/upgrade subprocess return codes remain actual evidence. Invalid captures are retained verbatim as `.invalid-exit.log` and indexed in `wrapper-exit-capture.json`; they are not success evidence. `run_validation.py` retains direct subprocess return codes for subsequent validations.

No actual model, external tool, countable ticket call, real remote SSH/Kubernetes/Apple run, or remote CI is established here. No push, deployment or release occurred. N04/N07 and the remaining remote/all-tool, Secret-purpose, full resource/expert/non-Skill/Office seams remain open; N08 does not start before M1 exits. N01–N15, O01–O42/F01–F12 and original PrismOS M1–M7 exit conditions are retained.

The post-staging brand gate initially rejected an unnecessary literal historical migration filename in the broad input list. Its bytes were checked identical to base 38073b1, and that untouched file is scoped to historical migration evidence rather than restated in the block input list. No allowlist changed. The actual failed gate log is retained losslessly in `logs/brand-staged.log.gz`, indexed with raw and archive SHA256 in `compressed-log-archives.json`; the local raw file is also preserved.
