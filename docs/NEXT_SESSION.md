# Session handoff — start of GUI Stage C

Written 2026-09-23 at the end of the session that built and confirmed GUI Stages A and B. **Read this whole file before doing anything else, and before asking the user to explain anything** — it is written so the user does not have to repeat themselves. It points and summarises; it does not decide. Precedence (user decision): **`docs/blueprint.md` is the single source of truth**; `docs/reviews/decisions.md` records each decision and why (revision 3, D1–D22); this file says where things stand and what is next.

After this file, read: blueprint §1 (purpose, governing rule), §6 (matching), §7 (the interface and its stages), §12 (built / designed / open); then `decisions.md` D12–D22. Then look at `images/` (`ls`) — the user's current test claim files.

---

## 1. The project in one paragraph

An offline Windows tool for one finance officer. A claim arrives as an **Excel claim sheet** (the claimed lines) plus a **PDF of receipts**. The tool reads every receipt page with OCR, and for each claimed line checks that the receipt shows the **exact date**, the **exact amount** and the **claimant's PIN** on the same page. Each line gets **PASS / CAUTION / REVIEW**; the officer makes the final call. **Governing rule: a wrong PASS is worse than a REVIEW** — whenever evidence is weak, missing or conflicting, the tool says so and the officer decides. Python 3.13, PySide6, RapidOCR (CPU), 8 GB RAM, no network at run time.

## 2. Status at a glance

| Stage | What | State |
|---|---|---|
| OCR module | read each page (measure → prepare → RapidOCR), never crash on a bad page | built, measured, proven |
| Stage A | window: file list, page viewer, OCR text panel, error tab, background OCR, cache, read-ahead | **built and confirmed by the user** |
| Stage B | live search panel (date, PIN, amount) over the whole document, highlights, continuous scroll | **built and confirmed by the user (2026-09-23)** |
| **Stage C** | **Excel claim rows replace the typed fields; each row searched once, mapped to its page; PASS / CAUTION / REVIEW** | **next — plan in §9** |
| Stage D | final layout: OCR panel removed, Verify / Decline, dispositions, claim-level "verify all" | after C |

Health command: **`run_tests.bat`** — 120 tests, all passing at the end of this session. Start the app: **`start_app.bat`** (or `.venv\Scripts\python.exe -m app`).

## 3. Project map (what every file does)

```
app/                        the application (python -m app)
  errors.py                 StageError — the one error shape (.summary one line, .full_text with traceback); ERROR / WARNING
  config_files.py           read_json_config(): every JSON config read the same way, problems -> StageError("config")
  paths.py                  PROJECT_ROOT; config folder paths resolved against it
  ocr/                      OCR (public entry: OcrReader in reader.py)
    reader.py               start() / load_pages() / read_page(); maps every box back onto the page (geometry)
    pipeline.py             proven internals: analyse -> advise -> apply -> RapidOCR; PageResult (+ .applied steps), Word (+ .page_box)
    geometry.py             exact inverse of crop/rotate/resize -> Word.page_box (page as displayed)
    image_files.py          the one JPG/PNG/HEIC reader (OCR and display share it: one pixel frame)
    enhance_rules.json      page-preparation rules, with measured evidence
    engine_settings.json    RapidOCR start-up settings (empty = defaults) + every option tried and why rejected
  layout/                   OCR segments -> printed rows (rows.py, row_rules.json); no OCR/GUI imports
  matching/                 THE DECISION PACKAGE — imports nothing from OCR, image or GUI code
    search.py               public: Query, prepare_page, search_page, search_document -> DocumentMatches (best_page, places, …)
    amount_search.py        amount finder (trial winner A9); faded decimal -> POSSIBLE
    date_search.py          date finder (D4)            pin_search.py   PIN finder (P6)
    money.py                parse_typed_amount (exact Decimal, refuses ambiguity), amount_forms
    dates.py                date_forms (day-first, month names)      tokens.py   row -> tokens remembering their segments
    found.py                Found + strengths EXACT / CORRECTED / POSSIBLE     rules.py + matching_rules.json
  gui/                      PySide6 window, one file per pane
    application.py          run(), startup-failure window, last-resort exception hook -> Errors tab
    main_window.py          layout + signal wiring only
    document_session.py     the open file, OCR thread, cache, read-ahead      document_cache.py  readings kept until the app closes
    ocr_worker.py           background OCR, page on screen first               page_renderer.py   page sizes + pictures on demand
    document_view.py        continuous scroll, lazy page drawing, highlight overlays     page_pane.py  viewer + Prev/Next page
    file_panel.py           left file list (PDF, JPG/PNG/HEIC; .xlsx arrives in Stage C)
    ocr_text_panel.py       OCR text of the page in view        error_tab.py   every error, newest first, copyable
    search_panel.py         typed search (Stage B; replaced by the claim-row panel in Stage C)
    search_controller.py    runs searches; prepares each page's text when it arrives; live updates
    search_summary.py       result in plain words     highlights.py   hits -> outlines (amount blue, date purple, PIN teal)
    settings.py + gui_settings.json   window settings (folder, file types, dpi, zoom, viewer, colours)
tests/                      unittest, all synthetic data; fakes.py = FakeReader (forces every failure path)
tools/                      PROTOTYPES / MEASUREMENTS (say so in their docstrings)
  ocr_resolution_trial/     OCR speed/accuracy trials (answer key in private/, ignored)
  search_criteria_trial/    matching-rule trial (15,673 cases) + verify_app_matcher.py (app == trial winners)
docs/  blueprint.md · NEXT_SESSION.md · reviews/decisions.md (binding record) · reviews/01_consistency.md, audit/ (old review leads)
start_app.bat · run_tests.bat · requirements.in (each library with its reason) · requirements.txt (pinned)
Ignored by git: images/ (claim files), private/ (answer keys, PIN tables), outputs/ (trial results), .venv/
```

