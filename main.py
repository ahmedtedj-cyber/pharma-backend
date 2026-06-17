"""
PharmaVision AI — Backend FastAPI
Pipeline : YOLOv8 → PatchCore | WebSocket temps réel | REST API complète
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.database import init_db, get_db, AsyncSessionLocal
from routes import (
    cameras_router, products_router, lots_router,
    inspections_router, alerts_router, analytics_router,
    reports_router, settings_router
)
from services.inspection import traiter_frame_inspection, get_active_sessions, cleanup_stale_sessions
from websocket_manager import manager

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 Démarrage {settings.APP_NAME} v{settings.APP_VERSION}")
    await init_db()
    logger.info("✅ Base de données initialisée")

    # Nettoyer les sessions orphelines (EN_COURS au redémarrage)
    async with AsyncSessionLocal() as db:
        await cleanup_stale_sessions(db)

    from services.inference import _load_models
    logger.info("⏳ Chargement des modèles IA...")
    loaded = await asyncio.get_event_loop().run_in_executor(None, _load_models)
    if loaded:
        logger.info("✅ Modèles IA chargés avec succès")
    else:
        logger.warning("⚠️  Modèles IA non disponibles — mode MOCK actif")
    yield
    logger.info("🛑 Arrêt du serveur")


# ── Application ────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Backend PharmaVision AI — Détection d'anomalies pharmaceutiques "
        "par pipeline YOLOv8 → PatchCore sur caméra unique."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:4200",
    "http://127.0.0.1:4200",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "https://pharmagurad.netlify.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# ── Routers ────────────────────────────────────────────────────────────────

app.include_router(cameras_router)
app.include_router(products_router)
app.include_router(lots_router)
app.include_router(inspections_router)
app.include_router(alerts_router)
app.include_router(analytics_router)
app.include_router(reports_router)
app.include_router(settings_router)
app.include_router(stats_router)

# ── Routes de base ─────────────────────────────────────────────────────────

@app.get("/", tags=["Système"])
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "websockets": {
            "camera_stream": "ws://<host>/ws/camera/{session_id}",
            "alerts": "ws://<host>/ws/alerts"
        }
    }


@app.get("/health", tags=["Système"])
async def health():
    from services.inference import get_pipeline_status
    pipeline = get_pipeline_status()
    return {
        "status": "ok",
        "pipeline": pipeline,
        "websocket_stats": manager.get_stats(),
        "active_sessions": get_active_sessions()
    }


# ── WebSocket : flux caméra ────────────────────────────────────────────────

@app.websocket("/ws/camera/{session_id}")
async def websocket_camera(websocket: WebSocket, session_id: int):
    await manager.connect_camera(websocket, session_id)
    try:
        while True:
            async with AsyncSessionLocal() as db:
                result = await traiter_frame_inspection(db, session_id)

            if "error" in result:
                await websocket.send_json(result)
                await asyncio.sleep(1.0)
            else:
                await manager.broadcast_camera(session_id, result)
                await asyncio.sleep(0.2)

    except WebSocketDisconnect:
        manager.disconnect_camera(websocket, session_id)
        logger.info(f"Client WS caméra déconnecté — session {session_id}")
    except Exception as e:
        logger.error(f"Erreur WS caméra session {session_id}: {e}")
        manager.disconnect_camera(websocket, session_id)


# ── WebSocket : alertes ────────────────────────────────────────────────────

@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    await manager.connect_alerts(websocket)
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        manager.disconnect_alerts(websocket)
    except Exception as e:
        logger.error(f"Erreur WS alertes: {e}")
        manager.disconnect_alerts(websocket)


# ── Gestionnaire d'erreurs global ──────────────────────────────────────────

@app.exception_handler(404)
async def not_found(request, exc):
    return JSONResponse(status_code=404, content={"error": "Ressource introuvable", "path": str(request.url)})


@app.exception_handler(500)
async def server_error(request, exc):
    logger.error(f"Erreur 500 : {exc}")
    return JSONResponse(status_code=500, content={"error": "Erreur interne du serveur"})


# ── Point d'entrée ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="debug" if settings.DEBUG else "info"
    )