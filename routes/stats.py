"""
Router pour les statistiques système générales utilisées par le Dashboard.
Endpoint attendu par le frontend : GET /api/stats/system
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta, timezone

from models.database import get_db
from models.orm import InspectionResult, InspectionSession

router = APIRouter(prefix="/api/stats", tags=["Statistiques système"])


@router.get("/system", summary="Statistiques système globales (dashboard)")
async def system_stats(db: AsyncSession = Depends(get_db)):
    """
    Retourne les indicateurs système attendus par le frontend :
    - vitesse_inspection : nombre moyen d'inspections par minute (dernières 24h)
    - temps_moyen_analyse : durée moyenne d'analyse en ms (dernières 24h)
    - uptime_camera : pourcentage de sessions actives sans erreur (proxy de disponibilité)
    """
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    # Durée moyenne d'analyse (ms) sur les dernières 24h
    avg_dur_q = select(func.avg(InspectionResult.analysis_duration_ms)).where(
        InspectionResult.timestamp >= since
    )
    avg_duration = (await db.execute(avg_dur_q)).scalar() or 0.0

    # Nombre total d'inspections sur les dernières 24h
    count_q = select(func.count()).select_from(InspectionResult).where(
        InspectionResult.timestamp >= since
    )
    total_count = (await db.execute(count_q)).scalar() or 0

    # Vitesse d'inspection (par minute), calculée sur 24h = 1440 minutes
    vitesse_inspection = round(total_count / 1440, 1) if total_count > 0 else 0.0

    # Uptime caméra : proxy basé sur le ratio sessions actives / sessions totales récentes
    sessions_q = select(InspectionSession).where(
        InspectionSession.started_at >= since
    )
    sessions_rows = await db.execute(sessions_q)
    sessions = sessions_rows.scalars().all()

    if sessions:
        sessions_ok = sum(1 for s in sessions if s.total_inspected > 0)
        uptime_camera = round(sessions_ok / len(sessions) * 100, 1)
    else:
        uptime_camera = 100.0  # Pas de session = pas d'incident détecté

    return {
        "vitesse_inspection": vitesse_inspection,
        "temps_moyen_analyse": round(avg_duration, 1),
        "uptime_camera": uptime_camera,
    }
