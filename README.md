# PharmaVision AI — Backend

Backend FastAPI pour la détection d'anomalies pharmaceutiques par pipeline **YOLOv8 → PatchCore** sur caméra unique.

---

## 🏗️ Architecture

```
pharmavision-backend/
├── main.py                  # Point d'entrée FastAPI + WebSocket
├── config.py                # Paramètres (.env)
├── websocket_manager.py     # Gestionnaire connexions WS
├── seed.py                  # Données de démonstration
│
├── models/
│   ├── database.py          # Connexion SQLAlchemy async (SQLite)
│   └── orm.py               # Tous les modèles DB (Product, Lot, Session...)
│
├── services/
│   ├── camera.py            # Détection caméras + CameraStream
│   ├── inference.py         # Pipeline IA : YOLOv8 → PatchCore (+ mode mock)
│   ├── inspection.py        # Orchestration session + alertes automatiques
│   └── reports.py           # Génération PDF / Excel / CSV
│
├── routes/
│   ├── cameras.py           # GET /api/cameras
│   ├── products.py          # CRUD /api/products
│   ├── lots.py              # CRUD /api/lots
│   ├── inspections.py       # /api/inspection/start|stop|frame|sessions
│   ├── alerts.py            # /api/alerts
│   ├── analytics.py         # /api/analytics/stats|trends|pareto
│   ├── reports.py           # /api/reports/generate|download
│   └── settings.py          # /api/settings
│
├── ai_models/               # Dossier pour vos modèles .pt
│   ├── yolo_pharma.pt       # (à placer après entraînement)
│   └── patchcore_model.pt   # (à placer après entraînement)
│
├── exports/                 # Rapports PDF/Excel générés
├── requirements.txt
└── .env
```

---

## 🚀 Installation

### 1. Prérequis
- Python 3.11+
- (Optionnel) GPU NVIDIA avec CUDA pour accélérer l'IA

### 2. Environnement virtuel
```bash
python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows
```

### 3. Installation des dépendances
```bash
pip install -r requirements.txt
```

> **Note** : `ultralytics` et `anomalib` sont lourds (~2GB avec torch).  
> Si vous voulez juste tester l'API sans IA, commentez ces lignes dans requirements.txt.  
> Le backend fonctionne en **mode MOCK** automatiquement.

### 4. Configuration
Éditez `.env` si nécessaire (le fichier par défaut fonctionne sans modification).

### 5. Base de données + données de démo
```bash
python seed.py
```

### 6. Démarrage
```bash
python main.py
```

Accès :
- **API REST** : http://localhost:8000
- **Documentation Swagger** : http://localhost:8000/docs
- **ReDoc** : http://localhost:8000/redoc

---

## 📡 Endpoints principaux

### Caméras
| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/cameras/` | Lister les caméras disponibles |
| GET | `/api/cameras/{index}/snapshot` | Preview d'une caméra |
| GET | `/api/cameras/pipeline/status` | Statut des modèles IA |

### Inspection
| Méthode | URL | Description |
|---------|-----|-------------|
| POST | `/api/inspection/start` | Démarrer une session |
| POST | `/api/inspection/stop/{id}` | Arrêter une session |
| POST | `/api/inspection/frame/{id}` | Analyser le frame courant |
| GET | `/api/inspection/live-frame/{id}` | Dernier résultat (polling) |
| GET | `/api/inspection/sessions` | Historique des sessions |

### WebSocket
| URL | Description |
|-----|-------------|
| `ws://localhost:8000/ws/camera/{session_id}` | Flux frames annotées |
| `ws://localhost:8000/ws/alerts` | Alertes temps réel |

### Analytics
| Méthode | URL | Description |
|---------|-----|-------------|
| GET | `/api/analytics/stats/today` | KPIs du jour |
| GET | `/api/analytics/trends?days=7` | Tendance 7 jours |
| GET | `/api/analytics/defect-types` | Répartition anomalies |
| GET | `/api/analytics/pareto` | Analyse Pareto |

---

## 🤖 Mode MOCK vs Modèles réels

Le backend démarre automatiquement en **mode MOCK** si les modèles `.pt` sont absents.  
En mode MOCK, des résultats simulés réalistes sont générés (80% conformes, 12% suspects, 8% non-conformes).

Pour passer en mode réel :
1. Placez `yolo_pharma.pt` dans `ai_models/`
2. Placez `patchcore_model.pt` dans `ai_models/`
3. Redémarrez le serveur

---

## 🔌 Intégration avec Base44 (Frontend)

Le frontend Base44 se connecte via HTTP aux endpoints REST.

**Configuration Base44** : pointer toutes les requêtes vers `http://localhost:8000`

**Exemple de flux inspection depuis Base44** :
```
1. POST /api/inspection/start        → obtenir session_id
2. Polling GET /api/inspection/live-frame/{session_id}  (toutes les 500ms)
3. POST /api/inspection/stop/{session_id}
4. POST /api/reports/generate        → générer le rapport
```

---

## 🧪 Test rapide avec curl

```bash
# Lister les caméras
curl http://localhost:8000/api/cameras/

# KPIs du jour
curl http://localhost:8000/api/analytics/stats/today

# Tendance 7 jours
curl http://localhost:8000/api/analytics/trends?days=7

# Statut pipeline IA
curl http://localhost:8000/api/cameras/pipeline/status
```

---

## 📋 Protocole d'intégration des modèles IA

### Étape 1 — Entraîner YOLOv8
```bash
# Collecte 500 images de votre produit sur la chaîne de production
# Annotation avec labelImg ou Roboflow
# Entraînement :
python -c "
from ultralytics import YOLO
model = YOLO('yolov8n.pt')
model.train(data='dataset/data.yaml', epochs=100, imgsz=640)
# Le modèle final est dans : runs/detect/train/weights/best.pt
"
cp runs/detect/train/weights/best.pt ai_models/yolo_pharma.pt
```

### Étape 2 — Entraîner PatchCore
```bash
# Structure dataset :
# patchcore_dataset/train/good/  ← 300 images NORMALES uniquement
python -c "
from anomalib.data import Folder
from anomalib.models import Patchcore
from anomalib.engine import Engine
# ... (voir documentation anomalib)
"
cp exported_models/patchcore/model.pt ai_models/patchcore_model.pt
```

### Étape 3 — Redémarrer le serveur
```bash
python main.py
# Vérifier : curl http://localhost:8000/api/cameras/pipeline/status
# → "mode": "real"
```
