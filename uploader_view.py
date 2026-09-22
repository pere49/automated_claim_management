import flet as ft
import os
from datetime import datetime
from typing import List, Optional
from claim_store import ClaimStore

def show_snack(page, text: str, bgcolor=None):
    if not page:
        return
    snack = ft.SnackBar(
        content=ft.Text(text),
        bgcolor=bgcolor or ft.Colors.SURFACE_CONTAINER_HIGHEST,
        open=True
    )
    page.overlay.append(snack)
    try:
        page.update()
    except RuntimeError:
        pass

class UploaderView(ft.Container):
    def __init__(self, store: ClaimStore, on_claim_uploaded=None):
        super().__init__()
        self.store = store
        self.on_claim_uploaded = on_claim_uploaded
        self.padding = 20
        self.expand = True

        self.claim_pdf_path: Optional[str] = None
        self.statement_path: Optional[str] = None
        self.receipt_paths: List[str] = []

        # Instantiate FilePickers
        self.claim_picker = ft.FilePicker()
        self.statement_picker = ft.FilePicker()
        self.receipts_picker = ft.FilePicker()

        self._build_ui()

    def _build_ui(self):
        now = datetime.now()
        default_month = now.strftime("%m_%Y")
        default_date = now.strftime("%Y-%m-%d")

        # Explicitly sized Form Controls to eliminate Flutter layout constraint issues
        self.month_field = ft.TextField(
            label="Month & Year (mm_yyyy)",
            value=default_month,
            width=220,
            hint_text="e.g. 09_2026",
            prefix_icon=ft.Icons.CALENDAR_MONTH
        )
        self.name_field = ft.TextField(
            label="Individual / Employee Name",
            hint_text="e.g. John Doe",
            width=470,
            prefix_icon=ft.Icons.PERSON
        )
        self.project_field = ft.TextField(
            label="Project Name",
            hint_text="e.g. Project Alpha - Logistics",
            width=705,
            prefix_icon=ft.Icons.WORK
        )
        self.date_field = ft.TextField(
            label="Claim Date",
            value=default_date,
            width=220,
            prefix_icon=ft.Icons.EVENT
        )
        self.amount_field = ft.TextField(
            label="Total Claimed Amount ($)",
            hint_text="e.g. 450.00",
            width=240,
            prefix_icon=ft.Icons.ATTACH_MONEY,
            keyboard_type=ft.KeyboardType.NUMBER
        )

        # File Selection Buttons & Labels
        self.claim_pdf_text = ft.Text("No Claim PDF selected", color=ft.Colors.OUTLINE, size=13)
        self.claim_pdf_btn = ft.OutlinedButton(
            "Select Claim PDF*",
            icon=ft.Icons.PICTURE_AS_PDF,
            on_click=self._on_select_claim_pdf
        )

        self.statement_text = ft.Text("No Bank Statement selected (Optional)", color=ft.Colors.OUTLINE, size=13)
        self.statement_btn = ft.OutlinedButton(
            "Select Bank Statement",
            icon=ft.Icons.ACCOUNT_BALANCE,
            on_click=self._on_select_statement
        )

        self.receipts_text = ft.Text("No Receipts selected", color=ft.Colors.OUTLINE, size=13)
        self.receipts_btn = ft.OutlinedButton(
            "Select Receipts/Proofs*",
            icon=ft.Icons.RECEIPT,
            on_click=self._on_select_receipts
        )

        self.submit_btn = ft.FilledButton(
            "Upload & Organize Claim",
            icon=ft.Icons.CLOUD_UPLOAD,
            style=ft.ButtonStyle(bgcolor=ft.Colors.BLUE_700),
            height=48,
            on_click=self._submit_claim
        )

        # Form Card Container with explicit width
        form_card = ft.Card(
            content=ft.Container(
                width=760,
                padding=25,
                content=ft.Column(
                    [
                        ft.Row([
                            ft.Icon(ft.Icons.FILE_UPLOAD, size=28, color=ft.Colors.BLUE_400),
                            ft.Text("Submit New Project Payment Claim", size=20, weight=ft.FontWeight.BOLD)
                        ]),
                        ft.Text(
                            "Uploaded documents will be automatically formatted and organized into "
                            "the claims directory structure: mm_yyyy/individual_name/",
                            color=ft.Colors.SECONDARY,
                            size=13
                        ),
                        ft.Divider(height=20),
                        ft.Row([self.month_field, self.name_field], spacing=15),
                        ft.Row([self.project_field], spacing=15),
                        ft.Row([self.date_field, self.amount_field], spacing=15),
                        ft.Divider(height=20),
                        
                        # File Slots
                        ft.Text("Document Attachments", weight=ft.FontWeight.BOLD, size=15),
                        ft.Container(
                            content=ft.Column([
                                ft.Row([self.claim_pdf_btn, self.claim_pdf_text], alignment=ft.MainAxisAlignment.START),
                                ft.Row([self.statement_btn, self.statement_text], alignment=ft.MainAxisAlignment.START),
                                ft.Row([self.receipts_btn, self.receipts_text], alignment=ft.MainAxisAlignment.START),
                            ], spacing=15),
                            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                            padding=15,
                            border_radius=8
                        ),
                        ft.Container(height=15),
                        ft.Row([self.submit_btn], alignment=ft.MainAxisAlignment.END)
                    ],
                    spacing=14
                )
            )
        )

        self.content = ft.Column(
            [
                ft.Row([form_card], alignment=ft.MainAxisAlignment.CENTER)
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True
        )

    # def did_mount(self):
    #     if self.claim_picker not in self.page.overlay:
    #         self.page.overlay.extend([
    #         self.claim_picker,self.statement_picker, self.receipts_picker,
    #         ])
    #         self.page.update()

    async def _on_select_claim_pdf(self, e):
        files = await self.claim_picker.pick_files(
            dialog_title="Select Claim Form PDF",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["pdf"],
            allow_multiple=False
        )
        if files and len(files) > 0:
            self.claim_pdf_path = files[0].path
            fname = files[0].name or os.path.basename(self.claim_pdf_path)
            self.claim_pdf_text.value = f"Selected: {fname}"
            self.claim_pdf_text.color = ft.Colors.GREEN_400
        else:
            self.claim_pdf_path = None
            self.claim_pdf_text.value = "No Claim PDF selected"
            self.claim_pdf_text.color = ft.Colors.OUTLINE

        try:
            if self.page:
                self.page.update()
        except RuntimeError:
            pass

    async def _on_select_statement(self, e):
        files = await self.statement_picker.pick_files(
            dialog_title="Select Bank Statement File",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["pdf", "png", "jpg", "jpeg"],
            allow_multiple=False
        )
        if files and len(files) > 0:
            self.statement_path = files[0].path
            fname = files[0].name or os.path.basename(self.statement_path)
            self.statement_text.value = f"Selected: {fname}"
            self.statement_text.color = ft.Colors.GREEN_400
        else:
            self.statement_path = None
            self.statement_text.value = "No Bank Statement selected (Optional)"
            self.statement_text.color = ft.Colors.OUTLINE

        try:
            if self.page:
                self.page.update()
        except RuntimeError:
            pass

    async def _on_select_receipts(self, e):
        files = await self.receipts_picker.pick_files(
            dialog_title="Select Receipt Image(s) / PDF(s)",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["pdf", "png", "jpg", "jpeg", "webp"],
            allow_multiple=True
        )
        if files and len(files) > 0:
            self.receipt_paths = [f.path for f in files if f.path]
            self.receipts_text.value = f"Selected: {len(self.receipt_paths)} receipt file(s)"
            self.receipts_text.color = ft.Colors.GREEN_400
        else:
            self.receipt_paths = []
            self.receipts_text.value = "No Receipts selected"
            self.receipts_text.color = ft.Colors.OUTLINE

        try:
            if self.page:
                self.page.update()
        except RuntimeError:
            pass

    def _submit_claim(self, e):
        month = (self.month_field.value or "").strip()
        name = (self.name_field.value or "").strip()
        project = (self.project_field.value or "").strip()
        amt_str = (self.amount_field.value or "").strip()
        c_date = (self.date_field.value or "").strip()

        # Validation
        errors = []
        if not month:
            errors.append("Month & Year (mm_yyyy) is required.")
        if not name:
            errors.append("Individual Name is required.")
        if not project:
            errors.append("Project Name is required.")
        if not self.claim_pdf_path:
            errors.append("Claim Form PDF is required.")
        if not self.receipt_paths:
            errors.append("At least one Receipt / Proof file is required.")

        try:
            amount = float(amt_str)
            if amount <= 0:
                errors.append("Claimed Amount must be greater than $0.")
        except ValueError:
            errors.append("Claimed Amount must be a valid number.")

        if errors:
            show_snack(self.page, "Validation Error: " + " | ".join(errors), bgcolor=ft.Colors.RED_700)
            return

        # Create claim via store
        try:
            item = self.store.create_claim(
                month_year=month,
                individual_name=name,
                project_name=project,
                claimed_amount=amount,
                claim_date=c_date,
                claim_pdf_src=self.claim_pdf_path,
                statement_src=self.statement_path,
                receipt_srcs=self.receipt_paths
            )

            # Success Alert
            show_snack(self.page, f"Claim for {name} ({month}) successfully created in directory!", bgcolor=ft.Colors.GREEN_700)

            # Reset form
            self.name_field.value = ""
            self.project_field.value = ""
            self.amount_field.value = ""
            self.claim_pdf_path = None
            self.statement_path = None
            self.receipt_paths = []
            self.claim_pdf_text.value = "No Claim PDF selected"
            self.claim_pdf_text.color = ft.Colors.OUTLINE
            self.statement_text.value = "No Bank Statement selected (Optional)"
            self.statement_text.color = ft.Colors.OUTLINE
            self.receipts_text.value = "No Receipts selected"
            self.receipts_text.color = ft.Colors.OUTLINE

            if self.on_claim_uploaded:
                self.on_claim_uploaded()

            try:
                if self.page:
                    self.page.update()
            except RuntimeError:
                pass
        except Exception as ex:
            show_snack(self.page, f"Failed to save claim: {ex}", bgcolor=ft.Colors.RED_700)
