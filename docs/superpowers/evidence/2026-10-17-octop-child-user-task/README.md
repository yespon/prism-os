# Existing child execution: attachment → delegated DOCX → result/history

Branch: `codex/octop-integration`; baseline `83ea012`. This repairs the existing Harness `task` path. Original N01–N15/O01–O42/F01–F12, milestones, M1 exits and N08 prerequisite remain. It does not introduce durable PlatformRun/AgentVersion/child recovery or accept full Octop AgentTeams/cross-Agent collaboration.

## Capability outcome

The authenticated chat APIs now support a parent Agent delegating an attached brief to a general-purpose child, which reads the owned attachment and creates a Chinese DOCX/table. The parent only calls `task` and `present_files`. The resulting file is downloadable and appears in a new session's history; same-tenant nonowners and other tenants are denied. Actual configured `gpt-5.6-luna` completed this task in both the owned WSL native profile (18036) and main application image (18026). API acceptance covers the UI's authenticated product API, not a new manual browser-rendering acceptance.

| Original capability | Baseline / entry | Evidence / remaining boundary |
|---|---|---|
| O08/O09 child delegation | Pinned b6 source and original ledger children; existing Harness `task` | Actual generic child DOCX task accepted. Catalog-specific child selection, full AgentTeams/cross-Agent delegation, cancellation and independent durable recovery remain. |
| O11/O21 result/history/files | `/api/threads/{id}/uploads`, authenticated LangGraph stream, artifact/history routes | Chinese facts, unpredictable uploaded marker and table checked from downloaded DOCX; parent cannot substitute its own read/create; current ACL checked. |
| O38/O39 PrismOS constraints | Current native Agent/resource snapshot, file guard, tenant model allowlist, host read middleware | Targeted revoke/model-deny/private-context/thread-pool tests; existing Policy/Approval/Action/Audit paths retained. This ordinary task is not a fresh real incident-governed child acceptance. |
| O40 upgrade | Original source sync plus owned image lifecycle | See frozen source receipts and runtime cycle; no remote CI, push or production release. |

## Failures retained and code boundary

`real-child-baseline.json`: actual child lost native Agent identity, so current file authorization correctly refused the attachment; no document was produced. Earlier small graph-step budgets also exhausted. An execution-completed child summary incorrectly said “Task Succeeded” even when its natural-language result described failure.

`real-child-context-fixed.json`: identity repair let execution continue but copied LangGraph context inherited the parent's PostgreSQL saver across the background worker's independent event loop. Actual run failed with a loop-bound lock. `real-child-loop-fixed.json` is a separate successful real execution after fixing that defect; no failed receipt was rewritten as success.

Repairs are confined to the existing orchestration/host seams: whitelist/copy native parent identity, selected resources and referenced attachments without forwarding the one-use execution capability; refresh native parent snapshot/tool groups; enter parent tenant context and check the current enabled model; copy private host ContextVars through both pools; explicitly keep this existing ephemeral child graph independent of the parent's loop-bound saver. Parent checkpoint/history remains. Completion text now asks the parent to verify the returned outcome and artifacts. No file guard or governance check was relaxed.

The old executor tests used session-long module mocks that contaminated later graph tests. Their fixture now restores modules at module exit. The first related failure and corrected run are both retained. The final saver regression uses actual parent/child LangGraph graphs and both background pools with a parent-thread-only checkpoint saver.

## Evidence reuse and configuration

Raw transcripts and credentials remain under ignored owner-only `backend/tmp/n04-wsl`; public receipts contain synthetic task content/IDs/hashes only. Use the existing model configuration by name; do not paste keys. Main product: `http://localhost:18026`; separate WSL native browser profile: `http://localhost:18036`.

`octop_child_task_probe.py --resume <accepted receipt> --output <new receipt>` checks existing terminal execution, artifact hash/history/current ACL without another model request. Select `--base-url http://127.0.0.1:18026 --fixture backend/tmp/n04-wsl/live-fixture.json` for the main image. WSL native defaults use its independent fixture. No rerun of an unchanged successful model task is counted as new progress.

Previously accepted Office, non-Skill script and incident-governed tasks retain their documented environment/coverage bounds. Their production scope is not broadly reused across changed orchestration inputs: this block runs the related host/image/upgrade checks. Frontend, dependency lock, schemas, original imports, receiver and Office implementation bytes remain unchanged; old full backend evidence is historical, not a new full backend result. M1 remains open and N08 remains unstarted.

Final evidence: `real-child-main-image.json` includes actual child tool names; `child-stream-proof.json` independently extracts the earlier native child's actual calls without re-execution. `runtime-cycle.json` passed restart/previous-image/reapply and preserved the new DOCX plus earlier Chinese PDF/PNG/current ACL. `final-proof-current.json` corrects an initial source-scope path typo, verifies actual `backend/packages/octop-capabilities`, current image source hashes/readiness and recorded-only native ownership reference update. Main security remains unchanged and ticket count stays 26.

`upgrade.json` deliberately failed its frozen-input gate when the probe script was improved during validation; it is not accepted. `upgrade-frozen.json` passed all three source phases for related tests. A subsequent new saver regression changes only `test_child_execution_context.py`; `upgrade-saver-final.json` reruns that file at all three phases, while the other unchanged tests retain the frozen receipt. Production image bytes are unchanged by that test addition; `child-image-related` uses the built image, and `child-image-saver-final` mounts only the new test file read-only into the same network-disabled image. The runtime image is not mislabeled as containing the later test-file bytes.
