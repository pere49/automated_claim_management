"""The officer-facing PySide6 window.

Public entry point: application.run(). Each other file is one piece:
    settings.py          gui_settings.json -> GuiSettings
    ocr_worker.py        runs OCR on a background thread, page on screen first
    document_cache.py    every file's OCR reading, kept until the app closes
    document_session.py  the open PDF, the OCR thread, the cache, read-ahead
    page_renderer.py     page sizes and page pictures, on demand
    main_window.py       lays out the panes and wires them together
    file_panel.py        left: files in the working folder
    document_view.py     middle: the whole document as one continuous scroll, highlights
    page_pane.py         middle: the document view, Previous/Next page, fit width
    ocr_text_panel.py    right, upper: OCR reading of the page in view, grouped into rows
    search_panel.py      right, lower: search fields, results, Previous/Next match
    search_controller.py runs a search over the open document; keeps it current
    search_summary.py    a search result in plain words
    highlights.py        search hits -> outlines on the pages
    error_tab.py         every structured error of the session
"""