## 4. How a claim file flows through the code today

1. `file_panel` lists files in `images/` → the officer clicks one → `document_session.open()` gets page sizes (`page_renderer`, no rendering) and shows the whole document in `document_view` at once.
2. `ocr_worker` (background thread) renders the pages and reads the missing ones, **page in view first**: `OcrReader.read_page` → `pipeline.process_page` (analyse → advise → apply → RapidOCR) → `geometry.attach_page_boxes` (every Word gets `page_box`).
3. Back on the window thread, `document_session` groups the words into printed rows (`app/layout`) and stores the reading in `document_cache` (kept until the app closes; keyed by path + size + modification time).
4. `search_controller.page_arrived` prepares that page's text for searching (`matching.prepare_page`: tokens + trimmed cores, once).
5. A search (`matching.search_document`) is lookups over the prepared pages; `highlights.shapes_for` turns hits into outlines via `Word.page_box`; `document_view` draws them as overlays and scrolls to the best page.
6. Every failure anywhere becomes a `StageError` in the Errors tab; one bad page / row / file never stops the rest.

## 5. What Stages A and B delivered (all confirmed working by the user)

**Stage A:** app package and launchers; file list; background OCR with a responsive window; in-memory cache of every reading (switching files loses nothing, asks nothing; closing asks); read-ahead of the other files; page on screen read first; OCR text panel grouped into rows; Errors tab; start-up failure window; exception hook; photos/screenshots (JPG/PNG/HEIC) as claim files; Word files deliberately not supported.

**Stage B:** search panel (calendar date picker with "not set", PIN any format, amount with ambiguity refusal); search over every page, live updates while reading, best page brought into view, results per key (pages, places, "possible", "OCR character correction"), no verdict; highlights on every occurrence, one colour per key, neighbours on the same row faint, possible matches dashed; Previous / Next match; continuous scroll viewer with lazy drawing (on-screen pages at once, one above/below when idle, far pages released); exact page positions for highlights.

**Measured on real claims (4-core CPU):** OCR ≈ 10 s per page (unchanged by design); preparing a page's text for search 5–15 ms (done when the page arrives); searching all 49 real claim pages ≈ 60 ms; search / next match with the page already drawn ≈ 20 ms; bringing an undrawn page into view 70–110 ms (decoding its photo at 200 dpi).

**Proven:** `app/matching` equals the approved trial winners on all 15,673 trial cases (0 disagreements; `verify_app_matcher.py`); page positions within 2.5 px under forced crop/rotate/resize (`tests/test_geometry.py`) and by eye on real straightened/cropped pages.

## 6. Measurements and trials already done — do not repeat

- **OCR engine settings:** memory arena (identical output, +1.2 GB — rejected), larger recognition batch (changed output on 17/28 pages — rejected), explicit threads, two pages in parallel (each page slower) — none adopted. Evidence in `app/ocr/engine_settings.json`.
- **Detection resolution** (22 pages, 194 hand-checked values): current 10.2 s/page, 186/194 found; 1600 px 8.1 s, 186/194 but every page read differently; ≤1280 px loses values. **User: keep current.** Full-resolution recognition: 186/194, slower — not adopted. Remaining misses are faint/blurred print.
- **Search rules** (65 real pages incl. Kenyan and Ethiopian claims, 497 hand-checked values, 14,700 real decoys, ~560 fabricated): amount 326/333 found, 0 false of 12,633; date 80/81, 0 of 201; PIN 83/83, 0 of 1,992 (the 85 look-alike cases accepted by the user). Rejected alternatives and why: blueprint §6.
- **Orientation:** sideways/upside-down pages still yield their values; row order scrambles. User: no correction.

