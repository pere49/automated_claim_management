"""GuiSettings: the review window's settings, read from gui_settings.json."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app import paths
from app.config_files import read_json_config
from app.errors import StageError

DEFAULT_SETTINGS = Path(__file__).resolve().with_name("gui_settings.json")


@dataclass(frozen=True)
class GuiSettings:
    working_folder: Path
    file_extensions: tuple[str, ...]
    pdf_render_dpi: int
    zoom_step: float
    min_zoom: float
    max_zoom: float
    window_size: tuple[int, int]
    pane_widths: tuple[int, int, int]
    shutdown_wait_seconds: int
    read_ahead: bool
    display_dpi: int
    page_gap_px: int
    render_margin_pages: int
    highlight_colours: dict[str, str]
    highlight_fill_alpha: int
    neighbour_alpha: int
    highlight_line_px: int
    tour_auto_start: bool
    tour_green_ms: int
    tour_yellow_ms: int
    status_colours: dict[str, str]
    sheet_margin_frac: float
    row_button_frac: float
    tint_alpha: int
    current_colour: str
    current_line_px: int
    label_height_frac: float
    card_tint_alpha: int
    card_value_pt: int
    badge_font_pt: int
    badge_padding_px: int
    badge_text_colour: str
    ocr_export_path: Path | None
    company_pin_file: Path
    company_pin_key: str


def load_settings(path: Path = DEFAULT_SETTINGS) -> GuiSettings:
    """Read and check gui_settings.json. Raises StageError(stage="config")."""
    d = read_json_config(path, {
        "working_folder": str, "file_extensions": list, "pdf_render_dpi": int,
        "zoom_step": (int, float), "min_zoom": (int, float), "max_zoom": (int, float),
        "window_size": list, "pane_widths": list,
        "shutdown_wait_seconds": int, "read_ahead": bool, "display_dpi": int, "page_gap_px": int,
        "render_margin_pages": int, "highlight_colours": dict, "highlight_fill_alpha": int, "neighbour_alpha": int,
        "highlight_line_px": int, "tour": dict, "status_colours": dict, "sheet_view": dict, "status_cards": dict, "badge": dict,
        "ocr_export_path": str, "company_pin_file": str, "company_pin_key": str,
    })

    def fail(message: str) -> StageError:
        return StageError("config", message, file=path.name)

    exts = d["file_extensions"]
    if not exts or not all(isinstance(e, str) and e.startswith(".") for e in exts):
        raise fail("'file_extensions' must be a non-empty list like [\".pdf\"]")
    if d["pdf_render_dpi"] <= 0:
        raise fail("'pdf_render_dpi' must be greater than zero")
    if d["zoom_step"] <= 1:
        raise fail("'zoom_step' must be greater than 1")
    if not 0 < d["min_zoom"] < d["max_zoom"]:
        raise fail("'min_zoom' must be above zero and below 'max_zoom'")
    if d["shutdown_wait_seconds"] < 1:
        raise fail("'shutdown_wait_seconds' must be at least 1")
    if d["display_dpi"] <= 0:
        raise fail("'display_dpi' must be greater than zero")
    if d["page_gap_px"] < 0 or d["render_margin_pages"] < 0:
        raise fail("'page_gap_px' and 'render_margin_pages' must not be negative")
    colours = d["highlight_colours"]
    if set(colours) != {"amount", "date", "pin"} or not all(
            isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in colours.values()):
        raise fail("'highlight_colours' must give amount, date and pin each a colour like \"#1f6feb\"")
    for key in ("highlight_fill_alpha", "neighbour_alpha"):
        if not 0 <= d[key] <= 255:
            raise fail(f"'{key}' must be between 0 and 255")
    if d["highlight_line_px"] < 1:
        raise fail("'highlight_line_px' must be at least 1")
    tour = d["tour"]
    if not (isinstance(tour.get("auto_start"), bool) and all(
            isinstance(tour.get(k), int) and not isinstance(tour.get(k), bool) and tour[k] > 0
            for k in ("green_ms", "yellow_ms"))):
        raise fail("'tour' must hold auto_start (true/false) and green_ms / yellow_ms (milliseconds above zero)")
    names = {"green", "yellow", "red", "grey"}
    if set(d["status_colours"]) != names or not all(_colour(c) for c in d["status_colours"].values()):
        raise fail(f"'status_colours' must give {', '.join(sorted(names))} each a colour like \"#1a7f37\"")
    view, badge = d["sheet_view"], d["badge"]
    if not (_number(view.get("margin_frac"), 0, 0.2) and _number(view.get("row_button_frac"), 0.1, 1)
            and _whole(view.get("tint_alpha"), 0, 255) and _colour(view.get("current_colour"))
            and _whole(view.get("current_line_px"), 1, 20) and _number(view.get("label_height_frac"), 0.1, 1)):
        raise fail("'sheet_view' needs margin_frac (0-0.2), row_button_frac (0.1-1), tint_alpha (0-255), "
                   "current_colour (like \"#1f6feb\"), current_line_px (1-20) and label_height_frac (0.1-1)")
    cards = d["status_cards"]
    if not (_whole(cards.get("tint_alpha"), 0, 255) and _whole(cards.get("value_pt"), 6, 40)):
        raise fail("'status_cards' needs tint_alpha (0-255) and value_pt (6-40)")
    if not (_whole(badge.get("font_pt"), 5, 40) and _whole(badge.get("padding_px"), 0, 40)
            and _colour(badge.get("text_colour"))):
        raise fail("'badge' needs font_pt (5-40), padding_px (0-40) and text_colour (like \"#ffffff\")")
    if not d["company_pin_file"].strip() or not d["company_pin_key"].strip():
        raise fail("'company_pin_file' and 'company_pin_key' must not be empty")
    ocr_export_path = d["ocr_export_path"].strip()
    sizes = {}
    for key, count in (("window_size", 2), ("pane_widths", 3)):
        value = d[key]
        if len(value) != count or not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in value):
            raise fail(f"'{key}' must be {count} positive whole numbers")
        sizes[key] = tuple(value)

    return GuiSettings(
        working_folder=paths.resolve(d["working_folder"]),
        file_extensions=tuple(e.lower() for e in exts),
        pdf_render_dpi=d["pdf_render_dpi"],
        zoom_step=float(d["zoom_step"]), min_zoom=float(d["min_zoom"]), max_zoom=float(d["max_zoom"]),
        window_size=sizes["window_size"], pane_widths=sizes["pane_widths"],
        shutdown_wait_seconds=d["shutdown_wait_seconds"],
        read_ahead=d["read_ahead"],
        display_dpi=d["display_dpi"], page_gap_px=d["page_gap_px"], render_margin_pages=d["render_margin_pages"],
        highlight_colours=dict(colours), highlight_fill_alpha=d["highlight_fill_alpha"],
        neighbour_alpha=d["neighbour_alpha"], highlight_line_px=d["highlight_line_px"],
        tour_auto_start=tour["auto_start"], tour_green_ms=tour["green_ms"], tour_yellow_ms=tour["yellow_ms"],
        status_colours=dict(d["status_colours"]),
        sheet_margin_frac=float(view["margin_frac"]), row_button_frac=float(view["row_button_frac"]),
        tint_alpha=view["tint_alpha"], current_colour=view["current_colour"], current_line_px=view["current_line_px"],
        label_height_frac=float(view["label_height_frac"]),
        card_tint_alpha=cards["tint_alpha"], card_value_pt=cards["value_pt"],
        badge_font_pt=badge["font_pt"], badge_padding_px=badge["padding_px"], badge_text_colour=badge["text_colour"],
        ocr_export_path=paths.resolve(ocr_export_path) if ocr_export_path else None,
        company_pin_file=paths.resolve(d["company_pin_file"]), company_pin_key=d["company_pin_key"].strip(),
    )


def _colour(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) is not None


def _whole(value: object, low: int, high: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def _number(value: object, low: float, high: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and low <= value <= high
