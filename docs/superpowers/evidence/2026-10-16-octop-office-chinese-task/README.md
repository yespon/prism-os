# Real Chinese PDF and native preview task

Continue 24855bf; same branch, model and original Office expert. Actual product upload places a current OS font into the owned thread. The expert reads the existing Word report, creates a Chinese PDF using that exact uploaded font_path, presents it, then responds to a natural follow-up by rendering its first page and presenting a PNG. Downloads, fresh-login history, per-run success and cross-tenant/same-tenant nonowner denial are checked. This is actual configured gpt-5.6-luna execution through product APIs, not browser-click acceptance.

## Actual defect, not hidden by text extraction

The first PDF and preview passed text/download/auth assertions, but visual inspection of both native and independent Poppler renders found boxes in place of spaces. Those receipts prove only their named checks; they do not alone accept the complete Chinese task. Original PDF/font bytes stay private, and the bad PNGs/arguments are retained publicly as synthetic evidence.

A TTC-to-single-face control did not fix the problem. A small OFL fixture with ordinary space and no-break space mapped to the same glyph reproduces lost text (A B becomes AB) and bad pixels. The current font is a real example of such aliases. Keep validated Unicode-to-glyph IDs and generate one distinct CID per used Unicode character, even when glyph IDs coincide. The original boolean font_coverage interface remains. Explicit ToUnicode/CIDToGID data uses the [PDFium native API](https://pdfium.googlesource.com/pdfium/+/refs/heads/main/public/fpdf_edit.h); default Latin-1 fonts and all existing rights/size/map/shape/line limits remain. No font substitution, OS fallback lookup or new dependency was added.

The alias regression fails before the mapping change and passes after it, checking both Unicode spellings and actual blank-space pixels. Normal TTF, actual TTC and its extracted-face controls are archived; normalization was an investigation control and is not the production fix. Fixed native and independent rendered Chinese reports were visually checked: spaces and Chinese text are legible, with no replacement boxes.

## Complete task and scoped reuse

`real-chinese-fixed.json` reuses only the already uploaded font: actual fresh authorized read matches the original SHA; it does not upload again. The relevant production font code changed, so a new model generation and new output filename are required. Old files and history are preserved. `native-preview-fixed.json` runs the remaining preview task, explicitly proving render of the existing fixed PDF, no create call, unchanged PDF SHA and history/current ownership checks.

Related format/font tests, current no-network immutable image and fixed-host source old/current/rollback tests pass. The optional Unicode task and preview script join the frozen host boundary; CI includes its static check. No repeated full backend/frontend run is claimed. Exact unchanged prior scope remains historical evidence. Runtime restart/image rollback/reapply checks both accepted run IDs, PDF/PNG hashes, history and nonowner denial, without submitting a model task. Real model regeneration on every future candidate source image remains a continuous-upgrade acceptance requirement, not inferred from fixture tests or artifact continuity.

## Private assets and minimal use

The font is the current workstation's existing msyh.ttc, validated by current size/embedding/glyph checks. Font and embedding PDF stay in ignored owner-only test storage and are not imported into source, images or public evidence. Public evidence contains hashes, synthetic text, and rendered PNGs. No general font redistribution/Office fidelity claim is made.

Use an owned TrueType-outline TTF/TTC covering the requested characters, upload it through the ordinary attachment API/UI, and provide its virtual path to the expert. Default PDF font supports Latin-1; unsupported outlines, missing glyphs and advanced shaping/layout/OCR/forms remain explicit pending boundaries. To repeat in the existing WSL test environment, run scripts/octop_office_unicode_probe.py with --source pointing to an accepted template task and --font pointing to the local font, or --reuse-font pointing to a still-current prior receipt. Never provide credentials on the command line.

All original N/O/F, milestones and exits remain; this accepts basic Chinese generation/preview, not complete Office or all experts. Original Policy/Approval/Action/Audit remain, M1 is not declared exited and N08 is not started.
