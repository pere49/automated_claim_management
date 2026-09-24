"""PROTOTYPE (tools/) — detection-resolution trial, step 1 of 2: read the pages.

Reads every test page once per variant in trial_config.json and saves each
reading (text, box, confidence), the time each engine stage took, and the
detection size actually used. Page preparation is advised for each
variant's own engine limits (shared between variants with equal limits), as
the application would do it.

A variant with "detect_max_side" overrides RapidOCR's detector sizing for
this trial only (its get_preprocess otherwise picks 2000 px for these pages
whatever Det.limit_side_len says). A variant with "recognize_full_resolution"
keeps detection unchanged but cuts each detected line from the full-resolution
page (boxes mapped back through RapidOCR's own shrink ratio and padding).

    .venv/Scripts/python.exe tools/ocr_resolution_trial/run_trial.py

Output: outputs/ocr_resolution_trial/readings.json (ignored by git: holds
document text). Score it with score.py. Not part of the application.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.config_files import read_json_config  # noqa: E402
from app.ocr import OcrReader  # noqa: E402
from app.ocr import pipeline  # noqa: E402
import numpy as np  # noqa: E402
from rapidocr.ch_ppocr_det.utils import DetPreProcess  # noqa: E402
from rapidocr.utils.process_img import get_rotate_crop_image  # noqa: E402

CONFIG = Path(__file__).resolve().with_name("trial_config.json")


def rendered_pages(reader: OcrReader, cfg: dict) -> list:
    folder = ROOT / cfg["pages_folder"]
    pdfs, seen = [], set()
    for path in sorted(p for p in folder.iterdir() if p.suffix.lower() == ".pdf"):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest not in seen:  # identical files are counted once
            seen.add(digest)
            pdfs.append(path)
    return [page for pdf in pdfs for page in reader.load_pages(pdf, cfg["pdf_render_dpi"])]


def prepare(pages: list, rules: dict, limits) -> list[tuple[str, object]]:
    out = []
    for page in pages:
        analysis = pipeline.analyse(page.bgr, rules)
        steps, _ = pipeline.advise(analysis, rules, limits)
        out.append((f"{page.source.name}#{page.number}", pipeline.apply_plan(page.bgr, steps) if steps else page.bgr))
    return out


def make_engine(variant: dict) -> tuple[pipeline.PaddleEngine, list]:
    engine = pipeline.PaddleEngine({**pipeline.DEFAULT_ENGINE_PARAMS, **variant.get("params", {})})
    det = engine._ocr.text_det
    used: list[int] = []
    original = det.get_preprocess
    side = variant.get("detect_max_side")

    def sizing(max_wh: int, _det=det, _side=side, _original=original):
        op = DetPreProcess(_side, "max", _det.mean, _det.std) if _side else _original(max_wh)
        used.append(min(op.limit_side_len, max_wh) if op.limit_type == "max" else max_wh)
        return op

    det.get_preprocess = sizing
    if variant.get("recognize_full_resolution"):
        full_resolution_crops(engine._ocr)
    return engine, used


def full_resolution_crops(ocr) -> None:
    """Make RapidOCR cut text lines from the image it was given, not from its
    shrunk working copy. Detection and the returned boxes are unchanged."""
    original_pre, original_detect = ocr.preprocess_img, ocr.detect_and_crop

    def pre(ori_img):
        ocr._trial_full = ori_img
        return original_pre(ori_img)

    def detect(img, op_record):
        small_h, small_w = img.shape[:2]            # before RapidOCR's padding
        _, det_res = original_detect(img, op_record)
        full = ocr._trial_full
        full_h, full_w = full.shape[:2]
        pad = op_record.get("padding_1", {"top": 0, "left": 0})
        crops = []
        for box in det_res.boxes:
            pts = np.array(box, dtype=np.float32).copy()
            pts[:, 0] = (pts[:, 0] - pad["left"]) * full_w / small_w
            pts[:, 1] = (pts[:, 1] - pad["top"]) * full_h / small_h
            crops.append(get_rotate_crop_image(full, pts))
        return crops, det_res

    ocr.preprocess_img, ocr.detect_and_crop = pre, detect


def read_all(engine: pipeline.PaddleEngine, used: list, pages: list) -> list[dict]:
    engine._ocr(pages[0][1])  # warm-up, not timed
    results = []
    for page_id, image in pages:
        used.clear()
        start = time.perf_counter()
        out = engine._ocr(image)
        total = time.perf_counter() - start
        stages = [round(float(x), 3) for x in (getattr(out, "elapse_list", None) or [])]
        words = [] if out.txts is None else [
            {"text": str(t), "conf": round(float(s), 4), "box": pipeline.to_points(b)}
            for b, t, s in zip(out.boxes, out.txts, out.scores)]
        results.append({"page": page_id, "seconds": round(total, 3), "det_cls_rec": stages,
                        "detect_side_px": used[0] if used else None, "words": words})
    return results


def main() -> None:
    cfg = read_json_config(CONFIG, {"variants": list, "pages_folder": str, "output_folder": str})
    reader = OcrReader()
    reader.start()
    pages = rendered_pages(reader, cfg)
    print(f"{len(pages)} pages rendered", flush=True)
    out_dir = ROOT / cfg["output_folder"]
    out_dir.mkdir(parents=True, exist_ok=True)
    readings, prepared_by_limit = {}, {}
    for variant in cfg["variants"]:
        engine, used = make_engine(variant)
        limit = engine.limits.max_side_len
        if limit not in prepared_by_limit:
            prepared_by_limit[limit] = prepare(pages, reader._rules, engine.limits)
        readings[variant["name"]] = read_all(engine, used, prepared_by_limit[limit])
        rows = readings[variant["name"]]
        secs = sum(r["seconds"] for r in rows)
        sides = sorted({r["detect_side_px"] for r in rows if r["detect_side_px"]})
        print(f"{variant['name']:24} {secs / len(rows):5.2f} s/page  detection sizes used {sides[0]}-{sides[-1]} px",
              flush=True)
        (out_dir / "readings.json").write_text(json.dumps(readings), encoding="utf-8")


if __name__ == "__main__":
    main()
