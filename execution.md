# Plan: Wiring the Flet UI to the OCR Backend

## Context

- **Backend** (`description.md`): existing OCR/matching pipeline in `app/ocr/`, `app/layout/`, `app/matching/`, currently driven by a PySide6 GUI. No HTTP API exists yet. The reusable, framework-agnostic entry points are `OcrReader` (in `app/ocr/reader.py`), `group_rows` (in `app/layout/`), and `search_document` (in `app/matching/`). `StageError` (in `app/errors.py`) is the shared error type and must be converted to plain messages before reaching any UI.
- **Frontend** (`description_ui.md`): a Flet UI prototype (`main.py`, `uploader_view.py`, `verifier_view.py`, `manager_view.py`) currently backed by demo data in `claim_store.py`.
- **Goal**: replace the demo data path in `claim_store.py` with real calls into the OCR backend, without coupling the Flet UI to Qt-specific code (`MainWindow`, `DocumentSession`, `OcrWorker`, Qt signals — these must not be reused).
- **Flet version note**: target current Flet (1.0 line, currently ~0.85.x on PyPI). This is async-first: entry point is `ft.run(main)` with `async def main(page: ft.Page)`, event handlers can be `async def` and are typed as `ft.Event[Control]`, and background work should not block the event loop. This differs from older (0.2x-era) Flet tutorials that rely on purely synchronous handlers — don't follow those patterns.

---

## Step 0 — Decide the integration boundary

Two valid options; pick the first and only revisit the second if a real need for decoupling appears (separate web frontend, remote OCR, multiple UI clients):

1. **In-process (recommended, start here)**: import `app.ocr`, `app.layout`, `app.matching` directly inside the Flet app's process. No second server to run or monitor.
2. **Local HTTP microservice**: expose the backend via the FastAPI service `description.md` sketches (`POST /documents`, `POST /documents/{id}/process`, `GET /documents/{id}/results`, etc.), bound to `127.0.0.1` only, with Flet as an HTTP client.

Build Step 1 below in a way that is easy to move behind an HTTP layer later if needed — i.e., keep it as a pure function/class with plain-data inputs and outputs, no Flet imports inside it.

---

## Step 1 — Build a claim-processing service module

Create `app/services/claim_processor.py`. This is the **only** module the Flet views are allowed to call for OCR/matching — never `OcrReader`, `group_rows`, or `search_document` directly from view code, and never anything from `app/gui/*` (Qt-coupled).

Responsibilities:

- Start/reuse `OcrReader`, call `load_pages` + `read_page` per page.
- Run OCR output through `group_rows` to get `TextRow`s.
- Run `search_document` / `prepare_page` to get date/amount/PIN match results.
- Catch `StageError` and convert to a list of human-readable strings — never let a raw `StageError` or traceback reach the UI layer.
- Return a plain, Flet-agnostic result object, e.g.:

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class ClaimOcrResult:
    status: Literal["queued", "processing", "done", "failed"]
    pages: list          # PageResult-like: text, word boxes, per-page errors
    matches: dict         # {"date": "EXACT"/"CORRECTED"/"MISSING", "amount": ..., "pin": ...}
    suggested_decision: str   # "PASS" / "CAUTION" / "REVIEW" (see docs/blueprint.md)
    errors: list[str]
```

Write unit tests for this module independent of Flet, reusing `app/tests/fakes.py`'s fake OCR reader to exercise failure paths without running real OCR.

---

## Step 2 — Define the status mapping (do this before wiring UI)

Backend decision model (`docs/blueprint.md`): **PASS / CAUTION / REVIEW**.
Flet UI verification statuses: **Verified/Approved, Needs Revision, Rejected, Pending**.

Mapping to implement:

| Backend decision | UI pre-selected status | Notes |
|---|---|---|
| PASS | Verified/Approved | Reviewer still confirms manually |
| CAUTION | Needs Revision | Surface which field (date/amount/PIN) triggered it |
| REVIEW / OCR failure | Pending | Don't auto-approve or auto-reject on uncertainty |

The reviewer's manual choice always overrides the suggestion — OCR informs, never decides automatically.

---

## Step 3 — Async execution pattern in current Flet

- Entry point: `async def main(page: ft.Page)`, run via `ft.run(main)`.
- OCR is CPU-bound and potentially slow per page — never call it directly inside an `async def` event handler (it will block the event loop). Offload it:

```python
async def handle_upload(e: ft.Event[ft.Button]):
    progress_ring.visible = True
    page.update()
    result = await asyncio.to_thread(claim_processor.process_claim, claim_paths)
    progress_ring.visible = False
    apply_result_to_ui(result)
    page.update()
```

- For page-by-page progress (the OCR pipeline already yields per-page as it goes), use `page.run_task` to launch a background coroutine that processes one page at a time and updates a progress indicator after each page, instead of blocking until the whole document finishes.
- For multi-file claims (claim PDF + bank statement + receipts), process concurrently with `asyncio.gather` over multiple `asyncio.to_thread` calls if latency matters.

---

## Step 4 — Wire each view

### `uploader_view.py`
- On save: call `claim_processor` (async, per Step 3) instead of writing directly to the demo store.
- Persist the returned `ClaimOcrResult` alongside claim metadata via `claim_store.py`.
- On failure, surface `result.errors` via the existing snack-bar pattern.

### `verifier_view.py` (largest change)
- Render actual PDF pages (reuse the same rasterization approach as `app/gui/page_renderer.py` — PyMuPDF-based; this is separate from the OCR read path per `description.md` and safe to reuse standalone).
- Draw highlight rectangles from `PageResult.words` coordinates, mapped through `app/ocr/geometry.py`, over the rendered page image.
- Pre-fill "verified amount" and reviewer-note hints from `matches`.
- Pre-select verification status per the Step 2 mapping.

### `manager_view.py`
- Swap summary cards/table from demo counts to real aggregates over stored `ClaimOcrResult`s (total claims, verified vs. pending/revision, total value, etc.) — mostly a `claim_store` query change once real data is flowing.

---

## Step 5 — `claim_store.py` becomes the seam

- Keep `claim_store.py` as the single place views read/write claim data.
- Change internals to persist `ClaimOcrResult` (JSON is fine) alongside existing claim metadata.
- Add a config/feature flag to fall back to demo data, so the UI can be developed/tested without re-running OCR every time.

---

## Step 6 — Rollout order

1. Build and unit-test `claim_processor.py` in isolation (no Flet).
2. Wire `uploader_view.py` first — it produces real data.
3. Wire `verifier_view.py` next — it consumes/displays that data (PDF render + highlights + pre-fill).
4. Wire `manager_view.py` last — it aggregates data the other two now produce.
5. Keep the demo-data fallback flag alive until each view is confirmed working against real OCR results, then remove it.

---

## Out of scope for this pass

- Standing up the FastAPI service described in `description.md` — only revisit if a genuine need for a decoupled/remote backend appears.
- Anything in `app/gui/*` (Qt) or `tools/` (experiments) — not to be imported by the Flet app.
