# Real Office user task, not source/tool-only completion

Continue 2338505 on the existing integration branch. Existing O ledger gains task baseline/current entry/status/missing chain/scenario/evidence/original milestone fields; no IDs, children, F items, full-parity decisions or original exit conditions were removed.

## Newly usable task

Using actual product Web API paths and genuine login (automated HTTP, not a browser-click acceptance), a private Agent with the configured gpt-5.6-luna reads an uploaded Chinese brief, creates a DOCX with title/paragraphs/table and original marker, and calls present_files. The original artifact endpoint downloads the actual document. Fresh login accesses the same checkpoint history and exact artifact SHA; another tenant and another same-tenant user cannot access the private thread or file. `report.docx` is that actual downloaded synthetic report.

The four independent Office tools were already registered; registration was not the missing link. Actual model execution exposed the untyped DOCX document argument and ambiguous table nesting. Added an explicit nested model-visible document schema, paragraph/style schema and concrete table example. Invalid shapes actually emitted by the model are rejected before file writes. Existing accepted document operations and current authority checks remain.

## Actual evidence and failures

- `real-docx-first`: real attachment read succeeds, model emits two wrong table shapes, no report; recursion error retained privately and sanitized tool outcomes retained publicly.
- `docx-schema`: new test initially validated the internal injected-runtime schema; fixed it to validate the actual model-visible tool_call_schema. Failure retained.
- `real-docx-current`: read_file → office_docx(status ok) → present_files succeeded and actual downloaded content/table passed. The probe's exact Cache-Control comparison failed on proxy-combined values; changed to directive membership without altering product caching.
- `task-artifact-history`: reuses precisely that successful model execution, performs new authenticated downloads/history/ACL checks, sends no model request. Its successful result records the source receipt.
- `runtime-cycle.json`: actual Gateway/LangGraph restart, previous b0ee063a image and current d92ae2ea image; at every stage newly authenticated artifact/history/ACL checks pass, exact SHA stays unchanged. No re-generation or ticket call.
- Current targeted DOCX/image tests, Ruff and current no-network image pass. Source upgrade probe preserves old/current/rollback behavior tests and now freezes the optional real-task probe as a host contract. Initial probe rejected inputs changed during its run; preserved, then restarted only after inputs froze.

The full backend run in 2338505 covers the unchanged baseline, not this schema change. Only related functional/integration/image/upgrade checks are new here; frontend/source archives/locks/other capabilities reuse prior evidence solely for unchanged inputs. Runtime private data and raw streams stay ignored; public secret scanning and healthy/off checks are required before commit.

## Boundaries and next independent work

This accepts the basic attachment-to-DOCX task with the actual configured model, not complete Office, UI click behavior, enterprise tool acceptance, or all O21/O26 parity. Advanced formats/layout/OCR/forms, all other native groups, experts/subagents, external business workers and original milestone gates remain.

A concrete next gap is confirmed in the original office-automation template: its prompt directs the four excluded bundled Skills and advertises full availability. Native replacement tools exist, but the expert needs an explicit local adapter plus an actual template-created task. Preserve imported upstream prompt bytes and source-policy boundary; do not declare the excluded/unimplemented goals deleted. N08 and durable delegation still require original M1 exit; this single expert task is independent.

Raw brand-failure logs are retained as lossless .log.gz archives with original byte SHA in raw-log-archives.json, including the prior restored-service diagnostic. The raw diagnostic itself contained the detected legacy spelling; no brand allowance was added. Final gate includes all staged archives and source.
