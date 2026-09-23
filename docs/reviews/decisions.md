# Decisions log

**Status: BINDING.** Blueprint, code and reviews follow this file. Where this file and `docs/blueprint.md` disagree, this file wins and the blueprint is corrected. If a decision here turns out to create a hole, raise it as a question — do not quietly work around it.

**Owner** = the project owner's decision, taken in conversation.
**Derived** = a consequence I worked out while applying an owner decision. Derived entries bind in the same way, but they are the ones most worth challenging, because the owner has not separately confirmed each.

Revision 2. D4 and D6 were rewritten in this revision; the superseded text is noted inside each.

---

## D1 — What CONFIRMED means

**Owner.** A row is CONFIRMED when the PIN and every receipt's details match the claim form: for each receipt, the invoice number, the date and the total amount are the same as the corresponding entry in the .xlsx.

Anything else — a mismatch, a document that failed to open, or a match that fails because the OCR did not read the document properly — is not a system decision. It goes to manual check, and the claim is confirmed or declined only after a person looks at it.

**Lands in:** §1.2, §15.1, §15.3 matrix.
**Status:** partly applied.

---

## D2 — The officer decides last, in both directions

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

**Owner** (answering Q1), and implied by D1. Layouts 1 and 2 have no invoice number column, so under D1 nothing on them can pass. The third layout — one receipt per row, with an invoice number column — becomes the supported form.

Layouts 1 and 2 stay supported for parsing and sum checks; their rows report a missing claimed value and are never passed by the system. Under D2 the officer can still accept them by hand.

**Status:** not yet applied.

**Superseded, in part, by D1's later redefinition.** In the session that produced D9 onward, the owner redefined CONFIRMED itself as PIN plus each receipt's date and amount matching the Excel — explicitly dropping the invoice number, because the Excel format actually in use has no invoice number column ("ignore invoice number bc it is not in the excel"). That is a narrower requirement than D1's original wording, which listed invoice number, date and total. Under the redefined CONFIRMED, D7's premise — that a row without an invoice number can never pass — no longer holds: it can, on date and amount and PIN alone. D7's other point, that the form should eventually gain an invoice-number column, stands as a genuine improvement worth making, but is no longer a blocking requirement for reaching CONFIRMED. `docs/blueprint.md` §1 and §12 follow this redefinition. This entry is left in place, corrected, rather than deleted, so the reasoning that produced the original requirement is not lost.

---

## D8 — The duplicate key is built from read values

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

## Open, needing an owner decision

| # | Question | Why it cannot be derived |
|---|---|---|
| **O1** | **What anchors the total?** Under pure search-and-match, a claimed 30,000 that appears anywhere on a receipt matches — including as a deposit, a line item or a "balance due" on a 50,000 invoice. My proposed rule, doc-type-free: the matched amount must be **the largest amount on the receipt, or sit beside a total-type keyword**; otherwise YELLOW. That handles the part-paid hotel invoice correctly. Confirm or replace. | It is a question about what you want a part-payment to do, not an evidence question. |
| **O3** | Does the company hold a different tax ID per country, or one ID everywhere? D4 derives the country from which ID matched, so a single global ID breaks that derivation. | Depends on the company's actual registrations. |

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
| D7 Form carries invoice number | No |
| D8 Duplicate key from read values | No |
| D10 Document type does not gate | No |
| D11 Three flags | No |
| D12 One crop per match | No |
