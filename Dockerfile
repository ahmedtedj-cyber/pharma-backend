FROM python:3.12-slim

WORKDIR /app

# Dépendances système nécessaires pour OpenCV (cv2) et autres libs natives
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Installer les dépendances Python d'abord (pour profiter du cache Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le reste du code
COPY . .

# Railway injecte la variable PORT automatiquement, on l'utilise dans la commande de démarrage
ENV PORT=8000
EXPOSE 8000

CMD ["python", "main.py"]
