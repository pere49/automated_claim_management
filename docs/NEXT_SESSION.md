# Session handoff — Stage C reworked and confirmed; status cards (D42) awaiting the owner's look

Written 2026-09-24 at the end of the session that reworked GUI Stage C after the owner looked at the first version. **Read this whole file before doing anything else, and before asking the user to explain anything.** Precedence (user decision): **`docs/blueprint.md` is the single source of truth**; `docs/reviews/decisions.md` records each decision and why (revision 5, D1–D41); this file says where things stand and what is next.

After this file, read: blueprint §3 (flow), §6 (matching and Stage C checking), §7 (the interface), §12–§13; then `decisions.md` D23–D42 (D34–D42 are this session's).

---

## 1. The project in one paragraph

An offline Windows tool for one finance officer. A claim arrives as a **claim sheet** (a PDF of it — exported from Excel, or scanned; Excel files are not read for now) plus a **PDF of receipts**. Every non-zero amount in the columns from Motor Vehicle Fuel to Other is one **claim item**, paired with its row's date. After OCR reads every receipt page, each item is checked: its **date** and its **amount** (exact, or with only the cents dropped) printed **as the receipt's total** on one page not already paired with another item, plus the company's **Kenyan PIN** when the "PIN required" switch is on. Each item is **PASS / CAUTION / REVIEW**, coloured by **rule B**: green verified, yellow a receipt whose date or amount does not match, red no valid receipt. The claim sheet is shown **as its PDF** with a coloured button per row; every receipt page carries a **badge** saying what does not match. **Governing rule: a wrong PASS is worse than a REVIEW.** Python 3.13, PySide6, RapidOCR (CPU), 8 GB RAM, no network.

## 2. Status at a glance

| Stage | What | State |
|---|---|---|
| OCR module | read each page (measure → prepare → RapidOCR), never crash on a bad page | built, measured, proven |
| Stage A | window, file list, viewer, OCR text, errors, background OCR, cache, read-ahead | **built, confirmed** |
| Stage B | live search (date, PIN, amount), highlights, continuous scroll | **built, confirmed (2026-09-23)**; the typed-search panel removed 2026-09-24 (D42) — its matcher is what the checking uses |
| **Stage C** | claim sheet checked against the receipts — **reworked 2026-09-24 to the owner's design (D34–D41)**: sheet shown as its PDF with row buttons, page badges, rule B, one Total status, Excel reading removed; then **D42**: OCR text and Search removed, status cards (VERIFICATION, TOTAL GRAND, REPEATED) under the sheet, PIN toggle, titles | **rework confirmed by the owner ("everything is working very fine"); D42 built and verified, awaiting the owner's look** |
| Stage D | officer sign-off per amount (D2, D3), final layout | after the user confirms C |

Health command: **`run_tests.bat`** — **189 tests, all passing** at the end of this session (202 before D42; the Search panel's own tests went with it). `tools/search_criteria_trial/verify_app_matcher.py` — **0 disagreements**. Start the app: **`start_app.bat`**.

## 3. Project map

```
app/                        the application (python -m app)
  errors.py · config_files.py (read_json_config; accepts a str path) · paths.py
  company_pin.py            the company PIN from .env (COMPANY_PINS=…; file/key named in gui_settings.json)
  ocr/                      OcrReader (reader.py); pipeline.py; geometry.py (page_box); image_files.py; rules
  layout/                   OCR segments -> printed rows (rows.py, row_rules.json)
  matching/                 finding a value on a page (search.py, amount/date/pin_search.py, money.py, …)
  claims/                   READING a claim sheet (claim_rules.json — expense names, the Motor..Other range):
                            pdf_text.py (text layer + drawn lines) · pictures.py + image_grid.py (scanned) ·
                            table_grid.py (words in ruled cells, keeping each row's and column's position) ·
                            layout.py (header, the Motor..Other range, Total row) · amounts.py · sheet_dates.py
                            (R10u) · sheet_builder.py · reader.py (read_claim_file, sheet_kind,
                            looks_like_claim_sheet; Excel refused with a message) · model.py (+ SheetPlace, Box:
                            where the table sits on the page, in fractions of the page)
  checking/                 THE DECISION PACKAGE (checking_rules.json — anchors, repeats, red_problems, badge_lines;
                            imports no OCR/image/GUI code): labels.py · page_facts.py (+ total_value: the page's
                            printed total, shown on badges) · repeats.py · receipts.py (ReceiptFacts, + date_hits,
                            pin_hits, printed_total) · findings.py · assignment.py (pairing) · verdict.py (reason +
                            detail) · links.py (one page per amount: pair → amount → date only when certain) ·
                            badges.py (problems, rule B colours, badge lines, every page's PageResult) · totals.py
                            (sums + total_status) · engine.py (decide: pairing → verdicts → links → badges → statuses)
  gui/                      main_window.py (layout + wiring; pane sizes in proportion to the window until a divider is
                            dragged) · claim_session.py · sheet_view.py (the claim sheet as its PDF: row buttons,
                            cycling, tints, "No receipt found", outlines, follow the scroll) + sheet_canvas.py (picture
                            fitted to width) + sheet_overlay.py (page fractions → scene; marks) + row_buttons.py ·
                            status_cards.py (VERIFICATION / TOTAL GRAND / REPEATED under the sheet) + elided_label.py ·
                            receipts_header.py ("Receipt claim:", PIN toggle, Auto, Next) + toggle_switch.py ·
                            page_badges.py (badge item) · page_preparer.py (pages tokenised once for the checking) ·
                            claim_presenter.py (badges, every amount's highlights, row of a page) · page_renderer.py
                            (+ render_region: part of a page) · document_view.py (+ set_badges) · tour.py ·
                            file_panel.py · document_session.py · settings.py + gui_settings.json
                            (no OCR text or Search panel: removed, D42)
tests/                      unittest, synthetic data only: fakes.py, claim_fixtures.py (the claim-form template drawn
                            as a ruled PDF), test_claims (24), test_checking (31), test_claim_window (26), …
tools/                      PROTOTYPES / MEASUREMENTS: … · badge_colour_trial (rule A vs B on the real claims) ·
                            stage_c_acceptance (the real claims through the application — Excel tabs read by the
                            runner only; run it after any change to app/claims or app/checking)
Ignored by git: images/, private/ (every tools/*/private/: answer keys, real pairings), outputs/, .venv/, .env
```

## 4. How a claim flows through the code

1. The officer clicks a claim-sheet PDF (**Claim sheet** slot; right-click → "Use as claim sheet" for a scanned one, read by OCR after the receipts). `app/claims` reads it: a grid per page with each row's and column's position → ClaimSheet (items from Motor to Other, dates by R10u, SheetPlace). The window draws the page cropped to its printed area (`render_region`), fitted to width, with a grey button per claim row.
2. The officer clicks the receipts PDF (**Receipts**), read by OCR as in Stage A/B.
3. When every receipt page has a reading: `analyse_receipts` → `find_all` → `decide`: pairing → verdicts → **links** (pair; page printing the amount; the page printing the date only when it is the only free page with that date and the amount the only unlinked one with it) → **badges** (Amount / Date / PIN / Repeated / Unreadable / No receipt found; red_problems red, the rest yellow) → sums → statuses (Verification, Total, PIN, Repeated).
4. The window: row buttons take their rows' worst colours, failed amounts are tinted ("No receipt found" written where there is none), every receipt page gets its badge, every amount's highlights go on its page, the status cards and the PIN toggle fill, the tour starts if configured. Scrolling the receipts outlines the page's row and brings it to the middle (the sheet does not move while the row stays the same). A row button shows its amounts in turn. The PIN switch re-runs only `decide`.

## 5. What was done this session

- **Recovered** the previous session's end (it had finished cleanly) and **committed Stage C as it was** — `e202fa6` on `backend`, local only, not pushed — so the Excel reader stays in history.
- **The owner's redesign, settled over four rounds of questions** (D34–D41): status compressed and moved above the receipts; one Total status; Verification lists failing pages; badges on every receipt page with the mismatch ("4b"); the claim sheet shown as its PDF (cropped, fitted to width) with row buttons replacing clickable cells, cycling through a row's amounts; failed amounts tinted, "No receipt found" on the row; scroll-follow; Excel reading removed; Motor..Other range; larger claim side, smaller OCR/Search; reason line and grand-total lines removed; Auto and Next to check kept.
- **Colour rule measured, then chosen:** the owner first asked for red on any date/amount miss when the PIN is not required. `tools/badge_colour_trial/` showed that on July this makes 10 red rows and no yellow (5 with no receipt mixed with 5 with a receipt one detail off) and makes the PIN switch work backwards; on the Kenyan claims both rules agree. The owner chose **rule B** (red = no valid receipt).
- **Linking by date (2a)** checked against the answer key: the three July amounts linked by date all point at their right receipts (two slips added together); two 29 Jun amounts with two candidate pages stay "No receipt found".
- **Then D42** (the owner, after using it): the OCR text and Search panels removed completely; three status cards under the sheet (VERIFICATION, TOTAL GRAND — the Total renamed — and REPEATED, each with one small line of figures); the PIN switch a toggle above the receipts (its colour the PIN status) with Auto and Next to check where they were; titles "Receipt claim:" and "Claim sheet:". The search controller's page preparation, which the checking needs, became `page_preparer.py`; the typed-search code and OCR panel were deleted (git history keeps them).
- **Bugs found and fixed while verifying:** a fit-to-width scroll-bar ping-pong that froze the window when the sheet pane was short (found by a test at 420 px high; your screen is 680 px); the "sheet could not be drawn" message being wiped when the check finished (found by the failure-path test); an OCR slip ("1O1AL:±1.300.02") read as 1,011,300.02 on a badge (the shown total now reads only plain numbers); "Date ? ≠ ?" for a row with no date (now "Date: none on the sheet"); the pane sizes not applied at the real window size (now shared out in proportion, following the window until a divider is dragged); the OCR/Search tabs refusing to shrink (the search fields now scroll); a long Verification page list widening the receipts pane and squeezing the sheet on July (the status words now shrink with "…", the full text in the tooltip).

## 6. Verified

- `run_tests.bat`: **189 tests pass** after D42 (claims 24, checking 31, claim window 25, main window with the page-preparation tests — including every new failure path: claim page that cannot be drawn, Excel file refused, broken claim PDF, unreadable receipt page, checking crash reported once without values, broken colour/badge/range rules, broken settings, a long status text never widening a pane, the OCR text and Search gone, the header above the receipts and the cards under the sheet).
- `verify_app_matcher.py`: 0 disagreements (matching untouched).
- **Real claims through the application** (`tools/stage_c_acceptance/`), row buttons green / yellow / red: Week1 6 / 1 / 2 (two receipts without the company PIN → red), Week2 5 / 1 / 0 (Excel tab = PDF export), July 10 / 5 / 5 (text sheet = scanned sheet), wrong pair 0 / 1 / 5; stress cases: page repeated → the copy red "Repeated p. 3", the claim green; repeated and claimed twice → both red; claimed twice with one receipt → second "No receipt found"; every page linked to at most one amount.
- **Real window after D42** (Week 2, 1280 × 680 at 150 %): checked 53 s after opening; "Receipt claim:" and the green ON toggle above the receipts; the sheet at full height; cards VERIFICATION yellow "p. 6", TOTAL GRAND red "Not matched" / "4,570.00 of 4,900.00", REPEATED green "None"; panes 140 / 454 / 674 px.
- **Real window, real OCR, at the owner's screen size** (1280 × 680 logical, 150 % — off-screen with the Windows fonts, screenshots checked by eye): **Week 2** checked 70 s after opening (6 pages), 5 green + 1 yellow buttons, the 330.00 tinted, ✓ badges and page 6 "Date ? ≠ 14 Aug", the row button bringing page 6 into view with its highlights, the row outlined; panes 11 / 36 / 53 %. **July** checked after 387 s (26 pages), buttons 10 / 5 / 5, badges as in the acceptance run; then the **scanned July sheet** read by OCR in 19 s with exactly the same colours. A missing claim-sheet file (the owner moved the files mid-session) was reported as one structured error and nothing broke.

## 7. Measurements and trials — do not repeat

- **OCR:** RapidOCR defaults (every alternative measured). ≈ 10–14 s per page.
- **Search rules** (65 real pages): amount 326/333, 0 false of 12,633; date 80/81; PIN 83/83.
- **Claim-sheet dates** R10u: 99.67% of 50,282 fabricated dates, 2 wrong; all 65 real dates right.
- **Cents dropped:** 24/24 fabricated, 127/131 real; the date is always required.
- **Repeated pages:** text + moment, 9/15 re-captures, 0 wrong (per document).
- **Total anchor A4m+:** 31/31 claimed amounts kept; cash / change / tax / before-discount refused. Buyer-PIN: 0 wrong flags on 71 pages.
- **Colour rule** (`tools/badge_colour_trial/`, rebuilt at the end of the session to read the application's own problem keys — its first version re-derived the links and went stale once the app linked pages itself, miscounting July as 12 green rows): A and B identical on Week1 / Week2 / wrong pair; July rows A 10 green / 0 yellow / 10 red, B 10 / 5 / 5 (= the application's colours).
- **Claim-sheet margins:** the printed area fills 85–93 % of the page width, 58 % of the Week 2 page height → cropping enlarges the text only ~15 %.
- **Motor..Other range** = exactly the eight named columns on all three real text sheets.

## 8. Decisions in force (details: decisions.md)

D13 PASS / CAUTION / REVIEW · D15 search rules · D16 faded decimal never passes (now "Amount", yellow) · D17 one receipt per page · D18 highlights · D19 whole-document search · D20 cache · D21 OCR settings · D22 hiding OCR time decided last · D23 Kenyan PIN in `.env` + "PIN required" switch · D24 every non-zero expense amount is an item · D25 reading the sheet (now PDF only) · D26 dates R10u · D27 cents dropped · D28 a paired page leaves every later search · D29 repeated pages (the copy's badge always red) · D30 separate files for now · D31 Auto / Next to check · D33 total anchor, buyer PIN · **D34 rule B** · **D35 links + badges, date link only when certain** · **D36 row buttons** · **D37 one Total status** · **D38 status above the receipts** · **D39 sheet shown as its PDF, Excel removed for now** · **D40 Motor..Other range** · **D41 layout, main folder only** · **D42 status cards under the sheet, PIN toggle, OCR text and Search removed**.

## 9. Environment, files and repository

- Windows 10, 4 cores, screen 1280×680 available at 150 % scaling. Python 3.13.4 in `.venv`; PySide6-Essentials 6.11.2, rapidocr 3.9.2, onnxruntime 1.30.0, pymupdf 1.28.2, opencv-python 5.0; openpyxl 3.1.5 is still installed (used only by the acceptance runner and old trials) — **no new library was added**.
- `images/` (git-ignored; every file back at its top level since 21:54 on 2026-09-24 — the owner had moved them into `New folder/` and `weak2/` for a while, now empty): the Week 2 claim-sheet PDF export `_Cash expenses Claim Form - Week 2 (…).pdf` ↔ `cash expense claim form-week-.PDF` (and its identical copy `…-week.PDF`); `… Cash expenses Claim july_pdf.pdf` (text) and `excel _example_sample.pdf` (scanned; also as `.png`) ↔ `reciept for july (002).pdf`; `Cash expenses claim-July-EA-2026.pdf` (16 daily allowances, no receipts); `expense_claim_form-week 1-(…).pdf` = Week 1 receipts (its sheet exists only as the workbook's Week1 tab — no PDF, so only the acceptance runner checks it); `Receipts Week 2 (…).pdf` = another claim (wrong-pair test); the workbook itself (not listed). **The file list shows the main folder only (D41).** The acceptance runner and the colour trial find files by name wherever they are.
- **Git:** branch `backend`, **pushed through `66f1fe9`** (2026-09-24, owner's request) to github.com/pere49/automated_claim_management: `e202fa6` = Stage C as first built (with the Excel reader), `66f1fe9` = the rework and D42. Nothing uncommitted. Commit and push only when the user asks; never force; privacy sweep first (a sweep before `e202fa6` found one real file-name prefix in this note, replaced with "…").

---

## 10. Next: the owner's look at D42, then Stage D

**Ask the user to try it** (start_app.bat): click `_Cash expenses Claim Form - Week 2 (…).pdf` (Claim sheet), then `cash expense claim form-week-.PDF` (Receipts); wait about a minute. Look at: the sheet shown as itself with 5 green buttons and 1 yellow (the 330.00 tinted); the cards under the sheet (VERIFICATION p. 6, TOTAL GRAND Not matched / 4,570.00 of 4,900.00, REPEATED None); the PIN toggle ON in green; the ✓ badges and page 6's "Date ? ≠ 14 Aug"; scrolling the receipts (the row follows, outlined); the row buttons; Auto / Next to check; the PIN toggle (turn it off: grey, the rows re-colour). Then July (its text sheet, then `reciept for july (002).pdf`; 26 pages, ~5 min): 10 green, 5 yellow, 5 red rows; pages 18 and 21 linked by date ("Amount 1,709.00 ≠ 3,015.00", "Amount 760.01 ≠ 2,060.00").

**Known limits to mention (blueprint §13):** on a 1280 px screen the sheet's text is small (fit to width; Ctrl + wheel zooms); the badge's receipt figure is the largest amount on a total row (a receipt holding two slips shows one of them); a scanned claim sheet waits for the receipts (one OCR engine); a receipt layout never seen may print its total under an unlisted label → "Amount"; 6 of 15 re-captured receipts are not detected as repeats; a page listing several claims inside the receipts is not guarded (separate files for now).

**Then Stage D** (after the user confirms C): the officer's own sign-off per amount (D2, D3) — so a yellow can count as verified after a manual check; a report / export; the final layout (fitting the sheet's height too, removing the OCR text). Later: Excel reading back if wanted (in git history), repeats across claims, card / statement matching, hiding OCR time before the app opens.

## 11. Standing rules (CLAUDE.md — both marked crucial)

One job per file; public entry points in `__init__.py`; config beside the code that reads it. Every stage wrapped at one boundary with `StageError`; one bad item never stops a batch; nothing printed; nothing exits. Money is exact `Decimal`. Logs and errors never contain document text, names, amounts or PINs. Only synthetic data in committed files. No new library without saying why. One stage at a time, confirmed by the user before the next. Verify before reporting: real input through the application's own code, every failure path broken on purpose, `run_tests.bat` run and reported.
