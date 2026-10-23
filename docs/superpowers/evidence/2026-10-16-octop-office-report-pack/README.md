# One original Office expert, a complete report-pack task

Continue 2b22290 on the same integration branch. Actual original expert reads its existing Word report and produces a Chinese XLSX progress table, a two-slide Chinese PPTX and an English PDF, with the original marker and facts. `report-task-acceptance.json` records successful task termination, actual tools, independent content checks, native downloads, new-session history and exact hashes. `report-pack.zip` contains those three actual downloaded synthetic reports. English PDF validates the default font path; a real CJK-font task remains separate from prior isolated font evidence.

## Actual runtime failure and fix

The first task killed LangGraph (exit 133, OOM=false), causing state delivery 502. Original stream and full service log remain private; sanitized container/input/output facts are archived. No new target output was present; the original Word hash was unchanged.

The exact model PDF input reproduces SIGTRAP in a no-network container on the previous image. Removing only empty lines succeeds. PDFium traps on an empty native text object. The fix validates every line and skips native object creation for empty strings while preserving the original line index/vertical spacing. It retains empty pages, text limits, fonts, ownership and resource checks. Current-image replay of the exact original input passes. A subprocess regression prevents native failure from killing pytest and verifies visible text, 36-point spacing across a blank line and a genuinely empty page.

The initial regression used an unavailable optional reader and then an unsupported page context-manager API; both test failures remain. Production creation already succeeded in those runs. Final regression uses the existing PDFium reader with explicit close; no dependency was added. Actual task PDF text is independently checked with the existing Poppler pdftotext.

## Recovery without repeated successful work

The original read/inspection and model-proposed three calls were retained in checkpoint history. The dead run still appeared running after restart. The authenticated native cancel endpoint accepted interrupt (202); subsequent actual statuses are old run interrupted / continuation success. No database status was fabricated or record deleted.

Continuation uses the explicit known post-model checkpoint, confirms all three target files are absent before continuing, and preserves every prior message and DOCX inspection call ID. Only pending local creations and remaining presentation steps run. The final probe reuses that task, submits no new task/model run, and verifies actual XLSX cells, PPTX slide XML, Poppler PDF text, downloads and history. This is manual recovery through existing product APIs, not acceptance of N08 durable Task/Run/Attempt orchestration or automatic crash recovery.

## Validation and retained boundaries

- Related host suite: 41 existing tests pass; its newly added reader test failed. After correcting only the new test/reader/imports, the regression passes. No repeated full backend run.
- Current immutable image contains the corrected production PDF module. Its regression source predates final test-reader edits; the exact current test file is mounted read-only for the no-network current-image check. All 42 relevant format/font tests pass there. Runtime-image receipt checks deployed production bytes, not a false claim that the image contains the final test version.
- Fixed-host old/current/rollback source behavior probe passes for the affected format/font tests; the optional real report probe joins the frozen host boundary and CI static checks.
- Actual restart, previous/current image rollback/reapply retain successful task history, all three artifact hashes and authorization. These checks do not regenerate reports. The previous image's known empty-text defect is not re-enabled/exercised during the read-only rollback check.
- Cross-tenant and same-tenant nonowner access is rejected. Existing Policy/Approval/Action/Audit code is preserved; original ticket/read-only evidence is reused only for unchanged paths. Final services must be healthy and controlled Action/trusted graph switches off.

The prior full backend/frontend/source/lock evidence applies only to unchanged inputs. Source fixture tests plus actual artifact continuity do not equal real model execution on every future upstream candidate image; that continuous-upgrade acceptance remains required. Original O/F/N items, all milestones and necessary exits remain, M1 is not declared exited and N08 is not started. Other experts, advanced Office, CJK real-task acceptance, full native tools, external business runtime, original gates and remote CI remain.
