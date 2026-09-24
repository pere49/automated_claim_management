Read skill `python-fact-grounded-coding`

I’ll map the repository first, then trace the OCR and GUI entry points so the API guidance is grounded in the actual code rather than assumptions.

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\docs\\NEXT_SESSION.md"
}

Read , lines 1 to 220
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\docs\\blueprint.md",
  "view_range": [
    1,
    220
  ]
}

Ran terminal command: Get-ChildItem -Force; Get-ChildItem -Recurse -File | Select-Object FullName

Ran terminal command: git status --short

Read , lines 1 to 180
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\docs\\NEXT_SESSION.md",
  "view_range": [
    1,
    180
  ]
}

Read tool output
Completed with input: {
  "path": "C:\\Users\\kevin\\AppData\\Local\\Temp\\1790249030461-copilot-tool-output-19376-9e273e43-7d0f-4aed-a21a-9256c78f1ee2.txt",
  "view_range": [
    1,
    220
  ]
}

Search for `RapidOCR|OcrReader|QMainWindow|PySide|ocr|api|FastAPI|Flask`

Find files matching `app/**/*.py`

Find files matching `tests/**/*.py`

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\app\\ocr\\reader.py"
}

Read , lines 1 to 260
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\app\\ocr\\pipeline.py",
  "view_range": [
    1,
    260
  ]
}

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\app\\matching\\search.py"
}

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\app\\layout\\rows.py"
}

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\app\\__main__.py"
}

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\app\\gui\\main_window.py"
}

Read , lines 1 to 260
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\app\\gui\\document_session.py",
  "view_range": [
    1,
    260
  ]
}

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\app\\gui\\ocr_worker.py"
}

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\requirements.in"
}

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\app\\ocr\\engine_settings.json"
}

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\app\\ocr\\enhance_rules.json"
}

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\app\\errors.py"
}

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\app\\paths.py"
}

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\app\\gui\\application.py"
}

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\app\\gui\\file_panel.py"
}

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\app\\gui\\search_controller.py"
}

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\app\\ocr\\__init__.py"
}

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\app\\matching\\__init__.py"
}

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\app\\layout\\__init__.py"
}

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\README.md"
}

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\run_tests.bat"
}

Read 
Completed with input: {
  "path": "C:\\Users\\kevin\\.gemini\\antigravity\\scratch\\claim_verifier_app\\start_app.bat"
}

Ran terminal command: Get-ChildItem -Path app,docs,tools -Recurse -File | Where-Object { $_.FullName -notmatch '\\.venv\\' } | ForEach-Object { $_.FullName.Substring((Get-Location).Path.Length + 1) }

`List repository files` completed

I inspected the current working tree. This is a **Python desktop application**, not an API yet. The OCR engine is **RapidOCR**, running locally through ONNX Runtime and OpenCV.

One important note: the repository currently has local Git changes. The documentation describes a top-level `tests/` folder, but the current filesystem has tests under `app/tests/`.

## High-level structure

```text
claim_verifier_app/
├── app/              Main Python application package
├── docs/             Architecture and design documentation
├── tools/            OCR and matching experiments
├── images/           Local input files, ignored by Git
├── .venv/            Local Python environment, ignored by Git
├── requirements.in   Direct dependencies and reasons
├── requirements.txt  Pinned installed dependencies
├── start_app.bat     Starts the desktop GUI
├── run_tests.bat     Runs the test suite
├── README.md         Very short project description
└── pdf_image.py      Standalone PDF/image helper script
```

---

# `app/`

`app/` is the main application package.

## Core files

### `app/__main__.py`

This is the entry point for:

```text
python -m app
```

It calls `app.gui.application.run()`, which starts the PySide6 desktop application.

### `app/errors.py`

Defines the shared `StageError` error type.

Errors contain:

- The stage that failed, such as `ocr`, `load`, `matching`, or `config`
- A human-readable summary
- Optional file and page information
- The original exception
- A full traceback for detailed diagnostics

