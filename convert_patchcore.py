# convert_patchcore.py
import torch
from anomalib.models import Patchcore

CKPT_PATH = "ai_models/model.ckpt"
OUTPUT_PATH = "ai_models/patchcore_model.pt"

print("Chargement du checkpoint...")
try:
    model = Patchcore.load_from_checkpoint(CKPT_PATH)
    model.eval()
    torch.save(model, OUTPUT_PATH)
    print(f"✅ Converti avec succès → {OUTPUT_PATH}")
except Exception as e:
    print(f"❌ Erreur : {e}")
    print("\nEssai méthode alternative...")
    try:
        ckpt = torch.load(CKPT_PATH, map_location="cpu")
        torch.save(ckpt, OUTPUT_PATH)
        print(f"✅ Converti (méthode 2) → {OUTPUT_PATH}")
    except Exception as e2:
        print(f"❌ Échec total : {e2}")