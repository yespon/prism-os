# Restored service: actual user task (2026-10-16)

Based on b6471ab, existing WSL snapshot and unchanged current application image. No production code changed in this block.

## Available behavior and acceptance

`restored-exact-path-flow.json` and its successful process receipt prove an independent restored application, auth and checkpoint database plus runtime configuration/files can boot and complete a native user task. Genuine HTTP login through the cloned product proxy/frontend, configured `gpt-5.6-luna`, native Agent/Skill, successful read_file, approval and actual HTTPS ticket receiver were used. After restarting Gateway/LangGraph, the approved operation submits once, approval is consumed, timeline/history remain accessible, and repeating resume makes no extra POST. Requester review and cross-tenant access are rejected; disabling the Skill rejects new diagnosis.

The cloned receiver advances 25 to 26. The original receiver stays 26 to 26 and original Compose bytes remain unchanged. All cloned services, networks and databases are removed; private runtime files, final database dumps and full diagnostic transcripts stay ignored under backend/tmp. This is an actual configured model and self-hosted HTTPS test target, not acceptance of a customer's enterprise service.

## Preserved failures and explicit reuse

- Initial readiness checks rejected one historical busy thread projection. The actual listed run was interrupted. The final probe checks every actual run and rejects pending/running/unknown rather than changing history or clearing data.
- `restored-user-flow-current.json`: native restore/login/history/model availability/old Skill edit/new Skill create and role checks passed. Its model supplied an Agent-name path instead of the Skill path; file access correctly failed and no ticket was submitted. The failed receipt and sanitized read-failure facts remain.
- The successful run uses literal Skill file arguments and reuses only that prior successful prepare scope, explicitly recorded by `baseline_checks_executed: false` / `reused_prepare_evidence`. Model execution, authorization, restart/resume/withdrawal are new actual executions.
- `backend-full-final-result.json` and raw log: 2453 passed, 18 skipped (optional dependencies), return code 0. `backend-full-inputs.json` / `input-reuse.json` verify all 13631 frozen tracked backend/scripts/Skills/config inputs unchanged. No repeat full run, image build, frontend build or source upgrade cycle was launched. Previous image/frontend/upgrade evidence covers only its unchanged inputs.
- `final-runtime.json`: current owned services healthy, original Action/trusted graph switches off, immutable image/proxy/receiver bytes and private file boundaries checked.

M1 is not declared exited and N08 is not started. Full Octop task parity, other tools/file entry coverage, original milestone gates and remote CI remain. This block adds restored task continuity, not completion of all Agent/Office/external capabilities.
