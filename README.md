# Claim Verifier App

A lightweight Python desktop application built with **Flet 1.0** for managing project payment claims.

## Table of Contents
- [Overview](#overview)
- [Features](#features)
- [Installation](#installation)
- [Running the App](#running-the-app)
- [Project Structure](#project-structure)
- [Usage Guide](#usage-guide)
- [Dependencies](#dependencies)
- [Development](#development)
- [License](#license)

---

## Overview

The **Claim Verifier App** allows users to:
- Upload claim PDFs, bank statements, and receipt images.
- Automatically organise uploaded documents into a directory hierarchy `mm_yyyy/individual_name/`.
- Verify claims side‑by‑side with a PDF viewer.
- Manage and export claim statistics.

It demonstrates how to use modern Flet APIs such as `Page.overlay` for snack‑bars, async `FilePicker` services, and component based UI composition.

---

## Features

- **Async file‑picker dialogs** for PDFs, images, and multiple receipts.
- **Dynamic UI feedback** – selected file labels turn green and display the chosen filename/count.
- **Snack‑Bar notifications** using `Page.overlay` (replaces the deprecated `Page.open`).
- **Side‑by‑side claim verification** with a PDF viewer.
- **Document manager dashboard** with CSV export.
- **Sample data generation** for quick start‑up.

---

## Installation

1. **Clone the repository** (or simply open the project folder located at:
   `C:\Users\kevin\.gemini\antigravity\scratch\claim_verifier_app`).
2. **Create a virtual environment** (recommended):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1   # PowerShell
   # or .\.venv\Scripts\activate.bat for cmd
   ```
3. **Install dependencies**:
   ```powershell
   pip install flet
   ```
   The app only depends on the `flet` package (version 1.0+).

---

## Running the App

From the project root:
```powershell
python main.py
```
The GUI window will appear. Use the navigation bar at the bottom to switch between:
- **Verification (Side‑by‑Side)** – view and compare claims.
- **Upload Claim** – select files and submit a new claim.
- **Document Manager & Stats** – view summary tables and export CSV.

---

## Project Structure

```
claim_verifier_app/
│   main.py                # Application entry point
│   claim_store.py         # Data model and persistence logic
│   verifier_view.py       # UI for side‑by‑side verification
│   uploader_view.py       # UI for uploading claims (file‑picker handling)
│   manager_view.py        # Dashboard & statistics UI
│   README.md              # *You are reading it now*
│   requirements.txt       # (optional) pinning of dependencies
└─ claims_data/            # Generated claim directories (mm_yyyy/…)
```

---

## Usage Guide

### 1. Upload a Claim
- Click **Select Claim PDF** and choose a PDF file.
- Optionally select a **Bank Statement** (PDF/PNG/JPG).  
- Select **Receipts/Proofs** (multiple files allowed).
- Fill in the month, name, project, date, and amount.
- Press **Upload & Organise Claim**. A green snack‑bar confirms success and the form resets.

### 2. Verify a Claim
- Switch to the **Verification** tab.
- Pick a claim from the list; the PDF will load side‑by‑side with extracted details.
- Use the navigation arrows to step through multiple claims.

### 3. Document Manager
- View a table of all stored claims.
- Export the overview as a CSV using the **Export CSV** button.
- Delete claims via the trash icon.

---

## Dependencies

- **Python 3.10+** (tested on Windows 10/11)
- **flet 1.0** – UI framework that ships with its own lightweight web‑view runtime.

---

## Development

To modify the UI or add new features:
1. Open any of the `*_view.py` modules.
2. Remember that **FilePicker** instances are registered in `page.services` (see `main.py`).
3. Use `await picker.pick_files(...)` for async dialogs.
4. For notifications, call `show_snack(page, "Message", bgcolor=ft.Colors.<COLOR>)`.

Run sanity checks by importing the modules:
```python
python -c "import uploader_view, verifier_view, manager_view"
```
No import errors should be raised.

---

## License

This example project is provided under the **MIT License**. Feel free to adapt it for your own purposes.
