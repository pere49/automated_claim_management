import flet as ft
import os
import csv
from typing import List
from claim_store import ClaimStore, ClaimItem

class ManagerView(ft.Container):
    def __init__(self, store: ClaimStore, on_select_claim_for_verify=None):
        super().__init__()
        self.store = store
        self.on_select_claim_for_verify = on_select_claim_for_verify
        self.padding = 15
        self.expand = True

        self._build_ui()
        self.refresh_dashboard()

    def _build_ui(self):
        # 1. Summary Cards
        self.stat_total_claims = ft.Text("0", size=24, weight=ft.FontWeight.BOLD)
        self.stat_total_amount = ft.Text("$0.00", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_400)
        self.stat_verified_count = ft.Text("0", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_400)
        self.stat_pending_count = ft.Text("0", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_400)

        card_total = self._build_stat_card("Total Claims", self.stat_total_claims, ft.Icons.FOLDER_SHARED, ft.Colors.BLUE_900)
        card_amount = self._build_stat_card("Total Claim Value", self.stat_total_amount, ft.Icons.MONETIZATION_ON, ft.Colors.PURPLE_900)
        card_verified = self._build_stat_card("Verified Claims", self.stat_verified_count, ft.Icons.CHECK_CIRCLE, ft.Colors.GREEN_900)
        card_pending = self._build_stat_card("Pending / Revision", self.stat_pending_count, ft.Icons.PENDING_ACTIONS, ft.Colors.AMBER_900)

        stats_row = ft.Row([card_total, card_amount, card_verified, card_pending], spacing=15)

        # 2. Controls & Directory Info
        self.dir_path_text = ft.Text(f"Directory: {self.store.root_dir}", size=12, color=ft.Colors.SECONDARY)
        self.open_dir_btn = ft.OutlinedButton(
            "Open Folder in Explorer",
            icon=ft.Icons.FOLDER_OPEN,
            on_click=self._open_root_folder
        )
        self.export_csv_btn = ft.FilledButton(
            "Export Summary to CSV",
            icon=ft.Icons.DOWNLOAD,
            style=ft.ButtonStyle(bgcolor=ft.Colors.TEAL_700),
            on_click=self._export_csv
        )

        dir_bar = ft.Row(
            [
                ft.Row([ft.Icon(ft.Icons.STORAGE, size=20), self.dir_path_text]),
                ft.Row([self.open_dir_btn, self.export_csv_btn], spacing=10)
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        )

        # 3. Table & Filters
        self.month_filter = ft.Dropdown(
            label="Month",
            width=140,
            dense=True,
            on_select=lambda _: self._apply_table_filters()
        )
        self.status_filter = ft.Dropdown(
            label="Status",
            width=150,
            dense=True,
            options=[
                ft.dropdown.Option("ALL", "All Statuses"),
                ft.dropdown.Option("Pending", "Pending"),
                ft.dropdown.Option("Verified", "Verified"),
                ft.dropdown.Option("Needs Revision", "Needs Revision"),
                ft.dropdown.Option("Rejected", "Rejected"),
            ],
            value="ALL",
            on_select=lambda _: self._apply_table_filters()
        )
        self.search_field = ft.TextField(
            hint_text="Filter claims by name or project...",
            width=260,
            dense=True,
            prefix_icon=ft.Icons.SEARCH,
            on_change=lambda _: self._apply_table_filters()
        )

        table_header_row = ft.Row(
            [
                ft.Text("Document & Claim Directory Overview", size=18, weight=ft.FontWeight.BOLD),
                ft.Row([self.month_filter, self.status_filter, self.search_field], spacing=10)
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        )

        self.table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Month")),
                ft.DataColumn(ft.Text("Individual Name")),
                ft.DataColumn(ft.Text("Project")),
                ft.DataColumn(ft.Text("Claimed ($)"), numeric=True),
                ft.DataColumn(ft.Text("Verified ($)"), numeric=True),
                ft.DataColumn(ft.Text("Status")),
                ft.DataColumn(ft.Text("Files")),
                ft.DataColumn(ft.Text("Actions")),
            ],
            rows=[],
            heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border_radius=8
        )

        table_container = ft.Container(
            content=ft.Column([self.table], scroll=ft.ScrollMode.AUTO, expand=True),
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8,
            expand=True
        )

        self.content = ft.Column(
            [stats_row, dir_bar, table_header_row, table_container],
            spacing=15,
            expand=True
        )

    def _build_stat_card(self, title: str, content_ctrl: ft.Control, icon, color):
        return ft.Card(
            content=ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(icon, size=28, color=ft.Colors.WHITE),
                            bgcolor=color,
                            padding=12,
                            border_radius=8
                        ),
                        ft.Column(
                            [
                                ft.Text(title, size=12, color=ft.Colors.SECONDARY),
                                content_ctrl
                            ],
                            spacing=2
                        )
                    ],
                    spacing=15
                ),
                padding=12
            ),
            expand=True
        )

    def refresh_dashboard(self):
        all_items = self.store.scan_all()
        months = sorted(list(set(item.month_year for item in all_items)), reverse=True)

        self.month_filter.options = [ft.dropdown.Option("ALL", "All Months")] + [
            ft.dropdown.Option(m, m) for m in months
        ]
        if not self.month_filter.value:
            self.month_filter.value = "ALL"

        # Update stats
        total_claims = len(all_items)
        total_val = sum(item.claimed_amount for item in all_items)
        verified_items = [i for i in all_items if i.status == "Verified"]
        verified_val = sum(i.verified_amount for i in verified_items)
        pending_items = [i for i in all_items if i.status in ["Pending", "Needs Revision"]]

        self.stat_total_claims.value = str(total_claims)
        self.stat_total_amount.value = f"${total_val:,.2f}"
        self.stat_verified_count.value = f"{len(verified_items)} (${verified_val:,.2f})"
        self.stat_pending_count.value = str(len(pending_items))

        self._apply_table_filters(all_items)

    def _apply_table_filters(self, items: List[ClaimItem] = None):
        if items is None:
            items = self.store.scan_all()

        m_filter = self.month_filter.value
        s_filter = self.status_filter.value
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

        rows = []
        for item in filtered:
            st = item.status
            if st == "Verified":
                chip_color = ft.Colors.GREEN_700
            elif st == "Rejected":
                chip_color = ft.Colors.RED_700
            elif st == "Needs Revision":
                chip_color = ft.Colors.AMBER_800
            else:
                chip_color = ft.Colors.ORANGE_800

            st_chip = ft.Container(
                content=ft.Text(st.upper(), color=ft.Colors.WHITE, size=11, weight=ft.FontWeight.BOLD),
                bgcolor=chip_color,
                padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                border_radius=10
            )

            files_desc = []
            if item.claim_pdf:
                files_desc.append("Claim PDF")
            if item.statement_file:
                files_desc.append("Bank Stmt")
            if item.receipt_files:
                files_desc.append(f"{len(item.receipt_files)} Receipt(s)")
            files_str = " + ".join(files_desc) if files_desc else "None"

            row = ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(item.month_year, weight=ft.FontWeight.BOLD)),
                    ft.DataCell(ft.Text(item.individual_name.replace("_", " "))),
                    ft.DataCell(ft.Text(item.project_name)),
                    ft.DataCell(ft.Text(f"${item.claimed_amount:,.2f}")),
                    ft.DataCell(ft.Text(f"${item.verified_amount:,.2f}")),
                    ft.DataCell(st_chip),
                    ft.DataCell(ft.Text(files_str, size=12, color=ft.Colors.SECONDARY)),
                    ft.DataCell(
                        ft.Row([
                            ft.IconButton(
                                ft.Icons.FOLDER_OPEN,
                                tooltip="Open Claim Directory",
                                on_click=lambda _, p=item.dir_path: self._open_folder(p)
                            ),
                            ft.IconButton(
                                ft.Icons.RATE_REVIEW,
                                tooltip="Verify in Dual Viewer",
                                icon_color=ft.Colors.BLUE_400,
                                on_click=lambda _, it=item: self._verify_claim(it)
                            )
                        ], spacing=2)
                    )
                ]
            )
            rows.append(row)

        self.table.rows = rows
        try:
            if self.page:
                self.page.update()
        except RuntimeError:
            pass

    def _open_folder(self, dir_path: str):
        if os.path.exists(dir_path):
            try:
                os.startfile(dir_path)
            except Exception as e:
                print(f"Error opening folder: {e}")

    def _open_root_folder(self, e):
        self._open_folder(self.store.root_dir)

    def _verify_claim(self, item: ClaimItem):
        if self.on_select_claim_for_verify:
            self.on_select_claim_for_verify(item)

    def _export_csv(self, e):
        all_items = self.store.scan_all()
        csv_path = os.path.join(self.store.root_dir, "claims_summary_report.csv")
        try:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Month_Year", "Individual_Name", "Project_Name",
                    "Claim_Date", "Claimed_Amount", "Verified_Amount",
                    "Status", "Verifier_Notes", "Updated_At", "Directory_Path"
                ])
                for item in all_items:
                    writer.writerow([
                        item.month_year,
                        item.individual_name,
                        item.project_name,
                        item.metadata.get("claim_date", ""),
                        item.claimed_amount,
                        item.verified_amount,
                        item.status,
                        item.metadata.get("verifier_notes", ""),
                        item.metadata.get("updated_at", ""),
                        item.dir_path
                    ])

            if self.page:
                snack = ft.SnackBar(
                    content=ft.Text(f"Summary report exported to: {csv_path}"),
                    action="Open Folder",
                    on_action=lambda _: self._open_folder(self.store.root_dir),
                    bgcolor=ft.Colors.TEAL_700,
                    open=True
                )
                self.page.overlay.append(snack)
                try:
                    self.page.update()
                except RuntimeError:
                    pass
        except Exception as ex:
            if self.page:
                snack = ft.SnackBar(
                    content=ft.Text(f"Failed to export CSV: {ex}"),
                    bgcolor=ft.Colors.RED_700,
                    open=True
                )
                self.page.overlay.append(snack)
                try:
                    self.page.update()
                except RuntimeError:
                    pass
