# Receipt & Claim Verifier — System Design and Build Plan

Revision: 2026-09-23. Replaces all earlier drafts, including the 22-part phase-checklist blueprint.

Offline, one officer, one Windows 10/11 machine, 8 GB RAM, CPU only. No network at runtime. The only online activity is one-time developer setup (installing libraries, downloading model files) before any claim data touches the machine.

---

## 0. How to read this document

This is a living technical design, not a checklist. Every component carries one of three status labels, and nothing is treated as settled unless it says so:

| Label | Meaning |
|---|---|
| **BUILT** | Real code, run against real input, failure paths deliberately broken and checked. |
| **DESIGNED** | Specified here, agreed, not yet coded. |
| **OPEN** | Not decided. Listed in §10 with the build step it blocks. |

Precedence: `CLAUDE.md` (working rules) → this file (architecture and plan) → `docs/reviews/decisions.md` (binding reasoning, D1–D12). If this file and the decision log disagree, the more recent, more specific statement wins and the older one is corrected in place. `NEXT_SESSION.md` is a pointer, never the record of truth.

Method: **inside-out**. Build the uncertain core first as a directly testable piece, measure it on real files, then build the structure around it. Each stage is confirmed by eye by the person who can judge correctness before the next stage is added.

---

## 1. Purpose, governing rule, scope

**Problem.** A finance officer receives an expense claim: an Excel sheet of claimed lines and a PDF of receipts. Today every receipt is checked by eye. The system does the reading and cross-checking and hands the officer a short exception list.

**Governing rule — never traded for convenience:**

> A wrong CONFIRMED is worse than an honest UNDECIDED. When evidence is weak, missing or in conflict, the system says so and the officer decides.

**Definition of a pass (CONFIRMED)** for one claim row: on one and the same receipt page, the system finds (1) the exact claimed date, (2) the exact claimed amount, and (3) the company's own tax PIN. Invoice number is not required (no such column in the current Excel form; D7 corrected accordingly). See §10, Q1: the amount rule currently has a safety gap that must be closed before passes are shown to the officer.

**Non-goals:**
- No network use at runtime, no cloud, no telemetry, no auto-update.
- No handwriting recognition. No fraud or authenticity detection — the tool checks consistency, not genuineness.
- No VAT checking.
- No QR/barcode reading (dropped).
- No behaviour that depends on document type. Till slip, hotel invoice, mobile-money screenshot and card slip are processed identically.
- No guessing on unrecognised files — refuse and report.
- One officer, one machine. No server, no shared install.

---

## 2. Fixed decisions

Do not re-open without a stated reason recorded in `decisions.md`.

| Topic | Decision |
|---|---|
| OCR engine | RapidOCR only (Paddle detection + recognition models on ONNX Runtime, CPU). Tesseract was built, measured and dropped: never more accurate, ~2× time. |
| Safety mechanism | Closed exact search + mandatory human disposition + aggregate arithmetic check (§3.1). Not multi-engine agreement. |
| Value matching | Always exact after normalisation. Never fuzzy. |
| Label matching | May tolerate OCR noise. Labels only decide where to look. |
| Country identification | By which of the company's own registered tax IDs is found on the receipt. Never by reading authority names or currency words. |
| Page = receipt | One receipt per PDF page (standing rule; see risk R5). |
| Document type | Never changes behaviour. |
| Caching / persistence | None in the current phase. Every file open re-reads from scratch. |
| GUI | PySide6, single native process. |
| Intake | Folder listing (`images/`) now; email-based intake later. Intake is swappable; nothing downstream depends on it. |
| PINs | Fabricated placeholders until real values are supplied. |
| Money | Exact decimal, never float. One parser. |
| Excel | Mandatory claim source, read by cell. No PDF claim forms. |
| Card/statement matching | Deferred, optional. |
| Test data | Synthetic by default. Real documents only with the officer's permission, on his machine, never committed or uploaded. |

---

## 3. Architecture

### 3.1 Safety model

Earlier drafts relied on two independent OCR engines agreeing. That is gone. Three mechanisms replace it; none is optional.

1. **Closed, deterministic search.** The system never asks "what is the total?". It asks "does this exact claimed amount appear on this receipt?" — one right answer, exact string comparison after normalisation.
2. **Mandatory human disposition.** Each row carries a *system finding* and an *officer disposition* as two separate fields, never merged. A pass is a recommendation; a flag is a prompt. The claim cannot be closed until every row has a disposition.
3. **Aggregate arithmetic check.** Sum of each accepted receipt's own declared total vs. the Excel's stated grand total. Independent of any single field reading.

