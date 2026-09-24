"""The officer-facing PySide6 window.

Public entry point: application.run(). Each other file is one piece:
    settings.py          gui_settings.json -> GuiSettings
    ocr_worker.py        runs OCR on a background thread, page on screen first
    document_cache.py    every file's OCR reading, kept until the app closes
    document_session.py  the open PDF, the OCR thread, the cache, read-ahead
    page_renderer.py     page sizes and page pictures, on demand
    main_window.py       lays out the panes and wires them together
    file_panel.py        left: files in the working folder, the Claim sheet / Receipts slots
    receipts_header.py   middle, top: "Receipt claim:", the PIN toggle (toggle_switch.py), Auto, Next to check
    document_view.py     middle: the whole document as one continuous scroll, highlights, badges
    page_pane.py         middle: the document view, Previous/Next page, fit width
    page_badges.py       the badge in each receipt page's corner
    sheet_view.py        right: the claim sheet as its PDF, a button per row (sheet_canvas.py,
                         sheet_overlay.py, row_buttons.py)
    status_cards.py      right, under the sheet: Verification, TOTAL GRAND, Repeated (elided_label.py)
    claim_session.py     the claim sheet and its receipts, checked together
    claim_presenter.py   a checked claim -> badges, highlights, the row of a page
    page_preparer.py     every read page tokenised once for the checking
    tour.py              Auto / Next to check
    highlights.py        found values -> outlines on the pages
    error_tab.py         every structured error of the session
"""
