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
    right_pane_heights: tuple[int, int]
    shutdown_wait_seconds: int
    read_ahead: bool
    display_dpi: int
    page_gap_px: int
    render_margin_pages: int
    highlight_colours: dict[str, str]
    highlight_fill_alpha: int
    neighbour_alpha: int
    highlight_line_px: int


def load_settings(path: Path = DEFAULT_SETTINGS) -> GuiSettings:
    """Read and check gui_settings.json. Raises StageError(stage="config")."""
    d = read_json_config(path, {
        "working_folder": str, "file_extensions": list, "pdf_render_dpi": int,
        "zoom_step": (int, float), "min_zoom": (int, float), "max_zoom": (int, float),
        "window_size": list, "pane_widths": list, "right_pane_heights": list,
        "shutdown_wait_seconds": int, "read_ahead": bool, "display_dpi": int, "page_gap_px": int,
        "render_margin_pages": int, "highlight_colours": dict, "highlight_fill_alpha": int, "neighbour_alpha": int,
        "highlight_line_px": int,
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
    sizes = {}
    for key, count in (("window_size", 2), ("pane_widths", 3), ("right_pane_heights", 2)):
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
        right_pane_heights=sizes["right_pane_heights"],
        shutdown_wait_seconds=d["shutdown_wait_seconds"],
        read_ahead=d["read_ahead"],
        display_dpi=d["display_dpi"], page_gap_px=d["page_gap_px"], render_margin_pages=d["render_margin_pages"],
        highlight_colours=dict(colours), highlight_fill_alpha=d["highlight_fill_alpha"],
        neighbour_alpha=d["neighbour_alpha"], highlight_line_px=d["highlight_line_px"],
    )
