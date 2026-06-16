from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, cast, Date
from datetime import datetime, timedelta, timezone
from models.database import get_db
from models.orm import (
    InspectionResult, InspectionSession, Lot, Product,
    DecisionEnum, DefectTypeEnum
)

router = APIRouter(prefix="/api/analytics", tags=["Analytique"])


@router.get("/stats/today", summary="KPIs du jour (dashboard)")
async def stats_today(db: AsyncSession = Depends(get_db)):
    """Retourne les KPIs agrégés pour la journée en cours."""
    today = datetime.now(timezone.utc).date()
    today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)

    # Sessions du jour
    sessions_q = select(InspectionSession).where(
        InspectionSession.started_at >= today_start
    )
    sessions_rows = await db.execute(sessions_q)
    sessions = sessions_rows.scalars().all()

    total = sum(s.total_inspected for s in sessions)
    conformes = sum(s.total_conforme for s in sessions)
    suspects = sum(s.total_suspect for s in sessions)
    non_conformes = sum(s.total_non_conforme for s in sessions)
    active_sessions = sum(1 for s in sessions if s.is_active)

    taux = round(conformes / total * 100, 2) if total > 0 else 0.0

    # Durée moyenne d'analyse
    dur_q = select(func.avg(InspectionResult.analysis_duration_ms)).where(
        InspectionResult.timestamp >= today_start
    )
    avg_duration = (await db.execute(dur_q)).scalar() or 0.0

    return {
        "date": today.isoformat(),
        "total_inspected": total,
        "total_conforme": conformes,
        "total_suspect": suspects,
        "total_non_conforme": non_conformes,
        "conformity_rate": taux,
        "active_sessions": active_sessions,
        "avg_analysis_duration_ms": round(avg_duration, 1),
        "inspection_rate_per_minute": _calc_rate(sessions)
    }


@router.get("/trends", summary="Tendance conformité sur N jours")
async def trends(
    days: int = Query(7, ge=1, le=365),
    db: AsyncSession = Depends(get_db)
):
    """Retourne le taux de conformité par jour pour les N derniers jours."""
    result = []
    today = datetime.now(timezone.utc).date()

    for i in range(days - 1, -1, -1):
        day = today - timedelta(days=i)
        day_start = datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)
        day_end = datetime.combine(day, datetime.max.time()).replace(tzinfo=timezone.utc)

        sessions_q = select(InspectionSession).where(
            and_(
                InspectionSession.started_at >= day_start,
                InspectionSession.started_at <= day_end
            )
        )
        sessions_rows = await db.execute(sessions_q)
        sessions = sessions_rows.scalars().all()

        total = sum(s.total_inspected for s in sessions)
        conformes = sum(s.total_conforme for s in sessions)
        non_conformes = sum(s.total_non_conforme for s in sessions)
        suspects = sum(s.total_suspect for s in sessions)
        taux = round(conformes / total * 100, 2) if total > 0 else None

        result.append({
            "date": day.isoformat(),
            "label": day.strftime("%a %d/%m"),
            "total": total,
            "conformes": conformes,
            "suspects": suspects,
            "non_conformes": non_conformes,
            "conformity_rate": taux
        })

    return {"days": days, "data": result}


