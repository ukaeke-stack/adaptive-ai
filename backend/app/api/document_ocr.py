"""OCR for scanned PDFs using local Tesseract; bounded to avoid resource exhaustion."""
from io import BytesIO
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
import fitz
from PIL import Image
import pytesseract
from app.security.sessions import require_user

router = APIRouter(prefix="/v1/assistant/documents", tags=["document OCR"])
MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 40
MAX_PIXELS = 20_000_000
MAX_CHARS = 100_000

@router.post("/ocr-pdf")
async def ocr_pdf(request: Request, file: UploadFile = File(...)):
    require_user(request)
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=415, detail="Upload a PDF document.")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="PDF must be 10 MB or smaller.")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="The uploaded file is not a valid PDF.")
    try:
        document = fitz.open(stream=data, filetype="pdf")
        if document.is_encrypted:
            raise HTTPException(status_code=422, detail="Password-protected PDFs are not supported.")
        page_count = document.page_count
        if page_count > MAX_PAGES:
            document.close()
            raise HTTPException(status_code=413, detail=f"OCR is limited to {MAX_PAGES} pages per request.")
        output, total = [], 0
        try:
            for index, page in enumerate(document):
                # Check predicted dimensions before rendering to avoid allocating huge pixmaps.
                rect = page.rect
                scale = 1.5
                predicted_width = int(rect.width * scale)
                predicted_height = int(rect.height * scale)
                if predicted_width <= 0 or predicted_height <= 0 or predicted_width * predicted_height > MAX_PIXELS:
                    raise HTTPException(status_code=413, detail=f"Page {index + 1} is too large to OCR safely.")
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                image = Image.open(BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(image, timeout=20)
                text = text[:max(0, MAX_CHARS - total)]
                output.append({"page": index + 1, "text": text})
                total += len(text)
                if total >= MAX_CHARS:
                    break
        finally:
            document.close()
        combined = "\n\n".join(f"[Page {p['page']}]\n{p['text']}" for p in output)
        return {"filename": (file.filename or "document.pdf")[:200], "page_count": page_count,
                "processed_pages": len(output), "text": combined, "character_count": len(combined),
                "method": "local-tesseract-ocr", "truncated": total >= MAX_CHARS}
    except HTTPException:
        raise
    except pytesseract.TesseractNotFoundError as exc:
        raise HTTPException(status_code=503, detail="OCR engine is not installed on this server. Contact the service administrator.") from exc
    except Exception as exc:
        if "timeout" in str(exc).lower():
            raise HTTPException(status_code=422, detail="OCR took too long on a page. Try a smaller or clearer document.") from exc
        raise HTTPException(status_code=422, detail="Could not OCR this PDF. It may be damaged or contain unsupported pages.") from exc


@router.post("/ocr-image")
async def ocr_image(request: Request, file: UploadFile = File(...)):
    """Extract text from a user-selected photo or scanned image using local OCR."""
    require_user(request)
    allowed_types = {"image/png", "image/jpeg", "image/webp", "image/tiff", "image/bmp"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=415, detail="Upload a PNG, JPEG, WEBP, TIFF, or BMP image.")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image must be 10 MB or smaller.")
    try:
        image = Image.open(BytesIO(data))
        image.verify()
        image = Image.open(BytesIO(data))
        width, height = image.size
        if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
            raise HTTPException(status_code=413, detail="Image dimensions exceed the safe OCR limit.")
        image = image.convert("RGB")
        extracted = pytesseract.image_to_string(image, timeout=20)[:MAX_CHARS]
        return {"filename": (file.filename or "image")[:200], "text": extracted,
                "character_count": len(extracted), "width": width, "height": height,
                "method": "local-tesseract-ocr", "truncated": len(extracted) >= MAX_CHARS}
    except HTTPException:
        raise
    except pytesseract.TesseractNotFoundError as exc:
        raise HTTPException(status_code=503, detail="OCR engine is not installed on this server. Contact the service administrator.") from exc
    except Exception as exc:
        if "timeout" in str(exc).lower():
            raise HTTPException(status_code=422, detail="OCR took too long. Try a smaller or clearer image.") from exc
        raise HTTPException(status_code=422, detail="Could not OCR this image. It may be damaged or unsupported.") from exc