Cost of this trade: no second engine can catch a misreading. Mitigation is generous abstention and the officer's review (§11).

### 3.2 Pipeline

```
 INTAKE            OCR (per page)             MATCH (per row)              REVIEW
 ---------         -------------------        ----------------------       -------------------
 folder list  -->  analyse -> advise   -->    normalise claimed values --> system finding
 (email later)     -> apply -> read           exact search: date, amount   + officer disposition
 Excel parse       Words + boxes              -> PIN on same page          aggregate check
                   OcrStageError per page     highlight selection          error tab
```

### 3.3 Module map

| Module | Job | Status |
|---|---|---|
| OCR + image preparation | Measure page, apply only needed processing, read with RapidOCR | **BUILT** (`tools/ocr_smoke/ocr_compare.py`, `enhance_rules.json`) |
| Error type | `OcrStageError` shape, reused by every module | **BUILT** |
| GUI shell | Three panes, file list, page viewer, OCR panel, error tab | **DESIGNED** — Step 1, active |
| Money & date parsing | Printed form ↔ exact value; claimed value → all printed forms | **DESIGNED** |
| Matcher | Normalise, exact search, segment joining, PIN search, highlight selection | **DESIGNED** |
| Excel parser | Claim rows + grand total, formula and stored values | **DESIGNED** |
| Row status + aggregate | System finding, disposition, reconciliation | **DESIGNED** |
| Config loader | Company, country, keywords, thresholds; refuse to start on invalid config | **DESIGNED** |
| Coordinate mapping | OCR-image box → original PDF page coordinates | **DESIGNED** (data already stored in the enhancement plan) |
| Persistence | Encrypted case store | Deferred (§6.8) |
| Duplicates (D8) | Cross-receipt and cross-claim fingerprint | **OPEN** (§10) |
| Statement matching | Card claims vs. statement debits | Deferred |

### 3.4 Engineering rules (from `CLAUDE.md`, both marked crucial)

**File organisation.** One job per file. A processing module does not parse arguments or write reports. Config lives in its own file beside the code that reads it. A fix stays inside the file it concerns.

**Error handling.** The machine cannot be debugged live; a screenshot of the error tab is the whole diagnostic session.
- Every stage that can fail is wrapped at one boundary and yields a structured error: stage name, plain description, file/page/row context, wrapped traceback (`.summary`, `.full_text`).
- One bad page, row or file never stops a batch; the error attaches to that item.
- No `print`, no process exit on recoverable errors. Callers decide presentation — ultimately the error tab.
- Logs and errors carry IDs and codes, never document text, names, amounts or PINs.

**Verification standard.** Nothing is reported working until it has run on real input and each new failure path has been deliberately triggered. This found two real bugs in the OCR module that code reading missed.

**Dependencies.** Every new library is added to `requirements.in` with a written reason, then locked with exact versions.

---

## 4. End-to-end flow (target behaviour, Stage D)

1. Officer opens the app. Left pane lists PDFs and Excel files in the working folder.
2. Clicking a PDF runs OCR on every page, one at a time (§6.1), with progress shown. Minutes for a real claim.
3. Clicking an Excel file loads claim rows (receipt-number hint, date, amount) and the declared grand total.
4. Clicking a different file of the same kind asks "current data will be lost — continue?". Confirm discards that side's in-memory state entirely. PDF side and Excel side are independent.
5. Selecting a row drives the search: start at the page the receipt-number hint points to; look for exact date and exact amount; if not both there, search all other pages. On the page holding both, search for the company PIN.
6. The row gets a system finding: **pass**, **caution** or **needs review** (§6.4 rules).
7. Each accepted receipt contributes its own declared total to a running sum, compared against the Excel grand total at claim level.
8. Officer reviews with Verify / Decline, acting on the open page and writing the disposition to the row matched to it. A separate PDF-side Next/Previous browses pages without triggering search (orphans, corrections).
9. Claim-level "verify all" stays locked until every row has a disposition.
10. Any failure becomes one entry in the error tab. Nothing crashes the session.

---

## 5. Data model

Smaller than earlier drafts. The Observation/Candidate/Evidence machinery existed to reconcile several OCR channels; with one engine and closed search it is retired, along with QR records, per-document-type keyword records and invoice-number matching fields.

