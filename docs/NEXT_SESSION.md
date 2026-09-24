# Session handoff — Stage C built, awaiting the owner's check by eye

Written 2026-09-24 at the end of the session that planned, measured and built GUI Stage C. **Read this whole file before doing anything else, and before asking the user to explain anything.** Precedence (user decision): **`docs/blueprint.md` is the single source of truth**; `docs/reviews/decisions.md` records each decision and why (revision 4, D1–D33); this file says where things stand and what is next.

After this file, read: blueprint §3 (flow), §6 (matching and Stage C checking), §7 (the interface), §12–§13; then `decisions.md` D23–D33.

---

## 1. The project in one paragraph

An offline Windows tool for one finance officer. A claim arrives as a **claim sheet** (Excel, a PDF of it, or a scanned picture of it) plus a **PDF of receipts**. Every non-zero amount in the sheet's expense columns is one **claim item**, paired with its row's date. After OCR reads every receipt page, each item is checked: its **date** and its **amount** (exact, or with only the cents dropped) printed **as the receipt's total** on one page not already paired with another item, plus the company's **Kenyan PIN** when the "PIN required" switch is on. Each item is **PASS / CAUTION / REVIEW**, shown green / yellow / red with a plain reason; the officer makes the final call. **Governing rule: a wrong PASS is worse than a REVIEW.** Python 3.13, PySide6, RapidOCR (CPU), 8 GB RAM, no network.

## 2. Status at a glance

| Stage | What | State |
|---|---|---|
| OCR module | read each page (measure → prepare → RapidOCR), never crash on a bad page | built, measured, proven |
| Stage A | window, file list, viewer, OCR text, errors, background OCR, cache, read-ahead | **built, confirmed** |
| Stage B | live search (date, PIN, amount), highlights, continuous scroll | **built, confirmed (2026-09-23)** |
| **Stage C** | **claim sheet (Excel / PDF / scanned) checked against the receipts; status strip; coloured sheet; Auto / Manual tour** | **built 2026-09-24 (C1 + C2 + C3) — the user asked for the complete stage; awaiting the user's check by eye** |
| Stage D | officer sign-off per amount (D2, D3), final layout | after the user confirms C |

Health command: **`run_tests.bat`** — **181 tests, all passing** at the end of this session. `tools/search_criteria_trial/verify_app_matcher.py` — **0 disagreements**. Start the app: **`start_app.bat`**.

## 3. Project map

```
app/                        the application (python -m app)
  errors.py · config_files.py (read_json_config; accepts a str path) · paths.py
  company_pin.py            the company PIN from .env (COMPANY_PINS=…; file/key named in gui_settings.json)
  ocr/                      OcrReader (reader.py); pipeline.py; geometry.py (page_box); image_files.py; rules
  layout/                   OCR segments -> printed rows (rows.py, row_rules.json)
  matching/                 finding a value on a page (search.py, amount/date/pin_search.py, money.py, …);
                            + amount_texts, make_hit (search.py), pin_matches, is_pin_shaped (pin_search.py)
  claims/                   READING a claim sheet (claim_rules.json): excel.py (openpyxl, read-only) ·
                            pdf_text.py (text layer + drawn lines) · pictures.py + image_grid.py (scanned: lines found
                            in the picture, OCR words placed in them) · table_grid.py · layout.py (header row holding
                            Date + expense names; header block of codes skipped; Total row or a sums row) ·
                            amounts.py (exact cents) · sheet_dates.py (rule R10u) · sheet_builder.py · reader.py
                            (read_claim_file, sheet_kind, looks_like_claim_sheet — loaded lazily) · model.py
  checking/                 THE DECISION PACKAGE for Stage C (checking_rules.json; imports no OCR/image/GUI code):
                            labels.py · page_facts.py (total marks A4m+, other buyer, whole parts, fingerprints) ·
                            repeats.py (text + moment, indexed) · receipts.py (ReceiptFacts: PIN scan, repeats, amount
                            index) · findings.py · assignment.py (two passes, consumption, red double claim, date
                            settled by the receipt, guard) · verdict.py (status, colour, reason, nearest miss) ·
                            totals.py · engine.py (analyse_receipts, find_all, decide, check_claim) · model.py
  gui/                      main_window.py (layout + wiring) · claim_session.py (slots, reading the sheet, running the
                            checks when the receipts are fully read) · sheet_grid.py + sheet_model.py + frozen_table.py
                            (the coloured sheet, date column frozen, tabs, reason line, grand totals) · status_strip.py ·
                            tour.py · file_panel.py (+ slots, right-click "Use as claim sheet / receipts") ·
                            document_session.py (+ request_reading, document_done) · search_controller.py
                            (+ prepared_pages) · the Stage A/B panes · settings.py + gui_settings.json
tests/                      unittest, synthetic data only: fakes.py (FakeReader), claim_fixtures.py (the claim-form
                            template as Excel or ruled PDF), test_claims, test_checking, test_claim_window, …
tools/                      PROTOTYPES / MEASUREMENTS: ocr_resolution_trial · search_criteria_trial (+ cents_rule.py,
                            verify_app_matcher.py) · date_parsing_trial · duplicate_pages_trial · total_anchor_trial ·
                            stage_c_timing · stage_c_dryrun (checking prototype) · stage_c_acceptance (the real
                            claims through the application — run it after any change to app/claims or app/checking)
Ignored by git: images/, private/ (every tools/*/private/: answer keys, real pairings), outputs/, .venv/, .env
```

