# Consistency review 01: blueprint Parts 3, 7, 13, 15

Scope: `docs/blueprint.md` Part 3 (architecture, records, reason codes), Part 7 (data model, config), Part 13 (search and verify, evidence policy), Part 15 (decision layer). Review only. Nothing in the blueprint was changed.

Section numbers use the blueprint's own numbering. Where a finding depends on a step outside these four Parts (for example 5.19, 8.2, 9.4, 14.1), that step is named and cited for context only. It was not reviewed for its own consistency.

Severity scale:
- **blocker**: the design cannot be implemented as written, or it can produce a wrong CONFIRMED.
- **important**: two parts disagree or leave a gap that will cause rework or unsafe behaviour.
- **minor**: naming, hygiene, wording.

## Summary

| Question | Result |
|---|---|
| 1. Do 3.3 and 7.1 match field for field? | No. Only RowResult matches. Every other record differs in fields, names or contents, and both lists omit fields and records the rules need (A1 to A9). |
| 2. Reason codes: produced and defined? | No. `AMBIGUOUS` is never produced. Nine outcomes listed in B3 have no code. REFUTED has no codes at all (B1 to B6). |
| 3. Does 13.6 agree with R1 to R13? | Partly. 13.6 covers 3 fields. R6, R10 and R11 need evidence it never describes, and R1, R2, R3, R9 and R12 are only partly covered (C1 to C10). |
| 4. Do all references resolve? | All task and section IDs cited resolve. Four config or component references do not, and many IDs collide (D1 to D9). |
| 5. Are 15.1 and 13.6 consistent? | No. There is no evaluation order, "required check" is undefined, and some rows have no outcome (E1 to E8). |

---

## A. Records: Part 3.3 against Part 7.1

Field-for-field comparison:

| Record | 3.3 | 7.1 | Difference |
|---|---|---|---|
| Money | absent | present | Only in 7.1 (A9). |
| SourceFile | name, type, size, hash, page count, "how accepted or why refused" | Id, name, type, size, hash, page count, status, refusal reason | Id, status added (A9). |
| Claim | employee, project, profile, currency, date, rows, category totals, grand total, advance, balance | same plus Id, and every total "as written" | Id and "as written" only in 7.1 (A9). |
| ClaimRow | row no., date, description, category, amount, receipt ref text, invoice no. if present | "category code", "receipt ref as typed", plus no-receipt reason if stated | Name changes plus one new field (A7). |
| ReceiptCrop | file and page, position, quality scores, doc type guess | Id, source file, page, box, doc type, quality per region, variants | Id, variants added (A6). |
| Observation | field, value as read, channel, box, local quality, confidence, nearby label words | field, raw value, **normalized value**, channel, box, local quality, confidence, label context words, **variant id** | Two fields added; three names differ (A3). |
| Candidate | absent | present | Only in 7.1 (A3). |
| Evidence | "all **observations**, which channels agree, which conflict" | "all **candidates**, which channels support each, conflicts" | Different contents (A3). |
| Verdict | check, outcome, reason code, evidence used | check name, outcome, reason code, evidence references, plain-language note | Note added (A3). |
| RowResult | row, verdicts, combined outcome | same | Match. |
| Report / ClaimResult | Report: summary, exception list, undecided list, sums check, tool version | ClaimResult: row results, sum-check verdicts, orphans, refused files, tool and config versions | Different names and contents (A8). |

### A1. Observation, Candidate and Evidence lack fields the rules need
- **Severity:** blocker
- **Where:** 3.3 Observation; 7.1 Observation, Candidate, Evidence; needed by R1 (15.3), tasks 7.8, 7.9, 7.17 (13.2, 13.3) and 13.1.
- **Conflict:** R1 requires a PIN "in a buyer or neutral position" and 7.9 sorts PINs into buyer, supplier or unknown. No record has a field for that role or for the party block. Task 7.17 records the closed-search result "as another observation", and 13.1 requires open and closed findings to agree. Nothing marks whether an observation came from the open finder or the closed searcher. No field holds the currency read with an amount, or the rank from 7.8. Nothing ties an Observation to a receipt (see A2).
- **Fix:** Add to `Observation`: `crop_id`, `origin` (open or closed), `party_role` (buyer, supplier, unknown), `block` (header, party, items, totals, footer), `currency` (optional). Add to `Candidate`: `party_role`, `rank`, `label_group`, `normalized_value`. Since Phase 9 is built on hand-made observations before any OCR exists, freeze these fields in Phase 2 (task 2.2).

### A2. No identifiers or keys on most records
- **Severity:** important
- **Where:** 7.1 Observation, Candidate, Evidence, Verdict, RowResult; 3.3 all records.
- **Conflict:** `Verdict.evidence references` cannot resolve because Observation, Candidate and Evidence have no Id. `Evidence` is "for one field on one receipt" but has neither a receipt key nor a field key. `RowResult.Row` has no defined key. Only SourceFile, Claim and ReceiptCrop have an Id, and only in 7.1.
- **Fix:** Give every record an `id`. Add `Evidence.crop_id` and `Evidence.field`. Define references as ids and validate them in the loader tests (task 2.10).

