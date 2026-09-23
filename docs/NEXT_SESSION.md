# Session handoff

Written 2026-09-23, for whoever (human or Claude) picks this up next. Read this file first, in full, before opening anything else or asking the user to re-explain something. If this file and `docs/blueprint.md` ever disagree, trust `docs/blueprint.md` — this file is a pointer and a task list, not the record of truth.

Reading order after this file: `docs/blueprint.md` §7 (the interface and its build sequence), §6 (the matching design Stage B builds), §12 (built / designed / open). Then `docs/reviews/decisions.md` only if something below needs its reasoning.

## Where the project actually stands

**GUI Stage A is built and tested, and waiting for the user's by-eye confirmation.** Start it with `start_app.bat` (or `.venv\Scripts\python.exe -m app`). Picking a PDF in the left list shows it at once and reads its pages with the real OCR on a background thread, the page on screen first; each page's text appears beside it grouped into printed rows. Raw Previous/Next page and the Errors tab work. The search fields and a disabled Search button are present and do nothing.

**OCR readings are cached in memory until the app closes (added 2026-09-23 at the user's request).** Switching files asks nothing and loses nothing; a half-read file resumes with only its missing pages; failed pages are retried on the next open; an edited file (size or modification time changed) is read again. With `read_ahead` on in `gui_settings.json`, the other PDFs in the folder are read in the background when the engine is idle. The file list shows each file's state ("read", "reading 2/4", "could not open"). Closing the app asks first, because that is where the cache is lost. Pages are rendered for display on demand (`page_renderer.py`, tens of milliseconds), so the page never waits for OCR. Measured on real PDFs: first page shown in 0.35 s, a cached file's text shown in 0.08 s, a page jumped to is read next. Known cost: a page already being read cannot be interrupted, so opening an unread file can wait up to one page's reading time (about 10-15 s) before its own reading starts.

**Do not start Stage B until the user says Stage A is confirmed.** Their check is: open real PDFs, compare the OCR panel against each page by eye, and try the file switching and error tab.

**Code layout (decided and built this session):** one package, `app/`.
- `app/errors.py` — `StageError`, the one error shape (`OcrStageError` subclasses it). `ERROR` / `WARNING` levels.
- `app/config_files.py` — every JSON config is read through `read_json_config()`, so config problems are always the same structured error.
- `app/ocr/` — the proven OCR module, moved from `tools/ocr_smoke/` unchanged except for the shared error base. Public entry: `OcrReader` (`start`, `load_pages`, `read_page`). `pipeline.py` is the internal machinery (was `ocr_compare.py`).
- `app/layout/` — groups OCR segments into printed rows (`group_rows`, rules in `row_rules.json`). Imports nothing from OCR or GUI, so the matcher can reuse it.
- `app/gui/` — one file per pane, plus `ocr_worker.py` (background thread, page on screen first), `document_cache.py` (readings kept until the app closes), `document_session.py` (open file, OCR thread, cache, read-ahead), `page_renderer.py` (on-demand page display), `main_window.py` (layout and wiring only), `application.py` (start-up and the last-resort exception hook), and settings in `gui_settings.json`.
- `app/ocr/image_files.py` — the one reader for photo/screenshot files (JPG, PNG, HEIC), used by both the OCR and the display so they share one pixel frame (orientation flag applied).
- `app/ocr/engine_settings.json` — RapidOCR start-up settings; empty (defaults) after measurement, with every tested option and why it was not adopted recorded in the file.
- `tests/` — 72 tests, standard-library unittest. **`run_tests.bat` is now the health command** (CLAUDE.md updated to say so). `tests/fakes.py` has a `FakeReader` that forces every failure path.
- `tools/` and `outputs/` were removed (empty once the OCR module moved).

**Repository:** the user ran `git init` in the project folder on 2026-09-23. There are no commits and no remote yet. The user asked about pushing to `https://github.com/pere49/automated_claim_management.git`, then withdrew that. Do not commit or push without being asked. `.gitignore` was rewritten to keep out every claim document anywhere in the tree (PDF, images, Excel/CSV, emails, Office lock files), the person-to-PIN table and company tax IDs, secrets, logs, screenshots, case data and outputs. Real PIN tables go in `private/` or a file named `person_pins*`, `*_pins.*` or `*.local.json`. Only `*.example.json` templates with fabricated values may be committed. It was verified with `git check-ignore`, and 47 code, doc and test files remain committable.

**Libraries:** `PySide6-Essentials` 6.11.2 added, with the reason in `requirements.in`. `pytesseract` removed from the list and from `.venv`. `requirements.txt` is now the pinned `pip freeze` of `.venv`. `python-docx` is still listed but no code uses it; ask before removing it.

## What testing found and fixed this session

- **Row grouping chained two printed lines** on `yem_p2.pdf`: "9928", printed between "RECEIPT NUMBER:" and "DATE:", pulled both lines into one row. Fixed with a second rule, `max_overlap_per_height` in `row_rules.json`: segments that overlap horizontally are never on the same row. Checked on five real, differently laid-out pages. A unit test reproduces the case.
- **A corrupt PDF stayed locked by Windows** after it failed to open, because the stored error kept the PDF library's internal state alive. `StageError` now releases that state when it is created. The traceback text is unaffected. The integration test would fail again if this regressed.
- **Quitting without closing the window** (for example at Windows logoff) would have left the OCR thread running and crashed Qt on exit. The session now also stops on application quit. Both quit paths were run on the real entry point and exit cleanly with code 0.
- **The configured window (1600 × 950) is larger than this machine's screen** (1280 × 680 at 150 % scaling). The window now opens maximized when the configured size does not fit. Panes can no longer be dragged to zero width, so the file list hides only through its toolbar toggle.

## OCR speed — measured 2026-09-23, do not re-measure from scratch

About 10 s per page on this 4-core CPU (detection 5-8 s, recognition 4-13 s). Every engine option was tested on all 28 pages in images/ for identical text and positions; none was adopted (details in `app/ocr/engine_settings.json`): a memory arena was identical but held about 1.2 GB more memory for 5-9% speed; a larger recognition batch changed the output on 17 of 28 pages; reading two pages at once raised total throughput about 22% but made each single page take about 16 s instead of 10 s. The speed-ups that were adopted change only *when* reading happens, never what is read: the cache, the page on screen first, read-ahead, and on-demand page display. **Detection resolution was measured with a full accuracy test** (`tools/ocr_resolution_trial/`, prototype; answer key in its `private/` folder, results in `outputs/ocr_resolution_trial/summary.json`, both ignored by git). On 22 pages / 194 hand-checked values: current 10.2 s/page, 186/194 found; detect-only 1600 px 8.1 s, 186/194; 1280 px 6.5 s, 182/194; 1024 px 5.4 s, 182/194; 800 px 4.6 s, 169/194; whole image 1600 px 8.5 s, 185/194; 1280 px 6.7 s, 183/194. Every lower setting reads every page somewhat differently. **Decided 2026-09-23: keep the current setting.** Also tried and not adopted: recognising each text line from the full-resolution page (detection unchanged): 11.1 vs 10.6 s/page, 186/194 either way (2 recovered, 2 lost) — the current misses are faint or blurred print, not resolution. RapidOCR ignores `Det.limit_side_len` on large pages, so a detection-only change would need an override of its detector sizing, guarded by a start-up check that the override took effect. To re-run: `run_trial.py` then `score.py` in that folder.

## The next task, once Stage A is confirmed: GUI Stage B

Blueprint §7 has the agreed spec, and §6 the matching design. In summary:

1. **First, keep the full processing plan on each page result.** `PageResult.used_steps` stores only step names. Highlighting needs the crop offset, rotation angle and resize factor that were applied, because word boxes are in the coordinates of the processed image, not of the displayed page. Store the applied `Step` objects (name and params) on `PageResult`, then write one mapping function from processed-image coordinates to page coordinates. Test it by drawing boxes on real pages that were cropped and rotated.
2. **Build the matcher as its own clean, tested package** (for example `app/matching/`), the way the OCR module was built. It should cover:
   - money parsing into exact `Decimal` values, never float, returning "cannot parse" when the separators are ambiguous;
   - generating the printed forms of an amount and a date;
   - exact search over rows, joining adjacent segments on a row (reuse `app/layout`);
   - the PIN closed search: at Stage B the PIN is typed into the PIN field as a search keyword; the person-to-PIN table (claimant name -> PIN) comes with Stage C, not before;
   - picking which segments to highlight, on the same printed row only.

   It must import nothing from OCR or GUI code, per CLAUDE.md, and must not be a throwaway: Stage C reuses it unchanged.
3. **Wire the search button to it** against the open page, and draw the highlight in `page_pane.py`'s graphics view.

Still to put to the user, at Stage C (not before). Ask, don't assume:
- **The person-to-PIN table's form.** Where it comes from, what shape it has, and how names are matched between it and the Excel (exact spelling or normalised). Its real values must stay in `private/` or an ignored file name (see `.gitignore`).

**Do not start the search work until the user asks.** On 2026-09-23 the user said explicitly not to proceed to the next step yet.

## Stage B decisions taken 2026-09-23 (user), before any Stage B code

- **Stage B shows what was found, not a verdict.** Per key: found or not, on which pages, where. PASS / CAUTION / REVIEW verdicts arrive with Stage C.
- **Verdicts (for Stage C):** PASS / CAUTION / REVIEW stay. Date or amount not matching exactly -> REVIEW (the user calls it "yellow review"). CAUTION = a different buyer PIN printed, or our PIN only under a seller label.
- **The three search keys are date, amount and PIN.** Date and amount are each expanded into their set of printed forms before searching (e.g. 1200 -> 1200, 1,200, 1,200.00, 1200.00; dates in all their written forms).
- **Amounts count anywhere on the receipt** (no largest-amount or beside-a-total-label requirement), **but only as a value standing on its own**: never inside a longer number, code or word (e.g. 500 must not match inside 4245002 or a PIN).
- **One receipt per page** is assumed (it will be a strict intake rule); multi-receipt pages are not handled.
- **The search field is a Date field** (no free keyword).
- **Search covers every page of the open file**, and the page where the match is found is brought into the viewer. Page changes by the officer only move the viewer; they do not re-run the search. Stage C does the search once per Excel row and maps rows to pages, so clicking a row opens its page with no new search.
- **The page viewer becomes a continuous scroll view** of the whole document (user request), not one page at a time.
- **Joining split segments** only when they are close together on the row (gap limit in config), proven by decoy tests.
- Still open from this round: PIN look-alike characters (user asked for a recommendation), and the clarifications listed in the session's final message.

## Decided — do not re-open these without a stated reason

- **CONFIRMED means** PIN found, plus date and amount matching the Excel, all on the same receipt. No invoice number (D7 was corrected to say so).
- **Value matching is always exact** after normalisation, never fuzzy. Labels may tolerate OCR noise.
- **Document type never changes behaviour.**
- **Status names are PASS, CAUTION and REVIEW** (2026-09-23). CLAUDE.md and the blueprint now say so; older text saying CONFIRMED / UNDECIDED means PASS / REVIEW.
- **OCR readings are cached in memory until the app closes; nothing is persisted to disk** (2026-09-23, reversing the earlier "no caching" decision; blueprint §8).
- **Stage B takes the PIN as a typed search keyword**; the person-to-PIN table is Stage C (2026-09-23).
- **PINs are fabricated placeholders** for now. No Excel sample exists yet, so build against the row shape in the blueprint plus a synthetic fixture.
- **RapidOCR is the only engine.** QR reading is out of scope.
- **The GUI is PySide6**, in `app/gui/`, with the layout above. The file list shows PDFs only until Stage C adds Excel. Images (JPG/PNG) are not listed.
- **Switching files asks nothing** (nothing is lost); **closing the app asks first** when any readings are cached.
- **The file list shows PDFs and photos/screenshots (JPG, JPEG, PNG, HEIC, HEIF)** (2026-09-23). An image is one page; checked on all 7 real image files in images/ (display and OCR frames identical).
- **No whole-page orientation correction** (user, 2026-09-23: as long as the text is detected, orientation does not matter). Measured: sideways/upside-down pages still yield their values, but the row order in the OCR panel is scrambled or reversed. Do not re-propose without a new reason.
- **Highlights stay on the same printed row** (2026-09-23).
- **Highlight colour depends on the value type**: one colour each for amount, date and PIN, so the officer sees at a glance which value matched where (2026-09-23).
- **Highlighting design (agreed in discussion, 2026-09-23):** page-frame boxes are computed once per page in the background worker (the applied crop/rotate/resize combined into one transform, applied to every box) and cached beside the rows; highlights are overlay items in the page's QGraphicsScene in page pixels (Qt handles zoom/scroll; cosmetic pens); search runs over the cached rows. Prerequisite: PageResult must keep the applied steps with their parameters, not just their names, and the mapping must be tested to within 1-2 px on synthetic pages with forced crop/rotate/resize plus real pages by eye.
- **Country is not used for now** (2026-09-23). Neither the Excel nor the receipts state one. The PIN to search for is the claimant's: the Excel gives the person's name, and a person-to-PIN table supplied at search time gives the PIN. People in the same country share a PIN. No currency check runs. `decisions.md` D4 and D5 carry a dated note, and blueprint §6 and §9 are updated.

## Still genuinely open — ask, don't assume

From blueprint §12, plus the Stage B questions above:
- **The total anchor.** What anchors "the total" on a page showing several amounts. Needed before the aggregate total check.
- **PDF and Excel mismatch.** Whether to warn when the loaded PDF and Excel don't obviously belong to the same claim.
- **Duplicate detection.** How it (`decisions.md` D8) fits the simplified single-engine flow.
- **Card and statement matching.** Whether it is ever built.
- **Memory on long claims.** While a file is being read, all its pages are rendered in memory at once (about 25 MB per A4 page at 300 dpi, released after). Fine for the claims seen so far; revisit if long claims appear (blueprint §13).
- **Hiding OCR time before the app is opened — decide at the very end, not before.** The user's two candidate approaches: start the application with Windows and let it read in the background, or let the (future) email intake trigger OCR as claims arrive, so readings are ready when the officer opens the app. Either would need readings to outlive the window (today the cache is memory-only), which ties it to the persistence decision in blueprint §8. Do not build either until the user brings it up.

## Standing rules, restated because they matter more than any single task

From `CLAUDE.md`, both marked crucial:
- **File organization.** One job per file. Public entry points are exported from each folder's `__init__.py`. Config lives in its own file next to the code that reads it.
- **Error handling.** Wrap each stage at one clear boundary and raise `StageError` or a subclass. One bad item never stops a batch. Nothing prints to a console, and nothing exits the process on a recoverable error.

**Verify before reporting something works.** Run it against real input, and deliberately break each new failure path. This session that approach found the problems listed above, none of which reading the code had shown. Run `run_tests.bat` before finishing any task and report the result.