This is important for an API because API responses should convert these structured errors into JSON instead of exposing raw tracebacks directly.

### `app/config_files.py`

Shared JSON configuration loading and validation.

### `app/paths.py`

Defines the project root and resolves configured folders relative to the project.

---

# `app/ocr/`

`app/ocr/` contains the OCR pipeline.

## `app/ocr/reader.py`

This is the main public OCR interface.

The important class is `OcrReader`:

```python
reader = OcrReader()
reader.start()
pages = reader.load_pages(path, dpi)
result = reader.read_page(page)
```

Its responsibilities are:

1. Start RapidOCR and load its configuration
2. Load PDF or image pages
3. Read pages individually
4. Return OCR words and their positions
5. Attach page coordinates for highlighting
6. Return page-level errors without stopping the entire document

This is the most important module to reuse from an API.

The API should not call internal OCR functions directly. It should use `OcrReader`.

## `app/ocr/pipeline.py`

Contains the internal OCR processing pipeline:

```text
analyse page
    ↓
advise image enhancements
    ↓
apply enhancements
    ↓
run RapidOCR
    ↓
return PageResult
```

It measures page characteristics such as:

- Brightness
- Contrast
- Noise
- Skew
- Text size
- Sharpness

Then it conditionally applies image processing such as:

- Cropping
- Denoising
- Deskewing
- Brightening
- Contrast adjustment
- Resizing
- Sharpening

The processing rules are not hard-coded entirely in Python. They are read from configuration files.

## `app/ocr/image_files.py`

Loads image files such as:

- JPG
- PNG
- HEIC

It provides a shared image-loading path for OCR and display.

## `app/ocr/geometry.py`

Maps OCR coordinates back to the original rendered page.

This allows the GUI to draw highlights over recognized words.

## `app/ocr/enhance_rules.json`

Contains image-enhancement thresholds and rules.

For example, it controls when denoising, deskewing, sharpening, or brightening occurs.

## `app/ocr/engine_settings.json`

Contains RapidOCR startup settings.

Currently, the active RapidOCR parameter set is mostly the engine default configuration.

## `app/ocr/__init__.py`

Exports the public OCR API:

- `OcrReader`
- `OcrStageError`
- `Page`
- `PageResult`
- `Word`
- `read_image_rgb`

---

# `app/layout/`

`app/layout/` converts individual OCR words into printed rows.

RapidOCR may return a receipt line like this:

```text
TOTAL     12,542.00
```

as separate OCR segments:

```text
TOTAL
12,542
.00
```

## `app/layout/rows.py`

Groups OCR segments based on their coordinates.

It produces:

- `Segment`
- `TextRow`
- `RowRules`
- `group_rows()`

The grouping uses position and spacing, not the actual text content.

## `app/layout/row_rules.json`

Contains the thresholds used to determine whether two OCR segments belong to the same printed row.

## `app/layout/__init__.py`

Exports the row-grouping functions and data structures.

---

# `app/matching/`

`app/matching/` is the document-search and claim-verification layer.

It is intentionally separated from the OCR code. It does not load images or run RapidOCR. It works on already extracted text rows.

## `app/matching/search.py`

This is the main matching interface.

It defines:

```python
Query
PreparedPage
PageMatches
DocumentMatches
search_page()
search_document()
```

A query can contain:

- A date
- An amount
- A tax PIN

Example:

```python
Query(
    date=date(2026, 8, 12),
    amount=Decimal("760.00"),
    pin="A012345678Z",
)
```

The matching result contains:

- Which pages contain the date
- Which pages contain the amount
- Which pages contain the PIN
- Which values were exact
- Which values required OCR correction
- Which values were only possible matches
- The best page containing the evidence
- Any page-specific errors

## `app/matching/amount_search.py`

Finds money values in OCR text.

Money comparisons use `Decimal`, not floating-point numbers.

## `app/matching/date_search.py`

Finds dates in OCR text.