## 7. Decisions in force (details: decisions.md D13–D22 and blueprint)

PASS / CAUTION / REVIEW (D13) · country not used; PIN = the claimant's, from a person-to-PIN table (D14; typed in Stage B) · search rules = measured trial winners, values always exact after normalisation (D15) · faded decimal point = CAUTION only (D16) · one receipt per page, a strict intake rule (D17) · highlights: same row, one colour per key, every occurrence (D18) · whole-document search, continuous scroll, each Excel row searched once and mapped to its page (D19) · readings cached in memory until the app closes (D20) · OCR at RapidOCR defaults, no orientation correction, photos yes, Word no (D21) · hiding OCR time before the app opens (start with Windows / email-triggered) decided last (D22) · document type never changes behaviour · RapidOCR is the only engine · decision code never returns a plain true/false.

## 8. Environment and repository

- Windows 10, 4 cores, screen 1280×680 at 150 %. Python 3.13.4 in `.venv`. Key packages: PySide6-Essentials 6.11.2, rapidocr 3.9.2, onnxruntime 1.30.0, pymupdf 1.28.2, openpyxl 3.1.5 (already installed — Stage C needs no new library), numpy 2.5.3, pillow 12.3.0.
- `images/` (git-ignored) now holds the user's **full claim files**: a cash claim sheet PDF and a card claim PDF (claim sheet + card statement + receipts), receipt bundles for two claim weeks, a 26-page Ethiopian receipts bundle (telebirr slips, a bank screenshot, ERCA receipts), and two .docx files (ignored by design). Real names and PINs appear in them — never copy them into committed files (a privacy sweep on 2026-09-23 replaced the one real PIN that had crept into examples with the fabricated `A012345678Z`).
- Git: branch **`backend`** of `https://github.com/pere49/automated_claim_management.git`. Pushed: `4ca2920` (Stage A era) and `f791e2b` (Stage B, the trials, the consolidated docs — 2026-09-23). Commit and push only when the user asks; never force; run the privacy sweep on staged files first. The older `blueprint.md` on `master` is superseded by `docs/blueprint.md`; retiring it is the user's call.

---

## 9. The Stage C plan

### 9.1 Goal and definition of done

The officer opens a receipts PDF and its Excel claim sheet. Every claim row is searched once (reusing the Stage B matcher), mapped to its receipt page, and given PASS / CAUTION / REVIEW with a plain reason. Clicking a row (or row Previous / Next) shows its page with that row's highlights instantly, with no new search. The OCR text panel stays visible (Stage C exists so the whole flow — row → search → page → highlight → verdict — can be watched end to end). Done = all tests pass, `verify_app_matcher.py` still reports 0 disagreements, the real-claim acceptance run (9.6) gives the expected verdict on every row, every failure path has been broken on purpose, and the user confirms by eye.

### 9.2 What the claim sheets already tell us (from the two claim-form PDFs in `images/`, which have a digital text layer)

- Header: the claimant's **Name** at the top (this selects the PIN).
- Columns: Date · customers visited / expense description · project number / cost centre · **Receipt No** · category columns with account codes (Motor Vehicle Fuel, Travel, Breakfast, Lunch, Dinner, Daily Allowance, Hotel, Other) · **Rate** · **Total** with a currency in the header ("Total:USD", "Total:KES").
- Each row's amount sits in one category column; Total = amount × Rate. A totals row, "Less Advance", "Balance", signature dates follow.
- Dates are printed like "16-Jul-26"; amounts like "13,000.00". **Receipt No** is 1, 2, … — the receipt's order in the bundle, **not** its page number (the card PDF's page 1 is the claim sheet itself, pages 2–4 a card statement, page 5 the receipts).
- Observed traps: the July **cash** claim is 16 rows of a daily allowance in USD, while the July receipts bundle is in Ethiopian Birr with different dates — per-diem rows may have no receipt at all, and currency differs. On the **card** claim one row's claimed amount equals the card-statement line, while the hotel invoice shows a larger total (a part-payment) — under the current rules that row becomes REVIEW (amount not on the receipt page; statement matching deferred).
- These are PDFs of the sheets, not the Excel files. **The real .xlsx structure must still be confirmed.**

### 9.3 Questions to put to the user first (each with the recommendation to offer)