### A3. 3.3 and 7.1 disagree on Observation, Evidence and Verdict contents
- **Severity:** important
- **Where:** 3.3 and 7.1.
- **Conflict:** Observation: 7.1 adds `normalized value` and `variant id`, and renames three fields ("value exactly as read" / "raw value", "position box" / "box", "nearby label words" / "label context words"). Evidence holds observations in 3.3 but candidates in 7.1. Candidate does not appear in 3.3 or in the 3.1 flow diagram (Observation goes straight to Evidence). Verdict gets a plain-language note only in 7.1.
- **Fix:** Make 7.1 the single source of truth. Regenerate 3.3 from it, or delete 3.3's field lists and point to 7.1. Add Candidate to 3.1 and 3.3. State the nesting once: Observation is within Candidate, which is within Evidence.

### A4. The raw OCR word record is not defined
- **Severity:** important
- **Where:** 6.1 (adapter output) against 3.3 and 7.1 Observation.
- **Conflict:** 6.1 has adapters return "words with box, text, engine confidence, channel name, variant id". `Observation` requires a `field name`, which a bare word does not have until the field finder assigns it. The blueprint calls both things "Observation".
- **Fix:** Add an `OcrWord` record (`text`, `box`, `confidence`, `channel`, `variant_id`, `crop_id`) to 7.1. `Observation` is then built from OcrWord plus a field assignment (task 7.24).

### A5. Records that later steps need are missing from both lists
- **Severity:** blocker
- **Where:** 3.3, 7.1; needed by 15.1 ("matches exactly one receipt"), R7, R10, R11, 14.1 to 14.3, 5.8, 3.2 Case store.
- **Conflict:** There is no record for:
  - the matcher's output (receipt-to-row assignment, score, group, ambiguity, proposed split)
  - bank statement lines (date, description, debit, credit, balance) and statement matches
  - typed number labels detected beside receipts (5.8, which 14.1 step 1 uses first)
  - a receipt date and merchant name (used by R6, R10 and 14.1 step 2)
  - the duplicate key (supplier PIN, invoice number, total)
  - officer decision and audit entry (3.2 says the Case store holds them)
- **Fix:** Add `MatchResult`, `StatementLine`, `ReceiptLabel`, `DuplicateKey`, `OfficerDecision`, `AuditEntry`. Add `date` and `merchant` as field names alongside invoice number, PIN and total (see C1).

### A6. ReceiptCrop has no gate result and no document-type enumeration
- **Severity:** important
- **Where:** 3.3 ReceiptCrop, 7.1 ReceiptCrop; 5.18, 5.19 (gate), R12, 8.4.
- **Conflict:** 5.18 produces a tag (good, weak, poor) and 5.19 stops crops with Q_LOW or HANDWRITTEN. The record holds only scores. 3.3 lists four document types (receipt, invoice, statement, mobile confirmation), 8.4 defines about a dozen, and R12 needs an explicit "unknown". 3.3 says "guess" and 7.1 does not.
- **Fix:** Add `quality_tag`, `gate_status` (passed, stopped) and `refusal_code` to ReceiptCrop. Define one `DocType` enum shared by 3.3, 7.1, 8.4 and R12, including `UNKNOWN`. Drop "guess".

### A7. ClaimRow cannot hold what the sum checks and completeness rule need
- **Severity:** important
- **Where:** 3.3 and 7.1 ClaimRow; R4 (15.3); 4.13, 4.14, 4.16, 4.18 (cited).
- **Conflict:** ClaimRow has a single "category, amount". 4.13 reads "category amounts" (plural) and 4.14 reads row totals, and R4 compares a row total with its category cells. Neither definition has a list of category cells or a row total as written. 4.18 parses "6,7,no" into a reference list and 4.16 allows an "unclear" date, but ClaimRow has no field for either.
- **Fix:** Replace `category, amount` with `category_amounts: list[(category_code, Money)]` and add `row_total_as_written`, `receipt_refs: list`, `no_receipt_markers: list`, and `date` as `Date | UNCLEAR`.

### A8. Report against ClaimResult
- **Severity:** important
- **Where:** 3.3 Report; 7.1 ClaimResult; 6.2 (versions), 7.3 and R13 (unvalidated note), 17.1.
- **Conflict:** They are two names for the final record with different contents. 3.3's Report has no config version (6.2 requires it), no orphans and no refused files. 7.1's ClaimResult has no summary counts, no officer decisions (17.1 puts them in the report), no unvalidated-profile flag (R13 and 7.3 require a visible note) and no claim-level combined outcome (see E6).
- **Fix:** Keep one record, `ClaimResult`. Add `profile_validated: bool`, `counts`, `officer_decisions`. Describe the Report as a rendering of ClaimResult.

### A9. Minor record differences
- **Severity:** minor
- **Where:** 3.3 and 7.1 SourceFile, Claim, ClaimRow, Money.
- **Conflict:**
  - SourceFile has "how accepted or why refused" in 3.3 but `status` plus `refusal reason` in 7.1, and the reason type is not tied to the ReasonCode enum.
  - Claim has `Id` and "as written" only in 7.1, and it is not stated whether the totals are `Money` or raw text.
  - `Claim.currency` duplicates the currency inside every `Money`.
  - ClaimRow says `category` in 3.3 and `category code` in 7.1.
  - Money exists only in 7.1.
