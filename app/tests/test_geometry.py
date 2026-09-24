"""Text positions mapped back onto the displayed page (app/ocr/geometry.py).

A black rectangle is drawn at a known place on a synthetic page, the real
preparation steps (crop, rotate, resize, and tone steps that must not move
anything) are applied to the image, the rectangle is found again in the
result, and its corners are mapped back. They must land within a pixel or
two of where it was drawn.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass

import cv2
import numpy as np

from app.ocr import geometry, pipeline

pipeline.load_libraries()

RECT = (400, 700, 900, 780)  # x0, y0, x1, y1 on a 1600 x 2200 page
TOLERANCE_PX = 2.5


@dataclass
class Step:
    name: str
    params: dict


def page_with_rectangle() -> np.ndarray:
    img = np.full((2200, 1600, 3), 255, np.uint8)
    x0, y0, x1, y1 = RECT
    img[y0:y1, x0:x1] = 0
    return img


def rectangle_corners(img: np.ndarray) -> np.ndarray:
    gray = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ys, xs = np.nonzero(gray < 128)
    box = cv2.boxPoints(cv2.minAreaRect(np.column_stack([xs, ys]).astype(np.float32)))
    return box


def mapped_back(steps: list[Step]) -> np.ndarray:
    page = page_with_rectangle()
    prepared = pipeline.apply_plan(page, steps)
    corners = rectangle_corners(prepared)
    back = geometry.invert(geometry.page_transform(steps, page.shape[1], page.shape[0]))
    return np.array([geometry.apply(back, float(x), float(y)) for x, y in corners])


class GeometryTests(unittest.TestCase):
    def assertLandsOnRectangle(self, points: np.ndarray):
        x0, y0, x1, y1 = RECT
        xs, ys = sorted(points[:, 0]), sorted(points[:, 1])
        # minAreaRect measures pixel centres: the drawn rectangle spans x0 .. x1-1
        for got, want in ((xs[0], x0), (xs[1], x0), (xs[2], x1 - 1), (xs[3], x1 - 1),
                          (ys[0], y0), (ys[1], y0), (ys[2], y1 - 1), (ys[3], y1 - 1)):
            self.assertAlmostEqual(got, want, delta=TOLERANCE_PX)

    def test_no_steps_is_identity(self):
        self.assertEqual(geometry.page_transform([], 100, 100), geometry.IDENTITY)

    def test_crop(self):
        self.assertLandsOnRectangle(mapped_back([Step("crop", {"x0": 120, "y0": 300, "x1": 1500, "y1": 2000})]))

    def test_rotate_both_ways(self):
        for angle in (2.7, -4.1):
            with self.subTest(angle=angle):
                self.assertLandsOnRectangle(mapped_back([Step("rotate", {"angle_deg": angle})]))

    def test_resize_down_and_up(self):
        for factor in (0.62, 1.37):
            with self.subTest(factor=factor):
                self.assertLandsOnRectangle(mapped_back([Step("resize", {"factor": factor})]))

    def test_every_geometric_step_together_with_tone_steps(self):
        steps = [Step("crop", {"x0": 80, "y0": 150, "x1": 1550, "y1": 2100}),
                 Step("rotate", {"angle_deg": -3.3}),
                 Step("flatten_light", {"kernel_px": 61}),
                 Step("resize", {"factor": 0.8})]
        self.assertLandsOnRectangle(mapped_back(steps))

    def test_rotation_matches_opencv_matrix(self):
        """The arithmetic must equal what rotate_bound builds with OpenCV."""
        w, h, angle = 1600.0, 2200.0, 3.7
        ours, new_w, new_h = geometry._rotate_bound(angle, w, h)
        m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        m[0, 2] += new_w / 2 - w / 2
        m[1, 2] += new_h / 2 - h / 2
        for got, want in zip(ours, m.flatten()):
            self.assertAlmostEqual(got, float(want), places=6)
        self.assertEqual((new_w, new_h), pipeline.rotate_bound(np.zeros((int(h), int(w)), np.uint8), angle).shape[::-1])

    def test_attach_sets_every_page_box(self):
        result = pipeline.PageResult(1, [pipeline.Word("A", 1.0, [[10, 10], [20, 10], [20, 20], [10, 20]])],
                                     ["resize"], None, [], 0.0, applied=[Step("resize", {"factor": 0.5})])
        geometry.attach_page_boxes(result, 1000, 1000)
        self.assertEqual(result.words[0].page_box, [[20.0, 20.0], [40.0, 20.0], [40.0, 40.0], [20.0, 40.0]])

    def test_degenerate_transform_is_refused(self):
        with self.assertRaises(ValueError):
            geometry.invert((0.0, 0.0, 0.0, 0.0, 0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
