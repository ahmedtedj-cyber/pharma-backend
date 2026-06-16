from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from models.database import get_db
from models.orm import (
    InspectionSession, InspectionResult, Lot, Product, DecisionEnum
)
from services.inspection import (
    demarrer_session, arreter_session,
    traiter_frame_inspection, get_live_result, get_active_sessions
)

router = APIRouter(prefix="/api/inspection", tags=["Inspections"])


# ── Schémas ───────────────────────────────────────────────────────────────

class StartInspectionRequest(BaseModel):
    lot_id: int
    camera_index: int = 0
    conformity_threshold: float = 0.80
    notes: Optional[str] = None


# ── Gestion de session ────────────────────────────────────────────────────

@router.post("/start", status_code=201, summary="Démarrer une inspection")
async def start_inspection(
    data: StartInspectionRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        session = await demarrer_session(
            db,
            lot_id=data.lot_id,
            camera_index=data.camera_index,
            conformity_threshold=data.conformity_threshold,
            notes=data.notes
        )
        return {
            "session_id": session.id,
            "lot_id": session.lot_id,
            "camera_index": session.camera_index,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "message": "Inspection démarrée"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/stop/{session_id}", summary="Arrêter une inspection")
async def stop_inspection(session_id: int, db: AsyncSession = Depends(get_db)):
    try:
        session = await arreter_session(db, session_id)
        return {
            "session_id": session.id,
            "total_inspected": session.total_inspected,
            "total_conforme": session.total_conforme,
            "total_suspect": session.total_suspect,
            "total_non_conforme": session.total_non_conforme,
            "conformity_rate": session.conformity_rate,
            "stopped_at": session.stopped_at.isoformat() if session.stopped_at else None,
            "message": "Inspection arrêtée"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/active", summary="Sessions actives")
async def get_active():
    return {"active_session_ids": get_active_sessions()}


# ── Frame et résultats live ───────────────────────────────────────────────

@router.post("/frame/{session_id}", summary="Analyser le frame courant")
async def process_frame(session_id: int, db: AsyncSession = Depends(get_db)):
    """
    Capture et analyse un frame depuis la caméra de la session.
    Retourne le résultat immédiatement (pour polling rapide).
    """
    result = await traiter_frame_inspection(db, session_id)
    return result


@router.get("/live-frame/{session_id}", summary="Dernier résultat disponible (polling)")
async def live_frame(session_id: int):
    """
    Retourne le dernier résultat stocké en mémoire.
    Le frontend appelle cette route toutes les 500ms.
    """
    result = get_live_result(session_id)
    if not result:
        return {"status": "waiting", "message": "Aucun résultat disponible"}
    return result


# ── Historique ────────────────────────────────────────────────────────────

@router.get("/sessions", summary="Lister les sessions d'inspection")
async def list_sessions(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    lot_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    query = select(InspectionSession).order_by(InspectionSession.started_at.desc())
    if lot_id:
        query = query.where(InspectionSession.lot_id == lot_id)
    if is_active is not None:
        query = query.where(InspectionSession.is_active == is_active)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    query = query.offset((page - 1) * limit).limit(limit)
    rows = await db.execute(query)
    sessions = rows.scalars().all()

    result = []
    for s in sessions:
        lot = await db.get(Lot, s.lot_id)
        product = await db.get(Product, lot.product_id) if lot else None
        result.append({
            "id": s.id,
            "lot_id": s.lot_id,
            "lot_number": lot.lot_number if lot else "N/A",
            "product_name": product.name if product else "N/A",
            "product_type": product.product_type.value if product else "N/A",
            "camera_index": s.camera_index,
            "is_active": s.is_active,
            "total_inspected": s.total_inspected,
            "total_conforme": s.total_conforme,
            "total_suspect": s.total_suspect,
            "total_non_conforme": s.total_non_conforme,
            "conformity_rate": s.conformity_rate,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "stopped_at": s.stopped_at.isoformat() if s.stopped_at else None,
        })

    return {
        "sessions": result,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }


@router.get("/sessions/{session_id}", summary="Détail d'une session")
async def get_session(session_id: int, db: AsyncSession = Depends(get_db)):
    session = await db.get(InspectionSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session introuvable")

    lot = await db.get(Lot, session.lot_id)
    product = await db.get(Product, lot.product_id) if lot else None

    results_q = select(InspectionResult).where(
        InspectionResult.session_id == session_id
    ).order_by(InspectionResult.timestamp.desc()).limit(50)
    results_rows = await db.execute(results_q)
    results = results_rows.scalars().all()

    return {
        "id": session.id,
        "lot": {"id": lot.id, "lot_number": lot.lot_number} if lot else None,
        "product": {"id": product.id, "name": product.name} if product else None,
        "camera_index": session.camera_index,
        "is_active": session.is_active,
        "total_inspected": session.total_inspected,
        "total_conforme": session.total_conforme,
        "total_suspect": session.total_suspect,
        "total_non_conforme": session.total_non_conforme,
        "conformity_rate": session.conformity_rate,
        "conformity_threshold": session.conformity_threshold,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "stopped_at": session.stopped_at.isoformat() if session.stopped_at else None,
        "notes": session.notes,
        "recent_results": [
            {
                "id": r.id,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "decision": r.decision.value if r.decision else None,
                "anomaly_score": r.anomaly_score,
                "yolo_confidence": r.yolo_confidence,
                "analysis_duration_ms": r.analysis_duration_ms,
            }
            for r in results
        ]
    }


@router.get("/results", summary="Lister les résultats individuels")
async def list_results(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    session_id: Optional[int] = Query(None),
    decision: Optional[DecisionEnum] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    query = select(InspectionResult).order_by(InspectionResult.timestamp.desc())
    conditions = []
    if session_id:
        conditions.append(InspectionResult.session_id == session_id)
    if decision:
        conditions.append(InspectionResult.decision == decision)
    if date_from:
        conditions.append(InspectionResult.timestamp >= date_from)
    if date_to:
        conditions.append(InspectionResult.timestamp <= date_to)
    if conditions:
        query = query.where(and_(*conditions))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    query = query.offset((page - 1) * limit).limit(limit)
    rows = await db.execute(query)
    results = rows.scalars().all()

    return {
        "results": [
            {
                "id": r.id,
                "session_id": r.session_id,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "decision": r.decision.value if r.decision else None,
                "anomaly_score": r.anomaly_score,
                "yolo_confidence": r.yolo_confidence,
                "analysis_duration_ms": r.analysis_duration_ms,
                "defect_type": r.defect_type.value if r.defect_type else None,
            }
            for r in results
        ],
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }


@router.delete("/sessions/{session_id}", summary="Supprimer une session")
async def delete_session(session_id: int, db: AsyncSession = Depends(get_db)):
    session = await db.get(InspectionSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session introuvable")
    from sqlalchemy import delete as sa_delete
    await db.execute(sa_delete(InspectionResult).where(InspectionResult.session_id == session_id))
    await db.delete(session)
    await db.commit()
    return {"message": "Session supprimée"}