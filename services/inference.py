"""
Pipeline IA séquentiel : YOLOv8 → PatchCore
─────────────────────────────────────────────
Étape 1 : YOLOv8 détecte et localise le produit (ROI)
Étape 2 : PatchCore analyse la texture du ROI pour détecter les anomalies
Étape 3 : Décision finale CONFORME / SUSPECT / NON_CONFORME

Si les modèles réels (.pt) ne sont pas encore disponibles, le pipeline
fonctionne en mode MOCK avec des données simulées réalistes.
"""

import cv2
import numpy as np
import base64
import logging
import os
import time
import random
from typing import Optional
from config import settings

logger = logging.getLogger(__name__)

# ── Chargement lazy des modèles ───────────────────────────────────────────

_yolo_model = None
_patchcore_model = None
_models_available = False


def _load_models():
    global _yolo_model, _patchcore_model, _models_available

    yolo_ok = False
    patch_ok = False

    # Chargement YOLOv8
    if os.path.exists(settings.YOLO_MODEL_PATH):
        try:
            from ultralytics import YOLO
            _yolo_model = YOLO(settings.YOLO_MODEL_PATH)
            yolo_ok = True
            logger.info(f"✅ YOLOv8 chargé : {settings.YOLO_MODEL_PATH}")
        except Exception as e:
            logger.warning(f"⚠️  YOLOv8 non disponible : {e}")
    else:
        logger.warning(f"⚠️  Modèle YOLO introuvable : {settings.YOLO_MODEL_PATH} → mode MOCK")

    # Chargement PatchCore
    if os.path.exists(settings.PATCHCORE_MODEL_PATH):
        try:
            import torch
            _patchcore_model = torch.load(
                settings.PATCHCORE_MODEL_PATH,
                map_location="cuda" if _is_gpu_available() else "cpu"
            )
            _patchcore_model.eval()
            patch_ok = True
            logger.info(f"✅ PatchCore chargé : {settings.PATCHCORE_MODEL_PATH}")
        except Exception as e:
            logger.warning(f"⚠️  PatchCore non disponible : {e}")
    else:
        logger.warning(f"⚠️  Modèle PatchCore introuvable : {settings.PATCHCORE_MODEL_PATH} → mode MOCK")

    _models_available = yolo_ok and patch_ok
    return _models_available


def _is_gpu_available() -> bool:
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def get_pipeline_status() -> dict:
    return {
        "yolo_loaded": _yolo_model is not None,
        "patchcore_loaded": _patchcore_model is not None,
        "models_available": _models_available,
        "gpu_available": _is_gpu_available(),
        "yolo_path": settings.YOLO_MODEL_PATH,
        "patchcore_path": settings.PATCHCORE_MODEL_PATH,
        "mode": "real" if _models_available else "mock"
    }


# ── Pipeline principal ────────────────────────────────────────────────────

def inspecter_frame(frame: np.ndarray) -> dict:
    """
    Point d'entrée principal du pipeline.
    Reçoit un frame numpy BGR, retourne un dict de résultats.
    """
    start_time = time.time()

    if _models_available:
        result = _pipeline_reel(frame)
    else:
        result = _pipeline_mock(frame)

    result["analysis_duration_ms"] = round((time.time() - start_time) * 1000, 1)
    return result


def _pipeline_reel(frame: np.ndarray) -> dict:
    """Pipeline avec les vrais modèles YOLOv8 + PatchCore."""

    # ── Étape 1 : YOLOv8 détecte l'objet ──
    results = _yolo_model.predict(
        frame,
        conf=settings.YOLO_CONFIDENCE,
        verbose=False
    )

    if len(results[0].boxes) == 0:
        return {
            "status": "NO_OBJECT",
            "decision": "NO_OBJECT",
            "anomaly_score": 0.0,
            "yolo_confidence": 0.0,
            "bbox": None,
            "annotated_image_b64": _frame_to_b64(frame),
            "heatmap_b64": None
        }

    # ── Étape 2 : Découpe du ROI ──
    box = results[0].boxes[0]
    bbox = box.xyxy[0].cpu().numpy().astype(int)
    yolo_conf = float(box.conf[0].cpu().numpy())

    x1, y1, x2, y2 = bbox
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return {"status": "NO_OBJECT", "decision": "NO_OBJECT", "anomaly_score": 0.0}

    roi_resized = cv2.resize(roi, (224, 224))

    # ── Étape 3 : PatchCore analyse la texture ──
    tensor = _preprocess_for_patchcore(roi_resized)
    import torch
    with torch.no_grad():
        output = _patchcore_model(tensor)

    # Debug + extraction flexible du score
    import logging as _log
    _log.getLogger(__name__).info(f"PATCHCORE OUTPUT TYPE: {type(output)}, keys: {list(output.keys()) if isinstance(output, dict) else 'N/A'}")

    # Clés réelles du modèle : pred_score et anomaly_map
    anomaly_score = float(output["pred_score"].item())
    anomaly_score = max(0.0, min(1.0, anomaly_score))

    heatmap_np = None
    if "anomaly_map" in output:
        heatmap_np = output["anomaly_map"].squeeze().cpu().numpy()

    # ── Étape 4 : Décision ──
    decision = _decider(anomaly_score)

    # ── Étape 5 : Annotation visuelle ──
    annotated = _annoter_frame(frame, bbox, decision, anomaly_score)
    heatmap_colored = _coloriser_heatmap(heatmap_np, roi) if heatmap_np is not None else _generer_heatmap_mock(roi, anomaly_score)

    return {
        "status": "OK",
        "decision": decision,
        "anomaly_score": round(anomaly_score, 4),
        "yolo_confidence": round(yolo_conf, 4),
        "bbox": [int(x1), int(y1), int(x2), int(y2)],
        "annotated_image_b64": _frame_to_b64(annotated),
        "heatmap_b64": _frame_to_b64(heatmap_colored)
    }