- **Fix:** Type `refusal_reason` as a ReasonCode. State that totals as written are `Money`. Either remove `Claim.currency` or add a validation rule that every Money in the claim carries it (S5 allows a per-row currency, so decide which). Add Money to 3.3.

---

## B. Reason codes: Part 3.4 against where they are produced

| Code | Defined in 3.4 | Produced by | Status |
|---|---|---|---|
| Q_LOW | yes | gate 5.19; 15.2 example | No rule turns it into a verdict (B6). Definition says "at that field", the gate works per crop. |
| NO_CANDIDATE | yes | 8.2 step 5 (PIN only) | Not stated for total or invoice number. Overlaps Q_LOW (B5). |
| AMBIGUOUS | yes | **nothing** | Never produced (B2). |
| CHANNEL_CONFLICT | yes | 13.4, 13.6, R9 | Used for an arithmetic conflict, which the definition does not cover (B5). |
| INSUFFICIENT_EVIDENCE | yes | 13.6 PIN row; implied for total and invoice | OK. |
| MATCH_AMBIGUOUS | yes | 14.1 step 4, 14.3, 8.5 | No R-rule owns it (B6). |
| NO_RECEIPT | yes | 14.1 step 6; R7 by implication | Outcome for a row with a stated reason is undefined (E5). |
| ORPHAN_RECEIPT | yes | 14.1 step 6; R7 by implication | No claim-level Verdict to carry it (B6). |
| FORMAT_UNKNOWN | yes | 4.3, 4.11, 8.4, R12 | Used for three different things (B5). |
| PARSE_FAIL | yes | 4.3 | OK (intake only). |
| DUPLICATE | yes | R11, 14.2 | Outcome not stated (B6). |
| HANDWRITTEN | yes | 5.19, 8.4 | OK. |

### B1. REFUTED and CONFIRMED carry no reason codes
- **Severity:** blocker
- **Where:** 3.4 ("UNDECIDED. Always carries a reason code"); 7.1 Verdict ("reason code"); 15.2.
- **Conflict:** Every code in 3.4 explains an abstention or a refusal. None explains REFUTED. `Verdict.reason code` is listed without saying whether it is optional, so a REFUTED verdict for a wrong total, wrong PIN, failed sum or missing statement debit has no code to carry. The report and the officer screen (17.1: "each with its reason code in plain words") need one.
- **Fix:** Make `reason_code` required on non-CONFIRMED verdicts and add a REFUTED code set, at minimum `VALUE_MISMATCH`, `PIN_ABSENT`, `PIN_SUPPLIER_ONLY`, `SUM_MISMATCH`, `DATE_INVALID`, `CURRENCY_MISMATCH`, `NO_DEBIT`, `COST_CENTRE_INVALID`, `LABEL_MISMATCH`. Set `reason_code = None` for CONFIRMED and enforce it in the enum tests (tasks 2.3, 2.10).

### B2. AMBIGUOUS is defined but never produced
- **Severity:** important
- **Where:** 3.4; no step in 13.2, 13.3, 13.6 or 15.3 assigns it.
- **Conflict:** The definition ("several plausible values found and rules cannot choose") describes exactly what 7.8 (total ranking) and 7.9 (PIN sorting) can produce, but neither step says what happens on a tie. 8.3's amount-format ambiguity says "return UNDECIDED" with no code.
- **Fix:** In 7.8 and 7.9, add "a tie for first rank yields UNDECIDED (AMBIGUOUS)". Reuse AMBIGUOUS for the ambiguous separator case in 8.3 and for the open-versus-closed disagreement suggested in C9.

### B3. Outcomes are produced with no code defined
- **Severity:** important
- **Where:** R4, R5, R6, R8, R10, R13 (15.3); 13.5; 9.4 and 4.16 (cited).
- **Conflict:** These steps produce an outcome with no code:
  - Sum failures (R4, R5, S1 to S8): REFUTED.
  - R6 date sanity: 9.4 says "Flagged", 4.16 "unclear".
  - R8 cost centre missing or invalid.
  - R10 statement with no debit: "REFUTED or UNDECIDED".
  - R13 unvalidated profile: only a "visible note".
  - 13.5 plausible OCR-error mismatch: "UNDECIDED with a note".
  - R2 currency differs.
  - 9.4 claimed invoice number equal to the receipt number: "label mismatch".
  - 9.4 advance cell unreadable: UNDECIDED.
- **Fix:** Add `CONFUSABLE_MISMATCH` (13.5), `DATE_UNCLEAR`, `CLAIM_VALUE_MISSING` (for example no claimed invoice number, see C4), `PROFILE_UNVALIDATED` (as a note code, not an outcome), plus the REFUTED codes from B1. State that "Flagged" and "label mismatch" are not outcomes. Map each to one code.

### B4. No precedence when several codes apply
- **Severity:** important
- **Where:** 15.2 ("one primary reason code"); 9.6 (determinism).
- **Conflict:** A blurred PIN region can be Q_LOW, NO_CANDIDATE and INSUFFICIENT_EVIDENCE at once. 15.2 requires exactly one primary code and 9.6 requires the same input to give the same output, but no order is given.
- **Fix:** Add an ordered list in config, for example `PARSE_FAIL > FORMAT_UNKNOWN > HANDWRITTEN > Q_LOW > NO_RECEIPT > MATCH_AMBIGUOUS > CHANNEL_CONFLICT > CONFUSABLE_MISMATCH > AMBIGUOUS > NO_CANDIDATE > INSUFFICIENT_EVIDENCE`. Keep the rest as "secondary codes" in the missing-evidence list (15.2).