| Record | Fields |
|---|---|
| SourceFile | id, name, content hash, page count, accepted/refused + reason |
| ReceiptPage | file, page number, applied enhancement plan (crop offset, rotation, scale), list of Word, errors/warnings |
| Word | text, confidence, box in read-image coordinates |
| ClaimRow | row number, receipt-number hint, claimed date, claimed amount, invoice number (display only) |
| MatchResult | matched page or none; date found + where; amount found + where; PIN found + where + label side; candidate pages if ambiguous |
| RowStatus | system finding (pass / caution / needs review + reason) **and** officer disposition (none / verified / declined + reason + timestamp). Never merged. Displayed colour follows the disposition once it exists. |
| ClaimAggregate | sum of accepted declared totals, Excel grand total, reconciles yes/no/undecided |
| CountryIdentification | matched company tax ID → country → expected currency |
| ErrorEntry | `.summary`, `.full_text` |

---

## 6. Component specifications

### 6.1 OCR and image preparation — BUILT

Files: `tools/ocr_smoke/ocr_compare.py`, `tools/ocr_smoke/enhance_rules.json`. Entry point: `process_page`.

Per page:
1. **Analyse** — ink/paper brightness (local to the ink), text contrast, ink-weighted character height, tilt, lighting variation, background grain, edge sharpness.
2. **Advise** — decide which steps this page needs and at what strength, targeted at what RapidOCR will do with the image. Engine limits (max-side shrink, fixed recognition line height) are read from the running engine, so no upscale is proposed that the engine will undo, and cropping is advised only when it reduces the engine's own shrink factor.
3. **Apply** — only the advised steps.
4. **Read** — RapidOCR.

Measured result: of eight candidate steps, three kept — uneven-lighting correction on photographed non-white paper, shrink-reducing crop, deskew. Five (contrast stretch, denoise, brighten, enlarge, binarise) never helped or hurt; disabled by threshold in config, not deleted.

Failure behaviour: analyse/advise/apply failure → page read as-is, recorded as a warning. OCR engine failure → error, page has no words. One page never stops the document.

### 6.2 GUI — DESIGNED, Step 1 active

PySide6. Reasons: `QGraphicsView`/`QGraphicsScene` fits "rendered page + exact highlight boxes"; one native process means one set of tracebacks; ready table widget for the Excel browser. Cost: ~100–200 MB one-time install.

Target layout (Stage D):
```
+-----------+-------------------------+---------------------------+
| FILES     |   RECEIPT PAGE          |   CLAIM ROWS (Excel)      |
| (hidable) |   highlights on match   |   colour = row status     |
| PDFs      |                         |   Next / Prev row         |
| Excel     |   Prev / Next page      |   (drives search)         |
|           |   Verify / Decline      |                           |
+-----------+-------------------------+---------------------------+
| ERROR TAB: newest first, one line each, expandable to traceback |
+-----------------------------------------------------------------+
```

- Two independent navigation sets: row Next/Prev (triggers search, moves page) and page Next/Prev (no search).
- Verify/Decline act on the open page and update the disposition of the row matched to it.
- Row status is shown on the Excel side, because status belongs to a claim line, not a page.
- Highlight: only an exact match, plus up to two neighbouring segments each side (direction OPEN, Q3). No match → no highlight.

Staged build (§7, Steps 1–4): A shell with OCR panel → B live search on typed values → C Excel row drives search, OCR panel still visible → D final layout, OCR panel removed, review workflow on.

### 6.3 Money and dates — DESIGNED

**Money parser** (one function, exact decimal + currency):
- Currency word/symbol before, after, or absent.
- Thousands mark: comma, dot, space, apostrophe. Decimal mark: point or comma. Rule: two digits after the last mark → decimals; three → thousands.
- `/=`, `/-`, `=/` endings → no cents.
- Brackets or trailing minus → negative.
- Genuinely ambiguous separators → "cannot parse", never a guess (a guessed separator is a 100× error).

**Claimed-value expansion** (for search): each claimed amount is expanded into every plausible printed form (with/without thousands marks, with/without decimals, with `/=`). Each claimed date is expanded using the country's date order (day-first so far) and its month-name table from config.

**Excel lesson carried from the original sample:** a value displayed as `30.00` was stored as `30,000`. Always read cell values, and where a cell holds a formula, read both formula and stored value and flag any disagreement.

