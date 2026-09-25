"""OCR processing for the claim verifier: prepare and read one page at a time.

This is a library, not a script — there is no command-line interface, and
nothing here prints to the console. It is meant to be called, once per page,
by the review application (built separately): typically once for every page
right after a claim's PDF is opened, before the officer starts reviewing.

For one page:
  1. analyse(...)     measure the page: paper and ink brightness, contrast,
                       character size, tilt, lighting, noise, sharpness
  2. advise(...)      decide which processing this specific page needs, if
                       any, and how strong, aimed at what Paddle actually sees
  3. apply_plan(...)  run only the advised steps
  4. engine.read(...) read the result with RapidOCR (PaddleOCR on ONNX Runtime)

process_page(...) does all four for one page and returns a PageResult. Call
it once per page; it never raises for a single bad page — a failure becomes
PageResult.error or .warning instead, so one broken page cannot stop the
rest of a claim from being read.

Why the advice is Paddle-aware
    RapidOCR resizes every image before reading it: it shrinks any image
    whose longer side exceeds its configured limit, then cuts each text
    line out and resizes it to a fixed height for recognition. So what
    matters is the character size after Paddle's own shrink, not the
    original image. The limits are read from the running engine at
    start-up (PaddleEngine.limits), so the advice stays correct if those
    settings change. Colour is kept unless a step needs a grey image.

The rules for every decision — when a step fires and how strong — live in
enhance_rules.json beside this file, not in code, so they can be tuned
without a code change.

Error handling, since this system runs offline and cannot be live-debugged:
every failure that reaches an application boundary (loading a file, starting
the engine, reading a bad config) is raised as OcrStageError; every failure
during one page's processing is attached to that page's PageResult instead
of raised, so the caller can carry on with the rest of the claim. Every
OcrStageError carries a plain-language summary (.summary) and, when it wraps
another exception, the full traceback too (.full_text) — enough to diagnose
from a screenshot of the application's error tab, without needing to
reproduce the failure live. Route both .summary (for a list) and .full_text
(for the expanded detail) to that error tab; do not print them.

Use synthetic documents only.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.errors import StageError
from app.ocr.image_files import read_image_rgb

PDF_EXTS = {".pdf"}
DEFAULT_RULES = Path(__file__).resolve().with_name("enhance_rules.json")

# import name -> pip package name
REQUIRED = {
    "numpy": "numpy", "cv2": "opencv-python-headless", "PIL": "pillow",
    "pymupdf": "pymupdf", "rapidocr": "rapidocr", "onnxruntime": "onnxruntime",
}
# Quietens RapidOCR's own logging; callers may override via PaddleEngine(params=...).
DEFAULT_ENGINE_PARAMS: dict[str, Any] = {"Global.log_level": "error"}

# Every rules file must hold these keys; anything else in it (such as "_what") is ignored.
RULE_KEYS = {
    "analysis": ["long_side_px", "background_kernel_share_of_short_side", "ink_darker_than_paper_by", "stroke_core_share"],
    "crop": ["min_trim_share", "min_scale_gain", "margin_per_text_height", "min_margin_px"],
    "denoise": ["above_noise_sigma", "strength_per_sigma", "max_strength"],
    "deskew": ["search_limit_deg", "min_tilt_deg", "min_alignment_gain"],
    "flatten_light": ["above_background_spread", "below_paper_level", "kernel_per_text_height"],
    "stretch_contrast": ["below_text_contrast", "target_ink_level", "target_paper_level"],
    "brighten": ["below_paper_level", "target_paper_level", "min_gamma"],
    "resize": ["size_basis", "below_text_height_px", "above_text_height_px", "target_text_height_px",
               "max_upscale", "min_downscale"],
    "sharpen": ["below_sharpness", "min_amount", "max_amount", "radius_px"],
    "adaptive_threshold": ["below_text_contrast", "block_per_text_height", "offset_per_noise_sigma", "min_offset"],
}

# Loaded by load_libraries() after the dependency check, so this module can be
# imported and check_dependencies() called before the heavy libraries exist.
cv2: Any = None
np: Any = None


def load_libraries() -> None:
    global cv2, np
    import cv2 as _cv2
    import numpy as _np

    cv2, np = _cv2, _np


def check_dependencies() -> list[str]:
    """Pip package names this module needs that are not installed. Empty
    means everything is present. Call this, and act on a non-empty result,
    before calling load_libraries() or anything else here."""
    return [pkg for mod, pkg in REQUIRED.items() if importlib.util.find_spec(mod) is None]


def pkg_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


# ---------------------------------------------------------------- errors


class OcrStageError(StageError):
    """Raised, or attached to a PageResult, when a stage of OCR processing
    fails. Same shape as every other error in the application (see
    app/errors.py): a stage ("config" | "startup" | "load" | "enhance" |
    "ocr"), a plain description, file and page context, and the wrapped
    exception with its traceback. Kept as its own type so a caller can tell
    an OCR failure apart from any other."""


def load_rules(path: Path = DEFAULT_RULES) -> dict[str, Any]:
    try:
        rules = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OcrStageError("config", f"rules file not found: {path}", cause=exc) from exc
    except json.JSONDecodeError as exc:
        raise OcrStageError("config", f"rules file {path} is not valid JSON", cause=exc) from exc
    missing = [f"{section}.{key}" for section, keys in RULE_KEYS.items() for key in keys if key not in rules.get(section, {})]
    if missing:
        raise OcrStageError("config", f"rules file {path} is missing: {', '.join(missing)}")
    if rules["resize"]["size_basis"] not in ("small", "median"):
        raise OcrStageError("config", f"rules file {path}: resize.size_basis must be 'small' or 'median'")
    return rules


# ---------------------------------------------------------------- the engine


@dataclass
class PaddleLimits:
    """How RapidOCR resizes images before reading them, read from the running engine."""

    max_side_len: float  # longer images are shrunk to this; infinite when its preprocessing is off
    det_limit_side_len: int
    det_limit_type: str
    rec_height: int  # each text line is resized to this height for recognition

    def scale(self, width: float, height: float) -> float:
        """The factor RapidOCR shrinks an image of this size by before reading it."""
        return min(1.0, self.max_side_len / max(width, height))


@dataclass
class Word:
    text: str
    confidence: float
    box: list[list[float]]  # four corner points, in the coordinates of the image actually read
    page_box: list[list[float]] | None = None  # the same corners on the page as rendered (set by geometry.py)


@dataclass
class Reading:
    words: list[Word]
    seconds: float


def to_points(box: Any) -> list[list[float]]:
    return [[round(float(p[0]), 1), round(float(p[1]), 1)] for p in box]


class PaddleEngine:
    """Loads once and is reused for every page. Construction and reads never
    raise a bare exception — both convert any failure into OcrStageError."""

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        merged = dict(DEFAULT_ENGINE_PARAMS)
        merged.update(params or {})
        try:
            from rapidocr import RapidOCR

            self.version = pkg_version("rapidocr")
            self._ocr = RapidOCR(params=merged)
            cfg = self._ocr.cfg
            preprocess = bool(cfg.Global.use_preprocess_img)
            self.limits = PaddleLimits(
                max_side_len=float(cfg.Global.max_side_len) if preprocess else math.inf,
                det_limit_side_len=int(cfg.Det.limit_side_len),
                det_limit_type=str(cfg.Det.limit_type),
                rec_height=int(cfg.Rec.rec_img_shape[1]),
            )
        except Exception as exc:
            raise OcrStageError("startup", "the OCR engine could not be started", cause=exc) from exc

    def read(self, bgr: Any) -> Reading:
        start = time.perf_counter()
        try:
            out = self._ocr(bgr)
        except Exception as exc:
            raise OcrStageError("ocr", "the OCR engine raised an error while reading a page", cause=exc) from exc
        seconds = time.perf_counter() - start
        if out is None or getattr(out, "txts", None) is None:
            if out is not None and not hasattr(out, "txts"):
                raise OcrStageError("ocr", f"unrecognised result type ({type(out).__name__}) from rapidocr "
                                    f"{self.version}; this module needs updating for the installed version")
            return Reading([], seconds)
        words = [Word(str(t), float(s), to_points(b)) for b, t, s in zip(out.boxes, out.txts, out.scores)]
        return Reading(words, seconds)


# ---------------------------------------------------------------- loading pages


@dataclass
class Page:
    source: Path
    number: int  # 1-based
    bgr: Any


def to_bgr(arr: Any, channels: int) -> Any:
    if channels == 1:
        return cv2.cvtColor(arr[:, :, 0], cv2.COLOR_GRAY2BGR)
    if channels == 3:
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    if channels == 4:
        return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
    raise ValueError(f"unsupported channel count {channels}")


def load_pages(path: Path, dpi: int = 300) -> list[Page]:
    """Render every page of a PDF, or load a single image, as BGR arrays.
    Raises OcrStageError on any failure — a file that cannot be opened has
    no pages to give back, so this cannot degrade to a partial result."""
    try:
        if path.suffix.lower() in PDF_EXTS:
            import pymupdf

            pages: list[Page] = []
            with pymupdf.open(path) as doc:
                if doc.needs_pass:
                    raise ValueError("the PDF is password-protected")
                for page in doc:
                    pix = page.get_pixmap(dpi=dpi, alpha=False)
                    flat = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)
                    arr = flat[:, : pix.width * pix.n].reshape(pix.height, pix.width, pix.n)
                    pages.append(Page(path, page.number + 1, to_bgr(arr, pix.n)))
            return pages

        rgb = read_image_rgb(path)  # shared with the display, so both use one coordinate frame
        return [Page(path, 1, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))]
    except Exception as exc:
        raise OcrStageError("load", "could not open or render this file", file=path.name, cause=exc) from exc


# ---------------------------------------------------------------- 1. analyse


@dataclass
class Analysis:
    """Measurements of one page. Everything except the size and the marked area
    is measured where the text is, so plain margins and borders do not count."""

    width_px: int
    height_px: int
    content_box: tuple[int, int, int, int] | None  # x0, y0, x1, y1 around every mark on the page
    paper_level: float  # brightness of the paper right around the text, 0 black .. 255 white
    ink_level: float  # brightness of the dark core of the strokes
    text_contrast: float  # how much darker the stroke cores are than the paper around them
    ink_share: float  # fraction of the page that is ink
    text_height_px: float | None  # median character height; None when no text was found
    text_height_p10_px: float | None  # small characters
    text_height_p90_px: float | None  # large characters
    tilt_deg: float
    tilt_gain: float  # how much more distinct the lines are once straightened (1.0 = no better)
    tilt_at_limit: bool  # the tilt estimate hit the search limit, so it is not trusted
    background_spread: float  # how much the paper brightness varies across the text area
    noise_sigma: float  # grain in the plain paper between the text, in grey levels
    sharpness: float  # edge strength around the text (variance of the Laplacian)


def odd(value: float, minimum: int = 3) -> int:
    n = max(minimum, int(round(value)))
    return n if n % 2 else n + 1


def level_at(hist: Any, fraction: float) -> float:
    """Grey level below which `fraction` of the counted pixels fall, from a 256-bin histogram."""
    total = hist.sum()
    if total == 0:
        return 0.0
    return float(np.searchsorted(np.cumsum(hist), fraction * total))


def weighted_percentiles(values: Any, weights: Any, fractions: list[float]) -> list[float]:
    """Percentiles where each value counts in proportion to its weight."""
    order = np.argsort(values)
    cumulative = np.cumsum(weights[order], dtype=np.float64)
    positions = np.searchsorted(cumulative, np.array(fractions) * cumulative[-1])
    return [float(values[order][min(p, len(order) - 1)]) for p in positions]


def paper_background(gray: Any, kernel_px: int, smooth: bool) -> Any:
    """The paper without the text: a morphological closing wider than the
    characters fills each letter in with the paper around it. Worked out on a
    reduced copy so the kernel stays small; lighting changes slowly anyway."""
    h, w = gray.shape[:2]
    factor = min(1.0, 51.0 / kernel_px)
    small = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA) if factor < 1.0 else gray
    k = odd(kernel_px * factor)
    background = cv2.morphologyEx(small, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    if smooth:
        background = cv2.GaussianBlur(background, (0, 0), k / 4.0)
    return cv2.resize(background, (w, h), interpolation=cv2.INTER_LINEAR) if factor < 1.0 else background


def rotate_bound(image: Any, angle: float) -> Any:
    """Rotate and grow the canvas so no corner of the page is cut off."""
    h, w = image.shape[:2]
    cx, cy = w / 2.0, h / 2.0
    matrix = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_w, new_h = int(round(h * sin + w * cos)), int(round(h * cos + w * sin))
    matrix[0, 2] += new_w / 2.0 - cx
    matrix[1, 2] += new_h / 2.0 - cy
    return cv2.warpAffine(image, matrix, (new_w, new_h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def estimate_tilt(ink: Any, limit: float) -> tuple[float, float, bool]:
    """Find the rotation that makes text lines level, within +/- limit degrees.

    Level text gives dense rows separated by blank gaps, so the row sums of the
    ink mask are most uneven at the right angle. Returns the angle, how much
    more uneven the rows are there than at 0 degrees, and whether the answer
    sits at the limit (then the true tilt is outside the search, or unclear).
    """
    sh, sw = ink.shape
    centre = (sw / 2.0, sh / 2.0)
    scores: dict[float, float] = {}

    def score(angle: float) -> float:
        angle = round(float(angle), 2)
        if angle not in scores:
            matrix = cv2.getRotationMatrix2D(centre, angle, 1.0)
            turned = cv2.warpAffine(ink, matrix, (sw, sh), flags=cv2.INTER_NEAREST, borderValue=0)
            scores[angle] = float(np.var(turned.sum(axis=1, dtype=np.float64)))
        return scores[angle]

    best = max(np.arange(-limit, limit + 1e-9, 1.0), key=score)
    best = max(np.arange(max(-limit, best - 1.0), min(limit, best + 1.0) + 1e-9, 0.1), key=score)
    best = round(float(best), 2)
    level = score(0.0)
    gain = score(best) / level if level > 0 else 1.0
    return best, round(gain, 3), abs(best) >= limit - 0.05


def analyse(bgr: Any, rules: dict[str, Any]) -> Analysis:
    ra = rules["analysis"]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # Ink is judged against the paper right around it, not against the whole
    # page, so a white margin or a dark border around a photographed document
    # counts neither as paper nor as ink.
    kernel = odd(min(h, w) * ra["background_kernel_share_of_short_side"], minimum=15)
    background = paper_background(gray, kernel, smooth=False)
    ink_mask = gray.astype(np.float32) < background.astype(np.float32) * (1.0 - ra["ink_darker_than_paper_by"])
    ink = ink_mask.astype(np.uint8) * 255

    # Ink blobs: their sizes give the character height (each blob weighted by
    # its ink, so specks cannot outvote letters) and their extent gives the
    # marked area of the page.
    _, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    lefts, tops = stats[1:, cv2.CC_STAT_LEFT], stats[1:, cv2.CC_STAT_TOP]
    widths, heights = stats[1:, cv2.CC_STAT_WIDTH], stats[1:, cv2.CC_STAT_HEIGHT]
    areas = stats[1:, cv2.CC_STAT_AREA]
    letter_sized = (heights >= 4) & (heights <= h / 10) & (widths <= w / 10) & (areas >= 8)
    if int(letter_sized.sum()) >= 15:
        p10, median, p90 = weighted_percentiles(heights[letter_sized], areas[letter_sized], [0.1, 0.5, 0.9])
    else:
        p10 = median = p90 = None
    marks = areas >= 8
    content = None
    if marks.any():
        content = (int(lefts[marks].min()), int(tops[marks].min()),
                   int((lefts[marks] + widths[marks]).max()), int((tops[marks] + heights[marks]).max()))

    # The text area: paper within a few character heights of ink, worked out on
    # a reduced copy, which is also what the tilt search uses.
    factor = min(1.0, ra["long_side_px"] / max(h, w))
    small_ink = cv2.resize(ink, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA) if factor < 1.0 else ink
    reach = odd(kernel * factor / 2.0)
    near_small = cv2.dilate(small_ink, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (reach, reach)))
    text_area = cv2.resize(near_small, (w, h), interpolation=cv2.INTER_NEAREST) > 0
    if not text_area.any():
        text_area = np.ones_like(ink_mask)
    edges = cv2.dilate(ink, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))) > 0

    # Paper level and how much it varies, measured only where the text is.
    paper_hist = np.bincount(background[text_area], minlength=256)
    paper = level_at(paper_hist, 0.5)
    spread = level_at(paper_hist, 0.95) - level_at(paper_hist, 0.05)
    if ink_mask.any():
        # At the dark core of the strokes: letter edges are only faintly darker
        # than the paper, and there are far more edge pixels than core pixels.
        core = ra["stroke_core_share"]
        ink_lv = level_at(np.bincount(gray[ink_mask], minlength=256), core)
        darkening = np.clip(background[ink_mask].astype(np.int16) - gray[ink_mask], 0, 255).astype(np.uint8)
        contrast = level_at(np.bincount(darkening, minlength=256), 1.0 - core)
    else:
        ink_lv, contrast = paper, 0.0

    # Noise: Immerkaer's estimator, on the plain paper between the text.
    plain = text_area & ~edges
    laplace_mask = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float32)
    response = np.abs(cv2.filter2D(gray.astype(np.float32), -1, laplace_mask))
    noise = float(math.sqrt(math.pi / 2) / 6 * response[plain].mean()) if plain.any() else 0.0

    # Sharpness: how strong the edges are right around the text.
    laplacian = cv2.Laplacian(gray, cv2.CV_32F)
    sharpness = float(laplacian[edges].var()) if edges.any() else 0.0

    tilt, gain, at_limit = estimate_tilt(small_ink, rules["deskew"]["search_limit_deg"])

    return Analysis(
        width_px=int(w), height_px=int(h), content_box=content,
        paper_level=paper, ink_level=ink_lv, text_contrast=contrast,
        ink_share=round(float(ink_mask.mean()), 4),
        text_height_px=median, text_height_p10_px=p10, text_height_p90_px=p90,
        tilt_deg=tilt, tilt_gain=gain, tilt_at_limit=bool(at_limit),
        background_spread=spread, noise_sigma=round(noise, 2), sharpness=round(sharpness, 1),
    )


# ---------------------------------------------------------------- 2. advise


@dataclass
class Step:
    name: str
    params: dict[str, float]  # exactly what the step function receives
    reason: str  # the measurement that triggered it, and how strong it is


def size_basis(a: Analysis, rules: dict[str, Any]) -> tuple[float | None, str]:
    if rules["resize"]["size_basis"] == "small":
        return a.text_height_p10_px, "small characters"
    return a.text_height_px, "characters"


def advise(a: Analysis, rules: dict[str, Any], limits: PaddleLimits) -> tuple[list[Step], list[str]]:
    """Turn measurements into a plan. Returns the steps, in the order they are
    applied, and notes about steps considered and deliberately left out."""
    steps: list[Step] = []
    notes: list[str] = []
    th = a.text_height_px
    w, h = a.width_px, a.height_px  # the page size Paddle will be given, updated by crop and resize

    r = rules["crop"]
    if a.content_box:
        margin = max(r["min_margin_px"], r["margin_per_text_height"] * (th or 0.0))
        x0, y0 = max(0, int(a.content_box[0] - margin)), max(0, int(a.content_box[1] - margin))
        x1, y1 = min(w, int(a.content_box[2] + margin)), min(h, int(a.content_box[3] + margin))
        trimmed = 1.0 - (x1 - x0) * (y1 - y0) / (w * h)
        before, after = limits.scale(w, h), limits.scale(x1 - x0, y1 - y0)
        if trimmed >= r["min_trim_share"] and after - before >= r["min_scale_gain"]:
            steps.append(Step("crop", {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
                              f"{trimmed:.0%} of the page holds no marks at all: keep every mark plus {margin:.0f} px, "
                              f"so Paddle shrinks the page x{after:.2f} instead of x{before:.2f}"))
            w, h = x1 - x0, y1 - y0
        elif trimmed >= r["min_trim_share"]:
            notes.append(f"{trimmed:.0%} of the page is empty, but cropping it would change Paddle's shrink only from "
                         f"x{before:.2f} to x{after:.2f} (needs a gain of {r['min_scale_gain']}): not cropped")

    r = rules["denoise"]
    if a.noise_sigma > r["above_noise_sigma"]:
        strength = round(min(r["max_strength"], a.noise_sigma * r["strength_per_sigma"]), 1)
        steps.append(Step("denoise", {"strength": strength},
                          f"grain on the paper is {a.noise_sigma:.1f} (above {r['above_noise_sigma']}): strength {strength}"))

    r = rules["deskew"]
    if abs(a.tilt_deg) >= r["min_tilt_deg"]:
        if a.tilt_at_limit:
            notes.append(f"tilt estimate {a.tilt_deg:+.1f} deg sits at the {r['search_limit_deg']} deg search limit, "
                         "so it is not trusted: not rotated")
        elif a.tilt_gain < r["min_alignment_gain"]:
            notes.append(f"tilt {a.tilt_deg:+.1f} deg measured, but straightening makes the lines only "
                         f"{a.tilt_gain:.2f}x more distinct (needs {r['min_alignment_gain']}): not rotated")
        else:
            steps.append(Step("rotate", {"angle_deg": a.tilt_deg},
                              f"text tilted {a.tilt_deg:+.1f} deg; straightening makes the lines {a.tilt_gain:.2f}x more distinct"))

    r = rules["flatten_light"]
    flattened = a.background_spread > r["above_background_spread"] and a.paper_level < r["below_paper_level"]
    if a.background_spread > r["above_background_spread"] and not flattened:
        notes.append(f"brightness varies by {a.background_spread:.0f} across the text, but the paper is already white "
                     f"({a.paper_level:.0f}), so this is dark print or boxes, not shadow: lighting left alone")
    if flattened:
        kernel = (odd(th * r["kernel_per_text_height"], minimum=15) if th
                  else odd(min(a.width_px, a.height_px) / 20.0, minimum=15))
        steps.append(Step("flatten_light", {"kernel_px": kernel},
                          f"paper brightness varies by {a.background_spread:.0f} grey levels across the text "
                          f"(above {r['above_background_spread']}): shadows or a gradient; kernel {kernel} px"))

    # The contrast and brightness rules work from the levels after flattening,
    # which turns the paper white and scales the text's darkening with it.
    paper, contrast = a.paper_level, a.text_contrast
    if flattened and paper > 0:
        contrast, paper = min(255.0, contrast * 255.0 / paper), 255.0
    ink = paper - contrast

    r = rules["stretch_contrast"]
    stretched = 0 < contrast < r["below_text_contrast"] and a.ink_share > 0
    if stretched:
        ti, tp = r["target_ink_level"], r["target_paper_level"]
        steps.append(Step("stretch_contrast",
                          {"ink_level": round(ink, 1), "paper_level": round(paper, 1), "target_ink": ti, "target_paper": tp},
                          f"text contrast {contrast:.0f} is below {r['below_text_contrast']}: stretch {(tp - ti) / contrast:.1f}x "
                          f"(ink {ink:.0f} -> {ti:.0f}, paper {paper:.0f} -> {tp:.0f})"))
    elif contrast <= 0:
        notes.append("no measurable difference between ink and paper: contrast left unchanged")

    r = rules["brighten"]
    if not (flattened or stretched) and 0 < paper < r["below_paper_level"]:
        gamma = max(r["min_gamma"], math.log(r["target_paper_level"] / 255.0) / math.log(paper / 255.0))
        steps.append(Step("brighten", {"gamma": round(gamma, 3)},
                          f"paper is at {paper:.0f} (below {r['below_paper_level']}): gamma {gamma:.2f} "
                          f"lifts it to about {255.0 * (paper / 255.0) ** gamma:.0f}"))

    small, label = size_basis(a, rules)
    r = rules["resize"]
    factor = 1.0
    if small is None:
        notes.append("no letter-sized marks found, so character height is unknown: size left unchanged")
    else:
        seen = small * limits.scale(w, h)
        room = limits.max_side_len / max(w, h)  # beyond this, Paddle shrinks the page straight back
        if 0 < seen < r["below_text_height_px"]:
            wanted = min(r["max_upscale"], r["target_text_height_px"] / small)
            factor = min(wanted, room)
            if factor < 1.05:
                needed = int(math.ceil(max(w, h) * wanted / 100.0) * 100)
                notes.append(f"{label} reach Paddle at only {seen:.0f} px, but the page is already at Paddle's size limit "
                             f"({limits.max_side_len:.0f} px), so enlarging it would be undone. Paddle would need a limit of "
                             f"about {needed} px; larger limits cost time and memory")
                factor = 1.0
            elif factor < wanted - 0.05:
                notes.append(f"{label} would need x{wanted:.2f}, held to x{factor:.2f} by Paddle's size limit "
                             f"({limits.max_side_len:.0f} px)")
        elif seen > r["above_text_height_px"]:
            factor = max(r["min_downscale"], r["target_text_height_px"] / small)
        if abs(factor - 1.0) >= 0.05:
            after = small * factor * limits.scale(w * factor, h * factor)
            side = "below" if factor > 1 else "above"
            limit = r["below_text_height_px"] if factor > 1 else r["above_text_height_px"]
            steps.append(Step("resize", {"factor": round(factor, 3)},
                              f"{label} are {small:.0f} px and reach Paddle at {seen:.0f} px ({side} {limit}): "
                              f"scale x{factor:.2f} so they reach it at about {after:.0f} px"))
        else:
            factor = 1.0

    r = rules["adaptive_threshold"]
    binarize = a.text_contrast < r["below_text_contrast"]
    block, offset = 0, 0.0
    if binarize:
        size = (th or min(a.width_px, a.height_px) / 40.0) * factor
        block = odd(size * r["block_per_text_height"], minimum=15)
        offset = round(max(r["min_offset"], a.noise_sigma * r["offset_per_noise_sigma"]), 1)

    r = rules["sharpen"]
    if a.sharpness < r["below_sharpness"]:
        if binarize:
            notes.append(f"edges are soft (sharpness {a.sharpness:.0f}), but sharpening is skipped because the page is thresholded")
        else:
            shortfall = 1.0 - a.sharpness / r["below_sharpness"]
            amount = round(r["min_amount"] + shortfall * (r["max_amount"] - r["min_amount"]), 2)
            steps.append(Step("sharpen", {"amount": amount, "radius_px": r["radius_px"]},
                              f"edge sharpness {a.sharpness:.0f} is below {r['below_sharpness']}: unsharp mask, amount {amount}"))

    if binarize:
        steps.append(Step("adaptive_threshold", {"block_px": block, "offset": offset},
                          f"text contrast {a.text_contrast:.0f} is very low (below {rules['adaptive_threshold']['below_text_contrast']}): "
                          f"local black and white, block {block} px, offset {offset}"))

    return steps, notes


# ---------------------------------------------------------------- 3. apply
# Geometry steps work on colour or grey; tone steps need grey, so the page is
# turned grey only when the plan holds one. Paddle reads colour natively.

TONE_STEPS = {"flatten_light", "stretch_contrast", "brighten", "adaptive_threshold"}


def step_crop(img: Any, x0: int, y0: int, x1: int, y1: int) -> Any:
    return img[int(y0):int(y1), int(x0):int(x1)].copy()


def step_denoise(img: Any, strength: float) -> Any:
    if img.ndim == 3:
        return cv2.fastNlMeansDenoisingColored(img, None, float(strength), float(strength), 7, 21)
    return cv2.fastNlMeansDenoising(img, None, h=float(strength), templateWindowSize=7, searchWindowSize=21)


def step_rotate(img: Any, angle_deg: float) -> Any:
    return rotate_bound(img, angle_deg)


def step_flatten_light(gray: Any, kernel_px: int) -> Any:
    return cv2.divide(gray, paper_background(gray, kernel_px, smooth=True), scale=255)


def step_stretch_contrast(gray: Any, ink_level: float, paper_level: float, target_ink: float, target_paper: float) -> Any:
    levels = np.arange(256, dtype=np.float32)
    mapped = (levels - ink_level) * (target_paper - target_ink) / (paper_level - ink_level) + target_ink
    return cv2.LUT(gray, np.clip(mapped, 0, 255).astype(np.uint8))


def step_brighten(gray: Any, gamma: float) -> Any:
    levels = np.arange(256, dtype=np.float32) / 255.0
    return cv2.LUT(gray, np.clip(255.0 * levels ** gamma, 0, 255).astype(np.uint8))


def step_resize(img: Any, factor: float) -> Any:
    interpolation = cv2.INTER_CUBIC if factor > 1.0 else cv2.INTER_AREA
    return cv2.resize(img, None, fx=factor, fy=factor, interpolation=interpolation)


def step_sharpen(img: Any, amount: float, radius_px: float) -> Any:
    blurred = cv2.GaussianBlur(img, (0, 0), radius_px)
    return cv2.addWeighted(img, 1.0 + amount, blurred, -amount, 0)


def step_adaptive_threshold(gray: Any, block_px: int, offset: float) -> Any:
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, int(block_px), float(offset))


STEP_FUNCTIONS = {
    "crop": step_crop,
    "denoise": step_denoise,
    "rotate": step_rotate,
    "flatten_light": step_flatten_light,
    "stretch_contrast": step_stretch_contrast,
    "brighten": step_brighten,
    "resize": step_resize,
    "sharpen": step_sharpen,
    "adaptive_threshold": step_adaptive_threshold,
}


def apply_plan(bgr: Any, steps: list[Step]) -> Any:
    """Run only the advised steps, in order, with their advised strengths.
    An empty plan returns the page untouched."""
    img = bgr
    for step in steps:
        if step.name in TONE_STEPS and img.ndim == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img = STEP_FUNCTIONS[step.name](img, **step.params)
    return img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


# ---------------------------------------------------------------- 4. process one page


@dataclass
class PageResult:
    """What processing one page produced.

    `error` is set only when the page has no usable reading at all (the OCR
    engine itself failed) — `words` is then empty and there is nothing for
    the officer to review on this page. `warning` is set when something went
    wrong but the page was still read regardless (enhancement failed, so the
    page was read unprocessed instead) — `words` is still populated. Both are
    safe to show in an error console.
    """

    page_number: int
    words: list[Word]
    used_steps: list[str]  # names of the steps actually applied; empty means read as-is
    analysis: Analysis | None
    notes: list[str]
    seconds: float
    warning: OcrStageError | None = None
    error: OcrStageError | None = None
    applied: list[Step] = field(default_factory=list)  # the steps actually applied, with their parameters


def process_page(page: Page, rules: dict[str, Any], engine: PaddleEngine) -> PageResult:
    """Analyse, advise, prepare and read one page. Call this once per page in
    a loop; it never raises for a failure specific to this page, so check
    .error and .warning on each result rather than wrapping the call in
    try/except yourself. Wrap the loop itself in try/except only to guard
    against something outside this function (a cancelled run, and similar)."""
    to_read = page.bgr
    used_steps: list[str] = []
    applied: list[Step] = []
    analysis: Analysis | None = None
    notes: list[str] = []
    warning: OcrStageError | None = None

    try:
        analysis = analyse(page.bgr, rules)
        steps, notes = advise(analysis, rules, engine.limits)
        if steps:
            to_read = apply_plan(page.bgr, steps)
            used_steps = [step.name for step in steps]
            applied = list(steps)
    except Exception as exc:
        # Enhancement is an optimisation, not a requirement: fall back to
        # reading the page exactly as it is, but keep the failure visible.
        warning = OcrStageError("enhance", "could not analyse or prepare this page; read it unprocessed instead",
                                file=page.source.name, page=page.number, cause=exc)
        to_read, used_steps, applied, notes = page.bgr, [], [], []

    try:
        reading = engine.read(to_read)
    except OcrStageError as exc:
        exc.file, exc.page = page.source.name, page.number
        return PageResult(page.number, [], used_steps, analysis, notes, 0.0, warning=warning, error=exc,
                          applied=applied)
    except Exception as exc:
        # engine.read() is documented to raise only OcrStageError; this is a
        # safety net against an engine that does not honour that contract
        # (a caller's own test double, a future engine swap, or a bug), so a
        # single unanticipated failure here still cannot crash the caller.
        fallback = OcrStageError("ocr", "the OCR engine raised an unexpected error",
                                 file=page.source.name, page=page.number, cause=exc)
        return PageResult(page.number, [], used_steps, analysis, notes, 0.0, warning=warning, error=fallback,
                          applied=applied)

    return PageResult(page.number, reading.words, used_steps, analysis, notes, reading.seconds, warning=warning,
                      applied=applied)