def _pipeline_mock(frame: np.ndarray) -> dict:
    """
    Pipeline de simulation (mode MOCK) — utilisé quand les modèles ne sont
    pas encore disponibles. Simule des résultats réalistes pour tester
    l'app complète sans avoir les modèles entraînés.
    """
    # Simule une détection YOLO sur la zone centrale du frame
    h, w = frame.shape[:2]
    margin_x, margin_y = int(w * 0.15), int(h * 0.15)
    x1, y1 = margin_x, margin_y
    x2, y2 = w - margin_x, h - margin_y
    bbox = [x1, y1, x2, y2]

    yolo_conf = round(random.uniform(0.70, 0.98), 4)

    # Distribution réaliste : 80% conforme, 12% suspect, 8% non-conforme
    rand = random.random()
    if rand < 0.80:
        anomaly_score = round(random.uniform(0.05, 0.28), 4)
    elif rand < 0.92:
        anomaly_score = round(random.uniform(0.31, 0.58), 4)
    else:
        anomaly_score = round(random.uniform(0.61, 0.95), 4)

    decision = _decider(anomaly_score)

    # Annotation visuelle mock
    annotated = _annoter_frame(frame, bbox, decision, anomaly_score)

    # Heatmap simulée
    roi = frame[y1:y2, x1:x2]
    heatmap_mock = _generer_heatmap_mock(roi, anomaly_score)

    return {
        "status": "OK",
        "decision": decision,
        "anomaly_score": anomaly_score,
        "yolo_confidence": yolo_conf,
        "bbox": bbox,
        "annotated_image_b64": _frame_to_b64(annotated),
        "heatmap_b64": _frame_to_b64(heatmap_mock),
        "mock": True
    }


# ── Helpers ───────────────────────────────────────────────────────────────

def _decider(anomaly_score: float) -> str:
    if anomaly_score < settings.ANOMALY_THRESHOLD_CONFORME:
        return "CONFORME"
    elif anomaly_score < settings.ANOMALY_THRESHOLD_SUSPECT:
        return "SUSPECT"
    else:
        return "NON_CONFORME"


def _preprocess_for_patchcore(img: np.ndarray):
    """Normalisation ImageNet standard pour PatchCore."""
    import torch
    mean = np.array([0.485, 0.456, 0.406])
    std = np.array([0.229, 0.224, 0.225])
    img_float = img.astype(np.float32) / 255.0
    img_normalized = (img_float - mean) / std
    tensor = torch.tensor(img_normalized).permute(2, 0, 1).unsqueeze(0).float()
    return tensor


def _annoter_frame(frame: np.ndarray, bbox: list, decision: str, score: float) -> np.ndarray:
    """Dessine la bounding box et le label de décision sur le frame."""
    annotated = frame.copy()
    x1, y1, x2, y2 = bbox

    # Couleur selon décision
    color_map = {
        "CONFORME": (34, 197, 94),      # vert
        "SUSPECT": (245, 158, 11),      # orange
        "NON_CONFORME": (239, 68, 68),  # rouge
        "NO_OBJECT": (148, 163, 184)    # gris
    }
    color = color_map.get(decision, (255, 255, 255))

    # Rectangle
    cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)

    # Label
    label = f"{decision}  {score:.3f}"
    (text_w, text_h), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    cv2.rectangle(annotated, (x1, y1 - text_h - baseline - 4), (x1 + text_w + 4, y1), color, -1)
    cv2.putText(annotated, label, (x1 + 2, y1 - baseline - 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

    return annotated


def _coloriser_heatmap(heatmap: np.ndarray, roi: np.ndarray) -> np.ndarray:
    """Applique un colormap JET sur la heatmap et la superpose au ROI."""
    heatmap_norm = cv2.normalize(heatmap, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    heatmap_color = cv2.applyColorMap(heatmap_norm, cv2.COLORMAP_JET)
    roi_resized = cv2.resize(roi, (heatmap_color.shape[1], heatmap_color.shape[0]))
    overlay = cv2.addWeighted(roi_resized, 0.5, heatmap_color, 0.5, 0)
    return overlay


def _generer_heatmap_mock(roi: np.ndarray, anomaly_score: float) -> np.ndarray:
    """Génère une heatmap simulée pour le mode mock."""
    if roi.size == 0:
        roi = np.zeros((100, 100, 3), dtype=np.uint8)
    h, w = roi.shape[:2]
    heatmap = np.zeros((h, w), dtype=np.float32)

    # Plus le score est élevé, plus la zone chaude est grande
    num_zones = int(anomaly_score * 5) + 1
    for _ in range(num_zones):
        cx = random.randint(w // 4, 3 * w // 4)
        cy = random.randint(h // 4, 3 * h // 4)
        radius = int(min(w, h) * anomaly_score * 0.4)
        cv2.circle(heatmap, (cx, cy), max(radius, 10), anomaly_score, -1)

    heatmap = cv2.GaussianBlur(heatmap, (21, 21), 0)
    return _coloriser_heatmap(heatmap, roi)


def _frame_to_b64(frame: np.ndarray) -> str:
    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buffer).decode("utf-8")


# Chargement au démarrage
_load_models()