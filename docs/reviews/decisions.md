# Decisions log

**Status: BINDING record of decisions and their reasoning.**

**Precedence (revision 3, user decision 2026-09-23):** `docs/blueprint.md` is the single source of truth for the current design. This file records each decision and why it was taken; when the blueprint moves on, the affected entry here is corrected with a dated note (never silently). `docs/NEXT_SESSION.md` only points to the other two. If a decision here turns out to create a hole, raise it as a question — do not quietly work around it.

**Owner** = the project owner's decision, taken in conversation.
**Derived** = a consequence I worked out while applying an owner decision. Derived entries bind in the same way, but they are the ones most worth challenging, because the owner has not separately confirmed each.

Revision 4 (2026-09-24): D23–D33 added (the Stage C design, settled with the owner in one planning session, each rule measured first); D7, D8, D13, D14, D19 carry dated notes on what supersedes them; O1 is now scheduled (a measured trial opens C2). Revision 3 (2026-09-23): precedence rule above; D13–D22 added; D1, D2, D11 carry dated notes on what supersedes them. Revision 2 rewrote D4 and D6.

---

## D1 — What CONFIRMED means

> **Superseded in wording, 2026-09-23.** CONFIRMED is now called **PASS** (D13), and it means date, amount and PIN all found on the same receipt — no invoice number (see D7's correction).

**Owner.** A row is CONFIRMED when the PIN and every receipt's details match the claim form: for each receipt, the invoice number, the date and the total amount are the same as the corresponding entry in the .xlsx.

Anything else — a mismatch, a document that failed to open, or a match that fails because the OCR did not read the document properly — is not a system decision. It goes to manual check, and the claim is confirmed or declined only after a person looks at it.

**Lands in:** §1.2, §15.1, §15.3 matrix.
**Status:** partly applied.

---

## D2 — The officer decides last, in both directions

> **Names updated, 2026-09-23.** The system outcome is PASS / CAUTION / REVIEW (D13), not CONFIRMED / REFUTED / UNDECIDED. The rest of this entry stands: the system finding and the officer's decision are two fields, never merged.

**Owner.** The manual check is always available. The officer may **decline a row the system passed**, and **confirm a row the system flagged**, including incomplete or unmatched documents, after checking by hand.

Part of this decision:

-   The system verdict and the final disposition are **two different fields**, never merged. System outcome stays CONFIRMED / REFUTED / UNDECIDED; the officer's disposition is ACCEPTED / DECLINED / FOLLOW-UP. Both are stored and both appear in the report.
-   A row is not finished until a disposition exists.
-   Overrides do not relax the abstention rules. A wrong pass that an officer rubber-stamps is still a silent error.

**Lands in:** §7.1, §15, §17.1, §17.2, §18.1.
**Status:** not yet applied.

---

## D3 — Overrides are measured, not just recorded

**Owner** (answering Q5). Every override is recorded with its direction and reason, and reported separately from the system's own accuracy:

-   **Override-down:** passed rows the officer declined. Rising = the system passes things it should not.
-   **Override-up:** flagged rows the officer accepted. Rising = the system flags too much, or the officer has stopped reading.

**Lands in:** §18.1, §17.2.
**Status:** not yet applied.

---

## D4 — The country comes from which company tax ID matched *(revised)*

> **Set aside, 2026-09-23 (user decision).** Neither the Excel nor the receipts state a country, and none is needed for now. The PIN to search for is the claimant's: the Excel row gives the person's name, and a person-to-PIN table supplied at search time gives the PIN (people in the same country share one). No country is derived and no currency check runs. The rule below is kept for reference in case a currency check is ever wanted; it is not current. See blueprint §6.

**Owner.** Look for the PIN first. Search the OCR text for the company's tax IDs — the set of keys. **At least one must match.** Whichever one matches identifies the country, and the country then gives the expected currency.

*Supersedes revision 1, which identified the country from tax authority words, country names and currency, then used it to pick the tax ID pattern. That is dropped. Authority words are no longer used to determine country.*

**Why this is better than what it replaces:** it is a closed search against a known answer set, not an open guess. We are not asking "is there a buyer tax ID on this receipt?" — we are asking "does one of *our* IDs appear here?" A supplier has no reason to print another company's tax ID, so a hit is strong evidence the document was issued to us. It also needs no authority-word list, no country-name list and no per-country pattern matching.

**The rule:**

1.  Search the OCR text of the crop for every company tax ID in the configured set.
2.  No match → **RED**, follow-up required (D11). No country, so no currency check runs.
3.  One match → that ID's country is the receipt's country. Its currency is what the currency check expects.
4.  Two or more different company IDs match on one receipt → follow-up, not a silent pick.
5.  A matched ID whose country's currency disagrees with the currency on the receipt → **YELLOW**. This is the case of a supplier writing our Kenyan ID on a Ugandan invoice, and it is worth a look rather than a silent pass.

**Lands in:** §7.3a (rewritten), §8.2, §13.6, §15.3.
**Status:** §7.3a and §8.2 currently hold revision 1 and must be rewritten.

---

## D5 — The company's tax IDs are held as a country-keyed set

> **Set aside, 2026-09-23 (user decision).** Replaced for now by a person-to-PIN table, supplied at search time and never committed (see D4's note and blueprint §9).

**Derived, now load-bearing.** Company settings hold a country-to-ID map. D4 searches that whole set and the hit identifies the country, so this map is no longer a convenience — it is the mechanism.

**Still worth challenging (O3):** this assumes one ID per country of registration. If the company operates under a single ID everywhere, the country cannot be derived from which ID matched, and D4 needs a different country source.

**Status:** applied.

---

## D6 — The PIN check is a closed search, not a role analysis *(revised)*

**Owner.** We depend on the OCR result and the search-and-match confirmation. Finding one of our tax IDs in the text is the check.

*Supersedes revision 1, which required a positively identified buyer block and refused to confirm a lone unlabelled tax ID. That machinery — the party block detector, buyer and supplier marker lists as safety-critical inputs — is no longer needed for the pass decision.*

**What this removes:** the buyer/supplier block detector stops being load-bearing. §8.2's supplier-marker list becomes advisory. The earlier worry — that an unlabelled tax ID is usually the seller's — mostly dissolves, because we are matching against our own IDs and a supplier's own ID is not one of ours.

**The one hole it leaves, and the cheap guard (derived):** a receipt that **we** issued carries our tax ID as the seller. An employee submitting one of the company's own sales receipts as an expense would match. The guard is small and does not need a block detector: **if the matched ID sits under a seller-type label (`seller`, `supplier`, `vendor`, `issued by`, `our PIN`, `our TIN`), flag YELLOW rather than pass.** One label lookup, no layout analysis.

**Lands in:** §8.2, §13.6 PIN row.
**Status:** not yet applied.

---

## D7 — The claim form must carry an invoice number per row

> **Superseded, 2026-09-24 (D24).** Receipt and invoice numbers on the claim sheet are ignored entirely; each claimed amount is searched with its row's date across every page.

**Owner** (answering Q1), and implied by D1. Layouts 1 and 2 have no invoice number column, so under D1 nothing on them can pass. The third layout — one receipt per row, with an invoice number column — becomes the supported form.

Layouts 1 and 2 stay supported for parsing and sum checks; their rows report a missing claimed value and are never passed by the system. Under D2 the officer can still accept them by hand.

**Status:** not yet applied.

**Superseded, in part, by D1's later redefinition.** In the session that produced D9 onward, the owner redefined CONFIRMED itself as PIN plus each receipt's date and amount matching the Excel — explicitly dropping the invoice number, because the Excel format actually in use has no invoice number column ("ignore invoice number bc it is not in the excel"). That is a narrower requirement than D1's original wording, which listed invoice number, date and total. Under the redefined CONFIRMED, D7's premise — that a row without an invoice number can never pass — no longer holds: it can, on date and amount and PIN alone. D7's other point, that the form should eventually gain an invoice-number column, stands as a genuine improvement worth making, but is no longer a blocking requirement for reaching CONFIRMED. `docs/blueprint.md` §1 and §12 follow this redefinition. This entry is left in place, corrected, rather than deleted, so the reasoning that produced the original requirement is not lost.

---

## D8 — The duplicate key is built from read values

> **Superseded, 2026-09-24 (D29).** No key from supplier ID / invoice number / total. Repeated receipt pages are found by three measured checks; the claim sheet side gets no duplicate check.

**Owner** (answering Q3). The key (supplier tax ID, invoice number, total) is a suspicion fingerprint, not an identity assertion. A collision is a follow-up, never a decline on its own. The check blocks a pass only when the key is wholly unreadable.

**Status:** not yet applied.

---

## D9 — This file supersedes the earlier missing-decisions gap

**Owner.** No separate decisions file existed when the Session 2 audit ran; the owner confirmed none was needed. This file is the record from here on.

---

## D10 — Document type does not gate anything *(new)*

**Owner.** It does not matter whether the document is a receipt, a mobile payment confirmation, a card slip or an invoice. Everything depends on the OCR result and the search-and-match confirmation.

**What this removes:**

-   R12 (document type known) stops blocking a pass.
-   Per-document-type keyword groups collapse into one global ranking. The overlaps that needed resolving per type (`balance`, `deposit`, `advance paid`, `refund`) now need resolving once.
-   R10 (statement matching for card claims) stops blocking. **This answers O2:** there is no payment-method field to add, because nothing depends on it. Statement matching, if built at all, is a later extra.
-   Much of §8.4's document-type keyword library becomes optional — useful for display and for routing, not for decisions.

**What it does not remove (derived, see D12):** the requirement that matched values come from one receipt. Dropping document type is safe; dropping the crop boundary is not.

**Status:** not yet applied.

---

## D11 — Three flags *(new)*

> **Superseded, 2026-09-23 (D13).** The three states are PASS, CAUTION and REVIEW. A missing PIN is REVIEW, not a separate red. The RED/YELLOW mapping below is kept for history only.

**Owner.**

| Flag | When | Officer action |
|---|---|---|
| **RED** | No company tax ID found in the OCR text | Follow-up required |
| **YELLOW** | A tax ID matched, but an amount, invoice number, date or other receipt detail mismatches | Follow-up |
| **PASS** | Everything matches | None required |

Every flag can be changed after manual check (D2).

**Derived — how this maps onto the three outcomes.** `CLAUDE.md` requires decision code to return CONFIRMED, REFUTED or UNDECIDED and never a plain true or false, so the flag is the officer-facing priority and the outcome plus reason code stays the internal record. Both are stored:

-   **PASS** = CONFIRMED.
-   **YELLOW** = REFUTED where the reading is reliable and contradicts the claim, UNDECIDED where it could not be read. The officer sees one yellow either way; the report carries which it was, because "the amount is wrong" and "the amount is unreadable" need different follow-up.
-   **RED** = UNDECIDED (no tax ID found), or REFUTED where the image is good and the ID is reliably absent.

**Worth challenging:** RED (no PIN) outranks YELLOW (wrong amount). From a document-validity view that is right — without our ID the document may not be ours at all. From a fraud view an altered amount is the more serious signal and currently sits in the softer bucket. Say if you want a wrong amount escalated to red.

**Status:** not yet applied.

---

## D12 — All matched values must come from the same receipt *(new, derived)*

**Derived from D10.** With document type gone, the only thing preventing a coincidental match is the crop boundary. The invoice number, date and total that confirm a row must be found **within one receipt crop** — not merely somewhere in the OCR text of a page or a file.

**Why this must stay:** a page holding several receipts, or a statement holding fifty lines, will contain almost any amount and many date-shaped strings. Searching the whole page for the claimed values and passing on three independent hits is how a wrong pass happens. Requiring one crop keeps closed search honest without needing to know what kind of document it is.

**Status:** not yet applied.

---

## D13 — Three states: PASS, CAUTION, REVIEW *(revision 3)*

> **Corrected, 2026-09-24 (D28, D30).** The three states stand. Two parts are superseded: the colours (the claim sheet shows green / yellow / red — CAUTION is shown yellow with its reason, red is the REVIEW reason "one receipt for two claims"), and "found on several pages with no way to choose → REVIEW" (the first unused page wins, D28). The PIN is required only when the officer's switch says so (D23).

**Owner**, 2026-09-23. Every system finding is PASS, CAUTION or REVIEW — never a plain true or false. PASS: date, amount and PIN all found on the same page. CAUTION: only a possible match (faded decimal point), a PIN only under a seller label, or a different buyer PIN printed. REVIEW: date or amount not found exactly ("yellow review"), found on several pages with no way to choose, or no PIN found. Colours when shown (Stage C): PASS green, CAUTION orange, REVIEW yellow.

## D14 — Country is not used; the PIN comes from the claimant *(revision 3)*

> **Superseded in part, 2026-09-24 (D23).** Country is still not used. There is no person-to-PIN table and no PIN "lock-in": one Kenyan company PIN, and an officer switch for whether it is required.

**Owner**, 2026-09-23. Neither the Excel nor the receipts state a country. The PIN to search for is the claimant's, found by the Excel row's name in a person-to-PIN table supplied at search time (people in one country share a PIN). No currency check runs. Supersedes D4 and D5 for now. In Stage B the PIN is typed as a search keyword; the table arrives in Stage C.

## D15 — Search rules chosen by measured trial *(revision 3)*

**Owner**, 2026-09-23, approving the winners of `tools/search_criteria_trial/` (15,673 cases, 65 real pages, zero false matches for all three keys). Amounts: found with or without cents, only as a value on its own; without cents only beside a currency word or "/=", or ending a total line; printer marks, attached currency words, tax-code letters trimmed; split values joined only at a decimal tail. Dates: every printed form, label prefix trimmed, fused time tolerated. PIN: format-positional letter/digit repair, one differing character only for a configured OCR look-alike pair, fused label words removed. Details and numbers: blueprint §6. **Why:** a wrong PASS is worse than a REVIEW, so the rules were ranked by false matches first; each rejected alternative (no-cents anywhere, any-one-character PIN, general segment joining) was measured to produce false matches.

## D16 — Faded decimal point: CAUTION only *(revision 3)*

**Owner**, 2026-09-23. "430 00 KSh" read for 430.00 is reported as a possible match, never a PASS, because the same repair matches quantity-then-price lines.

## D17 — One receipt per page *(revision 3)*

**Owner**, 2026-09-23. Claims will be submitted one receipt per page as a strict intake rule; pages holding several receipts are not handled. This is what makes D12 (all values from one receipt) hold at page level.

## D18 — Highlights *(revision 3)*

**Owner**, 2026-09-23. Neighbouring segments extend along the same printed row only. One colour per key (amount blue, date purple, PIN teal). Every occurrence is highlighted.

## D19 — Search the whole document; the viewer scrolls *(revision 3)*

> **Corrected, 2026-09-24 (D24, D28).** In Stage C each claimed *amount* (not each row) is checked once and mapped to its page.

**Owner**, 2026-09-23. A search covers every page of the open file and brings the matching page into view. Moving through pages never re-runs a search. The viewer is one continuous vertical scroll. In Stage C each Excel row is searched once and mapped to its page.

## D20 — OCR readings cached until the application closes *(revision 3)*

**Owner**, 2026-09-23, reversing the earlier "no caching" decision. Readings are kept in memory, keyed by path, size and modification time; nothing is written to disk. Switching files loses nothing; closing the application asks first.

## D21 — OCR settings kept as measured *(revision 3)*

**Owner**, 2026-09-23. RapidOCR runs at its defaults. Lower detection resolution, full-resolution recognition, memory arena, larger batches and parallel pages were each measured and not adopted (evidence in `app/ocr/engine_settings.json`). No whole-page orientation correction (sideways pages still yield their values). Photos and screenshots (JPG, PNG, HEIC) are claim files; Word files are not supported.

## D22 — Hiding OCR time before the app opens: decided last *(revision 3)*

**Owner**, 2026-09-23. Starting with Windows, or email-triggered OCR, is decided at the final stages only; either needs readings to outlive the window, so it goes with the persistence decision.

## D23 — One Kenyan PIN, and an officer switch for whether it is required *(revision 4)*

**Owner**, 2026-09-24. The buyer PIN applies only to receipts from Kenya; Ethiopian receipts carry no buyer PIN (the telebirr "TIN" is the telecom operator's own, printed on every slip — removed from `.env`). So: the company's Kenyan PIN is held in `.env` (git-ignored, never committed; fabricated `A012345678Z` in anything committed). After OCR, a quick scan searches every receipt page for it: found on at least one page → the switch **"PIN required"** starts **Yes**; found on none → **No**. The officer can flip it at any time; colours and status follow at once (only the page assignment re-runs, never a search). Yes: an amount is green only with date, amount and PIN on the same page. No: the PIN is not needed (it is still highlighted where found). A claim mixing Kenyan and other receipts is handled by the officer flipping the switch (owner: keep it simple). **Why:** a PIN that most receipts can never carry cannot be a general requirement; the scan makes the right default automatic without guessing a country.

## D24 — What is claimed *(revision 4)*

**Owner**, 2026-09-24. Every non-zero amount in the expense columns — Motor Vehicle Fuel through Other, all of them, Daily Allowance included — is one **claim item**, paired with its row's date; one row can hold several items, each an individual receipt on its own page. The Total column is the row's total, Rate multiplies (derived: blank or 0 counts as 1, as the sheet's own formulas do), Less Advance and Balance are ignored. Receipt / invoice numbers on the sheet are ignored entirely. The claim sheet gets **no duplicate check**: the same amount can honestly be spent twice in a day. A daily allowance with no receipt is simply yellow ("no receipt found"); there is no exempt list.

## D25 — Reading the claim sheet *(revision 4)*

**Owner**, 2026-09-24 (the input may be Excel or PDF; must work on both; Excel read with no noticeable delay). **Derived design, owner-approved ("do the best you think"):** `.xlsx`/`.xlsm` read directly with openpyxl (already installed; 32–42 ms for the real two-sheet workbook in read-only mode), values as saved (formulas give their saved result). A workbook with several claim sheets shows them as tabs, starting on the sheet it was saved on. The header block (possibly several rows, holding ledger codes like 4740150) is found by header words in config; amounts are read only from the data rows between the header block and the Total row, so codes never become claims. Floats become exact cents (a typed cell with more than two decimals is flagged, never rounded silently). `.xls` is refused with a clear message (no new library). A PDF claim sheet is read from its **text layer** when it has one (sheets exported from Excel do: exact, milliseconds) and through OCR otherwise; either way the table is rebuilt from the header columns' positions and row bands (a wrapped description puts one row's numbers on two text lines). Pairing: two slots, "Claim sheet" and "Receipts"; Excel + PDF fill themselves; with two PDFs the sheet is recognised by its header words; the officer can swap.

## D26 — Claim-sheet dates *(revision 4)*

**Owner**, 2026-09-24: dates are read by the winner of a measured trial (`tools/date_parsing_trial/`, 4,000 fabricated sheets). Approved first: **R9** — a cell with one possible meaning is read directly; a cell with two (6/10/2026) takes the writer's order from the sheet's own unambiguous dates, else the order that keeps the sheet within one claim period (92 days, config), else the one reading found on a receipt carrying that amount; when the sheet's order gives a date no receipt shows while the other reading is on that amount's receipt, the row goes to the officer.
**Refined the same day.** The owner's real workbook showed Excel storing dates **swapped** (typed 3/8/2026 day-first into an Excel set to month-first: saved as 8 March; days above 12 stay text); R9 reads 38% of such sheets wrong. The owner asked for a rule that does not depend on the file and proposed two methods: (1) a day can be 1–31 but a month only 1–12, so a part above 12 fixes the order; (2) otherwise, the reading closer to today, since claims are monthly and a flip moves a date far. Both were measured (second round: 4,000 sheets, 50,282 dates, each checked 0–365 days after its last receipt). Method 1 is exactly the sheet's votes and stays first. Method 2 as described (the last listed date's closeness to today) read 742 dates wrong — for past dates "closer to today" means "the later reading", which fails when the flipped reading is later but not yet in the future, even for claims checked within 30 days — and it reads the real Week1 sheet as 8 Mar–8 Sep. The owner's two ideas behind method 2 are kept in their measurably safe form: **no reading can be after the day the claim is checked**, and **a flip spreads the sheet beyond one claim period**. **Approved by the owner, 2026-09-24 — R10u:** every date cell, from any file, reduced to its two readings the same way (text: day-first / month-first; an Excel date cell: stored / day and month exchanged); per sheet: (1) votes from dates with a part above 12, (2) no reading after the day of checking, (3) the reading that keeps the sheet within one claim period, then per row (4) the one reading on a receipt carrying the amount, (5) the guard; still undecided → the officer, never guessed. Measured: 99.67% correct, 2 wrong, 1 of them matching a receipt, 0.33% to the officer (R10s: 2 wrong, 0.37%); every one of the 65 dates on the owner's six real sheets (both Excel tabs, the Week 2 PDF export, the July sheet as text and as a picture, the new July-EA sheet) read right.

## D27 — Cents dropped *(revision 4)*

**Owner**, 2026-09-24. A claimed amount matches a receipt amount that is equal, or equal with its cents dropped: a claim of 500 matches 500, 500.00 or 500.34; a claim of 500.34 matches only 500.34; never upward (501 for 500.60, or 499, is yellow). A zero or blank cell is not an item. The date on the same page is always required — measured, the cents rule alone matches other receipts' amounts (760 vs 760.01), and only the date keeps them apart. Exact matches are assigned across the whole sheet before cents-dropped ones (two passes), so a 500 claim cannot take the 500.34 receipt a 500.34 claim needs. A time printed like "19.06" must not match a claim of 19 (guard measured when built). Trial: `tools/search_criteria_trial/cents_rule.py` (24/24 fabricated positives, 127/131 real, the time trap the one failure).

## D28 — Assigning receipts to claims *(revision 4)*

**Owner**, 2026-09-24. Each receipt page approves at most one claim item, and the **first match found wins** (owner: "search for 500, when found skip to 700"). Every item is checked at once after OCR, not live. **Derived, measured:** each claim searches only the pages that print its amount (an index of every amount text, built once per document) — the same page for every claim as searching every page, 13× faster at 26 pages, 138× at 500 (`tools/stage_c_timing/`). Results are kept; the PIN switch re-runs only the assignment. **Owner, restated as a general security rule (2026-09-24):** once a claimed amount's date and amount (and the PIN, when required) are found on a page, that page is paired with that amount and every later search looks only at unpaired pages. Tried end to end on the owner's real claims with `tools/stage_c_dryrun/` (Week1, Week2, July, a wrong pair, and stress cases): no page was ever paired twice; the same amount claimed twice with one receipt gives green then yellow "already paired with row 9".

## D29 — Repeated receipt pages *(revision 4)*

**Owner**, 2026-09-24. After the PIN scan and before checking, the receipts are checked for repeated pages. **Measured** (`tools/duplicate_pages_trial/`, 65 real pages, 15 same-receipt pairs captured differently, 2,065 different pairs): whole-page word overlap cannot separate them (same receipt as low as 0.45, different up to 0.72). **Two checks, catching 9 of 15 with 0 wrong** (387 different-receipt pairs inside a document, 1,678 across): nearly identical text (≥ 0.90; always catches the same scan repeated) and same date + same time + a shared amount. *Corrected the same day:* a third check — two or more long reference numbers printed on those two pages only — first measured 13 of 15 with 0 wrong, but "only" had been counted across all 65 pages of many files; counted inside one claim's PDF, as the application runs it, it flags two receipts from the same shop (their PO box, PIN, phone and till serial): 2 wrong inside a document, 15 across. The Stage C dry run found it on the real week-1 claim. Dropped, with every variant tried (with a shared date, with a shared amount, text ≥ 0.60 + date). An invoice-number check was also measured and rejected (a value read on only 23 of 65 pages; reading telebirr's letter-heavy numbers gave 190 wrong). Both checks run indexed (milliseconds).
**Status rule (owner):** green — no repeated page; **yellow** — a receipt is repeated but only one claim relies on it (the claim stays green on the first copy); **red** — a repeated receipt that two claims with the same amount on the same date rely on: **both amounts red**, neither counted in Grand total 2. The "same amount twice on one day" check runs only when a repeat was detected. Repeats cannot show green while a page is unread. Accepted risk: an undetected repeat (6 of 15 re-captured receipts in the trial; a page repeated as the same scan is always detected) plus the same amount claimed twice that day would show two greens.

## D30 — Colours, status and totals *(revision 4)*

**Owner**, 2026-09-24. Claim-sheet amounts: **green** when date, amount and (if required) PIN are on one unused page; **yellow** for everything else, with a plain reason (CAUTION shows here too, e.g. "possible match"); **red** for one receipt claimed twice (D29). Receipt highlights stay amount blue, date purple, PIN teal. A small status strip holds **Verification** (green only when every amount is green, Grand total 2 matches and every receipt page was read; else yellow — it replaces the earlier "document approved" light), **PIN** (green on every matched receipt; red when missing on one; grey "not required" when the switch is No) and **Repeated pages** (D29). At the bottom of the sheet: **Grand total 1** (the sheet's own arithmetic: row amounts against the grand Total; with a Rate, amounts × Rate) and **Grand total 2** (the approved amounts against the grand Total). When Grand total 1 fails, the rows whose own Total disagrees with their amounts are named. Yellow reasons say how near the miss was ("receipt dated one day earlier (23:55)"). A page carrying the amounts of several claims (the claim sheet itself or a statement scanned into the receipts) would approve the first claim; the owner agrees it is a safety issue but decides that **for now the claim sheet and the receipts always arrive as separate files** — the guard is recorded, not built.

## D31 — Auto and Manual *(revision 4)*

**Owner**, 2026-09-24. Checking happens all at once when reading finishes, so the live demonstration is a **tour** replaying the results: it starts by itself (config), selects each amount in sheet order, brings its receipt into view with highlights, lingers briefly on green and longer on yellow (config). Clicking any amount switches to **Manual** (the tour pauses; the page appears at once, from the saved result); **Auto** resumes where the tour stopped; **Next to check** jumps to the next yellow; keys: Space (Auto / pause), N (next to check), arrows (move between amounts).

## D32 — Layout *(revision 4)*

**Owner**, 2026-09-24. Right column, top to bottom: a **small** status strip (with the PIN switch, Auto and Next to check), the claim-sheet grid taking most of the height (sheet tabs, Grand totals at its bottom), and a bottom slot a little smaller than today's search panel holding two tabs, **OCR text** and **Search** (the typed search stays).

## D33 — Scheduled and deferred *(revision 4)*

> **Done, 2026-09-24 (owner: "do the recommended").** Total anchor: rule **A4m+** adopted — the amount on a total-labelled row, or under a total label standing as its column's header; never on a cash / change / card / discount row or a tax line (%). Measured through the application's own finder: 31 of 31 claimed amounts kept; every cash-tendered, change, tax and before-discount amount refused. The trial's first version was flawed (it accepted amounts it could not locate, so telebirr's cent-less amounts were never tested) and was corrected the same day; see `tools/total_anchor_trial/`. Different-buyer PIN: built as a CAUTION; 0 wrong flags on 71 real pages, no positive case in the samples.

**Owner**, 2026-09-24. C2 opens with a measured trial (like every rule so far) for **what anchors a claimed amount as the receipt's total** (O1: on 64 real pages, 6 print an amount larger than the claimable total, 3 of them on a cash / tender / change row — a claim of the cash handed over would pass today) and for the **different-buyer-PIN** CAUTION already decided in D13 (it must make 0 wrong flags on the real pages). Deferred to the next stage: the officer's own sign-off on each amount (D2, D3), so Verification cannot turn green while any amount is yellow. Later, not Stage C: repeats **across** claims (the same receipt in two weeks' claims), by keeping one-way fingerprints of checked receipts, never document text.

---

## Open, needing an owner decision

| # | Question | Why it cannot be derived |
|---|---|---|
| ~~O1~~ | *Closed 2026-09-24 (D33): rule A4m+, measured.* **What anchors the total?** Under pure search-and-match, a claimed 30,000 that appears anywhere on a receipt matches — including as a deposit, a line item or a "balance due" on a 50,000 invoice. My proposed rule, doc-type-free: the matched amount must be **the largest amount on the receipt, or sit beside a total-type keyword**; otherwise YELLOW. That handles the part-paid hotel invoice correctly. Confirm or replace. | It is a question about what you want a part-payment to do, not an evidence question. |
| ~~O3~~ | *Closed 2026-09-23 by D14: country is not used.* | — |

O2 (how to know a row was paid by card) is **closed** by D10 — nothing depends on it.

---

## Applied-status summary

| Decision | Blueprint updated? |
|---|---|
| D1 CONFIRMED definition | Partly |
| D2 Officer decides last | No |
| D3 Overrides measured | No |
| D4 Country from matched tax ID | No — §7.3a holds the superseded version |
| D5 Country-keyed ID set | Yes |
| D6 Closed PIN search | No — §8.2 holds the superseded version |
| D7 Form carries invoice number | Superseded (D24) |
| D8 Duplicate key from read values | Superseded (D29) |
| D23–D33 Stage C design | Yes — blueprint §3, §4, §6, §7, §9, §12, §13 (2026-09-24) |
| D10 Document type does not gate | No |
| D11 Three flags | No |
| D12 One crop per match | No |
