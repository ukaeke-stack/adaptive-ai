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
        if document.page_count > MAX_PAGES:
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
        return {"filename": (file.filename or "document.pdf")[:200], "page_count": document.page_count,
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
