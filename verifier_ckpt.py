# verifier_ckpt.py
import torch

# Pill
CKPT_PILL = "ai_models/pill/model.ckpt"

# Capsule  
CKPT_CAPSULE = "ai_models/capsule/model.ckpt"

for nom, chemin in [("PILL", CKPT_PILL), ("CAPSULE", CKPT_CAPSULE)]:
    print(f"\n{'='*50}")
    print(f"Vérification : {nom} → {chemin}")
    print('='*50)
    try:
        ckpt = torch.load(chemin, map_location="cpu")
        print(f"Type : {type(ckpt)}")
        if isinstance(ckpt, dict):
            print("Clés trouvées :")
            for k in ckpt.keys():
                print(f"  → {k}")
        else:
            print(f"Contenu direct : {type(ckpt)}")
    except FileNotFoundError:
        print(f"❌ Fichier introuvable : {chemin}")
    except Exception as e:
        print(f"❌ Erreur : {e}")