### 6.4 Matcher — DESIGNED, Step 2

Standalone, tested module. Stage B and Stage C use it unchanged; only the input source changes (typed fields → selected Excel row). No throwaway version.

1. **Segment joining.** RapidOCR splits values (`12,542` | `.00`). Join adjacent segments on the same printed row before comparison, as well as checking single segments.
2. **Exact search** of expanded date and amount forms over page text.
3. **Page selection.** Hint page first; else all pages. Exactly one page with both date and amount → candidate. More than one → needs review (ambiguous), listing the pages. None → needs review.
4. **PIN search** on the selected page only: closed search for each company tax ID. OCR position correction allowed only where the country's ID pattern forbids a character (letter in a digit slot); otherwise exact.
5. **Label side.** A PIN found only beside a seller-side label (`supplier`, `vendor`, `issued by`, config list) → caution.
6. **Country/currency.** Matched ID determines country and expected currency. Printed currency different from expected → caution.
7. **Declared total** (for the aggregate check): global total-keyword list, label match fuzzy-tolerant, value parsed exactly. Anchor rule OPEN (Q1).
8. **Highlight selection:** matched segments + neighbours (Q3).

**Row finding rules:**

| Finding | Condition |
|---|---|
| pass | date + amount + PIN exact on one page, PIN not supplier-only, currency consistent, *and Q1 satisfied* |
| caution | PIN found but wrong, or supplier-only, or currency mismatch |
| needs review | date or amount missing; several candidate pages; no PIN; unreadable page; any error during the row |

### 6.5 Excel parser — DESIGNED, Step 3

- Row shape: receipt-number hint, date, amount, plus a claim-level grand-total field. Later: employee name → PIN lookup.
- Built against a synthetic fixture now; adjust when a real sample arrives (none supplied yet).
- Layout described in config (which sheet, which columns, where the grand total sits). Unmatched layout → refuse with a structured error.
- Receipt hint parsing: `6,7,no`, `8,9,10`, `NA`, `-`, blank → list of page hints plus explicit no-receipt markers.
- Dates parsed with the country date order; ambiguous → flagged, never guessed.
- Sum checks that need no OCR (row totals, column totals, grand total, balance = total − advance where present) run here, as independent verdicts.

### 6.6 Aggregate check — DESIGNED, Step 4

Sum of declared totals of accepted receipts vs. Excel grand total. Reported at claim level only, never folded into any row's status. Blocked by Q1.

### 6.7 Configuration — DESIGNED

All in files, never inline; each threshold carries the evidence for its current value (pattern set by `enhance_rules.json`). Loader validates everything and refuses to start on an invalid file.

| File | Contents |
|---|---|
| Company | legal name; map country → company tax ID (D5: one ID per country — confirm); default country |
| Country profile (×6) | currency code/symbols/words, decimal places, date order, month names, tax-ID character pattern, `validated: true/false` |
| Keywords | one global total-keyword list; seller-side label list |
| Thresholds | all numeric cutoffs with evidence notes |
| Excel layout | column/cell mapping per known form |

Countries: Kenya (validated pattern: letter + 9 digits + letter), Ethiopia, Uganda, Tanzania, Rwanda, Burundi (unvalidated). A wrong pattern must produce an unmatched search, never a pass.

### 6.8 Storage — deferred

Now: nothing persisted. All state in memory for the open PDF/Excel pair; discarded on switch or close. Rationale: the "you will lose data" prompt stays literally true, and caching is premature while the review flow still changes.

Later (when resumable sessions or an audit trail are wanted): encrypted SQLite (SQLCipher; fallback plain SQLite in an encrypted folder) in `case_data/`, separate from `images/`. Any OCR cache keyed by file hash **and** rules version, so a stale result is never served as current.

---

## 7. Build plan

Each step: goal, deliverables, exit check. A step starts only when the previous exit check has been confirmed by eye.

| Step | Goal | Status |
|---|---|---|
| 0 | OCR core | **Done** |
| 1 | GUI Stage A — shell + OCR panel | **Active** |
| 2 | Matcher + GUI Stage B | Next |
| 3 | Excel parser + GUI Stage C | — |
| 4 | Row status, aggregate, GUI Stage D (review) | — |
| 5 | Measurement and hardening | — |
| 6 | Packaging and safe use | — |
| Later | Email intake, persistence, duplicates, statements | Deferred |

### Step 1 — GUI Stage A (active)

