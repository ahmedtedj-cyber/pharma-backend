from fastapi import APIRouter
from services.camera import scanner_cameras_disponibles, capture_snapshot
from services.inference import get_pipeline_status

router = APIRouter(prefix="/api/cameras", tags=["Caméras"])


@router.get("/", summary="Lister les caméras disponibles")
async def list_cameras():
    """Scanne et retourne toutes les caméras connectées au système."""
    cameras = scanner_cameras_disponibles()
    return {"cameras": cameras, "count": len(cameras)}


@router.get("/{index}/snapshot", summary="Capture une frame de preview")
async def get_snapshot(index: int):
    """Retourne une image base64 pour prévisualiser la caméra avant inspection."""
    image_b64 = capture_snapshot(index)
    if image_b64 is None:
        return {"error": f"Caméra {index} inaccessible", "image_b64": None}
    return {"camera_index": index, "image_b64": image_b64}


@router.get("/pipeline/status", summary="Statut du pipeline IA")
async def pipeline_status():
    """Retourne si YOLOv8 et PatchCore sont chargés ou en mode mock."""
    return get_pipeline_status()
