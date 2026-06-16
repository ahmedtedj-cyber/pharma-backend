from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from models.database import get_db
from models.orm import Alert, AlertLevelEnum, AlertStatusEnum

router = APIRouter(prefix="/api/alerts", tags=["Alertes"])


class AcknowledgeRequest(BaseModel):
    comment: str


class CreateAlertRequest(BaseModel):
    level: AlertLevelEnum
    message: str
    product_name: Optional[str] = None
    lot_number: Optional[str] = None
    lot_id: Optional[int] = None
    session_id: Optional[int] = None


@router.get("/", summary="Lister les alertes")
async def list_alerts(
    status: Optional[AlertStatusEnum] = Query(None),
    level: Optional[AlertLevelEnum] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    query = select(Alert).order_by(Alert.created_at.desc())
    if status:
        query = query.where(Alert.status == status)
    if level:
        query = query.where(Alert.level == level)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    query = query.offset((page - 1) * limit).limit(limit)
    rows = await db.execute(query)
    alerts = rows.scalars().all()

    return {
        "alerts": [_format_alert(a) for a in alerts],
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }


@router.get("/recent", summary="5 dernières alertes (dashboard)")
async def recent_alerts(db: AsyncSession = Depends(get_db)):
    query = select(Alert).order_by(Alert.created_at.desc()).limit(5)
    rows = await db.execute(query)
    alerts = rows.scalars().all()
    return {"alerts": [_format_alert(a) for a in alerts]}


@router.get("/count", summary="Nombre d'alertes actives")
async def count_active(db: AsyncSession = Depends(get_db)):
    q = select(func.count()).select_from(Alert).where(Alert.status == AlertStatusEnum.ACTIVE)
    count = (await db.execute(q)).scalar()
    return {"active_count": count}


@router.get("/{alert_id}", summary="Détail d'une alerte")
async def get_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte introuvable")
    return _format_alert(alert)


@router.post("/", status_code=201, summary="Créer une alerte manuellement")
async def create_alert(data: CreateAlertRequest, db: AsyncSession = Depends(get_db)):
    alert = Alert(**data.model_dump())
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return _format_alert(alert)


@router.patch("/{alert_id}/acknowledge", summary="Acquitter une alerte")
async def acknowledge_alert(
    alert_id: int,
    data: AcknowledgeRequest,
    db: AsyncSession = Depends(get_db)
):
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte introuvable")
    if alert.status == AlertStatusEnum.ACQUITTEE:
        raise HTTPException(status_code=400, detail="Alerte déjà acquittée")

    alert.status = AlertStatusEnum.ACQUITTEE
    alert.acknowledged_at = datetime.now(timezone.utc)
    alert.acknowledged_comment = data.comment
    await db.commit()
    return {"message": "Alerte acquittée", "alert_id": alert_id}


@router.patch("/{alert_id}/archive", summary="Archiver une alerte")
async def archive_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte introuvable")
    alert.status = AlertStatusEnum.ARCHIVEE
    await db.commit()
    return {"message": "Alerte archivée"}


@router.delete("/{alert_id}", summary="Supprimer une alerte")
async def delete_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte introuvable")
    await db.delete(alert)
    await db.commit()
    return {"message": "Alerte supprimée"}


def _format_alert(a: Alert) -> dict:
    return {
        "id": a.id,
        "level": a.level.value,
        "status": a.status.value,
        "message": a.message,
        "product_name": a.product_name,
        "lot_number": a.lot_number,
        "lot_id": a.lot_id,
        "session_id": a.session_id,
        "trigger_value": a.trigger_value,
        "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
        "acknowledged_comment": a.acknowledged_comment,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
