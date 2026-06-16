"""
Service de gestion caméra.
Détecte les caméras disponibles (webcam intégrée + USB),
fournit le flux de frames pour le pipeline IA.
"""

import cv2
import base64
import logging
from typing import Optional
from config import settings

logger = logging.getLogger(__name__)


def scanner_cameras_disponibles() -> list[dict]:
    """
    Scanne les index 0 → CAMERA_SCAN_MAX pour trouver toutes les caméras.
    Retourne une liste de dict : {index, label, width, height, fps}
    """
    cameras = []
    for i in range(settings.CAMERA_SCAN_MAX):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            label = "Webcam intégrée" if i == 0 else f"Caméra USB {i}"
            cameras.append({
                "index": i,
                "label": label,
                "width": width,
                "height": height,
                "fps": round(fps, 1)
            })
            cap.release()
    logger.info(f"Caméras détectées : {len(cameras)}")
    return cameras


def capture_snapshot(camera_index: int) -> Optional[str]:
    """
    Capture une seule frame et la retourne en base64 JPEG.
    Utilisé pour le preview avant de démarrer une inspection.
    """
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        logger.warning(f"Impossible d'ouvrir la caméra {camera_index}")
        return None
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return None
    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buffer).decode("utf-8")


def frame_to_base64(frame) -> str:
    """Convertit un frame numpy en string base64 JPEG."""
    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buffer).decode("utf-8")


class CameraStream:
    """
    Gère le cycle de vie d'une caméra pour une session d'inspection.
    Usage :
        stream = CameraStream(camera_index=0)
        stream.open()
        frame = stream.read_frame()
        stream.close()
    """

    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self._cap: Optional[cv2.VideoCapture] = None
        self.is_open = False
        self.frames_read = 0
        self.errors = 0

    def open(self) -> bool:
        # Essayer DirectShow d'abord (plus stable sur Windows), puis défaut
        for backend in [cv2.CAP_DSHOW, cv2.CAP_ANY]:
            cap = cv2.VideoCapture(self.camera_index, backend)
            if cap.isOpened():
                # Test lecture immédiate pour valider
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 15)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # buffer minimal = frames fraiches
                ret, _ = cap.read()
                if ret:
                    self._cap = cap
                    self.is_open = True
                    logger.info(f"Caméra {self.camera_index} ouverte (backend={'DSHOW' if backend == cv2.CAP_DSHOW else 'ANY'})")
                    return True
                cap.release()
        logger.error(f"Caméra {self.camera_index} inaccessible")
        return False

    def read_frame(self):
        """Retourne le frame numpy ou None en cas d'erreur.
        Rouvre la caméra si elle est bloquée (bug MSMF Windows).
        """
        if not self.is_open:
            return None

        # Essai 1 : lecture normale
        if self._cap and self._cap.isOpened():
            ret, frame = self._cap.read()
            if ret and frame is not None:
                self.frames_read += 1
                self.errors = 0
                return frame

        # Echec — rouvrir la caméra (contourne le bug MSMF)
        self.errors += 1
        logger.warning(f"Frame échoué ({self.errors}) — réouverture caméra")
        if self._cap:
            self._cap.release()
        for backend in [cv2.CAP_DSHOW, cv2.CAP_ANY]:
            cap = cv2.VideoCapture(self.camera_index, backend)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    self._cap = cap
                    self.frames_read += 1
                    self.errors = 0
                    logger.info(f"Caméra réouverte avec succès")
                    return frame
                cap.release()

        logger.error(f"Impossible de lire un frame après réouverture")
        return None

    def close(self):
        if self._cap:
            self._cap.release()
        self.is_open = False
        logger.info(f"Caméra {self.camera_index} fermée après {self.frames_read} frames")

    def get_stats(self) -> dict:
        return {
            "camera_index": self.camera_index,
            "is_open": self.is_open,
            "frames_read": self.frames_read,
            "errors": self.errors
        }