1. **A real Excel sample** (.xlsx, fabricated values, same layout). *Recommend:* essential before building the reader; meanwhile the reader is designed to find its header row and columns by configurable header words, not fixed positions.
2. **Which value is "the claimed amount" searched on the receipt:** the category-column amount (receipt currency) or Total after Rate (claim currency)? *Recommend:* the category amount — the receipt prints its own currency; show Total only for the claim sum.
3. **Rows that need no receipt** (daily allowance / per-diem): exempt categories listed in config (shown "no receipt needed", not REVIEW), or always REVIEW? *Recommend:* a config list of exempt categories, shown distinctly, never PASS.
4. **Receipt No:** use it only to choose between several pages that each have all three keys (otherwise REVIEW)? *Recommend:* yes — as a tie-breaker, never to override the search.
5. **Person-to-PIN table:** its source and format (JSON or .xlsx in `private/`), and name matching — exact, or ignoring case / extra spaces / name order? *Recommend:* ignore case and extra spaces only; anything else = "claimant not in PIN table" → REVIEW. A committed `*.example.json` with fabricated values documents the format.
6. **Pages that are not receipts** inside the PDF (the claim sheet itself, card statements): *Recommend:* no special handling — they cannot hold the PIN, so they never make a PASS; ambiguity counts only pages holding all three keys.
7. **One receipt claimed by two rows:** *Recommend:* both rows REVIEW "same receipt as row N" (a cheap in-claim duplicate check; cross-claim D8 stays open).
8. **Aggregate check:** *Recommend:* Stage C shows the Excel's own arithmetic (sum of row totals vs the sheet's total / balance, exact Decimal); the sum of receipts' declared totals waits for the total-anchor decision (blueprint §12).
9. **Seller-label and other-buyer-PIN CAUTION checks** (blueprint §6): *Recommend:* build in Stage C, label lists in config, measured on the real pages first (they must never fire on a receipt that correctly shows the claimant's PIN as buyer).
10. **Switching the Excel file:** *Recommend:* nothing is lost (row results are recomputed from cached OCR in milliseconds), no question asked — until Stage D adds officer decisions.
11. **Old .xls files:** openpyxl reads .xlsx/.xlsm only. *Recommend:* list .xlsx/.xlsm; an .xls is refused with a clear message (save as .xlsx).

Record every answer in blueprint §6/§7/§9 and as new D-entries in `decisions.md` **before** writing code.

### 9.4 Design (to confirm against the answers)

- **`app/claims/`** (new package; no OCR/GUI imports), one job per file:
  - `model.py` — `Claim` (file, sheet, claimant name, currency, rows, sheet total/balance) and `ClaimRow` (row number, date, description, receipt-no hint, category, amount, rate, total, problems).
  - `workbook.py` — open the .xlsx with openpyxl (`data_only=True`), pick the claim sheet; every failure → `StageError("excel")`.
  - `sheet_layout.py` — find the header row, the claimant name, and each column **by header words from config**, not positions.
  - `row_parser.py` — cells → `ClaimRow`, **one row at a time; a bad row is recorded on the row, never stops the sheet**. Money: openpyxl returns floats — convert with `Decimal(repr(value))` and accept only if it equals itself rounded to the currency's two places; otherwise the row is "amount unreadable" (never rounded silently). Formula cells without a cached value → "value not saved in the file" (ask the officer to open and save it in Excel). Dates: `datetime` cells, or text like "16-Jul-26" parsed day-first with the month names in config.
  - `pin_table.py` — load the person-to-PIN table from `private/` (path in config); name normalisation per answer 5.
  - `claim_rules.json` — header words, category names, exempt categories, totals-row words, name label, date formats, PIN-table location.
- **`app/matching/verdict.py`** (decision code; returns PASS / CAUTION / REVIEW + a reason code + page, never a bool). From a row's `DocumentMatches`: candidate pages = pages with date EXACT, amount EXACT and PIN EXACT/CORRECTED. Exactly one → PASS (downgraded to CAUTION by the seller-label / other-buyer-PIN checks). More than one → REVIEW "found on pages …" unless the Receipt No tie-breaker (answer 4) resolves it. None → CAUTION if the only gap is a POSSIBLE amount (faded decimal); else REVIEW naming what is missing on the best page. Claimed value missing/unreadable, or claimant not in the PIN table → REVIEW with that reason. Same page claimed by two rows → per answer 7. Rules and label lists in `matching_rules.json`.
- **Row matching** (`app/gui/row_matcher.py` or similar): reuse the prepared pages — first move the prepared-page cache out of `search_controller.py` into its own small file (`prepared_pages.py`) shared by both. Search all rows once when both files are open (one row per idle moment so the window never stalls), and when a new page arrives search **only that page** for every row and merge (~1 ms per row). Result per row: `DocumentMatches`, verdict, chosen page, hits.
- **Window:** file list adds `.xlsx`/`.xlsm` (gui_settings); one PDF and one Excel open at once (each marked in the list). The lower-right search panel is replaced by **`claim_panel.py`** (+ a table model file): claimant / sheet / totals line; table (row, date, description, receipt no, amount, status colour, page); row Previous / Next (separate from the PDF's Previous / Next page); a "why" line for the selected row (each key: found where / missing). Selecting a row → scroll to its page and show only that row's highlights (precomputed: instant). Status colours PASS green, CAUTION orange, REVIEW yellow (D13). OCR panel unchanged.
- **Errors:** every Excel / PIN-table / row failure is a `StageError` in the Errors tab, never containing claimed values, names or PINs.

### 9.5 Build order — each step verified before the next

0. Ask 9.3; record answers in blueprint and decisions.md; decide the package names with the user if anything differs from 9.4.
1. `app/claims` model + workbook + layout + row parser + `claim_rules.json`; tests on synthetic .xlsx built inside the tests with openpyxl.
2. Person-to-PIN table + committed `person_pins.example.json` (fabricated); tests.
3. `matching/verdict.py` + seller-label / other-buyer-PIN checks; measure the checks on the real pages (extend `tools/search_criteria_trial` — they must never fire where the claimant's PIN is correctly the buyer); `verify_app_matcher.py` must still report 0 disagreements.
4. Shared prepared-page cache + row matcher (incremental, idle-time); tests with FakeReader.
5. Claim panel + wiring; window tests (FakeReader + synthetic .xlsx).
6. Real acceptance (9.6), screenshots checked by eye, timing, each failure path broken on purpose.
7. Update blueprint / decisions / this file; `run_tests.bat`; hand to the user for the by-eye check.

### 9.6 Tests and acceptance

- **Synthetic .xlsx fixtures generated in the tests:** normal sheet; header not on row 1; merged header cells; extra sheets; blank and totals rows; amounts as floats that are and are not exact cents; text dates and real dates; formulas with no cached value; missing required column; claimant name missing; corrupt file; password-protected file; `.xls`.
- **Verdict:** a unit test for every branch (PASS, each CAUTION, each REVIEW reason, tie-breaker, same receipt twice, claimant not in table).
- **Window:** rows appear with statuses; clicking a row scrolls to its page with only its highlights; statuses update as pages are read; switching PDF or Excel; failures land in the Errors tab once.
- **Real acceptance (private, git-ignored):** build .xlsx claim sheets whose rows reproduce the real receipts' dates and amounts from the hand-checked answer keys (`tools/*/private/`), in `tools/stage_c_acceptance/private/`, with the expected verdict per row labelled by hand; run with the real OCR on the real receipts bundles; every row must get its expected verdict. Include deliberate mismatches (one cent off, wrong date, claimant without a PIN, per-diem row, the card part-payment row).

### 9.7 Risks to keep in view

Floats from Excel (never round silently) · formulas without saved values · header layouts that differ between the cash and card forms · currency of the claimed amount vs the receipt · per-diem rows without receipts · the claim sheet / statement pages inside the receipts PDF · two receipts on one page (neighbour outlines reach across; D17) · a part-paid invoice (REVIEW by design) · real names and PINs must never reach committed files, logs or error messages · performance with many rows × many pages (incremental search, idle-time work).

## 10. After Stage C

Stage D (blueprint §7): remove the OCR text panel; Verify / Decline acting on the row matched to the page in view; system finding and officer disposition kept as two fields (D2); a row is finished only with a disposition; claim-level "verify all" locked until every row has one. Still open (blueprint §12): the total anchor for the receipts-sum check; warning when the PDF and Excel don't belong together; cross-claim duplicate detection (D8); card/statement matching; memory on very long claims; hiding OCR time before the app opens (last).

## 11. Standing rules (CLAUDE.md — both marked crucial)

One job per file; public entry points in each folder's `__init__.py`; config beside the code that reads it, never inline thresholds. Every stage wrapped at one boundary with `StageError`; one bad item never stops a batch; nothing printed; nothing exits. Money is exact `Decimal`, never float. Logs and errors never contain document text, names, amounts or PINs. Only synthetic data in committed files. Do not add a library without saying why. One stage at a time; do not start Stage D before the user confirms C. **Verify before reporting:** run against real input, break each failure path on purpose, run `run_tests.bat` and report the result.
