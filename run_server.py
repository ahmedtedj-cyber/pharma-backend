"""
Point d'entrée PyInstaller pour PharmaVision AI Backend.
"""
import multiprocessing
import sys
import os

# ── Ajoute le dossier courant au PATH Python ──────────────────────────────
# Nécessaire pour que PyInstaller trouve main.py et les modules
if getattr(sys, 'frozen', False):
    # On tourne depuis le .exe PyInstaller
    base_dir = sys._MEIPASS
else:
    # On tourne normalement
    base_dir = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, base_dir)

# ── Lance uvicorn ─────────────────────────────────────────────────────────
import uvicorn

def run():
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    multiprocessing.freeze_support()
    run()