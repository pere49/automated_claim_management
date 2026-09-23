"""OcrReader: the one public way into the OCR module.

    reader = OcrReader()
    reader.start()                        # once; slow (loads the engine)
    pages = reader.load_pages(path, dpi)  # render every page of one file
    for page in pages:
        result = reader.read_page(page)   # never raises; check result.error / .warning;
                                          # each Word has .box (prepared copy) and .page_box (page as shown)

start() and load_pages() raise OcrStageError on failure — there is nothing
useful to carry on with if the engine cannot start or the file cannot be
opened. read_page() never raises: a failure on one page is attached to that
page's PageResult, so the rest of the document is still read.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config_files import read_json_config
from app.ocr import geometry, pipeline
from app.ocr.pipeline import OcrStageError, Page, PageResult

DEFAULT_ENGINE_SETTINGS = Path(__file__).resolve().with_name("engine_settings.json")


def load_engine_params(path: Path = DEFAULT_ENGINE_SETTINGS) -> dict[str, Any]:
    """RapidOCR start-up parameters from engine_settings.json. Raises StageError(stage="config")."""
    return dict(read_json_config(path, {"rapidocr_params": dict})["rapidocr_params"])


class OcrReader:
    def __init__(self, rules_path: Path | None = None, engine_params: dict[str, Any] | None = None,
                 engine_settings_path: Path | None = None) -> None:
        """engine_params, when given, replace engine_settings.json (used by tests and measurements)."""
        self._rules_path = rules_path or pipeline.DEFAULT_RULES
        self._engine_params = engine_params
        self._engine_settings_path = engine_settings_path or DEFAULT_ENGINE_SETTINGS
        self._rules: dict[str, Any] | None = None
        self._engine: pipeline.PaddleEngine | None = None

    @property
    def ready(self) -> bool:
        return self._engine is not None

    def start(self) -> None:
        """Check dependencies, load the rules and start the engine. Safe to
        call again; does nothing once started."""
        if self.ready:
            return
        missing = pipeline.check_dependencies()
        if missing:
            raise OcrStageError("startup", f"required packages are not installed: {', '.join(missing)}")
        try:
            pipeline.load_libraries()
        except Exception as exc:
            raise OcrStageError("startup", "image libraries are installed but could not be loaded", cause=exc) from exc
        rules = pipeline.load_rules(self._rules_path)         # raises OcrStageError("config")
        params = self._engine_params
        if params is None:
            params = load_engine_params(self._engine_settings_path)  # raises StageError("config")
        engine = pipeline.PaddleEngine(params)                # raises OcrStageError("startup")
        self._rules, self._engine = rules, engine

    def load_pages(self, path: Path, dpi: int) -> list[Page]:
        """Render every page of a PDF (or load one image). Raises OcrStageError."""
        self._require_started()
        return pipeline.load_pages(path, dpi=dpi)

    def read_page(self, page: Page) -> PageResult:
        """Prepare and read one page, and map every text box back onto the
        page as rendered (Word.page_box, for highlights). Never raises for a
        page-level failure."""
        self._require_started()
        result = pipeline.process_page(page, self._rules, self._engine)
        try:
            height, width = page.bgr.shape[:2]
            geometry.attach_page_boxes(result, width, height)
        except Exception as exc:
            # Unreachable when preparation itself failed (nothing was applied, so the map is the identity);
            # otherwise the text stays usable and only this page's highlights are missing.
            if result.warning is None:
                result.warning = OcrStageError(
                    "geometry", "text positions could not be mapped onto the page; highlights will be missing",
                    file=page.source.name, page=page.number, cause=exc)
        return result

    def _require_started(self) -> None:
        if not self.ready:
            raise OcrStageError("startup", "OcrReader.start() must succeed before pages can be loaded or read")
