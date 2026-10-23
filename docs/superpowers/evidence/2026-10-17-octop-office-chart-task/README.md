# Original Office expert: editable charts, speaker notes and revision history

Branch `codex/octop-integration`, baseline `68eb3f42`. Continues the original independent Office goals under O05/O11/O21/O40; it does not redefine M1, N08 or the retained excluded-source boundary.

## Actual user task

Native login → create from unchanged `expert:office-automation` → upload a synthetic revenue CSV with an unpredictable marker → configured `gpt-5.6-luna` reads it → editable XLSX/PPTX charts → add missing speaker notes in the same thread → upload a correction → edit existing XLSX and PPTX chart data into separate files → download/new-login history/checkpoint/current ACL.

The original data is 100/150/120; the correction changes only the second value to 175. Acceptance reads the downloaded XLSX cells/chart reference, PPTX chart cache and embedded editable XLSX. It checks the marker, actual speaker notes, current downloads/history and same-tenant nonowner/other-tenant denial. Model-visible tool calls are extracted from the actual SSE JSON, including calls no longer present in the compacted latest state. Original checkpoint message IDs are re-read through the authenticated checkpoint endpoint; normal context summarization is not misreported as lost history.

## Preserved failure and concrete capability added

`real-chart-task.json` is an actual failed acceptance, not a simulation. The model generated correct editable data/charts but put the requested “source remark” in visible slide text; the stricter acceptance required speaker notes. That wording was ambiguous and is not labeled a deleted capability or engine defect. The model also attempted unsupported workarounds, whose actual outcomes remain in private transcripts.

Inspection established a concrete editing gap: the native tool could create notes and replace existing note text, but could not add notes to an already generated deck. `office_pptx action=edit_notes` now adds/replaces/clears speaker notes by 1-based slide index and saves a new owned artifact. The tool exposes nested page/chart/note fields to the model. Strict numeric/index types retain the previous rejection of booleans and numeric strings; malformed/duplicate/out-of-range targets and control characters are denied. The existing package validation/current file access/atomic non-overwriting publication remain.

`real-chart-task-recovered.json` resumes the original Agent/thread and existing data, requests the new notes edit, and then performs the actual revenue correction. It does not regenerate the already verified first XLSX or original chart PPTX. Original template prompt bytes remain. The baseline failure receipt stays unchanged.

## Acceptance bounds and upgrade

This accepts basic editable chart generation/revision and speaker-note editing through the product's authenticated APIs with an actual configured model. It does not accept desktop visual rendering, advanced slide layouts/animations, full Office fidelity, all experts, full Octop collaboration or independent durable child recovery. Those original items remain pending; no excluded upstream Office source was copied.

`chart-notes-corrected` covers original chart/image behavior plus note add/replace/clear, unchanged chart XML/embedded data/slide shapes, current authority/revoke and authenticated download. The first fixture/schema-check test failures are retained and corrected. `chart-notes-strict-schema` and the final image cover strict model-visible input types. `upgrade.json` covers the first notes implementation; `upgrade-strict.json` reruns the changed strict schema/probe inputs. Unchanged chart/image checks retain their precisely scoped first receipt; the final strict image additionally checks formats/images. Earlier full backend/frontend evidence is historical; this block does not claim a new full backend or browser-rendering run.

The owned main test stack remains at `http://localhost:18026`, using the existing private model configuration. Existing WSL native profile is separate at `http://localhost:18036`. Raw transcripts/configuration/credentials stay in ignored owner-only runtime paths. Public files carry synthetic data/IDs/hashes only. No push, remote CI or production release is performed. All original N/O/F and milestone exits remain; M1 is open and N08 unstarted.

`runtime-cycle.json` and three `recheck-*.json` receipts passed restart, rollback to the previously accepted child-task image, and reapplication of the strict current image. No model request was resubmitted. Chart cells/cache/embedded workbook/speaker notes, the immutable pre-note files, old checkpoint, current ACL and the previous child DOCX remained available. `runtime-image-strict.json` separately records the intermediate pre-strict image and the actual previously accepted rollback target. `final-proof.json` verifies current image/source/readiness/security and updates only the recorded main-image reference in the existing native controller; the existing native profile then reloads the final code with its owned-process guard. Receiver count remains 26 and canary off.
