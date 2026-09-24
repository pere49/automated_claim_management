"""Receipt and claim verifier: offline review application.

Sub-packages, one concern each:
    errors.py, config_files.py  shared error shape and config-file reading
    ocr/                        page preparation and OCR (RapidOCR)
    layout/                     grouping OCR segments into printed rows
    gui/                        the officer-facing PySide6 window

Run with:  python -m app
"""