## 4. How a claim flows through the code

1. The officer clicks an Excel file (or a text-PDF claim sheet) → **Claim sheet** slot; right-click → "Use as claim sheet" for a scanned one (read by OCR in the background via `document_session.request_reading`). `app/claims` reads it: a grid per tab/page → header, columns, data rows, Total → ClaimSheet with its items, dates by R10u.
2. The officer clicks the receipts PDF → **Receipts** slot, opened in the viewer, read by OCR as in Stage A/B.
3. When **every receipt page has a reading** (failed pages count, and are reported), `ClaimSession.run`: `search.prepared_pages()` → `analyse_receipts` (PIN scan, repeated pages, amount index, total marks) → `find_all` (each item on the pages holding its amount) → `decide` (pairing, verdicts, totals, statuses).
4. The window colours the amounts, fills the status strip and grand totals, and the tour (if auto-start) walks every amount; clicking one shows its page and highlights; the PIN switch re-runs only `decide`.

## 5. What was built this session (Stage C)

C1 reading claim sheets (Excel tabs, text PDFs, scanned sheets) · C2 the checking (every rule measured first) · C3 the window: file slots, small status strip (Verification / PIN / Repeated pages, PIN switch, Auto, Next to check), claim-sheet grid (tabs for several sheets, date column frozen, zero rows hidden, amounts coloured, reason line, Grand totals 1 and 2), OCR text / Search as tabs in a smaller bottom slot, the Auto / Manual tour (Space, N), Excel in the file list.

**Verified:** 181 tests (61 new: claims 21, checking 21, window 18 incl. every new failure path — broken workbook, broken rules, checking crash reported once without values, unreadable receipt page, no PIN file, nothing checked before every page is read — plus config and settings). Real claims through the application (`tools/stage_c_acceptance/`): Week1 6 green / 3 yellow, Week2 5 / 1 (Excel tab = PDF export), July 18 / 11 (text sheet = scanned sheet), wrong pair 0 / 6; every yellow checked genuine against the answer keys; stress cases as designed. Real window with real OCR on Week2: 6 pages read in ~63 s, then checked (same results); the scanned July sheet read through the app's own OCR (29 items). **Two real bugs found by the real run and fixed:** the claim was checked the instant the receipts were opened (before any page was read); the Date column scrolled out of view.

## 6. Measurements and trials — do not repeat