@router.get("/defect-types", summary="Répartition des types d'anomalies")
async def defect_types(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db)
):
    """Retourne la répartition des types de défauts (donut chart)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Résultats non conformes avec type de défaut
    q = select(
        InspectionResult.defect_type,
        func.count().label("count")
    ).where(
        and_(
            InspectionResult.timestamp >= since,
            InspectionResult.decision == DecisionEnum.NON_CONFORME
        )
    ).group_by(InspectionResult.defect_type)

    rows = await db.execute(q)
    counts = {row.defect_type: row.count for row in rows}

    total = sum(counts.values()) or 1

    # Toutes les catégories avec leur count (0 si absent)
    result = []
    for dtype in DefectTypeEnum:
        count = counts.get(dtype, 0)
        result.append({
            "type": dtype.value,
            "count": count,
            "percentage": round(count / total * 100, 1)
        })

    result.sort(key=lambda x: x["count"], reverse=True)
    return {"period_days": days, "total_defects": total, "distribution": result}


@router.get("/pareto", summary="Analyse Pareto des anomalies")
async def pareto(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db)
):
    """Classement Pareto : les types d'anomalies qui représentent 80% des défauts."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    q = select(
        InspectionResult.defect_type,
        func.count().label("count")
    ).where(
        and_(
            InspectionResult.timestamp >= since,
            InspectionResult.decision == DecisionEnum.NON_CONFORME,
            InspectionResult.defect_type.isnot(None)
        )
    ).group_by(InspectionResult.defect_type).order_by(func.count().desc())

    rows = await db.execute(q)
    items = [{"type": r.defect_type.value if r.defect_type else "N/A", "count": r.count} for r in rows]

    total = sum(i["count"] for i in items) or 1
    cumulative = 0
    for item in items:
        item["percentage"] = round(item["count"] / total * 100, 1)
        cumulative += item["percentage"]
        item["cumulative_percentage"] = round(cumulative, 1)

    return {"period_days": days, "items": items}


@router.get("/by-product", summary="Conformité par produit")
async def by_product(db: AsyncSession = Depends(get_db)):
    """Retourne le taux de conformité moyen pour chaque produit."""
    products_q = select(Product)
    products_rows = await db.execute(products_q)
    products = products_rows.scalars().all()

    result = []
    for product in products:
        # Récupérer tous les lots du produit
        lots_q = select(Lot).where(Lot.product_id == product.id)
        lots_rows = await db.execute(lots_q)
        lots = lots_rows.scalars().all()

        total = sum(l.inspected_count for l in lots)
        # Récupérer sessions liées
        for lot in lots:
            sessions_q = select(InspectionSession).where(
                InspectionSession.lot_id == lot.id
            )
            sessions_rows = await db.execute(sessions_q)
            sessions = sessions_rows.scalars().all()
            total_i = sum(s.total_inspected for s in sessions)
            total_c = sum(s.total_conforme for s in sessions)
            if total_i > 0:
                result.append({
                    "product_id": product.id,
                    "product_name": product.name,
                    "product_type": product.product_type.value,
                    "total_inspected": total_i,
                    "conformity_rate": round(total_c / total_i * 100, 2)
                })
                break

    return {"products": result}


@router.get("/performance", summary="Métriques de performance système")
async def performance(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db)
):
    """Retourne les métriques de performance (vitesse, durée analyse)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    avg_dur_q = select(func.avg(InspectionResult.analysis_duration_ms)).where(
        InspectionResult.timestamp >= since
    )
    avg_dur = (await db.execute(avg_dur_q)).scalar() or 0.0

    count_q = select(func.count()).select_from(InspectionResult).where(
        InspectionResult.timestamp >= since
    )
    total_count = (await db.execute(count_q)).scalar() or 0

    return {
        "period_days": days,
        "total_inspections": total_count,
        "avg_analysis_duration_ms": round(avg_dur, 1),
        "estimated_rate_per_minute": round(60000 / avg_dur, 1) if avg_dur > 0 else 0
    }


def _calc_rate(sessions) -> float:
    """Calcule un débit estimé en unités/minute sur les sessions actives."""
    active = [s for s in sessions if s.is_active and s.total_inspected > 0]
    if not active:
        return 0.0
    # Moyenne du débit des sessions actives
    rates = []
    now = datetime.now(timezone.utc)
    for s in active:
        if s.started_at:
            elapsed_min = max((now - s.started_at).total_seconds() / 60, 0.01)
            rates.append(s.total_inspected / elapsed_min)
    return round(sum(rates) / len(rates), 1) if rates else 0.0