## `app/matching/dates.py`

Generates accepted date representations.

## `app/matching/money.py`

Parses typed amounts and generates possible printed forms of an amount.

It also defines `QueryError` for invalid search input.

## `app/matching/pin_search.py`

Normalizes and searches for PIN values.

## `app/matching/tokens.py`

Converts rows into searchable tokens.

## `app/matching/found.py`

Defines match strengths:

- `EXACT`
- `CORRECTED`
- `POSSIBLE`

## `app/matching/rules.py`

Loads and validates matching rules.

## `app/matching/matching_rules.json`

Contains the configurable matching behavior.

## `app/matching/__init__.py`

Exports the public matching API.

---

# `app/gui/`

`app/gui/` contains the PySide6 desktop interface.

This is currently where the application is wired together.

## `app/gui/application.py`

Starts the Qt application.

It:

1. Creates the Qt application
2. Loads GUI settings
3. Creates the main window
4. Installs a last-resort exception handler
5. Starts the event loop

## `app/gui/main_window.py`

Builds the main window and connects the major GUI components.

It coordinates:

- File list
- Document viewer
- OCR text panel
- Search panel
- Error tab
- Search results

This file is primarily GUI wiring and should not become the API implementation.

## `app/gui/document_session.py`

Manages the currently opened document.

It owns:

- The OCR worker
- The document cache
- Page loading state
- Read-ahead processing
- Page status
- Open-document state

It is strongly coupled to Qt signals and threads, so it should not be called directly by a web API.

## `app/gui/ocr_worker.py`

Runs OCR in a background Qt thread so the GUI does not freeze.

The worker:

1. Starts the OCR engine
2. Loads document pages
3. Reads one page at a time
4. Emits progress signals
5. Reports page-level failures
6. Continues after a failed page

For an API, this behavior needs to be replaced by either:

- A normal background worker/thread implementation
- A job queue
- An asynchronous task system

The Qt `QThread` should not be reused by the API.

## `app/gui/document_cache.py`

Caches OCR results for documents during the application session.

## `app/gui/page_renderer.py`

Renders PDF pages into images for display and determines page sizes.

## `app/gui/document_view.py`

Displays document pages and supports scrolling and page navigation.

## `app/gui/page_pane.py`

Displays an individual page.

## `app/gui/file_panel.py`

Scans the configured working folder and lists supported files.

## `app/gui/ocr_text_panel.py`

Displays OCR text for the current page.

## `app/gui/search_panel.py`

The current GUI search form for entering:

- Date
- Amount
- PIN

This is likely to be replaced or extended when Excel claim rows are integrated.

## `app/gui/search_controller.py`

Connects the GUI search fields to the matching package.

Its process is:

```text
GUI fields
  ↓
build Query
  ↓
prepare OCR rows
  ↓
search document
  ↓
emit SearchOutcome
```

This controller is useful as a behavioral reference for the future API service, but it is Qt-dependent.

## `app/gui/highlights.py`

Converts matching hits into screen highlight rectangles.

## `app/gui/search_summary.py`

Formats search results into user-readable GUI text.

## `app/gui/error_tab.py`

Displays errors and warnings inside the desktop interface.

## `app/gui/settings.py`

Loads and validates GUI configuration.

## `app/gui/gui_settings.json`

Contains desktop-specific settings, such as:

- Input folder
- Supported extensions
- PDF DPI
- Display DPI
- Read-ahead behavior
- Window settings

## `app/gui/startup_failure_window.py`

Shows a startup error window if the GUI configuration cannot be loaded.

---

# `app/tests/`

`app/tests/` contains the current test suite.

Important tests include:

- `test_ocr_integration.py` — OCR integration and failure handling
- `test_matching.py` — date, amount, and PIN matching
- `test_rows.py` — OCR segment grouping
- `test_document_session.py` — cache and GUI document behavior
- `test_main_window.py` — GUI behavior
- `fakes.py` — fake OCR reader used to force failure scenarios
- `qt.py` — Qt test helpers

