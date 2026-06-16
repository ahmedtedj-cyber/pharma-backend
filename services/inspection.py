"""
Service de gestion des sessions d'inspection.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select
from models.orm import (
    InspectionSession, InspectionResult, Lot, LotStatusEnum,
    DecisionEnum, Alert, AlertLevelEnum, AlertStatusEnum
)
from services.camera import CameraStream
from services.inference import inspecter_frame
from config import settings

logger = logging.getLogger(__name__)

# ── État en mémoire ───────────────────────────────────────────────────────
_active_streams:  dict[int, CameraStream] = {}
_live_results:    dict[int, dict]         = {}
_consecutive_nc:  dict[int, int]          = {}
_frame_counters:  dict[int, int]          = {}
_session_cache:   dict[int, dict]         = {}  # cache léger des compteurs

COMMIT_EVERY_N_FRAMES = 3


async def cleanup_stale_sessions(db: AsyncSession):
    try:
        result = await db.execute(
            select(InspectionSession).where(InspectionSession.is_active == True)
        )
        stale = result.scalars().all()
        for s in stale:
            s.is_active = False
            s.stopped_at = datetime.now(timezone.utc)
        if stale:
            await db.commit()
            logger.info(f"{len(stale)} session(s) orpheline(s) nettoyée(s)")
    except Exception as e:
        logger.error(f"Erreur cleanup: {e}")


async def demarrer_session(
    db: AsyncSession,
    lot_id: int,
    camera_index: int,
    conformity_threshold: float,
    notes: Optional[str] = None
) -> InspectionSession:

    lot = await db.get(Lot, lot_id)
    if not lot:
        raise ValueError(f"Lot {lot_id} introuvable")

    lot.status = LotStatusEnum.EN_COURS
    await db.flush()

    session = InspectionSession(
        lot_id=lot_id,
        camera_index=camera_index,
        conformity_threshold=conformity_threshold,
        notes=notes,
        is_active=True
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    stream = CameraStream(camera_index)
    if not stream.open():
        session.is_active = False
        await db.commit()
        raise RuntimeError(f"Impossible d'ouvrir la caméra {camera_index}")

    _active_streams[session.id]  = stream
    _live_results[session.id]    = {}
    _consecutive_nc[session.id]  = 0
    _frame_counters[session.id]  = 0
    _session_cache[session.id]   = {
        "total_inspected":   0,
        "total_conforme":    0,
        "total_suspect":     0,
        "total_non_conforme":0,
        "conformity_rate":   0.0,
    }

    logger.info(f"Session {session.id} démarrée — Lot {lot_id} — Caméra {camera_index}")
    return session


async def arreter_session(db: AsyncSession, session_id: int) -> InspectionSession:

    session = await db.get(InspectionSession, session_id)
    if not session:
        raise ValueError(f"Session {session_id} introuvable")

    if session_id in _active_streams:
        _active_streams[session_id].close()
        del _active_streams[session_id]

    # Flush cache → DB
    cache = _session_cache.get(session_id, {})
    session.total_inspected    = cache.get("total_inspected", session.total_inspected)
    session.total_conforme     = cache.get("total_conforme", session.total_conforme)
    session.total_suspect      = cache.get("total_suspect", session.total_suspect)
    session.total_non_conforme = cache.get("total_non_conforme", session.total_non_conforme)

    total = session.total_inspected
    if total > 0:
        session.conformity_rate = round(session.total_conforme / total * 100, 2)

    session.is_active  = False
    session.stopped_at = datetime.now(timezone.utc)

    try:
        await db.commit()
        await db.refresh(session)
    except Exception as e:
        logger.error(f"Erreur commit arrêt session {session_id}: {e}")
        await db.rollback()

    _live_results.pop(session_id, None)
    _consecutive_nc.pop(session_id, None)
    _frame_counters.pop(session_id, None)
    _session_cache.pop(session_id, None)

    logger.info(f"Session {session_id} arrêtée — {total} inspectés")
    return session


async def traiter_frame_inspection(db: AsyncSession, session_id: int) -> dict:
    """
    Capture + analyse un frame.
    Utilise un cache mémoire pour les compteurs → commit groupé toutes les N frames.
    Évite le problème MissingGreenlet en ne faisant pas d'await dans le pipeline sync.
    """

    # ── 1. Vérification session ──
    session = await db.get(InspectionSession, session_id)
    if not session or not session.is_active:
        return {"error": "Session inactive"}

    stream = _active_streams.get(session_id)
    if not stream:
        return {"error": "Caméra non disponible"}

    # ── 2. Lecture frame (sync) ──
    frame = stream.read_frame()
    if frame is None:
        return {"error": "Impossible de lire le frame"}

    # ── 3. Pipeline IA (sync — pas d'await ici) ──
    result = inspecter_frame(frame)

    if result.get("decision") == "NO_OBJECT":
        cache = _session_cache.get(session_id, {})
        live = {
            **result,
            "session_id":      session_id,
            "total_inspected": cache.get("total_inspected", 0),
            "conformity_rate": cache.get("conformity_rate", 0.0),
        }
        _live_results[session_id] = live
        return live

    # ── 4. Mise à jour cache mémoire (sans DB) ──
    decision_enum = DecisionEnum(result["decision"])
    cache = _session_cache.setdefault(session_id, {
        "total_inspected": 0, "total_conforme": 0,
        "total_suspect": 0, "total_non_conforme": 0, "conformity_rate": 0.0
    })

    cache["total_inspected"] += 1
    if decision_enum == DecisionEnum.CONFORME:
        cache["total_conforme"] += 1
        _consecutive_nc[session_id] = 0
    elif decision_enum == DecisionEnum.SUSPECT:
        cache["total_suspect"] += 1
    elif decision_enum == DecisionEnum.NON_CONFORME:
        cache["total_non_conforme"] += 1
        _consecutive_nc[session_id] = _consecutive_nc.get(session_id, 0) + 1

    total = cache["total_inspected"]
    cache["conformity_rate"] = round(cache["total_conforme"] / total * 100, 2) if total > 0 else 0.0

    # ── 5. Commit groupé toutes les N frames ──
    _frame_counters[session_id] = _frame_counters.get(session_id, 0) + 1
    if _frame_counters[session_id] >= COMMIT_EVERY_N_FRAMES:
        _frame_counters[session_id] = 0
        try:
            # Flush cache → session DB
            session.total_inspected    = cache["total_inspected"]
            session.total_conforme     = cache["total_conforme"]
            session.total_suspect      = cache["total_suspect"]
            session.total_non_conforme = cache["total_non_conforme"]
            session.conformity_rate    = cache["conformity_rate"]

            # Sauvegarde le résultat
            inspection_result = InspectionResult(
                session_id=session_id,
                decision=decision_enum,
                anomaly_score=result.get("anomaly_score"),
                yolo_confidence=result.get("yolo_confidence"),
                analysis_duration_ms=result.get("analysis_duration_ms"),
                bbox_x1=result["bbox"][0] if result.get("bbox") else None,
                bbox_y1=result["bbox"][1] if result.get("bbox") else None,
                bbox_x2=result["bbox"][2] if result.get("bbox") else None,
                bbox_y2=result["bbox"][3] if result.get("bbox") else None,
            )
            db.add(inspection_result)
            await db.commit()

        except Exception as e:
            logger.warning(f"Commit groupé ignoré (db busy): {e}")
            try:
                await db.rollback()
            except Exception:
                pass

    # ── 6. Alertes async (séparées du commit principal) ──
    try:
        await _verifier_alertes_safe(db, session_id, cache, result)
    except Exception as e:
        logger.warning(f"Alerte ignorée: {e}")

    # ── 7. Résultat live ──
    live = {
        **result,
        "session_id":        session_id,
        "total_inspected":   cache["total_inspected"],
        "total_conforme":    cache["total_conforme"],
        "total_suspect":     cache["total_suspect"],
        "total_non_conforme":cache["total_non_conforme"],
        "conformity_rate":   cache["conformity_rate"],
        "timestamp":         datetime.now(timezone.utc).isoformat(),
    }
    _live_results[session_id] = live
    return live


async def _verifier_alertes_safe(
    db: AsyncSession,
    session_id: int,
    cache: dict,
    result: dict
):
    """Vérifie et insère les alertes — dans une transaction séparée."""

    alerts_to_add = []

    # Règle 1 : Non-conformité critique isolée (score > 0.80)
    if result.get("decision") == "NON_CONFORME" and result.get("anomaly_score", 0) > 0.80:
        alerts_to_add.append(Alert(
            level=AlertLevelEnum.CRITIQUE,
            status=AlertStatusEnum.ACTIVE,
            message=f"Non-conformité critique (score: {result['anomaly_score']:.3f})",
            session_id=session_id,
            trigger_value=result.get("anomaly_score")
        ))

    # Règle 2 : Non-conformités consécutives
    nc_count = _consecutive_nc.get(session_id, 0)
    if nc_count >= settings.ALERT_CONSECUTIVE_INSPECTIONS:
        alerts_to_add.append(Alert(
            level=AlertLevelEnum.CRITIQUE,
            status=AlertStatusEnum.ACTIVE,
            message=f"{nc_count} non-conformités consécutives",
            session_id=session_id,
            trigger_value=float(nc_count)
        ))
        _consecutive_nc[session_id] = 0

    # Règle 3 : Taux NC global > seuil (après 10 inspections)
    total = cache.get("total_inspected", 0)
    if total >= 10:
        nc_rate = cache.get("total_non_conforme", 0) / total
        if nc_rate > settings.ALERT_NONCONFORMITY_RATE:
            alerts_to_add.append(Alert(
                level=AlertLevelEnum.AVERTISSEMENT,
                status=AlertStatusEnum.ACTIVE,
                message=f"Taux non-conformité élevé : {nc_rate*100:.1f}%",
                session_id=session_id,
                trigger_value=nc_rate
            ))

    if not alerts_to_add:
        return

    try:
        for alert in alerts_to_add:
            db.add(alert)
        await db.commit()
        logger.warning(f"⚠️ {len(alerts_to_add)} alerte(s) pour session {session_id}")
    except Exception as e:
        logger.warning(f"Commit alerte ignoré: {e}")
        try:
            await db.rollback()
        except Exception:
            pass


def get_live_result(session_id: int) -> dict:
    return _live_results.get(session_id, {})


def get_active_sessions() -> list[int]:
    return list(_active_streams.keys())