### B5. Definitions in 3.4 do not match how the codes are used
- **Severity:** important
- **Where:** 3.4 against R9, 13.4, 8.2 step 5, 5.19, 4.3, 4.11, 8.4.
- **Conflict:**
  - CHANNEL_CONFLICT is defined as "independent readers disagree" but R9 and 13.4 use it when arithmetic fails.
  - Q_LOW is defined "at that field" but 5.19 applies it per crop.
  - NO_CANDIDATE is paired with "image is poor" in 8.2 step 5, which overlaps Q_LOW. Poor crops are stopped earlier by the gate anyway.
  - FORMAT_UNKNOWN is defined for the document type, but is also used for an unsupported file type (4.3) and an unmatched claim form layout (4.11). Those cause a refusal, while an unknown document type in 8.4 gives UNDECIDED.
- **Fix:** Add `ARITH_CONFLICT`, or widen the CHANNEL_CONFLICT definition. Define Q_LOW as "region or crop", and restrict NO_CANDIDATE to "good quality but nothing found". Split FORMAT_UNKNOWN into `FILE_TYPE_UNKNOWN`, `DOC_TYPE_UNKNOWN` and `LAYOUT_UNKNOWN`.

### B6. Upstream codes, matching codes and claim-level codes have no path into a Verdict
- **Severity:** important
- **Where:** 15 intro; 15.2 ("quality gate abstains first"); R7, R11; 7.1 ClaimResult (orphans).
- **Conflict:** The decision layer may not import quality or OCR code (15), yet it must turn a gate result (Q_LOW, HANDWRITTEN) and intake refusals into verdicts. No R-rule covers them. MATCH_AMBIGUOUS has no rule. ORPHAN_RECEIPT is about a receipt with no row, so it fits no RowResult. R11's outcome for DUPLICATE (REFUTED or UNDECIDED) is not stated.
- **Fix:** Add a rule R0 "input admissible": it consumes `ReceiptCrop.gate_status` (A6) and `SourceFile.status`, and yields UNDECIDED with the carried code. Assign MATCH_AMBIGUOUS, NO_RECEIPT and ORPHAN_RECEIPT explicitly to R7. Add a claim-level verdict list on ClaimResult. Say what R11 returns for a duplicate (recommend REFUTED for an identical file hash, UNDECIDED for a key match).

---

## C. Evidence policy (13.6) against rules R1 to R13 (15.3)

13.6 has three rows: company PIN, total, invoice number. The rules need more.

| Rule | Evidence it needs | Does 13.6 say how to get it? | Finding |
|---|---|---|---|
| R1 PIN | buyer PIN, position | Yes, partly | C5 |
| R2 amount | total, currency, per document type | Yes, partly; currency and non-receipt types missing | C3 |
| R3 invoice number | claimed number, label | Yes, but different wording | C4 |
| R4, R5 sums | exact cells | Not needed (exact) | E2 (scope) |
| R6 date | receipt date | **No** (no field, keywords or policy) | C1 |
| R7 completeness | match result | No policy needed, but no rule owns the codes | B6 |
| R8 cost centre | config list | Config list does not exist | D1 |
| R9 arithmetic | repeats, paid minus change, item sums | Only as a veto | C6 |
| R10 statement | statement lines, merchant, date | **No** (no task builds the table) | C7 |
| R11 duplicate | supplier PIN, invoice number, total | **No** (supplier PIN has no policy) | C1, C2 |
| R12 doc type | document-type keywords | Not referenced by 13.6 | C3 |
| R13 profile | profile validated flag | Note only | C5 |

### C1. No evidence policy for date, merchant and supplier PIN
- **Severity:** blocker
- **Where:** 13.2 (7.19 finds only invoice number, PIN, total), 13.6, 7.2 (Evidence policy); R6, R10, R11 (15.3); 14.1 step 2 and 14.3 (cited).
- **Conflict:** Rules and matching use the receipt date, merchant name and supplier PIN. The finder (7.19) does not find them, Part 8 has no date or merchant keyword group, and 13.6 has no rows for them. R6 and R11 cannot run, and matching by "amount, date and merchant" has no source for two of the three.
- **Fix:** Extend field finding (7.19) and 13.6 with rows for `date`, `merchant` and `supplier_pin`. Date: an exact parse using the profile's date order, two independent sources or native text or QR. Any of them not met gives UNDECIDED. Add the matching keyword groups to Part 8 and tasks to 13.7.

### C2. R11 cannot say "no duplicate" on unread keys
- **Severity:** important
- **Where:** R11; 14.2 (cited); 13.6.
- **Conflict:** The duplicate key is supplier PIN plus invoice number plus total. If any part is unread or unconfirmed, the key cannot be compared, so "no duplicate found" would be an unsupported "pass". Missing a duplicate means the same receipt is claimed twice, which is a silent error.
- **Fix:** State R11 as three-valued. Not a duplicate is CONFIRMED only when all three key parts are CONFIRMED and none matches. An unconfirmed key gives UNDECIDED (INSUFFICIENT_EVIDENCE).

