# Receipt & Claim Verifier — System Design

Offline, single-officer, single-machine. Windows, 8 GB RAM, CPU only, no graphics card. No network at runtime — the one exception is one-time setup (installing libraries, downloading model files), done once by the developer, online, before any claim data ever touches the machine.

## 0. What this document is, and why it looks different from before

Earlier drafts of this document were a full specification written before any of the system existed: every phase, every record, every config file, a twelve-phase task checklist with tick boxes, all fixed on paper first and built to match afterward. That produced a thorough document and a large amount of specification that then had to be revised repeatedly as real testing overturned things the paper design had assumed — how RapidOCR actually resizes an image before reading it, whether a second OCR engine was worth its cost, whether QR codes on real receipts would even be usable, how a PIN check would really need to work once a real photographed receipt was in front of it.

The project has since moved to building **inside out**: start from the core, uncertain piece — the part that does the actual hard work of reading a receipt and finding a value in it — build it as something directly testable, run it against real files, measure what it actually does, and only then build the structure around it (folders, packages, a health command, a full config loader, the officer-facing screen), informed by what the core turned out to need rather than decided blind. The OCR and image-preparation module described in Part 5 was built and tested this way before a single line of the surrounding application existed, and it changed real decisions — Tesseract was tried and measured against RapidOCR and dropped; several candidate image-enhancement steps were tried and measured and switched off; a coordinate-mapping and error-handling pattern was proven by deliberately breaking it, not by reasoning about it on paper.

This document is now **a technical design of the current architecture, kept honest and current**, not a task list to tick through in a fixed order. It states what exists and is proven, what is designed and ready to build, and what is genuinely still undecided — three different things, kept visibly separate so nothing gets treated as settled by accident. It has no checkboxes. Progress is a fact about the code, not a mark on this page.

`docs/reviews/decisions.md` is the binding decision log: the reasoning behind each call, including the ones this document only states the current conclusion of. Where this document and that log ever disagree, the more recent, more specific statement wins, and the older one gets corrected — never both left standing as if unrelated.

## 1. Purpose and the governing rule

A finance officer receives an expense claim: an Excel spreadsheet listing what is claimed, and a PDF of the receipts that support it. Today the officer checks every receipt by eye. The system does that reading and cross-checking and hands the officer a short list of exceptions — receipts it could not confirm, and why.

**The governing rule, unchanged since the first line of this project and never to be traded away for convenience:**

> A wrong PASS is worse than an honest REVIEW. Whenever evidence is weak, missing, or in conflict, the system says so and the officer decides.

**Status names (user decision, 2026-09-23):** every system finding is one of **PASS**, **CAUTION** or **REVIEW** — never a plain true/false. Earlier drafts and `decisions.md` say CONFIRMED / UNDECIDED; read those as PASS / REVIEW.

**What PASS means, concretely, as currently defined:** for one claimed line, its receipt shows the exact date and exact amount stated in the Excel row, and the company's own tax PIN is found on that same receipt. All three, found and matching, on the same page — a pass. Anything else is not a system decision: it is handed to the officer, who confirms or declines it by hand. This is deliberately simpler than earlier drafts of this rule, which also required an invoice number match; the Excel format in current use carries no invoice number column, so that requirement is dropped for now. See §12 for why this is flagged as an open question rather than a closed one.

**Non-goals**, current and unchanged unless noted: no cloud or network use of any kind at runtime; no handwriting recognition; no guessing at an unrecognised file — it is refused and reported; no fraud or authenticity detection — the system checks that documents are consistent with the claim, not that they are genuine; no VAT checking; one officer, one computer, never a server or a shared installation. Two non-goals are new since earlier drafts: **no QR-code reading** (dropped — see §5), and **no behaviour that depends on what kind of document a receipt is** — a fiscal till slip, a hotel invoice, a mobile-money screenshot and a card slip are all read and checked exactly the same way; nothing in the system branches on document type.

## 2. How the system is organized, and why

