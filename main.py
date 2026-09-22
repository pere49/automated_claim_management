import flet as ft
import os
import sys
from claim_store import ClaimStore, generate_sample_data
from verifier_view import VerifierView
from uploader_view import UploaderView
from manager_view import ManagerView

def main(page: ft.Page):
    page.title = "ClaimVerify & Document Manager"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    page.spacing = 0
    page.window.width = 1380
    page.window.height = 920
    page.window.min_width = 1000
    page.window.min_height = 700

    # Initialize Claim Store
    claims_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "claims_data"))
    store = ClaimStore(root_dir=claims_dir)
    
    # Generate sample claims if empty
    generate_sample_data(store)

    # Views
    def on_status_changed():
        manager_view.refresh_dashboard()

    def on_claim_uploaded():
        verifier_view.refresh_claims()
        manager_view.refresh_dashboard()

    def on_select_claim_for_verify(item):
        verifier_view.refresh_claims()
        # Find index of selected item
        for idx, cl in enumerate(verifier_view.claims):
            if cl.dir_path == item.dir_path:
                verifier_view.current_index = idx
                verifier_view.current_claim = cl
                verifier_view._render_current_claim()
                break
        nav_bar.selected_index = 0
        switch_tab(0)

    verifier_view = VerifierView(store=store, on_status_changed=on_status_changed)
    uploader_view = UploaderView(store=store, on_claim_uploaded=on_claim_uploaded)
    manager_view = ManagerView(store=store, on_select_claim_for_verify=on_select_claim_for_verify)

    # Register FilePickers in page.services (Flet 1.0 non-visual services)
    page.services.extend([
        uploader_view.claim_picker,
        uploader_view.statement_picker,
        uploader_view.receipts_picker
    ])

    content_container = ft.Container(
        content=verifier_view,
        expand=True,
        padding=10
    )

    def switch_tab(index: int):
        if index == 0:
            verifier_view.refresh_claims()
            content_container.content = verifier_view
        elif index == 1:
            content_container.content = uploader_view
        elif index == 2:
            manager_view.refresh_dashboard()
            content_container.content = manager_view
        page.update()

    def toggle_theme(e):
        if page.theme_mode == ft.ThemeMode.DARK:
            page.theme_mode = ft.ThemeMode.LIGHT
            theme_btn.icon = ft.Icons.DARK_MODE
        else:
            page.theme_mode = ft.ThemeMode.DARK
            theme_btn.icon = ft.Icons.LIGHT_MODE
        page.update()

    theme_btn = ft.IconButton(
        icon=ft.Icons.LIGHT_MODE,
        tooltip="Toggle Dark/Light Mode",
        on_click=toggle_theme
    )

    # App Navigation Header
    header = ft.Container(
        content=ft.Row(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.VERIFIED, color=ft.Colors.BLUE_400, size=28),
                        ft.Text("ClaimVerify", size=20, weight=ft.FontWeight.BOLD),
                        ft.Text("|  Project Payment Verification & Document Manager", color=ft.Colors.SECONDARY, size=13)
                    ],
                    spacing=10
                ),
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Text(f"Directory: mm_yyyy/individual_name/", size=12, color=ft.Colors.GREEN_400),
                            padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                            border_radius=12
                        ),
                        theme_btn
                    ],
                    spacing=10
                )
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
        ),
        padding=ft.Padding.only(left=20, right=20, top=12, bottom=12),
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.only(bottom=ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT))
    )

    # Navigation Tabs
    nav_bar = ft.NavigationBar(
        destinations=[
            ft.NavigationBarDestination(
                icon=ft.Icons.SPLITSCREEN_OUTLINED,
                selected_icon=ft.Icons.SPLITSCREEN,
                label="Verification (Side-by-Side)"
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.CLOUD_UPLOAD_OUTLINED,
                selected_icon=ft.Icons.CLOUD_UPLOAD,
                label="Upload Claim"
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.DASHBOARD_OUTLINED,
                selected_icon=ft.Icons.DASHBOARD,
                label="Document Manager & Stats"
            ),
        ],
        selected_index=0,
        on_change=lambda e: switch_tab(e.control.selected_index)
    )

    page.add(
        ft.Column(
            [
                header,
                content_container,
                nav_bar
            ],
            expand=True,
            spacing=0
        )
    )

if __name__ == "__main__":
    ft.run(main)
