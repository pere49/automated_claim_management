import flet as ft
import os
from typing import List, Optional
from claim_store import ClaimStore, ClaimItem
from pdf_utils import render_pdf_page_to_base64, get_pdf_page_count, image_file_to_base64

class VerifierView(ft.Container):
    def __init__(self, store: ClaimStore, on_status_changed=None):
        super().__init__()
        self.store = store
        self.on_status_changed = on_status_changed
        self.expand = True

        self.claims: List[ClaimItem] = []
        self.current_index: int = 0
        self.current_claim: Optional[ClaimItem] = None

        # Left PDF Viewer State
        self.left_pdf_page = 0
        self.left_pdf_total_pages = 0
        self.left_pdf_zoom = 1.6

        # Right Viewer State
        self.right_tab_mode = "receipts" # "statement" or "receipts"
        self.right_receipt_idx = 0
        self.right_pdf_page = 0
        self.right_pdf_total_pages = 0
        self.right_zoom = 1.6

        self._build_ui()
        self.refresh_claims()

    def _build_ui(self):
        # 1. Filter & Navigation Header
        self.month_dropdown = ft.Dropdown(
            label="Month Filter",
            width=150,
            dense=True,
            on_select=self._on_filter_changed
        )
        self.status_dropdown = ft.Dropdown(
            label="Status Filter",
            width=160,
            dense=True,
            options=[
                ft.dropdown.Option("ALL", "All Statuses"),
                ft.dropdown.Option("Pending", "Pending"),
                ft.dropdown.Option("Verified", "Verified"),
                ft.dropdown.Option("Needs Revision", "Needs Revision"),
                ft.dropdown.Option("Rejected", "Rejected"),
            ],
            value="ALL",
            on_select=self._on_filter_changed
        )
        self.search_field = ft.TextField(
            hint_text="Search individual or project...",
            width=220,
            dense=True,
            prefix_icon=ft.Icons.SEARCH,
            on_change=self._on_filter_changed
        )

        self.prev_btn = ft.OutlinedButton(
            "Previous",
            icon=ft.Icons.ARROW_BACK,
            on_click=lambda _: self._navigate_claim(-1)
        )
        self.next_btn = ft.FilledButton(
            "Next Claim",
            icon=ft.Icons.ARROW_FORWARD,
            style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700),
            on_click=lambda _: self._navigate_claim(1)
        )
        self.counter_text = ft.Text("Claim 0 of 0", weight=ft.FontWeight.BOLD, size=15)
        self.status_chip = ft.Container(
            content=ft.Text("PENDING", color=ft.Colors.WHITE, size=12, weight=ft.FontWeight.BOLD),
            bgcolor=ft.Colors.ORANGE_700,
            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
            border_radius=12
        )

        header_bar = ft.Container(
            content=ft.Row(
                [
                    ft.Row([self.month_dropdown, self.status_dropdown, self.search_field], spacing=10),
                    ft.Row([
                        self.prev_btn,
                        self.counter_text,
                        self.status_chip,
                        self.next_btn
                    ], spacing=12)
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN
            ),
            padding=ft.Padding.only(left=15, right=15, top=10, bottom=10),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border_radius=8
        )

        # 2. LEFT PANE: Claim PDF Viewer
        self.left_title = ft.Text("Claim Form PDF", weight=ft.FontWeight.BOLD, size=14)
        self.left_page_text = ft.Text("Page 0 / 0", size=12)
        self.left_prev_page_btn = ft.IconButton(ft.Icons.NAVIGATE_BEFORE, on_click=lambda _: self._change_left_page(-1))
        self.left_next_page_btn = ft.IconButton(ft.Icons.NAVIGATE_NEXT, on_click=lambda _: self._change_left_page(1))
        self.left_zoom_in = ft.IconButton(ft.Icons.ZOOM_IN, on_click=lambda _: self._zoom_left(0.2))
        self.left_zoom_out = ft.IconButton(ft.Icons.ZOOM_OUT, on_click=lambda _: self._zoom_left(-0.2))

        DUMMY_IMG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        self.left_image = ft.Image(src=DUMMY_IMG, fit=ft.BoxFit.CONTAIN, width=400, height=600, expand=False)
        self.left_placeholder = ft.Text("No Claim PDF found", color=ft.Colors.OUTLINE)

        left_pane = ft.Container(width=420, height=650, expand=False,
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Row(
                            [
                                ft.Row([ft.Icon(ft.Icons.PICTURE_IN_PICTURE_OUTLINED, color=ft.Colors.BLUE_400), self.left_title]),
                                ft.Row([
                                    self.left_prev_page_btn,
                                    self.left_page_text,
                                    self.left_next_page_btn,
                                    ft.VerticalDivider(width=10),
                                    self.left_zoom_out,
                                    self.left_zoom_in
                                ])
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                        ),
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                        border_radius=ft.BorderRadius.only(top_left=8, top_right=8)
                    ),
                    ft.Container(
                        content=ft.Column(
                            [self.left_image, self.left_placeholder],
                            alignment=ft.MainAxisAlignment.CENTER,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            scroll=ft.ScrollMode.AUTO,
                            expand=True
                        ),
                        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                        expand=True,
                        padding=10
                    )
                ],
                expand=True
            ),

        )

        # 3. RIGHT PANE: Bank Statement / Receipts Viewer
        self.right_tab_segmented = ft.SegmentedButton(
            segments=[
                ft.Segment(value="receipts", label=ft.Text("Receipts / Proofs"), icon=ft.Icon(ft.Icons.RECEIPT_LONG)),
                ft.Segment(value="statement", label=ft.Text("Bank Statement"), icon=ft.Icon(ft.Icons.ACCOUNT_BALANCE)),
            ],
            selected=["receipts"],
            on_change=self._on_right_tab_change
        )

        self.right_title = ft.Text("Proof Viewer", weight=ft.FontWeight.BOLD, size=14)
        self.right_page_text = ft.Text("Item 0 / 0", size=12)
        self.right_prev_btn = ft.IconButton(ft.Icons.NAVIGATE_BEFORE, on_click=lambda _: self._change_right_item(-1))
        self.right_next_btn = ft.IconButton(ft.Icons.NAVIGATE_NEXT, on_click=lambda _: self._change_right_item(1))
        self.right_zoom_in = ft.IconButton(ft.Icons.ZOOM_IN, on_click=lambda _: self._zoom_right(0.2))
        self.right_zoom_out = ft.IconButton(ft.Icons.ZOOM_OUT, on_click=lambda _: self._zoom_right(-0.2))

        DUMMY_IMG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        self.right_receipt_thumbnails = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=8)
        self.right_image = ft.Image(src=DUMMY_IMG, fit=ft.BoxFit.CONTAIN, expand=True)
        self.right_placeholder = ft.Text("No proof files available", color=ft.Colors.OUTLINE)

        right_pane = ft.Container(
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Row(
                            [
                                self.right_tab_segmented,
                                ft.Row([
                                    self.right_prev_btn,
                                    self.right_page_text,
                                    self.right_next_btn,
                                    ft.VerticalDivider(width=10),
                                    self.right_zoom_out,
                                    self.right_zoom_in
                                ])
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                        ),
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH,
                        border_radius=ft.BorderRadius.only(top_left=8, top_right=8)
                    ),
                    self.right_receipt_thumbnails,
                    ft.Container(
                        content=ft.Column(
                            [self.right_image, self.right_placeholder],
                            alignment=ft.MainAxisAlignment.CENTER,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                            scroll=ft.ScrollMode.AUTO,
                            expand=True
                        ),
                        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
                        expand=True,
                        padding=10
                    )
                ],
                expand=True
            ),
            expand=True
        )

        # Dual split view
        split_viewer = ft.Row(
            [left_pane, ft.VerticalDivider(width=2, color=ft.Colors.OUTLINE_VARIANT), right_pane],
            expand=True,
            spacing=10
        )

        # 4. BOTTOM DECISION PANEL
        self.info_individual_text = ft.Text("Individual: -", weight=ft.FontWeight.BOLD, size=15)
        self.info_project_text = ft.Text("Project: -", color=ft.Colors.SECONDARY, size=13)
        self.info_amount_text = ft.Text("Claimed: $0.00", weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_300, size=15)

        self.status_radio_group = ft.RadioGroup(
            content=ft.Row([
                ft.Radio(value="Verified", label="Verified / Approved", fill_color=ft.Colors.GREEN_400),
                ft.Radio(value="Needs Revision", label="Needs Revision", fill_color=ft.Colors.AMBER_400),
                ft.Radio(value="Rejected", label="Rejected", fill_color=ft.Colors.RED_400),
                ft.Radio(value="Pending", label="Pending", fill_color=ft.Colors.GREY_400),
            ], spacing=15),
            on_change=self._on_status_radio_changed
        )

        self.verified_amount_field = ft.TextField(
            label="Verified Amount ($)",
            width=180,
            dense=True,
            keyboard_type=ft.KeyboardType.NUMBER
        )
        self.notes_field = ft.TextField(
            label="Verification Notes / Comments",
            hint_text="e.g. Verified against bank statement and receipt #1 & #2.",
            expand=True,
            dense=True
        )
        self.save_next_btn = ft.FilledButton(
            "Save & Next Claim",
            icon=ft.Icons.CHECK_CIRCLE,
            style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700),
            on_click=self._save_and_next
        )

        decision_panel = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Column([self.info_individual_text, self.info_project_text], spacing=2),
                            self.info_amount_text,
                            self.status_radio_group,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    ),
                    ft.Row(
                        [
                            self.verified_amount_field,
                            self.notes_field,
                            self.save_next_btn
                        ],
                        spacing=15
                    )
                ],
                spacing=8
            ),
            padding=ft.Padding.all(12),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border_radius=8
        )

        # Main Layout
        self.content = ft.Column(
            [header_bar, split_viewer, decision_panel],
            expand=True,
            spacing=10
        )

    def refresh_claims(self):
        all_items = self.store.scan_all()
        months = sorted(list(set(item.month_year for item in all_items)), reverse=True)
        
        current_m_val = self.month_dropdown.value
        self.month_dropdown.options = [ft.dropdown.Option("ALL", "All Months")] + [
            ft.dropdown.Option(m, m) for m in months
        ]
        if current_m_val in [opt.key for opt in self.month_dropdown.options]:
            self.month_dropdown.value = current_m_val
        else:
            self.month_dropdown.value = "ALL"

        self._apply_filters(all_items)

    def _apply_filters(self, items: List[ClaimItem] = None):
        if items is None:
            items = self.store.scan_all()

        m_filter = self.month_dropdown.value
        s_filter = self.status_dropdown.value
        q_filter = (self.search_field.value or "").strip().lower()

        filtered = []
        for item in items:
            if m_filter and m_filter != "ALL" and item.month_year != m_filter:
                continue
            if s_filter and s_filter != "ALL" and item.status != s_filter:
                continue
            if q_filter:
                combined = f"{item.individual_name} {item.project_name}".lower()
                if q_filter not in combined:
                    continue
            filtered.append(item)

        self.claims = filtered
        if not self.claims:
            self.current_index = 0
            self.current_claim = None
        else:
            if self.current_index >= len(self.claims):
                self.current_index = 0
            self.current_claim = self.claims[self.current_index]

        self._render_current_claim()

    def _on_filter_changed(self, e):
        self.current_index = 0
        self._apply_filters()

    def _navigate_claim(self, delta: int):
        if not self.claims:
            return
        new_idx = self.current_index + delta
        if 0 <= new_idx < len(self.claims):
            self.current_index = new_idx
            self.current_claim = self.claims[self.current_index]
            self._render_current_claim()

    def _render_current_claim(self):
        if not self.current_claim:
            self.counter_text.value = "Claim 0 of 0"
            self.prev_btn.disabled = True
            self.next_btn.disabled = True
            self.info_individual_text.value = "No Claims Found"
            self.info_project_text.value = "Adjust filters or upload new claims."
            self.info_amount_text.value = "$0.00"
            self.left_image.visible = False
            self.left_placeholder.visible = True
            self.right_image.visible = False
            self.right_placeholder.visible = True
            try:
                if self.page:
                    self.page.update()
            except RuntimeError:
                pass
            return

        total = len(self.claims)
        curr = self.current_index + 1
        self.counter_text.value = f"Claim {curr} of {total}"
        self.prev_btn.disabled = (self.current_index == 0)
        self.next_btn.disabled = (self.current_index == total - 1)

        claim = self.current_claim
        st = claim.status
        self.status_radio_group.value = st
        if st == "Verified":
            self.status_chip.content.value = "VERIFIED"
            self.status_chip.bgcolor = ft.Colors.GREEN_700
        elif st == "Rejected":
            self.status_chip.content.value = "REJECTED"
            self.status_chip.bgcolor = ft.Colors.RED_700
        elif st == "Needs Revision":
            self.status_chip.content.value = "REVISION"
            self.status_chip.bgcolor = ft.Colors.AMBER_800
        else:
            self.status_chip.content.value = "PENDING"
            self.status_chip.bgcolor = ft.Colors.ORANGE_800

        name_display = claim.individual_name.replace("_", " ")
        self.info_individual_text.value = f"Individual: {name_display} ({claim.month_year})"
        self.info_project_text.value = f"Project: {claim.project_name}"
        self.info_amount_text.value = f"Claimed: ${claim.claimed_amount:,.2f}"

        self.verified_amount_field.value = str(claim.metadata.get("verified_amount", claim.claimed_amount))
        self.notes_field.value = claim.metadata.get("verifier_notes", "")

        # Render Left PDF (Claim Form)
        self.left_pdf_page = 0
        if claim.claim_pdf and os.path.exists(claim.claim_pdf):
            self.left_pdf_total_pages = get_pdf_page_count(claim.claim_pdf)
            self._update_left_pdf_view()
        else:
            self.left_image.visible = False
            self.left_placeholder.value = "No Claim PDF in folder"
            self.left_placeholder.visible = True

        # Render Right Pane
        self.right_receipt_idx = 0
        self.right_pdf_page = 0
        self._update_right_pane()

        try:
            if self.page:
                self.page.update()
        except RuntimeError:
            pass

    def _update_left_pdf_view(self):
        if not self.current_claim or not self.current_claim.claim_pdf:
            return
        b64 = render_pdf_page_to_base64(
            self.current_claim.claim_pdf,
            page_number=self.left_pdf_page,
            zoom=self.left_pdf_zoom,
            force_portrait=True
        )
        if b64:
            self.left_image.src = f"data:image/png;base64,{b64}"
            self.left_image.visible = True
            self.left_placeholder.visible = False
        else:
            self.left_image.visible = False
            self.left_placeholder.visible = True

        self.left_page_text.value = f"Page {self.left_pdf_page + 1} / {self.left_pdf_total_pages}"
        self.left_prev_page_btn.disabled = (self.left_pdf_page == 0)
        self.left_next_page_btn.disabled = (self.left_pdf_page >= self.left_pdf_total_pages - 1)

    def _change_left_page(self, delta: int):
        new_p = self.left_pdf_page + delta
        if 0 <= new_p < self.left_pdf_total_pages:
            self.left_pdf_page = new_p
            self._update_left_pdf_view()
            self.page.update()

    def _zoom_left(self, delta: float):
        self.left_pdf_zoom = max(0.8, min(3.0, self.left_pdf_zoom + delta))
        self._update_left_pdf_view()
        self.page.update()

    def _on_right_tab_change(self, e):
        sel_list = list(e.control.selected) if hasattr(e.control, "selected") and e.control.selected else []
        sel = sel_list[0] if sel_list else "receipts"
        self.right_tab_mode = sel
        self.right_receipt_idx = 0
        self.right_pdf_page = 0
        self._update_right_pane()
        try:
            if self.page:
                self.page.update()
        except RuntimeError:
            pass

    def _update_right_pane(self):
        claim = self.current_claim
        if not claim:
            self.right_image.visible = False
            self.right_placeholder.visible = True
            return

        self.right_receipt_thumbnails.controls.clear()

        if self.right_tab_mode == "statement":
            self.right_receipt_thumbnails.visible = False
            stmt = claim.statement_file
            if stmt and os.path.exists(stmt):
                if stmt.lower().endswith(".pdf"):
                    self.right_pdf_total_pages = get_pdf_page_count(stmt)
                    b64 = render_pdf_page_to_base64(stmt, page_number=self.right_pdf_page, zoom=self.right_zoom)
                    self.right_page_text.value = f"Page {self.right_pdf_page + 1} / {self.right_pdf_total_pages}"
                else:
                    self.right_pdf_total_pages = 1
                    b64 = image_file_to_base64(stmt)
                    self.right_page_text.value = "Bank Statement (Image)"

                self.right_image.src = f"data:image/png;base64,{b64}" if b64 else ""
                self.right_image.visible = True
                self.right_placeholder.visible = False
                self.right_prev_btn.disabled = (self.right_pdf_page == 0)
                self.right_next_btn.disabled = (self.right_pdf_page >= self.right_pdf_total_pages - 1)
            else:
                self.right_image.visible = False
                self.right_placeholder.value = "No Bank Statement uploaded (Optional)"
                self.right_placeholder.visible = True
                self.right_page_text.value = "No Statement"
        else:
            # Receipts mode
            rcpts = claim.receipt_files
            if rcpts:
                self.right_receipt_thumbnails.visible = True
                # Build thumbnails
                for idx, r_path in enumerate(rcpts):
                    fname = os.path.basename(r_path)
                    is_sel = (idx == self.right_receipt_idx)
                    chip = ft.Chip(
                        label=ft.Text(f"Receipt #{idx+1}"),
                        selected=is_sel,
                        on_click=lambda _, i=idx: self._select_receipt(i)
                    )
                    self.right_receipt_thumbnails.controls.append(chip)

                cur_rcpt = rcpts[self.right_receipt_idx]
                if cur_rcpt.lower().endswith(".pdf"):
                    self.right_pdf_total_pages = get_pdf_page_count(cur_rcpt)
                    b64 = render_pdf_page_to_base64(cur_rcpt, page_number=self.right_pdf_page, zoom=self.right_zoom)
                    self.right_page_text.value = f"Rcpt {self.right_receipt_idx + 1}/{len(rcpts)} (Pg {self.right_pdf_page + 1}/{self.right_pdf_total_pages})"
                else:
                    self.right_pdf_total_pages = 1
                    b64 = image_file_to_base64(cur_rcpt)
                    self.right_page_text.value = f"Receipt {self.right_receipt_idx + 1} of {len(rcpts)}"

                self.right_image.src = f"data:image/png;base64,{b64}" if b64 else ""
                self.right_image.visible = True
                self.right_placeholder.visible = False
                self.right_prev_btn.disabled = (self.right_receipt_idx == 0 and self.right_pdf_page == 0)
                self.right_next_btn.disabled = (self.right_receipt_idx == len(rcpts) - 1 and self.right_pdf_page >= self.right_pdf_total_pages - 1)
            else:
                self.right_receipt_thumbnails.visible = False
                self.right_image.visible = False
                self.right_placeholder.value = "No Receipt files uploaded"
                self.right_placeholder.visible = True
                self.right_page_text.value = "No Receipts"

    def _select_receipt(self, idx: int):
        self.right_receipt_idx = idx
        self.right_pdf_page = 0
        self._update_right_pane()
        self.page.update()

    def _change_right_item(self, delta: int):
        if self.right_tab_mode == "statement":
            new_p = self.right_pdf_page + delta
            if 0 <= new_p < self.right_pdf_total_pages:
                self.right_pdf_page = new_p
                self._update_right_pane()
                self.page.update()
        else:
            claim = self.current_claim
            if not claim or not claim.receipt_files:
                return
            new_r = self.right_receipt_idx + delta
            if 0 <= new_r < len(claim.receipt_files):
                self.right_receipt_idx = new_r
                self.right_pdf_page = 0
                self._update_right_pane()
                self.page.update()

    def _zoom_right(self, delta: float):
        self.right_zoom = max(0.8, min(3.0, self.right_zoom + delta))
        self._update_right_pane()
        self.page.update()

    def _on_status_radio_changed(self, e):
        st = self.status_radio_group.value
        if st == "Verified":
            self.status_chip.content.value = "VERIFIED"
            self.status_chip.bgcolor = ft.Colors.GREEN_700
        elif st == "Rejected":
            self.status_chip.content.value = "REJECTED"
            self.status_chip.bgcolor = ft.Colors.RED_700
        elif st == "Needs Revision":
            self.status_chip.content.value = "REVISION"
            self.status_chip.bgcolor = ft.Colors.AMBER_800
        else:
            self.status_chip.content.value = "PENDING"
            self.status_chip.bgcolor = ft.Colors.ORANGE_800
        self.page.update()

    def _save_and_next(self, e):
        if not self.current_claim:
            return

        st = self.status_radio_group.value or "Pending"
        try:
            v_amt = float(self.verified_amount_field.value or 0.0)
        except ValueError:
            v_amt = self.current_claim.claimed_amount

        self.current_claim.metadata["status"] = st
        self.current_claim.metadata["verified_amount"] = v_amt
        self.current_claim.metadata["verifier_notes"] = self.notes_field.value or ""
        self.current_claim.metadata["verified_by"] = "Verifier"
        self.current_claim.save_metadata()

        if self.on_status_changed:
            self.on_status_changed()

        # Show snackbar feedback
        if self.page:
            snack = ft.SnackBar(
                content=ft.Text(f"Claim for '{self.current_claim.individual_name.replace('_', ' ')}' saved as {st.upper()}!"),
                bgcolor=ft.Colors.GREEN_700 if st == "Verified" else ft.Colors.SURFACE_CONTAINER_HIGHEST,
                open=True
            )
            self.page.overlay.append(snack)
            try:
                self.page.update()
            except RuntimeError:
                pass

        # Move to next claim automatically
        if self.current_index < len(self.claims) - 1:
            self._navigate_claim(1)
        else:
            self.refresh_claims()
