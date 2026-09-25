"""
Excel Template Manager - Flet Windows Desktop Application
Safely load, edit, and export Excel templates in-memory while preserving pristine disk originals.
"""

import os
import sys
import datetime
import traceback
from typing import Dict, Optional, List
import pandas as pd
import openpyxl
import flet as ft


def format_cell_value(val) -> str:
    """Format cell values, ensuring dates display cleanly as DD/MM/YYYY without timestamps."""
    if pd.isna(val) or val is None:
        return ""
    if isinstance(val, (pd.Timestamp, datetime.datetime, datetime.date)):
        return val.strftime("%d/%m/%Y")
    val_str = str(val).strip()
    if len(val_str) >= 10:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.datetime.strptime(val_str.split(".")[0], fmt)
                return dt.strftime("%d/%m/%Y")
            except ValueError:
                pass
    return val_str


class ExcelTemplateManagerApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.setup_page_properties()

        # Application State
        self.current_file_path: Optional[str] = None
        self.excel_sheets: Dict[str, pd.DataFrame] = {}
        self.current_sheet_name: Optional[str] = None
        self.is_sample_data: bool = False
        
        # Pagination State
        self.rows_per_page: int = 25
        self.current_page_idx: int = 0

        # Setup File Picker
        self.file_picker = ft.FilePicker()

        # UI Element References
        self.btn_upload = ft.Button(
            "Upload Template",
            icon=ft.Icons.FILE_UPLOAD_ROUNDED,
            color=ft.Colors.WHITE,
            bgcolor=ft.Colors.BLUE_600,
            on_click=self.trigger_upload,
        )

        self.btn_sample = ft.Button(
            "Load Sample Template",
            icon=ft.Icons.AUTO_AWESOME_ROUNDED,
            color=ft.Colors.BLUE_300,
            on_click=self.load_sample_template,
        )

        self.dd_sheet = ft.Dropdown(
            label="Sheet",
            hint_text="Select Worksheet",
            width=200,
            disabled=True,
            on_select=self.on_sheet_changed,
            border_color=ft.Colors.BLUE_700,
            focused_border_color=ft.Colors.BLUE_400,
        )

        self.btn_save = ft.Button(
            "Generate & Save Copy",
            icon=ft.Icons.SAVE_ALT_ROUNDED,
            disabled=True,
            color=ft.Colors.WHITE,
            bgcolor=ft.Colors.GREEN_600,
            on_click=self.trigger_save,
        )

        self.btn_add_row = ft.Button(
            "Add Row",
            icon=ft.Icons.ADD_ROUNDED,
            disabled=True,
            on_click=self.add_new_row,
        )

        # Status & Info Badges
        self.txt_status = ft.Text("No template loaded", size=13, color=ft.Colors.GREY_400, italic=True)
        self.badge_pristine = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.SHIELD_ROUNDED, size=16, color=ft.Colors.GREEN_400),
                    ft.Text("Disk Original Pristine", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_300),
                ],
                spacing=5,
            ),
            bgcolor=ft.Colors.GREEN_900,
            padding=ft.Padding(10, 4, 10, 4),
            border_radius=12,
            border=ft.Border.all(1, ft.Colors.GREEN_800),
            visible=False,
        )

        self.lbl_file_info = ft.Text("Ready", size=14, weight=ft.FontWeight.W_500, color=ft.Colors.BLUE_200)
        self.lbl_stats = ft.Text("", size=12, color=ft.Colors.GREY_400)

        # Data Container
        self.table_container = ft.Column(scroll=ft.ScrollMode.ALWAYS, expand=True)

        # Build Main View Layout
        self.build_ui()

    def setup_page_properties(self):
        self.page.title = "Excel Template Manager - Safe Monthly Data Entry"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = ft.Colors.GREY_900
        self.page.padding = 20
        self.page.window.width = 1120
        self.page.window.height = 800
        self.page.window.min_width = 850
        self.page.window.min_height = 600
        self.page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

        # Custom Dark Theme Setup
        self.page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)

    def build_ui(self):
        # Header Section
        header = ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(ft.Icons.TABLE_CHART_ROUNDED, size=32, color=ft.Colors.BLUE_400),
                        padding=10,
                        bgcolor=ft.Colors.BLUE_900,
                        border_radius=10,
                        border=ft.Border.all(1, ft.Colors.BLUE_800),
                    ),
                    ft.Column(
                        [
                            ft.Text("Excel Template Manager", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                            ft.Text(
                                "Safely load template files, update monthly data in memory, and export fresh copies.",
                                size=13,
                                color=ft.Colors.GREY_400,
                            ),
                        ],
                        spacing=2,
                    ),
                ],
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            margin=ft.Margin(0, 0, 0, 15),
        )

        # Action Toolbar (Controls)
        toolbar = ft.Container(
            content=ft.Row(
                [
                    ft.Row([self.btn_upload, self.btn_sample], spacing=10),
                    ft.Row([self.dd_sheet, self.btn_save], spacing=10),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                wrap=True,
            ),
            padding=16,
            bgcolor=ft.Colors.GREY_900,
            border_radius=12,
            border=ft.Border.all(1, ft.Colors.GREY_800),
        )

        # File Meta Info Bar
        info_bar = ft.Container(
            content=ft.Row(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.INSERT_DRIVE_FILE_ROUNDED, size=20, color=ft.Colors.BLUE_400),
                            self.lbl_file_info,
                            self.badge_pristine,
                        ],
                        spacing=10,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row([self.lbl_stats, self.btn_add_row], spacing=15, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=ft.Padding(16, 10, 16, 10),
            bgcolor=ft.Colors.GREY_900,
            border_radius=8,
            border=ft.Border.all(1, ft.Colors.GREY_800),
            margin=ft.Margin(0, 10, 0, 10),
        )

        # Main Table Card Area (Compact Width Container)
        table_card = ft.Container(
            content=self.table_container,
            padding=15,
            bgcolor=ft.Colors.GREY_900,
            border_radius=12,
            border=ft.Border.all(1, ft.Colors.GREY_800),
            expand=True,
        )

        # Bottom Status Bar
        status_bar = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.INFO_OUTLINE_ROUNDED, size=16, color=ft.Colors.GREY_500),
                    self.txt_status,
                ],
                spacing=8,
            ),
            padding=ft.Padding(10, 5, 10, 5),
        )

        # Assemble Main Layout with bounded compact width (980px)
        main_content = ft.Container(
            content=ft.Column(
                [
                    header,
                    toolbar,
                    info_bar,
                    table_card,
                    status_bar,
                ],
                expand=True,
                spacing=0,
            ),
            width=980,
            expand=True,
        )

        self.page.add(main_content)
        self.render_empty_state("Click 'Upload Template' or 'Load Sample Template' to start editing data.")

    def render_empty_state(self, message: str):
        self.table_container.controls = [
            ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.DESCRIPTION_OUTLINED, size=64, color=ft.Colors.GREY_700),
                        ft.Text(message, size=15, color=ft.Colors.GREY_500),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=12,
                ),
                alignment=ft.Alignment(0, 0),
                expand=True,
                height=350,
            )
        ]
        self.page.update()

    def show_toast(self, message: str, is_error: bool = False):
        color = ft.Colors.RED_700 if is_error else ft.Colors.GREEN_800
        icon = ft.Icons.ERROR_OUTLINE_ROUNDED if is_error else ft.Icons.CHECK_CIRCLE_ROUNDED

        snack = ft.SnackBar(
            content=ft.Row(
                [
                    ft.Icon(icon, color=ft.Colors.WHITE),
                    ft.Text(message, color=ft.Colors.WHITE, weight=ft.FontWeight.W_500),
                ],
                spacing=10,
            ),
            bgcolor=color,
            duration=4000,
        )
        try:
            self.page.show_dialog(snack)
        except Exception:
            pass
        self.txt_status.value = message
        self.txt_status.color = ft.Colors.RED_400 if is_error else ft.Colors.GREEN_400
        self.page.update()

    async def trigger_upload(self, _):
        try:
            files = await self.file_picker.pick_files(
                dialog_title="Select Excel Template File",
                allowed_extensions=["xlsx", "xls"],
                allow_multiple=False,
            )
            if files and len(files) > 0:
                self.load_excel_file(files[0].path)
        except Exception as ex:
            self.show_toast(f"Failed to open file picker: {str(ex)}", is_error=True)

    def load_excel_file(self, file_path: str):
        try:
            self.txt_status.value = f"Loading '{os.path.basename(file_path)}'..."
            self.page.update()

            # Read all sheets safely in memory
            xls = pd.ExcelFile(file_path)
            self.excel_sheets = {}
            for sheet in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet)
                
                # Reformat any datetime/date columns into string DD/MM/YYYY format
                for col in df.columns:
                    if pd.api.types.is_datetime64_any_dtype(df[col]):
                        df[col] = df[col].apply(format_cell_value)
                    else:
                        df[col] = df[col].apply(format_cell_value)
                
                df = df.fillna("")
                self.excel_sheets[sheet] = df

            self.current_file_path = file_path
            self.is_sample_data = False

            # Update Sheet Dropdown
            self.dd_sheet.options = [ft.DropdownOption(s) for s in xls.sheet_names]
            self.current_sheet_name = xls.sheet_names[0]
            self.dd_sheet.value = self.current_sheet_name
            self.dd_sheet.disabled = False
            self.btn_save.disabled = False
            self.btn_add_row.disabled = False
            self.badge_pristine.visible = True

            filename = os.path.basename(file_path)
            self.lbl_file_info.value = f"File: {filename}"
            
            self.render_current_sheet()
            self.show_toast(f"Successfully loaded '{filename}' ({len(xls.sheet_names)} sheet(s)). Pristine copy kept on disk.")

        except Exception as ex:
            err_msg = f"Error loading Excel file: {str(ex)}"
            self.show_toast(err_msg, is_error=True)
            traceback.print_exc()

    def load_sample_template(self, _):
        try:
            today_str = datetime.datetime.now().strftime("%d/%m/%Y")
            
            # Sheet 1: Monthly Budget & Expense Tracker
            df_monthly = pd.DataFrame([
                {
                    "ID": 101,
                    "Entry Date": today_str,
                    "Department": "Marketing",
                    "Category": "Digital Advertising",
                    "Planned ($)": 15000,
                    "Actual ($)": 14200,
                    "Variance ($)": 800,
                    "Status": "Under Budget",
                    "Notes": "Q3 Campaign active",
                },
                {
                    "ID": 102,
                    "Entry Date": today_str,
                    "Department": "IT & Infrastructure",
                    "Category": "Cloud Services (AWS/GCP)",
                    "Planned ($)": 22000,
                    "Actual ($)": 23500,
                    "Variance ($)": -1500,
                    "Status": "Over Budget",
                    "Notes": "Auto-scaling spike",
                },
                {
                    "ID": 103,
                    "Entry Date": today_str,
                    "Department": "Human Resources",
                    "Category": "Recruitment & Onboarding",
                    "Planned ($)": 8000,
                    "Actual ($)": 6500,
                    "Variance ($)": 1500,
                    "Status": "Under Budget",
                    "Notes": "Key hires deferred",
                },
                {
                    "ID": 104,
                    "Entry Date": today_str,
                    "Department": "Operations",
                    "Category": "Logistics & Shipping",
                    "Planned ($)": 30000,
                    "Actual ($)": 29800,
                    "Variance ($)": 200,
                    "Status": "On Track",
                    "Notes": "Carrier contracts",
                },
                {
                    "ID": 105,
                    "Entry Date": today_str,
                    "Department": "Research & Development",
                    "Category": "Software Licenses",
                    "Planned ($)": 12000,
                    "Actual ($)": 12000,
                    "Variance ($)": 0,
                    "Status": "On Track",
                    "Notes": "Annual renewal",
                },
            ])

            # Sheet 2: Department Summary
            df_summary = pd.DataFrame([
                {"Department": "Marketing", "Headcount": 14, "Lead": "Sarah Connor", "Approved": "Yes", "Last Updated": today_str},
                {"Department": "IT & Infrastructure", "Headcount": 22, "Lead": "Alex Mercer", "Approved": "Yes", "Last Updated": today_str},
                {"Department": "Human Resources", "Headcount": 6, "Lead": "Elena Rostova", "Approved": "Yes", "Last Updated": today_str},
                {"Department": "Operations", "Headcount": 35, "Lead": "Marcus Vance", "Approved": "Yes", "Last Updated": today_str},
                {"Department": "Research & Development", "Headcount": 18, "Lead": "Dr. Aris Thorne", "Approved": "Pending", "Last Updated": today_str},
            ])

            self.excel_sheets = {
                "Monthly Financials": df_monthly,
                "Department Overview": df_summary,
            }

            self.current_file_path = "Sample_Monthly_Template.xlsx (In Memory)"
            self.is_sample_data = True

            self.dd_sheet.options = [ft.DropdownOption(s) for s in self.excel_sheets.keys()]
            self.current_sheet_name = "Monthly Financials"
            self.dd_sheet.value = self.current_sheet_name
            self.dd_sheet.disabled = False
            self.btn_save.disabled = False
            self.btn_add_row.disabled = False
            self.badge_pristine.visible = True

            self.lbl_file_info.value = "File: Sample_Monthly_Template.xlsx"
            self.render_current_sheet()
            self.show_toast("Sample template loaded. Dates formatted as DD/MM/YYYY!")

        except Exception as ex:
            self.show_toast(f"Error generating sample template: {str(ex)}", is_error=True)

    def on_sheet_changed(self, e):
        sheet_name = e.control.value
        if sheet_name in self.excel_sheets:
            self.current_sheet_name = sheet_name
            self.current_page_idx = 0
            self.render_current_sheet()

    def add_new_row(self, _):
        if not self.current_sheet_name or self.current_sheet_name not in self.excel_sheets:
            return

        df = self.excel_sheets[self.current_sheet_name]
        today_str = datetime.datetime.now().strftime("%d/%m/%Y")
        
        # Create a blank new row dictionary matching columns
        new_row = {}
        for col in df.columns:
            if "date" in col.lower():
                new_row[col] = today_str
            else:
                new_row[col] = ""

        # If there's an ID column with numeric values, increment max ID
        if "ID" in df.columns and pd.api.types.is_numeric_dtype(df["ID"]):
            new_row["ID"] = int(df["ID"].max()) + 1 if not df["ID"].empty else 100

        # Append new row
        self.excel_sheets[self.current_sheet_name] = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        self.render_current_sheet()
        self.show_toast(f"Added new row to sheet '{self.current_sheet_name}'.")

    def delete_row(self, row_idx: int):
        if not self.current_sheet_name or self.current_sheet_name not in self.excel_sheets:
            return

        df = self.excel_sheets[self.current_sheet_name]
        if 0 <= row_idx < len(df):
            self.excel_sheets[self.current_sheet_name] = df.drop(df.index[row_idx]).reset_index(drop=True)
            self.render_current_sheet()
            self.show_toast(f"Row {row_idx + 1} deleted from memory.")

    def on_cell_value_changed(self, row_idx: int, col_name: str, new_val: str):
        if not self.current_sheet_name or self.current_sheet_name not in self.excel_sheets:
            return

        df = self.excel_sheets[self.current_sheet_name]
        
        # Try numeric conversion if column appears numeric
        try:
            if new_val.strip() == "":
                typed_val = ""
            elif "." in new_val:
                typed_val = float(new_val)
            else:
                typed_val = int(new_val)
        except ValueError:
            typed_val = new_val

        df.at[row_idx, col_name] = typed_val

        # Auto calculate Variance ($) if Planned ($) and Actual ($) exist
        if col_name in ["Planned ($)", "Actual ($)"] and "Variance ($)" in df.columns:
            try:
                planned = float(df.at[row_idx, "Planned ($)"]) if str(df.at[row_idx, "Planned ($)"]).strip() != "" else 0
                actual = float(df.at[row_idx, "Actual ($)"]) if str(df.at[row_idx, "Actual ($)"]).strip() != "" else 0
                variance = planned - actual
                df.at[row_idx, "Variance ($)"] = variance
                
                # Auto update Status if present
                if "Status" in df.columns:
                    if variance > 0:
                        df.at[row_idx, "Status"] = "Under Budget"
                    elif variance < 0:
                        df.at[row_idx, "Status"] = "Over Budget"
                    else:
                        df.at[row_idx, "Status"] = "On Track"
                        
                self.render_current_sheet()
            except Exception:
                pass

    def render_current_sheet(self):
        if not self.current_sheet_name or self.current_sheet_name not in self.excel_sheets:
            self.render_empty_state("No data found in current sheet.")
            return

        df = self.excel_sheets[self.current_sheet_name]
        total_rows = len(df)
        total_cols = len(df.columns)
        self.lbl_stats.value = f"Total: {total_rows} Rows | {total_cols} Columns"

        if total_rows == 0:
            self.render_empty_state(f"Sheet '{self.current_sheet_name}' is empty.")
            return

        # Build Data Columns
        columns = [
            ft.DataColumn(
                ft.Text("#", weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_300, size=12),
                numeric=True,
            )
        ]
        for col_name in df.columns:
            columns.append(
                ft.DataColumn(
                    ft.Text(str(col_name), weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE, size=12)
                )
            )
        columns.append(
            ft.DataColumn(ft.Text("Action", weight=ft.FontWeight.BOLD, color=ft.Colors.RED_300, size=12))
        )

        # Build Data Rows with Editable TextFields (Shorter Cell Widths)
        rows = []
        for r_idx, row in df.iterrows():
            cells = [
                ft.DataCell(
                    ft.Text(str(r_idx + 1), color=ft.Colors.GREY_500, size=12, weight=ft.FontWeight.W_500)
                )
            ]

            for col_name in df.columns:
                cell_val = row[col_name]
                str_val = format_cell_value(cell_val)
                
                # Determine field type / formatting styling & compact cell width
                is_num = isinstance(cell_val, (int, float)) and not isinstance(cell_val, bool)
                text_align = ft.TextAlign.RIGHT if is_num else ft.TextAlign.LEFT

                input_field = ft.TextField(
                    value=str_val,
                    text_size=12,
                    content_padding=ft.Padding(6, 3, 6, 3),
                    dense=True,
                    border_radius=6,
                    border_color=ft.Colors.GREY_800,
                    focused_border_color=ft.Colors.BLUE_400,
                    text_align=text_align,
                    bgcolor=ft.Colors.GREY_900,
                    width=130,  # Compact cell width constraint
                    on_change=lambda e, r=r_idx, c=col_name: self.on_cell_value_changed(r, c, e.control.value),
                )
                cells.append(ft.DataCell(input_field))

            # Action Cell (Delete Row button)
            btn_del = ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                icon_color=ft.Colors.RED_400,
                icon_size=18,
                tooltip="Delete Row",
                on_click=lambda _, r=r_idx: self.delete_row(r),
            )
            cells.append(ft.DataCell(btn_del))

            rows.append(ft.DataRow(cells=cells))

        # Assembly into DataTable wrapped with horizontal & vertical scroll
        data_table = ft.DataTable(
            columns=columns,
            rows=rows,
            border=ft.Border.all(1, ft.Colors.GREY_800),
            border_radius=8,
            vertical_lines=ft.BorderSide(1, ft.Colors.GREY_800),
            horizontal_lines=ft.BorderSide(1, ft.Colors.GREY_800),
            heading_row_color=ft.Colors.GREY_900,
            heading_row_height=42,
            data_row_min_height=40,
            data_row_max_height=48,
        )

        self.table_container.controls = [
            ft.Row([data_table], scroll=ft.ScrollMode.ALWAYS, expand=True)
        ]
        self.page.update()

    async def trigger_save(self, _):
        try:
            default_filename = f"Updated_Export_{datetime.datetime.now().strftime('%Y_%m')}.xlsx"
            export_path = await self.file_picker.save_file(
                dialog_title="Save Updated Excel Copy",
                file_name=default_filename,
                allowed_extensions=["xlsx"],
            )
            if export_path:
                if not export_path.lower().endswith(".xlsx"):
                    export_path += ".xlsx"
                self.export_to_excel(export_path)
        except Exception as ex:
            self.show_toast(f"Failed to open Save dialog: {str(ex)}", is_error=True)

    def export_to_excel(self, export_path: str):
        try:
            self.txt_status.value = f"Exporting to '{export_path}'..."
            self.page.update()

            # Write all in-memory sheets to new target file
            with pd.ExcelWriter(export_path, engine="openpyxl") as writer:
                for sheet_name, df in self.excel_sheets.items():
                    # Write without index unless required
                    df.to_excel(writer, sheet_name=sheet_name, index=False)

            self.show_toast(f"Exported copy saved to: {export_path}")

        except Exception as ex:
            err_msg = f"Error saving file: {str(ex)}"
            self.show_toast(err_msg, is_error=True)
            traceback.print_exc()


async def main(page: ft.Page):
    ExcelTemplateManagerApp(page)


if __name__ == "__main__":
    ft.run(main)