### C3. R2 has no currency evidence and 13.6's total row does not fit every document type
- **Severity:** important
- **Where:** R2 ("same currency"), R12; 13.6 Total row; 7.1 Money; 8.3 keyword groups (cited).
- **Conflict:**
  - Money equality needs a currency (7.1) and R2 requires it, but 13.6 says nothing about how currency is established when a receipt prints no currency word (8.3 allows none).
  - The total row requires a "strong total keyword" or "totals block". Statements and mobile confirmations have neither (8.3 uses "amount", "sent", "debited"), so for them CONFIRMED is only reachable through the QR, native-text or statement-debit shortcut.
  - 8.4 says some rules need a document type, but 13.6 does not say which keyword group applies to which type.
- **Fix:** Add a currency sub-rule to 13.6 (word or symbol within N boxes of the amount, otherwise UNDECIDED, no silent default from the profile). Make the total row reference "the keyword group configured for the document type". Have R12 gate R2 and R3 explicitly.

### C4. R3 and 13.6 disagree on which labels count; no rule for a missing claimed number
- **Severity:** important
- **Where:** R3; 13.6 Invoice number row; 8.1 (cited); 7.1 ClaimRow ("invoice number if present").
- **Conflict:** R3 accepts "one of the receipt's labeled numbers". 13.6 requires an "invoice-type label" (defined per document type in config, 8.1), and lets QR or native text confirm with no label at all. If the claim row has no invoice number (the field is optional in 7.1), no rule says what R3 returns, and 15.1 requires the invoice number CONFIRMED.
- **Fix:** Make R3 read 13.6: label must be in the document type's invoice-label group; QR or native text must still carry a matching label or field name. If the claimed number is absent, R3 returns UNDECIDED (`CLAIM_VALUE_MISSING`, from B3). State that such rows cannot reach CONFIRMED.

### C5. R1 against 13.6 (position wording and profile validity)
- **Severity:** important
- **Where:** R1, R13; 13.6 PIN row; 8.2 steps 3 to 5, 7.3 "Honest limit", 7.2 Company settings ("PIN(s)").
- **Conflict:**
  - 13.6 says "no supplier-only appearance", which can mean "not only in a supplier position" or "not in a supplier position at all". A PIN in both positions is not addressed.
  - R13 only adds a visible note for an unvalidated profile, but 7.3 says a wrong format must lead to UNDECIDED and never CONFIRMED.
  - Company PIN may be plural (7.2), and it is not said whether any one suffices.
- **Fix:** Reword 13.6: "the company PIN appears in a buyer or unknown position and does not appear in a supplier position". A PIN in both positions gives UNDECIDED (AMBIGUOUS). For an unvalidated profile, either cap PIN at UNDECIDED (`PROFILE_UNVALIDATED`) or state that exact match to the stored PIN is enough. Pick one, and update R13. Say that any listed company PIN suffices.

### C6. R9 and 13.4: arithmetic as evidence, veto or both
- **Severity:** important
- **Where:** 13.4; 13.6 Total row ("no failing arithmetic check"); R9; 15.1.
- **Conflict:** 13.4 lists repeated amounts, paid minus change and item sums as "independent supports". In 13.6 they only act as a veto. R9 is also a separate rule producing its own Verdict, but 15.1 does not list R9 among the checks needed for CONFIRMED. So arithmetic is counted inside the total verdict (13.6) and again outside it (R9), or dropped by 15.1. "Not computable" (no items on the receipt) is not distinguished from "failing".
- **Fix:** Choose one. Recommended: arithmetic is a veto only, embedded in the total verdict of 13.6; R9 becomes the note generator for it and is not a separate 15.1 input. Change the 13.4 heading to "vetoes and cross-checks". Define "no failing check" as "no computable check disagrees", with an absent check treated as neutral.

### C7. R10 and "statement debit alone"
- **Severity:** important
- **Where:** 13.6 Total row; R10; 8.5 and 9.4 (cited); 14.3 (cited); 13.7.
- **Conflict:** 13.6 lets a statement debit alone confirm the receipt total, with no date window or merchant match. R10 requires amount, date window and merchant. 8.5 says a statement is proof of payment, not of the invoice, and 9.4 expects a hotel invoice larger than the card charge (partial payment). No task in Phase 7 or 8 parses the statement transaction table, so R10 has no input.
- **Fix:** Remove "statement debit" from the total row. Keep it as R10's own evidence (card claims only). Add a task in 13.7 to find the statement table by its headers and produce `StatementLine` records (A5).

### C8. 13.6 conditions are not expressible in the config defined in 7.2
- **Severity:** important
- **Where:** 13.6; 7.2 Evidence policy; 2.7.
- **Conflict:** 7.2 says the policy file holds "how many independent sources", "which sources count as independent" and "which combinations are never enough alone". 13.6 also requires keyword position, no failing arithmetic check, and no supplier-only appearance. Those cannot be expressed as counts, so they would be hard-coded, against the "no hard-coded thresholds" rule.
- **Fix:** Extend the policy schema in 7.2: per field `required_sources`, `independence_groups`, `required_context` (label groups, blocks), `vetoes` (arithmetic, supplier position, contradiction), `single_source_allowed` (list, with the conditions above).

