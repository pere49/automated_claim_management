import flet as ft
import os
import asyncio
from decimal import Decimal
from datetime import datetime
from typing import List, Optional
from claim_store import ClaimStore
from backend_bridge import ClaimProcessor

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
        self.combined_pdf_path: Optional[str] = None
        self.statement_path: Optional[str] = None
        self.receipt_paths: List[str] = []

        # Instantiate FilePickers
        self.claim_picker = ft.FilePicker()
        self.combined_picker = ft.FilePicker()
        self.statement_picker = ft.FilePicker()
        self.receipts_picker = ft.FilePicker()
        self.claim_processor = ClaimProcessor()
        self.processing = False

        self._build_ui()

    def _build_ui(self):
        # File Selection Buttons & Labels
        self.claim_pdf_text = ft.Text("No Claim PDF selected", color=ft.Colors.OUTLINE, size=13)
        self.claim_pdf_btn = ft.OutlinedButton(
            "Select Claim PDF (Optional)",
            icon=ft.Icons.PICTURE_AS_PDF,
            on_click=self._on_select_claim_pdf
        )
        self.combined_pdf_text = ft.Text("No Combined PDF selected (Optional)", color=ft.Colors.OUTLINE, size=13)
        self.combined_pdf_btn = ft.OutlinedButton(
            "Select Combined PDF (Optional)",
            icon=ft.Icons.PICTURE_AS_PDF,
            on_click=self._on_select_combined_pdf,
        )

        self.statement_text = ft.Text("No Bank Statement selected (Optional)", color=ft.Colors.OUTLINE, size=13)
        self.statement_btn = ft.OutlinedButton(
            "Select Bank Statement",
            icon=ft.Icons.ACCOUNT_BALANCE,
            on_click=self._on_select_statement
        )

        self.receipts_text = ft.Text("No Receipts selected", color=ft.Colors.OUTLINE, size=13)
        self.receipts_btn = ft.OutlinedButton(
            "Select Receipts/Proofs (Optional)",
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
                        # File Slots
                        ft.Text("Document Attachments", weight=ft.FontWeight.BOLD, size=15),
                        ft.Container(
                            content=ft.Column([
                                ft.Row([self.combined_pdf_btn, self.combined_pdf_text], alignment=ft.MainAxisAlignment.START),
                                ft.Divider(height=1),
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

    async def _on_select_combined_pdf(self, e):
        files = await self.combined_picker.pick_files(
            dialog_title="Select Combined Claim Documents PDF",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["pdf"],
            allow_multiple=False,
        )
        if files and files[0].path:
            self.combined_pdf_path = files[0].path
            fname = files[0].name or os.path.basename(self.combined_pdf_path)
            self.combined_pdf_text.value = f"Selected: {fname}"
            self.combined_pdf_text.color = ft.Colors.GREEN_400
        else:
            self.combined_pdf_path = None
            self.combined_pdf_text.value = "No Combined PDF selected (Optional)"
            self.combined_pdf_text.color = ft.Colors.OUTLINE
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

    async def _submit_claim(self, e):
        # Validation
        errors = []
        source_pdf = self.claim_pdf_path or self.combined_pdf_path
        if not source_pdf:
            errors.append("Select a Claim PDF or Combined PDF.")

        if errors:
            show_snack(self.page, "Validation Error: " + " | ".join(errors), bgcolor=ft.Colors.RED_700)
            return

        month = datetime.now().strftime("%m_%Y")
        name = "Unassigned"
        project = "OCR Pending"
        c_date = datetime.now().strftime("%Y-%m-%d")

        self.processing = True
        self.submit_btn.disabled = True
        show_snack(self.page, "Processing claim document with OCR...", bgcolor=ft.Colors.BLUE_700)
        try:
            ocr_result = await asyncio.to_thread(
                self.claim_processor.process_claim,
                source_pdf,
                claim_date=c_date,
                claimed_amount=None,
            )
            extracted = ocr_result.extracted
            month = extracted.get("claim_date", c_date)[:7].replace("-", "_") if extracted.get("claim_date") else month
            name = extracted.get("individual_name", name)
            project = extracted.get("project_name", project)
            c_date = extracted.get("claim_date", c_date)
            if extracted.get("claimed_amount"):
                amount = Decimal(extracted["claimed_amount"])
            else:
                amount = Decimal("0.00")
            item = self.store.create_claim(
                month_year=month,
                individual_name=name,
                project_name=project,
                claimed_amount=amount,
                claim_date=c_date,
                claim_pdf_src=source_pdf,
                statement_src=self.statement_path,
                receipt_srcs=self.receipt_paths,
                ocr_result=ocr_result.to_dict(),
            )

            if ocr_result.status == "failed":
                message = "Claim saved, but OCR requires review: " + " | ".join(ocr_result.errors)
                show_snack(self.page, message, bgcolor=ft.Colors.ORANGE_800)
            else:
                show_snack(
                    self.page,
                    f"Claim for {name} ({month}) successfully created in directory!",
                    bgcolor=ft.Colors.GREEN_700,
                )

            # Reset form
            self.claim_pdf_path = None
            self.combined_pdf_path = None
            self.statement_path = None
            self.receipt_paths = []
            self.claim_pdf_text.value = "No Claim PDF selected"
            self.claim_pdf_text.color = ft.Colors.OUTLINE
            self.combined_pdf_text.value = "No Combined PDF selected (Optional)"
            self.combined_pdf_text.color = ft.Colors.OUTLINE
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
        finally:
            self.processing = False
            self.submit_btn.disabled = False
