import base64
import io
import pymupdf as fitz
from PIL import Image

def get_pdf_page_count(pdf_path: str) -> int:
    """Returns the total number of pages in a PDF document."""
    try:
        doc = fitz.open(pdf_path)
        count = len(doc)
        doc.close()
        return count
    except Exception as e:
        print(f"Error getting PDF page count: {e}")
        return 0

def render_pdf_page_to_base64(
    pdf_path: str,
    page_number: int = 0,
    zoom: float = 1.5,
    force_portrait: bool = False
) -> str:
    """Renders a specific PDF page to a base64 encoded PNG string."""
    try:
        doc = fitz.open(pdf_path)
        if page_number < 0 or page_number >= len(doc):
            page_number = 0
        
        page = doc.load_page(page_number)
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_bytes = pix.tobytes("png")
        doc.close()

        if force_portrait and pix.width > pix.height:
            with Image.open(io.BytesIO(img_bytes)) as image:
                image = image.transpose(Image.Transpose.ROTATE_90)
                output = io.BytesIO()
                image.save(output, format="PNG")
                img_bytes = output.getvalue()

        return base64.b64encode(img_bytes).decode("utf-8")
    except Exception as e:
        print(f"Error rendering PDF page: {e}")
        return ""

def image_file_to_base64(image_path: str, max_size: tuple = (1600, 1600)) -> str:
    """Loads an image file, resizes if needed, and returns base64 string."""
    try:
        with Image.open(image_path) as img:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            buffered = io.BytesIO()
            img.save(buffered, format="PNG")
            return base64.b64encode(buffered.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"Error converting image to base64: {e}")
        return ""
