"""Convert a PDF file into PNG images stored in an ``images`` folder."""

import argparse
from pathlib import Path

import fitz  # Install with: pip install PyMuPDF


def convert_pdf_to_images(pdf_path: str, output_dir: str = "images") -> None:
    pdf_file = Path(pdf_path)
    if not pdf_file.is_file():
        raise FileNotFoundError(f"PDF file not found: {pdf_file}")

    image_dir = Path(output_dir)
    image_dir.mkdir(parents=True, exist_ok=True)

    with fitz.open(pdf_file) as pdf:
        for page_number, page in enumerate(pdf, start=1):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            pixmap.save(str(image_dir / f"page_{page_number:03d}.png"))


# if __name__ == "__main__":
	# parser = argparse.ArgumentParser(description="Convert a PDF to images.")
	# parser.add_argument("pdf", help="Path to the PDF file")
	# parser.add_argument("-o", "--output", default="images", help="Output folder")
	# args = parser.parse_args()

pdf_path = "EA_Card Expenses_August.pdf"  # Replace with your PDF file path
output_dir = "./images"  # Replace with your desired output folder
convert_pdf_to_images(pdf_path, output_dir)
