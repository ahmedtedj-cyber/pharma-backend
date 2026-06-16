"""
Script de capture d'images pour entraîner YOLO sur des blisters.
Lance : python capturer_dataset.py
- Appuie ESPACE pour capturer une image
- Appuie Q pour quitter
Les images sont sauvegardées dans dataset/images/
"""

import cv2
import os
import time

SAVE_DIR = "dataset/images"
os.makedirs(SAVE_DIR, exist_ok=True)

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

count = len([f for f in os.listdir(SAVE_DIR) if f.endswith('.jpg')])
print(f"Images existantes : {count}")
print("ESPACE = capturer | Q = quitter")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Afficher le cadre de guidage
    h, w = frame.shape[:2]
    cx, cy = w // 2, h // 2
    bw, bh = int(w * 0.7), int(h * 0.7)
    x1, y1 = cx - bw // 2, cy - bh // 2
    x2, y2 = cx + bw // 2, cy + bh // 2

    display = frame.copy()
    cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.putText(display, f"Images: {count} | ESPACE=capturer Q=quitter",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.putText(display, "Centrer le blister dans le cadre vert",
                (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

    cv2.imshow("Capture Dataset Blisters", display)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break
    elif key == ord(' '):
        filename = os.path.join(SAVE_DIR, f"blister_{count:04d}.jpg")
        cv2.imwrite(filename, frame)
        count += 1
        print(f"Sauvegardé : {filename}")
        # Flash visuel
        flash = frame.copy()
        cv2.rectangle(flash, (0, 0), (w, h), (255, 255, 255), -1)
        cv2.imshow("Capture Dataset Blisters", flash)
        cv2.waitKey(100)

cap.release()
cv2.destroyAllWindows()
print(f"\nTerminé — {count} images sauvegardées dans '{SAVE_DIR}'")
print("\nProchaine étape : annoter les images sur https://roboflow.com")
print("Puis entraîner : yolo train model=yolov8n.pt data=dataset.yaml epochs=50")
