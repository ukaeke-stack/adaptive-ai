"""Bounded image inspection and transformation endpoints for user-selected files."""
from io import BytesIO
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageOps, UnidentifiedImageError
from app.security.sessions import require_user

router = APIRouter(prefix="/v1/assistant/images", tags=["image tools"])
MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 20_000_000
FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}

async def _read_image(request: Request, file: UploadFile):
    require_user(request)
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image must be 10 MB or smaller.")
    try:
        image = Image.open(BytesIO(data))
        image.verify()
        image = Image.open(BytesIO(data))
        if image.width <= 0 or image.height <= 0 or image.width * image.height > MAX_PIXELS:
            raise HTTPException(status_code=413, detail="Image dimensions exceed the safe processing limit.")
        return image
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status_code=415, detail="Upload a supported, valid image file.") from exc

def _encode(image: Image.Image, fmt: str, quality: int = 85) -> bytes:
    output = BytesIO()
    if fmt == "JPEG" and image.mode not in {"RGB", "L"}:
        image = image.convert("RGB")
    options = {"quality": quality, "optimize": True} if fmt in {"JPEG", "WEBP"} else {"optimize": True}
    image.save(output, format=fmt, **options)
    return output.getvalue()

@router.post("/inspect")
async def inspect_image(request: Request, file: UploadFile = File(...)):
    image = await _read_image(request, file)
    return {"filename": (file.filename or "image")[:200], "format": image.format,
            "width": image.width, "height": image.height, "mode": image.mode,
            "has_transparency": "A" in image.getbands(), "megapixels": round(image.width*image.height/1_000_000, 3)}

@router.post("/resize")
async def resize_image(request: Request, file: UploadFile = File(...), width: int = 1024, height: int = 1024, fit: bool = True):
    image = await _read_image(request, file)
    if not 1 <= width <= 6000 or not 1 <= height <= 6000 or width*height > MAX_PIXELS:
        raise HTTPException(status_code=422, detail="Width and height must be 1–6000 pixels and remain within the pixel limit.")
    if fit:
        image.thumbnail((width, height), Image.Resampling.LANCZOS)
    else:
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    fmt = image.format if image.format in FORMATS else "PNG"
    data = _encode(image, fmt)
    return Response(content=data, media_type=FORMATS[fmt], headers={"Content-Disposition": 'attachment; filename="norah-resized.'+fmt.lower()+'"'})

@router.post("/rotate")
async def rotate_image(request: Request, file: UploadFile = File(...), degrees: int = 90):
    image = await _read_image(request, file)
    if degrees not in {90, 180, 270, -90, -180, -270}:
        raise HTTPException(status_code=422, detail="degrees must be a 90-degree increment.")
    rotated = image.rotate(-degrees, expand=True)
    fmt = image.format if image.format in FORMATS else "PNG"
    data = _encode(rotated, fmt)
    return Response(content=data, media_type=FORMATS[fmt], headers={"Content-Disposition": 'attachment; filename="norah-rotated.'+fmt.lower()+'"'})

@router.post("/grayscale")
async def grayscale_image(request: Request, file: UploadFile = File(...)):
    image = await _read_image(request, file)
    result = ImageOps.grayscale(image)
    data = _encode(result, "PNG")
    return Response(content=data, media_type="image/png", headers={"Content-Disposition": 'attachment; filename="norah-grayscale.png"'})

@router.post("/compress")
async def compress_image(request: Request, file: UploadFile = File(...), quality: int = 80, output_format: str = "JPEG"):
    image = await _read_image(request, file)
    fmt = output_format.upper()
    if fmt not in {"JPEG", "WEBP", "PNG"}:
        raise HTTPException(status_code=422, detail="output_format must be JPEG, WEBP, or PNG.")
    if not 20 <= quality <= 95:
        raise HTTPException(status_code=422, detail="quality must be between 20 and 95.")
    data = _encode(image, fmt, quality)
    return Response(content=data, media_type=FORMATS[fmt], headers={"Content-Disposition": 'attachment; filename="norah-compressed.'+fmt.lower()+'"'} )
