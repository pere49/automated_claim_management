# A_STATE: audit progress and handover

**Status: complete.** `docs/audit/A_safety.md` is written and contains all six required sections plus the unverified list and the low-confidence list. Nothing was truncated for context; this file records coverage and what a next session should not have to redo.

## Inputs

| Input | Status |
|---|---|
| `docs/blueprint.md` Parts 3, 7, 8, 12, 13, 14, 15 | Read in full, including every keyword table in Part 8. |
| Supporting sections consulted | §1.2, §1.3, §2.1, §2.2, §4.2, §4.3, §5.18–5.20, §6.2, §9.2, §9.4, §11.2, §11.4, §17.1–17.2, §18.1, §19.1–19.2, §21.1–21.3, Part 22 glossary. |
| `docs/reviews/01_consistency.md` | Read. Treated as leads, not truth. |
| `docs/reviews/decisions.md` | **MISSING.** Does not exist in the repo. `docs/reviews/` contains only `01_consistency.md`. Nothing was assumed about its contents. |
| `CLAUDE.md` | Read. |

## Condition of the blueprint at audit time

The Session 1 fixes are already applied to `blueprint.md` (file is 5,400 lines, 257 task boxes). The audit was therefore run against the **current** text, not against the proposed text. The brief's fallback clause ("if the fixes are not yet in") did not apply.

**Conflict of interest, recorded:** the same assistant applied the Session 1 edits and then audited them. Eleven findings attack clauses written in that session and are tagged `[OWN]` in A_safety.md: S11, S18, S19, S22, S26, S27, S32, S33, S34, S39, S41. The two structures most in need of a fresh reviewer are §13.6's four-step evaluation order and the §15.3 scope matrix, both authored in Session 1.

## Coverage

- Task 1 (path to CONFIRMED): 11 blocking conditions enumerated with evidence and single point of failure.
- Task 2 (scenarios): 46 scenarios, S01–S46, against a required minimum of 30. Every category in the brief is covered; the mapping is below.
- Task 3 (independence audit): 12 policy lines assessed. Conclusion: no CONFIRMED-producing line is independent above the character-recognition layer.
- Task 4 (defence testing): top 10 ranked, each with a detective control, a preventive control and a stated cost in false UNDECIDED. Fix families F1–F21 each name what they remove or merge (§4.1 ledger).
- Task 5 (self-attack): 8 attacks on own fixes, with revisions and explicit drops. One fix-ordering constraint found (F11 before F2). One new record gap found during self-attack (no field for "a code was present but undecodable").
- Tasks 6–8: 5 questions with recommended answers, 9 unverified items with checks, 3 least-confident findings.

## Brief's required categories → scenario IDs

| Required category | Covered by |
|---|---|
| Look-alike digits 3/8, 5/6, 1/7, 0/O | S02, S03, S04, S05 |
| Thousand/decimal separator errors | S06, S07, S08 |
| Merged or cropped receipts | S10, S11, S12 |
| PIN in the wrong block | S13, S14, S16 |
| Supplier PIN equal to company PIN | S15 |
| Amount beside a wrong keyword | S17, S18, S19, S20, S24 |
| Repeated numbers | S22 |
| Currency missing or mismatched | S09 |
| Day/month swap | S29 |
| Partial payments | S18 |
| Credit notes and refunds | S20, S21 |
| Duplicates within and across claims | S33, S34, S35 |
| Statement debit on the wrong claim line | S30, S31 |
| Hidden text layer in a scanned PDF | S28 |
| QR payload disagreeing with printed text | S25, S26, S27 |
| Both OCR families sharing an error | S02, S03, S04 |
| Quality gate passing a bad region | S01, S10 |
| Formula stored value vs recomputation | S37, S38 |
| Rows tied to several receipts | S33, S36 |
| Keyword collisions accept vs exclusion | S43, S44 |
| Misleading officer-facing display | S40, S41 |

## The finding that matters most for the test suite

Every planted fault in §9.4 is planted in the document or the spreadsheet, on a receipt the generator draws correctly, with correct OCR assumed. No fault makes the reading drift *toward* the claimed value. That single gap hides scenario classes S02–S04, S06–S11, S17 and S29. Any next session working on Phase 3 should start there.

## Not done, and deliberately so

- No commands run, no OCR, no downloads, no edits outside `docs/audit/`.
- No frequency claims accepted as fact about real receipts, tax formats, library behaviour or engine speed; all nine are in the UNVERIFIED table with a check.
- No fix proposed that trades a wrong CONFIRMED for higher automation. Where a fix collapses the confirmed rate (F1, F3, F14), the cost is stated and escalated as Q1 rather than absorbed by weakening a rule.

## Recommended next actions, in order

1. Produce or locate `decisions.md`, then re-check S13, S18, S32 and Q1 against it.
2. Answer Q1 (form change vs. dropping R3). Nothing downstream is worth building until the confirmed path can exist at all.
3. Answer Q2 and Q3 — both change §13.6 and §14.2 text directly.
4. Extend §9.4 with reading-drift faults before Phase 3 is built.
5. Apply fix ordering F11 → F2; do not implement F2's QR leg first.
6. Have a reviewer who did not write Session 1 re-read §13.6 and the §15.3 matrix.
