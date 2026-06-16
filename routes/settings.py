from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from models.database import get_db
from models.orm import AppSettings
from config import settings as app_settings

router = APIRouter(prefix="/api/settings", tags=["Paramètres"])

# Paramètres avec leurs valeurs par défaut
DEFAULTS = {
    "camera_index": str(app_settings.DEFAULT_CAMERA_INDEX),
    "camera_resolution": "1280x720",
    "camera_fps": "15",
    "yolo_confidence": str(app_settings.YOLO_CONFIDENCE),
    "threshold_conforme": str(app_settings.ANOMALY_THRESHOLD_CONFORME),
    "threshold_suspect": str(app_settings.ANOMALY_THRESHOLD_SUSPECT),
    "alert_nc_rate": str(app_settings.ALERT_NONCONFORMITY_RATE),
    "alert_consecutive": str(app_settings.ALERT_CONSECUTIVE_INSPECTIONS),
    "alert_email": app_settings.ALERT_EMAIL or "",
    "alert_webhook_url": "",
    "company_name": app_settings.COMPANY_NAME,
    "report_language": app_settings.REPORT_LANGUAGE,
    "report_date_format": "DD/MM/YYYY",
    "data_retention_days": "90",
}


class SettingsUpdate(BaseModel):
    camera_index: Optional[int] = None
    camera_resolution: Optional[str] = None
    camera_fps: Optional[int] = None
    yolo_confidence: Optional[float] = None
    threshold_conforme: Optional[float] = None
    threshold_suspect: Optional[float] = None
    alert_nc_rate: Optional[float] = None
    alert_consecutive: Optional[int] = None
    alert_email: Optional[str] = None
    alert_webhook_url: Optional[str] = None
    company_name: Optional[str] = None
    report_language: Optional[str] = None
    report_date_format: Optional[str] = None
    data_retention_days: Optional[int] = None


async def _get_setting(db: AsyncSession, key: str) -> Optional[str]:
    row = await db.execute(select(AppSettings).where(AppSettings.key == key))
    setting = row.scalar()
    if setting:
        return setting.value
    return DEFAULTS.get(key)


async def _set_setting(db: AsyncSession, key: str, value: str):
    row = await db.execute(select(AppSettings).where(AppSettings.key == key))
    setting = row.scalar()
    if setting:
        setting.value = value
    else:
        db.add(AppSettings(key=key, value=value))


@router.get("/", summary="Lire tous les paramètres")
async def get_settings(db: AsyncSession = Depends(get_db)):
    result = {}
    for key in DEFAULTS.keys():
        result[key] = await _get_setting(db, key)
    return result


@router.put("/", summary="Mettre à jour les paramètres")
async def update_settings(data: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    updates = data.model_dump(exclude_none=True)
    for key, value in updates.items():
        await _set_setting(db, key, str(value))

    # Appliquer les seuils IA en temps réel
    from services import inference
    if "threshold_conforme" in updates:
        inference.settings.ANOMALY_THRESHOLD_CONFORME = float(updates["threshold_conforme"])
    if "threshold_suspect" in updates:
        inference.settings.ANOMALY_THRESHOLD_SUSPECT = float(updates["threshold_suspect"])
    if "yolo_confidence" in updates:
        inference.settings.YOLO_CONFIDENCE = float(updates["yolo_confidence"])

    await db.commit()
    return {"message": f"{len(updates)} paramètre(s) mis à jour", "updated_keys": list(updates.keys())}


@router.get("/{key}", summary="Lire un paramètre spécifique")
async def get_setting(key: str, db: AsyncSession = Depends(get_db)):
    value = await _get_setting(db, key)
    if value is None:
        return {"key": key, "value": None, "found": False}
    return {"key": key, "value": value, "found": True}