### C9. 13.1 and 13.6: open and closed agreement
- **Severity:** important
- **Where:** 13.1 ("CONFIRMED only when open finding and closed verifying agree"); 13.6.
- **Conflict:** 13.6 does not mention the open finder at all. The QR or native-text branch bypasses both directions. So the closed search can find the claimed amount beside "total" while the open finder ranks a different amount first (for example tendered cash), and 13.6 still returns CONFIRMED.
- **Fix:** Add to each 13.6 row: "and the open finder's top-ranked candidate for this field equals the verified value; a different top candidate gives UNDECIDED (AMBIGUOUS)". For QR or native text, require that the field name or label also matches.

### C10. Independence defined two ways
- **Severity:** important
- **Where:** 13.6 ("different channel families, or a non-OCR source"); glossary "Independent"; 13.4 (PIN row: "a second whitelisted re-read that agrees"); 7.17.
- **Conflict:** Channel E re-reads the same pixels with Tesseract or Paddle, at a location supplied by channel A. It is not a different family, yet 13.4 lists it as an independent support. Multiple image variants of the same crop, and two Paddle wrappers, are the same source too (12.1 already says the wrappers are "almost one channel").
- **Fix:** Define `independence_group` per adapter in config (`paddle`, `tesseract`, `qr`, `native`). Channel E belongs to the group of the engine it uses. Variants of one crop count once per group. Two sources are independent only if their groups differ. Remove the E re-read from the list of independent supports.

---

## D. References, layout and config

Verified to exist: tasks 2.1 to 2.10, 7.1 to 7.29, 9.1 to 9.11, K.1 to K.10, 6.6, 6.10; "see 13.5"; Parts 8, 16, 19, 20; the master-checklist ranges for P2, P6, P7 and P9. The problems below are the ones that do not resolve or that are ambiguous.

### D1. R8 refers to a cost-centre list that no config defines
- **Severity:** important
- **Where:** R8 ("valid against a list in config"); 7.2; 6.1 config layout.
- **Conflict:** 7.2 lists the config files and none holds cost centres or projects.
- **Fix:** Add a `cost_centres` file to 7.2 and 6.1, and cover it in the config loader tests (task 2.9).

### D2. The 7.2 config inventory is incomplete against later steps
- **Severity:** important
- **Where:** 7.2 (Keyword files, Thresholds, Company settings) against later steps.
- **Conflict:** 7.2 says it defines every config once, but these are referenced later and are missing from it:
  - exclusion label lists (K.2)
  - keyword group priority numbers (K.4)
  - document type to invoice-label mapping (8.1)
  - invoice-number allowed characters (7.5)
  - claim-period tolerance (R6, S7)
  - matching ambiguity margin (8.4)
  - glare, completeness and handwriting thresholds (5.17, 5.19, 8.4)
  - segmentation area and aspect limits (5.4)
  - upscale target character height (5.15)
  - the "usable native text" criterion (4.4)
  - LLM on/off (10.11)
- **Fix:** Add them to 7.2, or state that 7.2 is a summary and each Part owns its config with the loader (2.9) registering it.

### D3. The silent-error "ceiling you set" is undefined
- **Severity:** important
- **Where:** 15.2 ("stays at the ceiling you set"); 7.2 Thresholds; 19.2 (cited, "zero").
- **Conflict:** No config value or doc defines the ceiling, and the release gate says zero.
- **Fix:** Add `silent_error_ceiling` (default 0) to the policy config. Say that thresholds may be loosened only while the locked-set silent-error count stays at that value.

### D4. Component map (3.2) does not match the design
- **Severity:** minor
- **Where:** 3.2 against 4.2, 7.24, 12.1, 14.2, 14.3.
- **Conflict:** "Observation builder" appears in the "Talks to" column but is not a component. Channel E (field re-read) is not a component. Duplicate detection, statement matching and sum checks have no component (Claim parser is described as only reading the Excel, but step 2 in 4.2 also runs the sum checks).
- **Fix:** Add rows for Observation builder, Field re-read, Sum checker, Duplicate detector and Statement matcher, and say which package owns each.

### D5. Task IDs and section numbers collide
- **Severity:** minor
- **Where:** 7.1 to 7.4 (sections in Part 7) against tasks 7.1 to 7.4 (13.2); 9.1 to 9.5 (sections in Part 9) against tasks 9.1 to 9.5 (15.4); 8.1 to 8.6 against tasks 8.1 to 8.10; 5.3 and 6.2 and 6.3 against tasks 5.3, 6.2, 6.3; 2.1 and 2.2 against tasks 2.1 and 2.2.
- **Conflict:** "7.2" is either the configuration section or the document-type step, and "Part 7" is the data model while "Phase 7" is Part 13. Tasks 7.1 to 7.17 (13.2, 13.3) and 7.18 to 7.24 (13.7) also describe the same work twice, so two boxes would be ticked for one step.
- **Fix:** Prefix task IDs (`T7.2`), or number sections with a section sign (`§7.2`). Use "Phase" only for the build order and "Part" only for the document. Merge or cross-reference the duplicated task lists.

