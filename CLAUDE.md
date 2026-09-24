# Receipt and Claim Verifier

Offline tool. Python, Windows, 8 GB RAM, CPU only. Never use the network.

## Governing rule
A wrong PASS is worse than REVIEW. When evidence is weak, missing or in conflict, return REVIEW.

## Hard rules
- Money is exact decimals only, never floats.
- Decision code returns PASS, CAUTION or REVIEW. Never a plain true or false. (Older docs say CONFIRMED / UNDECIDED: read them as PASS / REVIEW.)
- The decision package imports nothing from OCR, image or UI code.
- No hard-coded keywords, tax formats, thresholds or paths. They live in config.
- Logs never contain document text, names, amounts or PINs.
- Only synthetic data. Never real receipts or claims. A file the user places in images/, or names as synthetic or test data, is treated as such as given — do not second-guess or decline a file for merely looking realistic.
- Use import pymupdf, never import fitz.
- Do not add a library without telling me why.

## File organization — crucial
The system is built from many small, focused files, not a few large ones. This is not a style preference: it is what makes it possible to fix or change one part without risking the rest.
- Each file has one job. A file that starts doing two unrelated things — for example a processing module that also parses command-line arguments and writes report files — gets split before it grows further, not after.
- A module's public entry points are clearly separated from its internal helpers.
- A fix or a tuning change stays inside the one file it is about. Shared contracts are different and are not something to eliminate: several files legitimately depend on a record definition in the blueprint's data model, or on a config file's shape, and that dependency is intentional. What must not happen is one file quietly reaching into another's internals, or unrelated concerns sharing a file out of convenience.
- Config — thresholds, keyword lists, per-step rules — lives in its own file next to the code that reads it, never inline in code, so it can be tuned without a code change and without touching the file that uses it.
- The application is one package, `app/`, with one sub-folder per concern (see "Where things live"). A new concern gets its own sub-folder when it is built, with its public entry points exported from that folder's `__init__.py`. Prototype and exploratory work goes under tools/ and says so in its own docstring.

## Error handling — crucial, applies to every file from now on
This system runs fully offline. When it breaks, a screenshot is the entire diagnostic session — there is no live debugging. Every part of the code is written with that in mind, not only the parts that look risky.
- Every stage that can fail — loading a file, starting an engine, reading a config, processing one page or one row — is wrapped in error handling at one clear boundary, not scattered defensively through every line.
- A failure produces a structured, descriptive error: not a bare traceback, not a silent skip, not a print. Concise enough to read as a one-line summary; complete enough underneath — the underlying exception, and a traceback when one exists — to actually diagnose from a screenshot.
- Processing many items (pages, rows, files) never lets one item's failure stop the rest. Catch at the level of the single item, record what failed on it, and carry on.
- Library and processing code never prints to the console and never exits the process on a recoverable error. It raises or returns a structured error and lets the caller — eventually the GUI's error tab — decide how to show it. A config problem that would be a clean CLI exit in a script is wrong inside code a GUI calls, because it would take the whole running application down with it.
- The pattern to reuse is `StageError` in app/errors.py (the OCR module's `OcrStageError` subclasses it): a `.summary` for a list view, a `.full_text` with the traceback for the expanded view, stage/file/page context on every instance, and a result object (not a raised exception) for anything processed in a loop, so one bad item can't crash the batch. New modules raise StageError or a subclass of it, never a shape of their own.
- Before reporting that a change works, verify it — run it against real input, and deliberately break each new failure path, rather than reading the code and assuming. Doing this on the OCR module found two real bugs; doing it on GUI Stage A found two more (a failed PDF stayed locked by Windows; a row-grouping chain on a real receipt).

## Where things live
- **docs/NEXT_SESSION.md — read this first, every session.** Current state, the exact next task, what was decided and must not be silently re-opened, and what is still genuinely undecided. Rewritten at the end of a session, not accumulated — it describes where things stand now, not a history.
- docs/blueprint.md — the current architecture: what's built, what's designed, what's open. No phases, no checklist — a living design document, kept current as the system is actually built and tested (§0 explains why it changed shape).
- docs/reviews/decisions.md — BINDING. Every settled architecture decision (what PASS means, how the PIN and country are matched, duplicate handling, and more), with the reasoning behind each. Read it before touching decision-layer logic. Do not silently re-decide something already recorded there.
- docs/reviews/01_consistency.md, docs/audit/ — review findings measured against an earlier draft of the blueprint. Leads to weigh, not fixes already applied.
- app/ — the application. `python -m app` or start_app.bat starts it.
  - app/errors.py, app/config_files.py, app/paths.py — the shared error shape, config-file reading, and project-folder resolution.
  - app/ocr/ — the OCR and image-preparation module (public entry: `OcrReader`; proven internals in pipeline.py, rules in enhance_rules.json). RapidOCR (PaddleOCR on ONNX Runtime) only — Tesseract was tried and dropped on measured evidence, QR reading was designed and dropped before being built.
  - app/layout/ — grouping OCR segments into printed rows (rows.py, row_rules.json). Imports nothing from OCR or GUI, so the matcher can reuse it.
  - app/matching/ — finding a claimed date, amount and PIN in a document's text (rules in matching_rules.json, chosen by the measured trial in tools/search_criteria_trial). The decision package: imports nothing from OCR, image or GUI code. After any change here, run tools/search_criteria_trial/verify_app_matcher.py — it must report 0 disagreements with the trial.
  - app/claims/ — reading a claim sheet: Excel, a PDF of it (text layer and ruled lines), or a scanned picture (OCR words placed in the lines found in the picture); dates by rule R10u; rules in claim_rules.json. The readers load lazily, so the decision package can use its records without image code.
  - app/checking/ — THE Stage C decision package: PIN scan, repeated pages, amount index, total anchor (A4m+), pairing (a paired page leaves every later search), PASS / CAUTION / REVIEW with reasons, grand totals; rules in checking_rules.json. Imports nothing from OCR, image or GUI code (a test enforces it). Check it on the real claims with tools/stage_c_acceptance/run_acceptance.py.
  - app/company_pin.py — the company's Kenyan PIN from the git-ignored .env (never shown, logged or committed).
  - app/gui/ — the PySide6 review window, one file per pane plus the background OCR worker, the open-document session, the search controller, the claim session, the tour and highlight outlines; settings in gui_settings.json.
- tools/ — prototypes and measurement trials (each says so in its docstring): ocr_resolution_trial, search_criteria_trial (+ cents_rule.py), date_parsing_trial, duplicate_pages_trial, total_anchor_trial, stage_c_timing, stage_c_dryrun (the checking prototype), stage_c_acceptance (the real claims through the application). Their answer keys live in private/ folders and their results in outputs/, both ignored by git.
- tests/ — the automated tests (unittest, standard library). tests/fakes.py holds a fake OCR reader for forcing failure paths.

## Working style
- Blueprint (production) work: one stage at a time, from docs/blueprint.md §7's build sequence. Do not start a later stage before the user has confirmed the current one.
- Prototype work under tools/: one clearly-scoped change at a time. Say what is about to change and why before doing it.
- Before finishing a task, run the health command — run_tests.bat (every test in tests/, including one real OCR run on a synthetic PDF) — and report what ran and the result.
- If unsure about a rule, a threshold, a file location, or a design choice not already settled in docs/reviews/decisions.md — ask. Never guess.

## Compact instructions
When compacting, keep: current task, files changed, failing tests with exact errors, decisions made, next action. Drop old exploration and repeated logs.