- **OCR:** RapidOCR defaults (every alternative measured). ≈ 10–14 s per page.
- **Search rules** (65 real pages): amount 326/333, 0 false of 12,633; date 80/81; PIN 83/83.
- **Claim-sheet dates** (4,000 sheets, 50,282 dates, checks 0–365 days late): **R10u** 99.67% correct, 2 wrong, 0.33% to the officer; the owner's methods as described 742 wrong; all 65 real dates right.
- **Cents dropped:** 24/24 fabricated, 127/131 real; the date is always required.
- **Repeated pages** (measured one document at a time): text + moment 9/15 re-captures, 0 wrong; reference numbers rejected (a shop's own numbers); invoice numbers rejected.
- **Total anchor A4m+** (through the app's finder, the owner's claims): 31/31 claimed amounts kept; cash tendered, change, tax lines, before-discount refused (no anchor: 22/22 larger amounts pass); still accepted: telebirr "Total Paid Amount" (transfer + fee). Buyer-PIN check: 0 wrong flags on 71 pages.
- **Timing:** everything after OCR well under a second for a 26-page claim (amount index; checking 27 ms); Excel 20–75 ms.
- **Two measurement flaws of this session, both corrected:** the repeat trial counted "rare" across all files instead of per document; the anchor trial accepted amounts it could not locate (telebirr's cent-less amounts). Lesson: measure through the application's own code.

## 7. Decisions in force (details: decisions.md)

D13 PASS / CAUTION / REVIEW (green / yellow / red) · D15 search rules · D16 faded decimal = CAUTION · D17 one receipt per page · D18 highlights · D19 whole-document search · D20 cache · D21 OCR settings · D22 hiding OCR time decided last · **D23** Kenyan PIN in `.env` + "PIN required" switch set by a scan · **D24** every non-zero expense amount is an item; receipt numbers ignored; no sheet-side duplicate check · **D25** reading Excel / PDF / scanned sheets · **D26** dates R10u · **D27** cents dropped, never upward, two passes · **D28** a paired page leaves every later search; amount index · **D29** repeated pages: text + moment; green / yellow / red, both amounts red on a double claim · **D30** colours, status strip, grand totals; claim sheet and receipts always separate files for now · **D31** Auto / Manual tour · **D32** layout · **D33** total anchor A4m+ and buyer-PIN CAUTION (done); officer sign-off next stage; repeats across claims later.

## 8. Environment, files and repository

- Windows 10, 4 cores, screen 1280×680 at 150 %. Python 3.13.4 in `.venv`; PySide6-Essentials 6.11.2, rapidocr 3.9.2, onnxruntime 1.30.0, pymupdf 1.28.2, openpyxl 3.1.5, opencv-python 5.0 — **no new library was added in Stage C**.
- `images/` (git-ignored): the real pairs — `Cash expenses Claim Form - Week 2 (…).xlsx` tab **Week1** ↔ `expense_claim_form-week 1-(…).pdf`, tab **Week2 ** (saved last) ↔ `cash expense claim form-week-.PDF` (and its identical copy); `_Cash expenses Claim Form - Week 2 (…).pdf` = the Week2 tab exported (text layer); `… Cash expenses Claim july_pdf.pdf` (text) and `excel _example_sample.pdf` (scanned) ↔ `reciept for july (002).pdf`; `Cash expenses claim-July-EA-2026.pdf` (text; 16 daily allowances, no receipts); `Receipts Week 2 (…).pdf` = another claim (wrong-pair test). Real names appear inside: never into committed files, logs or errors.
- The private answer keys and saved readings use the files' **old names** (the tools map them in their `private/` configs).
- **Git:** branch `backend`; pushed through `5c460e0`. **Everything of Stage C is uncommitted** (app/claims, app/checking, the new GUI files, tests, tools, docs). Commit and push only when the user asks; never force; privacy sweep on staged files first. `.env` and every `private/` folder are ignored (checked).

---

## 9. Next: the owner's check by eye, then Stage D

**Ask the user to try it** (start_app.bat): click the Week2 Excel file (Claim sheet slot), then `cash expense claim form-week-.PDF` (Receipts); wait for the reading (~1 min for 6 pages); look at: the colours (5 green, 330 yellow), the reason line under the sheet, the status strip, the grand totals, the PIN switch (flip it), Auto / Next to check / clicking an amount (the page comes into view with highlights), the Week1 tab (dates read as 3–9 Aug; 2 receipts without the company PIN → yellow). Then the July text sheet with the July receipts (26 pages, ~6 min): 18 green / 11 yellow.

**Known limits to mention (blueprint §13):** a scanned claim sheet waits for the receipts being read (one OCR engine); a receipt layout never seen may print its total under a label not listed → yellow "not printed as the receipt's total" (add the label to `checking_rules.json` after checking); 6 of 15 re-captured receipts are not detected as repeats; the total-anchor and buyer-PIN measurements rest on a small sample (3 claims); a page listing several claims inside the receipts is not guarded (separate files for now, D30).

**Then Stage D** (after the user confirms C): the officer's own sign-off per amount (D2, D3) — so Verification can turn green after a manual check; a report / export; the final layout. Later: repeats across claims (stored one-way fingerprints); card / statement matching; hiding OCR time before the app opens (with persistence).

## 10. Standing rules (CLAUDE.md — both marked crucial)

One job per file; public entry points in `__init__.py`; config beside the code that reads it. Every stage wrapped at one boundary with `StageError`; one bad item never stops a batch; nothing printed; nothing exits. Money is exact `Decimal`. Logs and errors never contain document text, names, amounts or PINs. Only synthetic data in committed files. No new library without saying why. One stage at a time, confirmed by the user before the next. Verify before reporting: real input through the application's own code, every failure path broken on purpose, `run_tests.bat` run and reported.