### D6. "Sample forms" are cited but not identified
- **Severity:** minor
- **Where:** 7.2 (Form layout files); task 2.6 ("Kenyan card claim sample", "Ethiopian cash claim sample").
- **Conflict:** The samples are not located or described, and the project rule is synthetic data only.
- **Fix:** Name them (path under `docs/` or `synthetic/`) and say they are invented reconstructions, or list the layout fields directly in the doc.

### D7. Import restrictions are stated four different ways
- **Severity:** important
- **Where:** 3.1 ("any OCR library"); 15 intro ("OCR, image or screen"); 9.10 ("OCR, image, quality or screen"); Phase 1 exit check; 6.1 ("NO OCR code").
- **Conflict:** None of the lists names `render/`, `segment/`, `prepare/`, `llm/`, `store/`, `intake/`, `verify/` or `fields/`, although the decision layer "only sees Observation records" (3.1). A blacklist test (9.10) would pass if the decision layer imported `llm/` or `store/`.
- **Fix:** Replace the blacklist test with an allowlist: the decision package may import only the records, enums and config-loader modules and the standard library. Use the same sentence in 3.1, 6.1, 6.2, 9.10 and 15.

### D8. 7.3 and 8.2 differ on tax ID details, and currency words are defined twice
- **Severity:** minor
- **Where:** 7.3 Ethiopia, Uganda, Rwanda, Tanzania (VRN); 8.2 format table; 7.2 Country profile against 8.3 currency words.
- **Conflict:** 7.3 says Ethiopia has "a fixed digit count" and Uganda and Rwanda are "numeric", while 8.2 says "commonly ten digits" (Ethiopia, Uganda) and "nine digits" (Rwanda). 7.3 says VRN is "not the buyer identity", but 8.2 lists it as a buyer marker and a generic PIN label. Currency codes and symbols sit in the country profile (7.2), and currency words are also listed in 8.3.
- **Fix:** Keep tax ID patterns and currency words in the country profile only. Have 8.2 and 8.3 reference them. Decide VRN once (recommend supplier or neutral marker only).

### D9. Checked and fine
- Every task range in the master checklist (19) that falls in these four Parts exists.
- The Part 7 to Part 13 to Part 15 flow of definitions (Money, Observation, Verdict, RowResult) resolves, apart from the gaps listed above.

---

## E. Combining outcomes: 15.1 against 13.6

### E1. 13.6 has no evaluation order
- **Severity:** blocker
- **Where:** 13.6 (table plus last paragraph); 13.1 ("nothing contradicts them").
- **Conflict:** The CONFIRMED column can be satisfied while a reliable reading contradicts the claim. Example: A and B read the claimed total beside "total", and the native text channel reads a different total. Row one says CONFIRMED, the last paragraph says CHANNEL_CONFLICT. Nothing says which is checked first, so a wrong CONFIRMED is possible.
- **Fix:** State the order in 13.6: (1) input admissible (R0); (2) any reliable reading contradicting the claim, or two contradicting each other, is evaluated first (REFUTED or CHANNEL_CONFLICT); (3) only then test the CONFIRMED policy; (4) otherwise UNDECIDED with the primary code from B4. Add a truth-table test for each of the four steps (task 9.2).

### E2. "Required check" is undefined in 15.1
- **Severity:** blocker
- **Where:** 15.1 (CONFIRMED and REFUTED bullets); R1 to R13.
- **Conflict:** CONFIRMED lists PIN, total, invoice number, exactly one receipt, and "the sum checks that involve the row". REFUTED triggers on "any required check". R6, R8, R9, R10, R11, R12 and R13 appear in neither clause, so a row with a duplicate receipt (R11), a card line with no debit (R10) or an unknown document type (R12) could still be CONFIRMED. 9.4 says a card line with no debit is never CONFIRMED. "Sum checks that involve the row" is also unclear: S2 to S4 (column, grand total, balance) involve every row.
- **Fix:** Replace the prose with a matrix in 15.3 with columns `rule`, `scope` (row, receipt, claim), `blocks CONFIRMED unless CONFIRMED`, `may force REFUTED`. Recommended: R1, R2, R3, R4 (row part), R7, R10 (card claims), R11, R12 block CONFIRMED. R6 blocks it for date after the claim date. R5 and S2 to S4 are claim-level verdicts shown in the summary, not row blockers. R8, R13 are notes unless config says otherwise. Confirm this scoping with the owner, since it changes what "CONFIRMED" means for a row.

### E3. Absence-based REFUTED and "reliable" are not in 13.6
- **Severity:** important
- **Where:** 13.6 (REFUTED only from a contradicting reading); 8.2 step 5, 15.2, 9.4 ("REFUTED on a good image"); 13.5.
- **Conflict:** 8.2, 9.4 and 15.2 make a field "truly absent on a good image" REFUTED. 13.6 gives REFUTED only when a reliable reading contradicts. "Reliable" and "truly absent" are defined nowhere, while 2.1 lists channel A's low recall as a known weakness, which looks like absence.
- **Fix:** Define in config `reliable_reading` (quality tag good at the region, engine confidence at least a threshold, mismatch not explained by the confusion table) and `reliable_absence` (region tag good, at least two independence groups read the region, all variants tried, channel E run, no candidate). Absence on anything less gives UNDECIDED (NO_CANDIDATE). Apply per field, and say explicitly which fields may be REFUTED by absence (recommend PIN only).