**Deliverables**
- `PySide6` added to `requirements.in` with reason; lock file updated.
- Left pane: hidable list of PDF and Excel files in `images/`.
- Middle pane: rendered current PDF page.
- Right-upper: OCR reading of the current page, grouped into readable rows (not a flat dump), scrollable.
- Right-lower: three inputs (keyword/date, PIN, amount) + Search button — present, inert.
- PDF Next/Previous (no search).
- "You will lose data" confirmation when switching to another PDF.
- Error tab: every `OcrStageError` of the session, one line each, expandable to full traceback.
- OCR runs in a worker thread with progress; the window never freezes.

**Must not exist, not even disabled:** Excel-row navigation, Verify/Decline.

**Exit check:** selecting a real PDF runs `process_page` on every page; the officer-side reader compares the OCR panel against the page by eye for each page; a deliberately broken page appears in the error tab without stopping the rest; switching PDFs shows the prompt and fully resets state.

### Step 2 — Matcher module + GUI Stage B

**Deliverables:** money parser, claimed-value expansion, segment joining, exact search, PIN search with label side, highlight selection — as one standalone tested module; unit tests including near-misses (one look-alike digit, moved decimal, PIN one character off, PIN supplier-only). GUI: search fields wired; result highlighted on the page via coordinate mapping (read-image box → PDF page).

**Exit check:** on real pages, typed exact values are found and highlighted in the right place; every near-miss produces no match; a broken input yields a structured error, not a crash.

**Blocked by:** Q3 (highlight direction) for highlight only; the search itself is not blocked.

### Step 3 — Excel parser + GUI Stage C

**Deliverables:** synthetic Excel fixture; parser (§6.5) with formula/stored-value comparison and OCR-free sum checks; config loader for company, country and layout files. GUI: typed fields replaced by a row navigator; selecting a row runs the unchanged matcher; OCR panel stays visible.

**Exit check:** stepping through rows, the right page opens, the right values are highlighted, and the OCR panel confirms it; every planted sum fault in the fixture is flagged.

**Blocked by:** a real Excel sample, for final layout adjustment only.

### Step 4 — Review workflow, GUI Stage D

**Deliverables:** RowStatus with separate finding and disposition; colour-coded rows; Verify/Decline with required short reason; claim-level "verify all" locked until every row has a disposition; aggregate check; OCR panel removed.

**Exit check:** a person who did not build the tool processes a synthetic claim end to end; every override is recorded with reason and time; the aggregate reconciles or is flagged.

**Blocked by:** Q1 (total anchor / pass rule) — hard blocker; Q4 (PDF–Excel mismatch warning) — should be answered.

### Step 5 — Measurement and hardening

**Deliverables:** synthetic corpus with truth files and planted faults (amount digit change, look-alike swap, moved separator, PIN off by one, PIN supplier-only, missing receipt, extra receipt, two receipts with equal amount and date, day/month swap, unreadable page, corrupt file); a separate locked test set, run once; degradation curve (blur, downscale, rotation, compression, fade). Shadow mode on a few real claims with written permission.

**Exit check:** zero silent wrong passes on the locked set, reported with its honest bound (0 errors in N cases → true rate likely below ≈3/N); needs-review rises with damage while wrong passes stay at zero.

### Step 6 — Packaging and safe use

**Deliverables:** one-folder bundle (PyInstaller or Nuitka, whichever runs cleanly), models bundled via a resource-path helper; version number in window title and every report; firewall outbound block; no update code; one-page user guide and recovery guide.

**Exit check:** bundle runs on a clean Windows machine, standard user, network off, verified with a network monitor.

**Safe-use conditions before real use:** officer confirms company policy allows this on a personal computer (his responsibility, stated plainly); BitLocker on or the risk recorded; no real document ever committed, uploaded, or pasted into any online tool.

### Later

- **Email intake** replaces the folder list: emails expandable to attached PDF and Excel. Intake layer only.
- **Persistence** (§6.8).
- **Duplicate detection** (D8), after Q5.
- **Card/statement matching**, if ever wanted.

---

## 8. Testing standard (all steps)

- Unit tests per module; one health command runs lint, type check and tests.
- Near-miss tests are mandatory for every value-matching function: nothing close-but-wrong may match.
- Failure paths are triggered deliberately, not reasoned about.
- Synthetic results are reported as synthetic, never as real-world accuracy.
- Tune on the development set only; run the locked test set once.

---