Two engineering rules govern every file in this project, stated in full in `CLAUDE.md` and restated here because they shape the architecture directly, not just the code style:

**File organization.** Each file has one job. A processing module does not also parse command-line arguments or write report files — when it did, in an earlier draft of the OCR tool, fixing one concern risked breaking the other, and it was split before it grew further. A fix stays inside the one file it is about. Config — thresholds, keyword lists, per-step rules — lives in its own file next to the code that reads it, never inline, so it can be tuned without a code change.

**Error handling.** This system runs on a machine that cannot be reached for live debugging. A screenshot of an error is the entire diagnostic session. Every stage that can fail is wrapped at one clear boundary and turned into a structured, descriptive error — never a bare traceback, never a silent skip, never a `print`. Processing many items (pages, rows, files) never lets one item's failure stop the rest. Library code never prints to the console and never exits the process on a recoverable error; it raises or returns a structured error and lets the caller — ultimately the GUI's error tab, described in §7 — decide how to show it. The concrete pattern is `StageError` in `app/errors.py` (the OCR module's `OcrStageError` is a subclass of it): one error shape, a one-line `.summary` for a list view, a `.full_text` with the underlying traceback for the expanded view, and file/page context on every instance. Every module built from here on raises `StageError` or a subclass of it rather than inventing its own shape.

**The safety architecture itself has changed, and this is worth stating plainly rather than leaving it implicit.** Earlier drafts leaned on *two independent OCR engines agreeing* as the mechanism that turned noisy pixel-reading into a trustworthy decision. That mechanism is gone: Tesseract was measured against RapidOCR and dropped (§5), and QR-code evidence was dropped before it was ever built. What replaces it is three things, none of them optional, working together:

1. **Closed, deterministic search.** The system never asks "what does this receipt say the total is?" — an open question with a fuzzy, guessable answer. It asks "does the exact amount from the Excel row appear on this receipt?" — a closed question with one right answer, checked by exact string comparison after normalisation, never by a fuzzy or approximate match on any value that gets compared to the claim.
2. **Mandatory human disposition.** Every row's system-computed status and the officer's own decision are two separate fields, always both recorded, never merged. The system's pass is a recommendation; the officer can decline it. Its flag is a prompt; the officer can clear it by hand. Nothing is final until a person has, at minimum, had the chance to say so.
3. **An arithmetic cross-check independent of any single reading.** The sum of what each accepted receipt itself declares as its total is compared against the claim's own stated grand total — a check that does not depend on OCR being right about any one field, only on the numbers reconciling in aggregate.

This is a real trade, not a free improvement, and §13 names its cost honestly.

## 3. End-to-end flow

1. The officer opens the application. The left panel lists every PDF and Excel file present in the working folder. **This is a deliberate placeholder for now, not the intended end state**: the plan is for claims to eventually arrive by email, with the left panel listing incoming emails — each expandable to its attached PDF and Excel files — rather than browsing a folder at all. That change affects intake only; nothing described from here on (OCR, matching, review, storage) changes because of it. Building against a folder now, with intake designed so it can be swapped out later, is deliberate — see §0's method.
2. Clicking a PDF loads it and starts OCR: every page is read, one at a time, through the pipeline in §5 (measure the page, decide what processing it needs, apply only that, read it). Pages the application has already read are not read again: every reading is kept in memory until the application closes (§8). The page on screen is read first, and the other files in the folder are read ahead in the background when the engine is otherwise idle.
3. Clicking an Excel file loads it into the right panel: the claim rows appear, each carrying its receipt-number hint, date, and claimed amount, plus the claim's declared grand total.
4. Switching to a different PDF loses nothing and asks nothing: the OCR reading of every file opened (or read ahead) stays in memory until the application closes, and a file only partly read resumes with its missing pages (§8). Closing the application is the one point where readings are lost, and it asks first. *(Changed 2026-09-23 at the user's request; earlier drafts discarded everything on each switch. How switching the Excel file treats validation state is decided when Stage C is built.)*
5. Once a PDF and an Excel file are both loaded, the officer steps through claim rows. Moving to a row is what drives the search, not the other way around, because the values being searched for come from the Excel: the system starts at the page the row's receipt-number hint points to, and looks there first for the row's exact date and exact amount; if either is missing, it searches outward across the rest of the document. Finding both on one page, it then searches that same page's text for the company's own tax PIN.
6. Each row resolves to one of three states: **PASS** (date, amount and PIN all found, on the same page), **CAUTION** (a PIN was found but does not match, or matches only under a clearly supplier-side label), or **REVIEW** (date or amount missing, or found on more than one candidate page with no way to choose between them, or no PIN found at all). §6 gives the exact rules.
7. A receipt accepted as a match to a row contributes its own declared total (found by a total-type keyword search on that page, independent of what value matched the claim) to a running sum for the claim. That sum is compared, at the claim level, against the Excel's own stated grand total — never folded silently into any one row's status.
8. The officer reviews using Verify and Decline, acting on whichever page is currently open in the PDF viewer and updating the Excel row that page is matched to. A pass can be declined; a caution or a needs-review row can be verified by hand after the officer looks at the evidence. A second, independent pair of navigation controls lets the officer browse raw PDF pages freely — for an orphan receipt, or to correct a wrong match — without ever triggering a search.
9. A row is not finished until it carries a disposition: either a clean system pass with no override, or an explicit officer decision. The claim-level "verify all" action stays locked until every row has one.
10. Anything that fails anywhere — a page that will not render, an engine that raises an unexpected error, a row whose search logic hits a case it was not written for — becomes one structured error in the error tab. Nothing crashes the session over one bad page or one bad row.

## 4. The data model

Records are kept deliberately smaller than earlier drafts. The old design's Observation/Candidate/Evidence apparatus existed to reconcile several independent OCR channels against each other; with one engine and a closed search, that reconciliation machinery has nothing left to do and is retired along with it.

**SourceFile** — id, original name, content hash, page count, accepted-or-refused status and reason.

**ReceiptPage** — one per page of a PDF (a receipt and a page are now the same thing, confirmed as a standing rule — no page is assumed to hold more than one receipt). Holds: which file, page number, the enhancement plan that was actually applied to it (§5), and its OCR reading.

**Word** — one OCR-detected text segment: text, confidence, and its box in the coordinates of whichever image was actually read. Mapping that box back to the original PDF page's own coordinates (needed for on-screen highlighting) is not yet built; the enhancement plan stored on the page carries everything needed to do it later — crop offset, rotation, and scale.

**ClaimRow** — from the Excel: row number, the claimant's name (which selects the PIN to search for, §6), receipt-number hint, claimed date, claimed amount. An invoice-number field stays present for display, since the recommended future form carries one, but nothing in matching reads it.

**MatchResult** — per row: which page it matched, if any; whether the date and amount were each found, and where; whether the PIN was found, where, and whether it matched; whether more than one page was a candidate (ambiguous) and which ones.

**RowStatus** — two fields, always both present, never merged into one: the **system finding** (PASS / CAUTION / REVIEW, with a reason), and the **officer disposition** (none yet / verified / declined, with a short typed reason and a timestamp). A row's on-screen colour is read from whichever of the two is authoritative at that moment — the officer's decision once one exists, the system's finding until then.

**ClaimAggregate** — the running sum of accepted receipts' declared totals, the Excel's own stated grand total, and whether they reconcile.

**CountryIdentification** — *not used for now (user decision, 2026-09-23; §6).* Neither the Excel nor the receipts state a country, and the PIN to search for comes from the claimant's name instead.

**ErrorEntry** — the `.summary` and `.full_text` of one `OcrStageError`, as shown in the error tab.

Retired from earlier drafts: the Observation/Candidate/Evidence records and the whole independence-group evaluation order they supported; every QR-related record; the per-document-type keyword-group records (document type no longer changes any behaviour, so nothing needs to be conditioned on it); invoice-number-based matching fields.

## 5. The OCR and image-preparation module — built and proven

This part describes real, tested code (`app/ocr/pipeline.py`, rules in `app/ocr/enhance_rules.json`, public entry point `OcrReader` in `app/ocr/reader.py`), not a plan. It was built and measured under `tools/ocr_smoke/` and moved into the application unchanged when GUI Stage A was built.

**Engine: RapidOCR only** (PaddleOCR's detection and recognition models, run on ONNX Runtime, CPU). Tesseract was built as a second, independent engine and measured against RapidOCR across a real set of test pages: RapidOCR read every page at least as well and several pages markedly better, while running both engines cost roughly double the time per page for no accuracy gain that measurement could find. Tesseract was removed. QR-code reading was designed but never built, and has been dropped from scope entirely.

**The pipeline, run once per page:**

1. **Analyse.** Measure the page: paper and ink brightness (judged against the paper immediately around the ink, not the whole page, so a white margin or a photographed background does not skew the reading), text contrast, character height (weighted by how much ink each mark actually has, so paper texture cannot outvote real letters), tilt, how much the lighting varies across the text, background grain, and edge sharpness.
2. **Advise.** Turn those measurements into a plan: which processing steps this specific page needs, if any, and exactly how strong each should be — aimed squarely at what the OCR engine itself will do with the image, not at making it look nicer. RapidOCR shrinks any image past a configured size before reading it and resizes each detected text line to a fixed height for recognition; the advice reads those limits from the running engine, so an upscale that would just be shrunk straight back is never proposed, and cropping is advised only when it actually changes how much the engine will shrink the page, not merely when there is empty space.
3. **Apply.** Run only the advised steps, with their advised strength. A page that needs nothing is read exactly as it is.
4. **Read.** Pass the result to the engine.

**Of eight candidate processing steps, three survived measurement**, evidence recorded next to each in `enhance_rules.json`: evening out uneven lighting on photographed, non-white paper; cropping when it measurably reduces the engine's own shrink factor; straightening a clear tilt. The other five — contrast stretching, denoising, brightening, enlarging, and converting to black-and-white — either never helped or measurably hurt, and are switched off by their config thresholds, not deleted, so any one can be re-tested the moment real evidence points the other way.

**Failure handling, proven by deliberately breaking each stage, not just reasoned about:** if the analyse/advise/apply stage fails for any reason, the page falls back to being read exactly as it came in, and the failure is recorded as a warning — the page still gets read, and the problem is still visible. Only a failure in the OCR engine itself leaves a page with nothing to show, and that becomes an error, not a warning. One page's failure never stops the rest of a document from being processed.

## 6. Matching and verification logic — designed, not yet built

**Normalising a claimed value before searching for it.** An amount is generated in every plausible printed form (with and without thousands separators, with and without a decimal part, with an East African `/=`-style ending) before the page text is searched; a date is generated using the country profile's date order (day-first, confirmed for the receipts seen so far) plus that country's month-name variants. Since RapidOCR frequently returns a value split across adjacent segments (`12,542` and `.00` as two separate boxes), adjacent segments on the same row are joined before comparison, not only single segments checked in isolation.

**The value search is always exact.** After normalisation, a value either matches character-for-character or it does not; nothing that gets compared against a claimed value is ever fuzzy-matched. This is the one rule the entire safety model in §2 rests on, and it is repeated here for that reason.

**Labels, unlike values, tolerate fuzziness.** Finding the total-type keyword that marks a total is allowed to tolerate OCR noise, spacing, and punctuation — a wrong label only means the wrong number gets looked at twice, never that a wrong number gets accepted as a match.

**The PIN check** is a closed search of the matched page's text for one known PIN: the claimant's. The Excel row gives the person's name; a person-to-PIN table, supplied when the search is run, gives that person's PIN. PINs are not unique to a person — people in the same country share one — but that does not matter to the search, which only asks whether the expected PIN appears. One exact match is sufficient. *(User decision, 2026-09-23, replacing the earlier "search every company tax ID" design; the table's real values are never committed — see `.gitignore`.)* A match found only under a clearly seller-side label (`supplier`, `vendor`, `issued by`, and config-listed equivalents) is a caution rather than a pass — it likely means the company's own sales document was submitted as an expense, not that the check failed outright.

**Country and currency are not used for now** (user decision, 2026-09-23). Neither document states a country, and nothing in the current flow needs one: the PIN comes from the claimant's name, and no currency check runs. The earlier design — country from which company tax ID matched, then a currency cross-check — is set aside, not deleted from `decisions.md` (D4, D5 carry a dated note), so it can be revisited if a currency check is ever wanted.

**The declared-total search**, feeding the aggregate check, is a single, global list of total-type keywords — global rather than per-document-type, because nothing in the system's behaviour is allowed to depend on what kind of document a receipt is. **What exactly anchors "the total" when a page shows several candidate amounts is not yet decided** — whether it should be the largest amount on the page, or the one sitting beside the strongest keyword, or some combination — and needs a decision before this piece is built; see §12.

**Duplicate detection** (matching receipts across a claim, and across claims already reviewed, by a fingerprint of read — not necessarily confirmed — values) was designed in an earlier phase of this project and is carried forward as still-valid in outline, but has not been re-examined against the simplified matching flow described here, and should be before it is built.

**Statement or card-transaction matching** is explicitly deferred: nothing in the current design depends on knowing whether a claim line was paid by card or cash, and building a statement-matching check is optional future work, not part of the core flow.

## 7. The review interface — designed, not yet built

**Technology: PySide6** (Qt for Python; installed as the `PySide6-Essentials` build, which holds every Qt module this interface uses at about half the size). Chosen over a browser-based local app because `QGraphicsView`/`QGraphicsScene` is built for exactly this interface's core interaction — a rendered page image with precise highlight boxes drawn on top of it — and because a single native process keeps the offline error-diagnosis story simple: one set of tracebacks, not a Python-side failure and a separate browser-side one to reconcile. It also has a ready table widget for the eventual Excel browser, and looks professional without extra work, which matters for a tool a non-technical officer uses daily. Cost, stated plainly since it is a new dependency: a heavier install than the alternatives (`pip install PySide6`, on the order of 100–200 MB) — a one-time cost, not a runtime one; the 8 GB budget is spent on OCR, not on an idle window.

**Layout.** Three panes. Left: a hidable list of every PDF, photo/screenshot (JPG, PNG, HEIC — one page each; added 2026-09-23) and, from Stage C, Excel file in the working folder (§3 — a placeholder for the eventual email-based intake). Middle: the currently open receipt page. Right: the currently open claim's Excel rows.

**Build sequence for this interface.** Built inside-out, in stages, each one confirmed by the person who can actually judge correctness before the next is added — not built once, complete, and tested at the end.

- **Stage A — the shell, with a stand-in right panel (built 2026-09-23; awaiting the user's by-eye confirmation).** The right pane is split in two: the upper part shows the OCR reading of the currently open PDF, grouped into readable rows rather than a flat dump, properly scrollable; the lower part holds the search fields (a keyword/date value, a PIN, a total amount) and a search button — present, but not yet wired to anything. Selecting a PDF from the left list is real and functional: it runs the full OCR pass (§5) on every page and populates the upper-right panel, so the reading can be checked by eye against the PDF itself. The PDF-side raw Next/Previous (no search triggered) is functional, for that same page-by-page cross-check. The error tab is functional, because real OCR failures are possible at this stage, not hypothetical. Deliberately absent, not merely inert: Excel-row navigation, and Verify/Decline — both act on a claim row, and there is no row without Excel.
- **Stage B — the search panel goes live.** The button and fields are wired to the real matching module from §6 (normalisation, exact-match search, highlight selection). The PIN is typed into the PIN field as a search keyword; no person-to-PIN table is involved yet (user decision, 2026-09-23) — the same module the finished system will use, not a stand-in — run against whichever page is open, with the result highlighted on the PDF. This proves the algorithm and the highlighting mechanism on their own, independent of Excel.
- **Stage C — Excel replaces the typed fields.** The search fields and button are replaced by an Excel row navigator (selectable rows, its own Next/Previous); the same matching module now takes its values from the selected row instead of typed input, and the PIN from the person-to-PIN table by the row's claimant name (§6, §9). The OCR-text panel stays visible alongside it at this stage specifically so the whole coordinated flow — row selected, search run, page shown, highlight drawn — can be watched and confirmed end to end, not just trusted because its parts were proven separately.
- **Stage D — the intended final layout.** Once that coordination is trusted, the OCR-text panel is removed and the right side becomes purely the Excel browser described below. Verify/Decline and the rest of the review workflow come online at this point.

**Opening files.** Clicking a PDF in the left list shows it in the middle pane and reads whatever pages the cache does not already hold (§5, §8). Clicking an Excel file loads it into the right pane (Stage C).

**Stage A as built** (`app/gui/`, one file per pane). OCR runs on a background thread (`ocr_worker.py`), so the window stays responsive. Pages are rendered for display on demand (`page_renderer.py`, a few tens of milliseconds each), so a page shows at once and its reading fills in when ready; the page on screen is always read next. Every reading is kept in `document_cache.py` until the application closes, keyed by path, size and modification time so an edited file is read again; the file list shows each file's state ("read", "reading 2/4"). With `read_ahead` on (gui_settings.json), the other files in the folder are read in the background when nothing else needs the engine. The upper-right panel shows each page's text grouped into printed rows by `app/layout/rows.py` (rules in `row_rules.json`: same row when vertical centres are within half a text height, and never when two segments overlap horizontally — text printed over other text is on another line). Switching files asks nothing, because nothing is lost; closing the window asks first when any readings are held. Switching away from a file mid-read stops it between pages and it resumes later with only its missing pages; pages whose reading failed are retried when the file is next opened. Anything that escapes a window event handler is caught and sent to the Errors tab rather than the console; if the window's own settings cannot be loaded, a small window showing that error opens instead of nothing. The search fields and a disabled Search button are present; nothing for Excel rows or Verify/Decline exists yet.

**Two independent sets of navigation controls, not one:**
- On the Excel side: Next/Previous steps through claim rows. Moving to a row is what triggers the search described in §6 and updates which page is shown in the middle pane — because the values being searched for belong to the row, not the page.
- On the PDF side: a separate Next/Previous simply pages through the document as it is, without ever running a search. This is how the officer reaches an orphan receipt, or corrects a wrong automatic match, without the row-driven controls getting in the way.

**Verify and Decline** sit on the PDF side and act on whichever page is currently open, updating the officer-disposition field of the Excel row that page is matched to — never the page itself, since status belongs to the claim line being checked, not to the piece of paper being looked at.

**Highlighting.** Only an exact match is highlighted — the matched segment plus its immediate neighbours, up to two segments each side. No match, no highlight; a page the search found nothing on is shown exactly as it is, which is itself informative. Neighbours are taken along the same printed row only (user decision, 2026-09-23), using the rows `app/layout` already builds. Each value type has its own highlight colour (amount, date, PIN; user decision, 2026-09-23). Page-frame boxes are computed once per page in the background and cached; highlights are overlay items in the page's graphics scene, so zooming and scrolling cost nothing and a search on the open page shows within one screen refresh.

**Row status** is shown on the Excel side, colour-coded, not as a light rail on the PDF side, because status is a fact about a claim line, which may not correspond one-to-one with page order.

**The error tab** is a plain, always-available list of every structured error raised or recorded during the session — newest first, one line each (`OcrStageError.summary`), expandable to the full detail (`.full_text`, including a traceback where one exists). This is the offline diagnostic channel described in §2: when the system breaks, this list, screenshotted, is expected to be enough to find and fix the problem without reproducing it live.

## 8. Storage — nothing now, sketched for later

**OCR readings are cached in memory for as long as the application runs** (user decision, 2026-09-23, reversing the earlier "no caching" choice). Every page read — of the open file, or of a file read ahead — is kept, keyed by the file's path, size and modification time, so switching files never loses finished work and an edited file is read again. Only the readings are kept (text, positions, a few measurements: kilobytes per page), never page images. Nothing is written to disk: closing the application discards the cache, and the window asks before closing.

**The cost that remains:** readings do not survive a restart — every file is read again the first time it is opened (or read ahead) after the application starts.

**When persistence is eventually wanted** — for resumable review sessions, or an audit trail of officer decisions — the plan is an encrypted local store: SQLite via SQLCipher, falling back to plain SQLite inside an encrypted folder if SQLCipher will not install cleanly on this Windows setup, kept in its own `case_data/` folder entirely separate from the officer's own `images/`, never mixed with it. That store would hold review decisions and, if OCR caching is ever worth reintroducing, an extraction cache keyed by file hash and by the version of the processing rules that produced it — so a cached result from before a rules change is never silently served as if it reflected the current logic.

## 9. Configuration

Everything below lives in its own config file, never inline in code — the same discipline `enhance_rules.json` already demonstrates for OCR, applied project-wide. Built so far: `app/ocr/enhance_rules.json` (page preparation), `app/layout/row_rules.json` (row grouping), `app/gui/gui_settings.json` (working folder, listed file types, render resolution, zoom, starting sizes). Each is read through `app/config_files.py`, so every config problem surfaces as the same kind of structured error.

**Person-to-PIN table** — each claimant's name and the PIN to search for on their receipts, supplied when the search is run. Holds real values, so it is never committed: it lives in `private/` or in a file matching the ignored patterns (`person_pins*`, `*_pins.*`, `*.local.json`); only a `*.example.json` template with fabricated values may be committed.

**Company settings** — legal name. *(The country-to-tax-ID map and default country profile of earlier drafts are not used for now — §6.)*

**Country profile** *(not used for now — §6; kept here in case a currency check returns)*, one per supported country — currency code, symbol, and words; how many decimal places the currency uses; date order; a tax-ID character pattern (used now only to correct an OCR character that cannot legally sit in its position — a letter where a digit belongs — never to open-search for an unknown ID).

**Keyword lists** — a single, global set of total-type keywords, no longer split by document type (§6). Fuzzy-tolerant when matched, exactly as `enhance_rules.json`'s own steps are threshold-tunable without a code change.

**Thresholds** — every numeric cutoff anywhere in the system, each with the evidence behind its current value recorded beside it, following the pattern already set in `enhance_rules.json`.

## 10. Money, dates, and the exactness rule

**Money** is parsed once, by one function, into an exact decimal amount and a currency — never a float, anywhere. The parser accepts a currency word or symbol before or after the number or none at all, thousand marks as comma, dot, space, or apostrophe, decimals as point or comma, an East African `/=` or `/-` ending as "no cents," and brackets or a trailing minus as negative. When the separators are genuinely ambiguous, the result is "cannot parse," never a guess — a guessed separator moves an amount by a factor of a hundred, which is exactly the kind of error this rule exists to prevent.

**Dates** are parsed day-first, as confirmed so far, with a config-held table of month names and abbreviations. (Earlier drafts took the date order from the claim's country profile; with country not used for now, one configured date format applies until real claims show otherwise.) An unreadable or genuinely ambiguous date is reported as such, never guessed.

**The exactness rule, stated once more because everything above depends on it:** matching a *value* against the claim is always exact, after normalisation, and never fuzzy. Matching a *label* that only helps find where to look is allowed to tolerate noise. These are not the same operation and must never be implemented as if they were.

## 11. Error handling and diagnostics, applied

Restated here in its fully applied form, generalising the pattern already proven in §5 to every module still to be built — the Excel parser, the matcher, eventually the storage layer:

- Every stage that can fail is wrapped at one clear boundary and produces a structured error in the shape of `OcrStageError`: a stage name, a plain description, file/page or row context where relevant, and, when it wraps another exception, that exception's full traceback.
- Processing many items — pages, rows, files — never lets one item's failure stop the batch. The failure attaches to that one item's result; the rest proceed.
- Nothing is printed to a console. Nothing calls an exit on a recoverable error. A structured error is raised or returned and the caller decides how to show it, which today means one place: the error tab in §7.
- Before any change is reported as working, it is verified by running it against real input and by deliberately breaking each new failure path — not by reading the code and assuming. This is not a formality: doing exactly this on the OCR module's own error handling found two real gaps that reading the code over would not have surfaced.

## 12. What is built, what is designed, and what is still genuinely open

**Built and proven.** The OCR and image-preparation module (§5) — `app/ocr/`. Row grouping of OCR text — `app/layout/`. The review interface's Stage A (§7) — `app/gui/`, started with `python -m app` or `start_app.bat`. An automated test suite — `tests/`, run with `run_tests.bat`, which is the project's health check: it covers the error and config shapes, row grouping (including the real receipt case that exposed the overlap rule), the background OCR with every failure path forced on purpose, the window's behaviour off-screen, and one real OCR run on a synthetic PDF.

**Designed here, not yet built.** Excel parsing (reading rows, the claimant's name, the grand-total field); the person-to-PIN lookup (§6, §9); the matcher (§6); the aggregate total check. The review interface's Stages B–D (§7): Stage B, the matcher behind the search fields, is next once Stage A is confirmed by eye.

**Not yet decided — named plainly so silence is never mistaken for a decision:**
- What exactly anchors "the total" on a page carrying several amounts.
- Whether the system should warn when the loaded PDF and the loaded Excel file do not obviously belong to the same claim — nothing currently checks this.
- How duplicate detection fits the simplified matching flow.
- Whether card/statement matching is ever built.
- How to hide OCR time before the officer opens the application — start with Windows and read in the background, or let the email intake trigger OCR on arrival. Decided at the final stages (user, 2026-09-23); either needs readings to outlive the window, so it goes together with the persistence decision in §8.

**Resolved 2026-09-23 (user):** highlight neighbours stay on the same printed row (§7); country is not used, and the PIN to search for comes from the claimant's name via a person-to-PIN table (§6, §9).

**Resolved since first written:** `docs/reviews/decisions.md`'s D7 once required an invoice-number column before any row could reach CONFIRMED. It has been corrected in place — D1's later, more specific redefinition of CONFIRMED (§1: PIN plus date plus amount, no invoice number) supersedes it, and D7 now says so. Noted here only so the correction itself isn't lost.

## 13. Risks and honest limits

**A silent wrong pass is the risk that matters most**; every other risk in this system is smaller than that one. The needs-review state is always the safe failure — the system is built to abstain generously rather than guess.

**Single-engine OCR is a real trade, not a free simplification.** There is no second engine left to catch a misreading the first one shares with itself. Safety now rests entirely on exact closed-search plus mandatory human review plus the aggregate check (§2) — not on two independent readings agreeing, which is what earlier drafts of this design relied on instead.

**Five of the six supported countries' tax-ID patterns are unvalidated** against real receipts and are marked as such in config; a wrong pattern is designed to produce an unmatched search, never a wrong pass.

**While a file is being read, all its pages are rendered in memory at once** (about 25 MB per A4 page at 300 dpi, released when the reading ends); the display holds only the page on screen. A 40-page claim briefly holds about 1 GB during its reading. Acceptable on 8 GB for claims seen so far; rendering page by page inside the OCR module would remove it if long claims become common.

**Readings do not survive a restart** (§8): the cache is memory only, so after the application starts each file is read again once. Persisting readings to disk is a separate, later decision (encrypted store, §8).