### E4. Matching failure against field verdicts
- **Severity:** important
- **Where:** 15.1; 14.1 (cited); R7.
- **Conflict:** If a row is MATCH_AMBIGUOUS or has no receipt, R1 to R3 have no single receipt to read. A field-level REFUTED against a possibly wrong receipt would be a false alarm, and 15.1 does not say matching outranks it.
- **Fix:** In 15.1, compute R1 to R3 only against the single matched receipt. If matching is MATCH_AMBIGUOUS or NO_RECEIPT, the row is UNDECIDED with that code, and R1 to R3 are not evaluated or are shown as "not evaluated".

### E5. Rows with a stated no-receipt reason or a group of receipts have no outcome
- **Severity:** important
- **Where:** R7; 15.1 ("matches exactly one receipt"); 3.4 (MATCH_AMBIGUOUS); 14.1 step 5 (cited).
- **Conflict:** R7 accepts "a stated reason" instead of a receipt, but 15.1 needs one matched receipt to CONFIRM, and NO_RECEIPT is defined only for rows with no stated reason. 3.4 defines a row with several receipts as MATCH_AMBIGUOUS, while 14.1 matches groups deliberately and never auto-accepts a split.
- **Fix:** Add `NO_RECEIPT_STATED`: such a row is UNDECIDED (never CONFIRMED, since nothing was verified) with the reason text shown. Amend 3.4: MATCH_AMBIGUOUS covers only unresolved choices, and a proposed group is UNDECIDED with a note "split proposed".

### E6. The claim-level combiner is not specified
- **Severity:** minor
- **Where:** 15.4 task 9.4 ("claim combiner"); 15.1; 7.1 ClaimResult.
- **Conflict:** 15.1 only combines rows, and ClaimResult has no claim-level outcome field.
- **Fix:** Say the claim has no single outcome, only counts per outcome plus the claim-level verdict list (B6), and remove "claim combiner" or define it.

### E7. Confusion-corrected matches against "plausible mismatch is never CONFIRMED"
- **Severity:** important
- **Where:** 7.12, 7.15, 8.2 PIN table (cited) against 13.5, 7.26; 9.4 (cited: 3 for 8, 5 for 6).
- **Conflict:** 7.12 and 7.15 allow a confusion-aware match, and 7.15 fixes letters and digits by position and then requires an exact match. 13.5 says a plausible-error mismatch is never CONFIRMED. Both can apply to the same read. The confusion table in 13.5 also lacks 3 and 8 and 5 and 6, which 9.4 plants as faults.
- **Fix:** Define it precisely. A correction that only fixes a slot-type violation (a letter in a digit slot) is allowed and recorded as `corrected`. A match reached by substituting between two characters valid in the same slot is never CONFIRMED and gives UNDECIDED (`CONFUSABLE_MISMATCH`). A corrected read counts as a source only if the independence groups behind it agree on the corrected string. Add the missing pairs to the table.

### E8. REFUTED and UNDECIDED together
- **Severity:** minor
- **Where:** 15.1 last bullet; 15.2.
- **Conflict:** "A REFUTED result never hides an UNDECIDED one" is a display rule, but RowResult stores only a combined outcome and a verdict list. It is unclear whether REFUTED always wins as the combined outcome.
- **Fix:** State the order: REFUTED, then UNDECIDED, then CONFIRMED, for the combined outcome, with all verdicts listed. Add the case to the truth table (9.2).

---

## Top 5 fixes, most important first

1. **Freeze the decision-layer input contract (A1, A2, A5, A6, B6).** Add the missing record fields and records (party role, origin, crop id, ids on every record, match result, statement line, duplicate key, gate result) and an R0 "input admissible" rule. Phase 9 is built on hand-made observations before OCR exists, so these must be fixed in Phase 2. Nothing else in the decision layer can be tested honestly until they are.
2. **Write the row-combination matrix and evaluation order (E1, E2, E4, E5, E8).** One table: each rule, its scope, whether it blocks CONFIRMED, whether it can force REFUTED. One ordered evaluation: admissible, then matching, then contradiction, then CONFIRMED policy, then UNDECIDED. This closes the path by which a duplicate, an unmatched statement line or a conflicting reading can end up CONFIRMED.
3. **Rewrite 13.6 as an ordered, config-expressible policy (C3, C4, C6 to C10, E3, E7).**
   - Require open and closed agreement.
   - Define independence groups.
   - Drop "statement debit alone".
   - Require a label for QR and native text.
   - Make arithmetic a veto.
   - Add the currency rule.
   - Define "reliable" and "reliable absence".
   - Extend the 7.2 policy schema so none of this is hard-coded.
4. **Complete the reason-code taxonomy (B1 to B5).** Add REFUTED codes and the missing UNDECIDED codes, give AMBIGUOUS a producer, add a precedence order for the single primary code, and split FORMAT_UNKNOWN.
5. **Add the missing evidence pipelines and config (C1, C2, C7, D1, D2, D3).** Add date, merchant and supplier PIN to field finding and policy. Add a task for parsing statement tables. Add the cost-centre list, the missing thresholds and `silent_error_ceiling` to config. Without them R6, R8, R10 and R11 cannot run, and matching by date and merchant has no input.