---

# `docs/`

`docs/` describes the intended architecture.

## `docs/blueprint.md`

The main architecture document.

It explains:

- The purpose of the system
- The PASS/CAUTION/REVIEW model
- OCR behavior
- Matching behavior
- GUI stages
- Future Excel claim processing
- Current open design decisions

## `docs/NEXT_SESSION.md`

The current project handoff document.

It says that the next planned development stage is to replace typed GUI search fields with Excel claim rows.

## `docs/reviews/decisions.md`

The binding decision record.

This should be consulted before changing:

- PASS/CAUTION/REVIEW behavior
- Matching rules
- PIN handling
- Duplicate handling
- Human review behavior
- Error semantics

---

# `tools/`

`tools/` contains prototypes and measurement experiments, not production application code.

## `tools/ocr_resolution_trial/`

Measures OCR performance at different resolutions and settings.

Important files:

- `run_trial.py`
- `score.py`
- `trial_config.json`

## `tools/search_criteria_trial/`

Measures different date, amount, and PIN matching strategies.

It includes:

- Synthetic test cases
- Trial configuration
- Measurement scripts
- An application matcher verification script

This folder should not be imported by the future API.

---

# Root scripts and dependencies

## `requirements.in`

Lists direct dependencies and why they exist.

Key dependencies:

- `pymupdf` — PDF rendering
- `pillow` — image loading
- `pillow-heif` — HEIC support
- `opencv-python-headless` — image processing
- `numpy` — image arrays
- `rapidocr` — OCR engine
- `onnxruntime` — CPU model execution
- `openpyxl` — Excel reading
- `PySide6-Essentials` — desktop GUI

The project correctly uses `import pymupdf`, not `import fitz`.

## `requirements.txt`

The pinned environment used by the local virtual environment.

## `start_app.bat`

Starts the GUI using the project virtual environment.

## `run_tests.bat`

Runs the project tests using `unittest`.

## `README.md`

Currently contains only a short project label, so it does not document installation or API usage yet.

---

# Current processing flow

The current application flow is:

```text
User selects PDF/image in GUI
        ↓
DocumentSession
        ↓
OcrWorker on a QThread
        ↓
OcrReader
        ↓
OCR pipeline
        ↓
RapidOCR
        ↓
Word objects with text and coordinates
        ↓
group_rows()
        ↓
TextRow objects
        ↓
prepare_page()
        ↓
search_document()
        ↓
DocumentMatches
        ↓
GUI highlights and summary
```

# What exists for an API today?

There is currently **no HTTP API**, no FastAPI application, no Flask application, and no REST route file.

The reusable backend already exists in these packages:

```text
app/ocr/
app/layout/
app/matching/
app/errors.py
```

The GUI layer is mainly an adapter around those packages.

## Recommended future API boundary

The clean design would be:

```text
frontend
   ↓ HTTP/JSON
API layer
   ↓
claim verification service
   ↓
OCR + layout + matching
```

A future API could expose endpoints such as:

```text
POST /documents
POST /documents/{id}/process
GET  /documents/{id}/status
GET  /documents/{id}/pages
GET  /documents/{id}/results
POST /documents/{id}/claims
```

A result could eventually look like:

```json
{
  "document_id": "local-job-id",
  "status": "complete",
  "pages": [
    {
      "page": 1,
      "text": "...",
      "words": [],
      "matches": {
        "date": "EXACT",
        "amount": "EXACT",
        "pin": "CORRECTED"
      }
    }
  ],
  "decision": "PASS",
  "errors": []
}
```

The API should call `OcrReader`, `group_rows`, and `search_document` directly. It should **not** call `MainWindow`, `DocumentSession`, `OcrWorker`, or Qt signals.

Because this project is designed to remain offline, the API should most likely bind only to localhost, for example:

```text
http://127.0.0.1:8000
```

That would allow a local frontend to use it without exposing claim data to the network.