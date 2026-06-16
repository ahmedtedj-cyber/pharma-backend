"""
Seed de la base de données avec des données de démonstration.
Lance avec : python seed.py
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone
from models.database import init_db, AsyncSessionLocal
from models.orm import (
    Product, Lot, InspectionSession, InspectionResult, Alert,
    ProductTypeEnum, LotStatusEnum, DecisionEnum, AlertLevelEnum, AlertStatusEnum
)


PRODUCTS = [
    {"name": "Paracétamol 500mg", "code": "PARA-500", "product_type": ProductTypeEnum.COMPRIME, "description": "Comprimé analgésique standard"},
    {"name": "Amoxicilline 250mg", "code": "AMOX-250", "product_type": ProductTypeEnum.GELULE, "description": "Antibiotique en gélule"},
    {"name": "Solution Physiologique", "code": "SOL-PHYS", "product_type": ProductTypeEnum.FLACON, "description": "Sérum physiologique 250ml"},
    {"name": "Vitamine C 1000mg", "code": "VIT-C-1G", "product_type": ProductTypeEnum.COMPRIME, "description": "Complément vitaminique"},
    {"name": "Insuline Rapide", "code": "INS-RAP", "product_type": ProductTypeEnum.AMPOULE, "description": "Insuline injection rapide"},
]

DECISIONS = [
    DecisionEnum.CONFORME,
    DecisionEnum.CONFORME,
    DecisionEnum.CONFORME,
    DecisionEnum.CONFORME,
    DecisionEnum.CONFORME,
    DecisionEnum.SUSPECT,
    DecisionEnum.NON_CONFORME,
]


async def seed():
    await init_db()
    print("🌱 Initialisation de la DB...")

    async with AsyncSessionLocal() as db:
        # ── Produits ──
        products = []
        for p_data in PRODUCTS:
            product = Product(**p_data)
            db.add(product)
            products.append(product)
        await db.flush()
        print(f"  ✅ {len(products)} produits créés")

        # ── Lots ──
        lots = []
        lot_statuses = [
            LotStatusEnum.APPROUVE,
            LotStatusEnum.EN_COURS,
            LotStatusEnum.APPROUVE,
            LotStatusEnum.QUARANTAINE,
            LotStatusEnum.LIBERE,
        ]
        for i, product in enumerate(products):
            for j in range(2):
                manufacture_date = datetime.now(timezone.utc) - timedelta(days=random.randint(10, 60))
                lot = Lot(
                    lot_number=f"LOT-{manufacture_date.strftime('%Y%m%d')}-{product.code}-{j+1:02d}",
                    product_id=product.id,
                    quantity=random.randint(500, 5000),
                    inspected_count=random.randint(100, 500),
                    manufacture_date=manufacture_date,
                    expiration_date=manufacture_date + timedelta(days=730),
                    status=lot_statuses[i % len(lot_statuses)]
                )
                db.add(lot)
                lots.append(lot)
        await db.flush()
        print(f"  ✅ {len(lots)} lots créés")

        # ── Sessions d'inspection (7 derniers jours) ──
        sessions = []
        for day_offset in range(7):
            day = datetime.now(timezone.utc) - timedelta(days=6 - day_offset)
            num_sessions = random.randint(2, 4)

            for _ in range(num_sessions):
                lot = random.choice(lots)
                total = random.randint(50, 200)
                nc_rate = random.uniform(0.02, 0.15)
                suspect_rate = random.uniform(0.05, 0.10)
                non_conformes = int(total * nc_rate)
                suspects = int(total * suspect_rate)
                conformes = total - non_conformes - suspects

                started = day.replace(hour=random.randint(6, 16), minute=random.randint(0, 59))
                stopped = started + timedelta(minutes=random.randint(20, 120))

                session = InspectionSession(
                    lot_id=lot.id,
                    camera_index=0,
                    conformity_threshold=0.85,
                    started_at=started,
                    stopped_at=stopped,
                    total_inspected=total,
                    total_conforme=conformes,
                    total_suspect=suspects,
                    total_non_conforme=non_conformes,
                    conformity_rate=round(conformes / total * 100, 2),
                    is_active=False
                )
                db.add(session)
                sessions.append(session)

        await db.flush()
        print(f"  ✅ {len(sessions)} sessions créées")

        # ── Résultats individuels (pour la dernière session) ──
        if sessions:
            last_session = sessions[-1]
            result_count = 0
            for i in range(min(50, last_session.total_inspected)):
                decision = random.choice(DECISIONS)
                if decision == DecisionEnum.CONFORME:
                    score = round(random.uniform(0.05, 0.28), 4)
                elif decision == DecisionEnum.SUSPECT:
                    score = round(random.uniform(0.31, 0.58), 4)
                else:
                    score = round(random.uniform(0.61, 0.95), 4)

                result = InspectionResult(
                    session_id=last_session.id,
                    timestamp=last_session.started_at + timedelta(seconds=i * 3),
                    decision=decision,
                    anomaly_score=score,
                    yolo_confidence=round(random.uniform(0.75, 0.99), 4),
                    analysis_duration_ms=round(random.uniform(45, 250), 1),
                    bbox_x1=random.randint(50, 200),
                    bbox_y1=random.randint(50, 150),
                    bbox_x2=random.randint(400, 600),
                    bbox_y2=random.randint(350, 480),
                )
                db.add(result)
                result_count += 1
            print(f"  ✅ {result_count} résultats d'inspection créés")

        # ── Alertes de démonstration ──
        alerts_data = [
            {
                "level": AlertLevelEnum.CRITIQUE,
                "status": AlertStatusEnum.ACTIVE,
                "message": "Taux non-conformité critique : 18.5% sur lot LOT-20240315-PARA-500-01",
                "lot_id": lots[0].id if lots else None,
            },
            {
                "level": AlertLevelEnum.AVERTISSEMENT,
                "status": AlertStatusEnum.ACTIVE,
                "message": "5 non-conformités consécutives détectées — Vérifier le réglage machine",
                "lot_id": lots[1].id if len(lots) > 1 else None,
            },
            {
                "level": AlertLevelEnum.INFO,
                "status": AlertStatusEnum.ACQUITTEE,
                "message": "Nouveau modèle IA disponible — PatchCore v2.1",
                "acknowledged_comment": "Pris en compte, déploiement prévu semaine prochaine",
            },
            {
                "level": AlertLevelEnum.CRITIQUE,
                "status": AlertStatusEnum.ARCHIVEE,
                "message": "Caméra déconnectée pendant 5 minutes — Session interrompue",
            },
        ]
        for a_data in alerts_data:
            db.add(Alert(**a_data))
        print(f"  ✅ {len(alerts_data)} alertes créées")

        await db.commit()
        print("\n✅ Seed terminé avec succès !")
        print("   Lancez le serveur avec : python main.py")
        print("   Documentation API      : http://localhost:8000/docs")


if __name__ == "__main__":
    asyncio.run(seed())
