"""The officer-facing PySide6 window.

Public entry point: application.run(). Each other file is one piece:
    settings.py          gui_settings.json -> GuiSettings
    ocr_worker.py        runs OCR on a background thread, page on screen first
    document_cache.py    every file's OCR reading, kept until the app closes
    document_session.py  the open PDF, the OCR thread, the cache, read-ahead
    page_renderer.py     renders one PDF page for display, on demand
    main_window.py       lays out the panes and wires them together
    file_panel.py        left: files in the working folder
    page_pane.py         middle: the open page, raw Previous/Next, zoom
    ocr_text_panel.py    right, upper: OCR reading grouped into rows
    search_panel.py      right, lower: search fields (not wired yet — Stage B)
    error_tab.py         every structured error of the session
"""
