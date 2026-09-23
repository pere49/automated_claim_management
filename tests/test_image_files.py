"""Photos and screenshots (JPG, PNG, HEIC) as claim files: listed, shown, read,
and shown in exactly the pixel frame the OCR reads them in."""

from __future__ import annotations

import dataclasses
import tempfile
import unittest
from pathlib import Path

from tests.qt import qt_app, wait_until  # sets the off-screen platform first

from PIL import Image

from app.errors import StageError
from app.gui import page_renderer
from app.gui.main_window import MainWindow
from app.gui.settings import load_settings
from app.ocr import OcrReader, read_image_rgb
from tests.fakes import FakeReader, make_pdf

EXIF_ORIENTATION = 0x0112
ROTATE_90_CW = 6  # EXIF: the stored pixels must be turned 90 degrees clockwise to display


def make_image(path: Path, size=(240, 120), orientation: int | None = None) -> Path:
    image = Image.new("RGB", size, "white")
    if orientation is None:
        image.save(path)
    else:
        exif = Image.Exif()
        exif[EXIF_ORIENTATION] = orientation
        image.save(path, exif=exif)
    return path


def heic_supported() -> bool:
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
        with tempfile.TemporaryDirectory() as folder:
            Image.new("RGB", (16, 16)).save(Path(folder) / "x.heic")
        return True
    except Exception:
        return False


class ImageFileTests(unittest.TestCase):
    def setUp(self):
        qt_app()
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.folder = Path(self._dir.name)

    def window(self) -> MainWindow:
        settings = dataclasses.replace(load_settings(), working_folder=self.folder, read_ahead=False)
        w = MainWindow(settings, FakeReader())
        w.confirm = lambda *a: True
        w.show()
        w.start()
        self.addCleanup(w.close)
        return w

    def test_images_are_listed_with_pdfs(self):
        make_pdf(self.folder / "a.pdf", 1)
        make_image(self.folder / "b.png")
        make_image(self.folder / "c.JPG")
        make_image(self.folder / "d.jpeg")
        (self.folder / "e.gif").write_bytes(b"GIF89a")
        w = self.window()
        self.assertEqual(w.files.file_names(), ["a.pdf", "b.png", "c.JPG", "d.jpeg"])

    def test_an_image_opens_as_one_page_and_is_read(self):
        make_image(self.folder / "shot.png")
        w = self.window()
        w.files.file_chosen.emit(self.folder / "shot.png")
        self.assertTrue(wait_until(lambda: not w.session.busy))
        self.assertEqual(w.page_pane.position_text, "Page 1 of 1")
        self.assertEqual(w.ocr_panel.text, "TOTAL    100.00\nTHANK YOU")
        self.assertEqual(w.files.state_of("shot.png"), "read")

    @unittest.skipUnless(heic_supported(), "this Pillow/pillow-heif build cannot write HEIC")
    def test_heic_photo_opens(self):
        make_image(self.folder / "phone.heic")
        w = self.window()
        w.files.file_chosen.emit(self.folder / "phone.heic")
        self.assertTrue(wait_until(lambda: not w.session.busy))
        self.assertEqual(w.page_pane.position_text, "Page 1 of 1")

    def test_display_and_ocr_share_one_frame_for_a_rotated_photo(self):
        path = make_image(self.folder / "sideways.jpg", size=(240, 120), orientation=ROTATE_90_CW)
        pixmap = page_renderer.render_page(path, 1, dpi=300)
        pixels = read_image_rgb(path)
        self.assertEqual((pixmap.width(), pixmap.height()), (120, 240), "orientation flag not applied for display")
        self.assertEqual(pixels.shape[:2], (240, 120), "orientation flag not applied for OCR")

    def test_broken_image_is_refused_with_a_display_error(self):
        bad = self.folder / "broken.png"
        bad.write_bytes(b"not an image")
        with self.assertRaises(StageError) as ctx:
            page_renderer.page_count(bad)
        self.assertEqual((ctx.exception.stage, ctx.exception.file), ("display", "broken.png"))


class RealOcrOnImageTests(unittest.TestCase):
    def test_real_ocr_reads_text_from_a_png(self):
        from PIL import ImageDraw, ImageFont
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "receipt.png"
            image = Image.new("RGB", (900, 300), "white")
            draw = ImageDraw.Draw(image)
            try:
                font = ImageFont.truetype("arial.ttf", 48)
            except OSError:
                self.skipTest("no TrueType font available to draw test text")
            draw.text((40, 110), "TOTAL 1,234.00", fill="black", font=font)
            image.save(path)
            reader = OcrReader()
            reader.start()
            pages = reader.load_pages(path, 300)
            result = reader.read_page(pages[0])
        self.assertEqual(len(pages), 1)
        self.assertIsNone(result.error)
        self.assertIn("1,234.00", " ".join(w.text for w in result.words))


if __name__ == "__main__":
    unittest.main()