## 9. Error handling — summary

Every module uses the `OcrStageError` shape. One boundary per stage. Batch never stops on one item. No console output, no exit. Error tab is the single diagnostic channel. No document content in any log or error text.

---

## 10. Open questions

Each has the step it blocks and a proposed default, to be accepted or replaced.

| # | Question | Blocks | Proposed default |
|---|---|---|---|
| Q1 | **What anchors "the total", and must the matched amount be it?** Currently a pass needs the claimed amount to appear *anywhere* on the page. A line item, subtotal or tendered cash equal to the claim would pass a receipt whose real total is larger. | Step 4 (hard) | Pass requires the matched amount to be the page's declared total: the amount beside the strongest total keyword, lowest such occurrence on the page. Amount found but not anchored → needs review. |
| Q2 | Date/country order dependency: dates are expanded with the country's date order, but the country is known only after the PIN is found on the date-matched page. | Step 2 | Expand dates with the union of all configured country formats (all day-first today), or take country from the claim. Revisit if any month-first country is added. |
| Q3 | Highlight neighbours: same printed row only, or any direction? | Step 2 (highlight) | Same printed row only. |
| Q4 | Warn when the loaded PDF and Excel do not obviously belong to the same claim? | Step 4 | Warn if fewer than half of rows find any candidate page. |
| Q5 | How duplicate detection (D8) fits single-engine closed matching. | Later | Fingerprint = file hash + (company-ID match, date, declared total) per page; flag, never block. |
| Q6 | One tax ID per country of registration (D5) — true for the company? | Step 3 | Confirm with the officer. |
| Q7 | Card/statement matching — ever built? | Later | No, unless requested. |

---

## 11. Risks and limits

| # | Risk | Mitigation |
|---|---|---|
| R1 | Silent wrong pass — the risk that matters most. | Exact closed search, Q1 fix, mandatory disposition, aggregate check, locked-set measurement. |
| R2 | Single-engine OCR: no second reading to catch a shared misread. | Exact values only; misreads produce no match (needs review), not a wrong pass. |
| R3 | Automation bias: officer rubber-stamps passes. | Pass is a recommendation; consider a random sample of passes shown for spot-check (later). |
| R4 | Five of six countries' ID patterns unvalidated. | Marked in config and report; pattern used only for positional correction. |
| R5 | "One receipt per page" is false in practice (the original sample had two receipts side by side; multi-page hotel invoices exist). | Two receipts on a page → amount/date from one, PIN from the other could combine into a false pass. Detect multiple total keywords / date blocks per page → needs review. Revisit the rule with real samples. |
| R6 | No caching: full OCR on every open, minutes per claim. | Accepted for now; persistence later (§6.8). |
| R7 | Synthetic data flatters accuracy. | Shadow mode on real claims before reliance. |
| R8 | Library updates silently change results. | Locked versions; regression fixtures. |
| R9 | Company data on a personal machine. | Officer's policy confirmation, encryption, offline, no real data in development. |

---

## 12. Repository layout

Current (real):
```
CLAUDE.md
NEXT_SESSION.md
docs/blueprint.md
docs/reviews/decisions.md
requirements.in / lock file
images/                      # working folder (placeholder intake)
tools/ocr_smoke/ocr_compare.py
tools/ocr_smoke/enhance_rules.json
```

Proposed, created only when a step needs it:
```
app/gui/            # Step 1 — PySide6 windows, no business logic
app/matching/       # Step 2 — matcher, money/date parsing
app/claim/          # Step 3 — Excel parser, sum checks
app/config/         # Step 3 — loader + company/country/keyword/threshold files
app/review/         # Step 4 — row status, aggregate
tests/              # per module, plus synthetic fixtures
case_data/          # later, persistence only
```

---

## 13. Glossary

| Term | Meaning |
|---|---|
| Closed search | Looking for a known value, rather than reading an unknown one. |
| Normalisation | Expanding a claimed value into every printed form it could take, before exact comparison. |
| System finding | pass / caution / needs review, computed by the tool. |
| Disposition | The officer's verified / declined decision with reason. |
| Declared total | The total a receipt itself states, used only for the aggregate check (and, per Q1, for the pass rule). |
| Silent wrong pass | A pass on a row that is actually wrong. The number to keep at zero. |
| Locked test set | Synthetic claims never used for tuning, run once. |
| Shadow mode | Running the tool beside manual checking, without relying on it. |
