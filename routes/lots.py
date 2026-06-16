from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from models.database import get_db
from models.orm import Lot, Product, LotStatusEnum

router = APIRouter(prefix="/api/lots", tags=["Lots"])


class LotCreate(BaseModel):
    lot_number: str
    product_id: int
    quantity: int
    manufacture_date: Optional[datetime] = None
    expiration_date: Optional[datetime] = None


class LotUpdate(BaseModel):
    status: Optional[LotStatusEnum] = None
    quantity: Optional[int] = None
    expiration_date: Optional[datetime] = None


@router.get("/", summary="Lister tous les lots")
async def list_lots(
    product_id: Optional[int] = Query(None),
    status: Optional[LotStatusEnum] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    query = select(Lot).order_by(Lot.created_at.desc())
    if product_id:
        query = query.where(Lot.product_id == product_id)
    if status:
        query = query.where(Lot.status == status)

    rows = await db.execute(query)
    lots = rows.scalars().all()

    result = []
    for lot in lots:
        product = await db.get(Product, lot.product_id)
        result.append({
            "id": lot.id,
            "lot_number": lot.lot_number,
            "product_id": lot.product_id,
            "product_name": product.name if product else "N/A",
            "product_type": product.product_type.value if product else "N/A",
            "status": lot.status.value,
            "quantity": lot.quantity,
            "inspected_count": lot.inspected_count,
            "manufacture_date": lot.manufacture_date.isoformat() if lot.manufacture_date else None,
            "expiration_date": lot.expiration_date.isoformat() if lot.expiration_date else None,
            "created_at": lot.created_at.isoformat() if lot.created_at else None,
        })
    return {"lots": result, "count": len(result)}


@router.get("/{lot_id}", summary="Détail d'un lot")
async def get_lot(lot_id: int, db: AsyncSession = Depends(get_db)):
    lot = await db.get(Lot, lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail="Lot introuvable")
    product = await db.get(Product, lot.product_id)
    return {
        "id": lot.id,
        "lot_number": lot.lot_number,
        "product": {"id": product.id, "name": product.name} if product else None,
        "status": lot.status.value,
        "quantity": lot.quantity,
        "inspected_count": lot.inspected_count,
        "manufacture_date": lot.manufacture_date.isoformat() if lot.manufacture_date else None,
        "expiration_date": lot.expiration_date.isoformat() if lot.expiration_date else None,
    }


@router.post("/", status_code=201, summary="Créer un lot")
async def create_lot(data: LotCreate, db: AsyncSession = Depends(get_db)):
    # Vérifier produit existe
    product = await db.get(Product, data.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produit introuvable")

    # Vérifier numéro de lot unique
    existing = await db.execute(select(Lot).where(Lot.lot_number == data.lot_number))
    if existing.scalar():
        raise HTTPException(status_code=409, detail=f"Lot '{data.lot_number}' déjà existant")

    lot = Lot(**data.model_dump())
    db.add(lot)
    await db.commit()
    await db.refresh(lot)
    return {"id": lot.id, "lot_number": lot.lot_number, "status": lot.status.value}


@router.patch("/{lot_id}/quarantine", summary="Mettre un lot en quarantaine")
async def quarantine_lot(lot_id: int, db: AsyncSession = Depends(get_db)):
    lot = await db.get(Lot, lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail="Lot introuvable")
    lot.status = LotStatusEnum.QUARANTAINE
    await db.commit()
    return {"message": f"Lot {lot.lot_number} mis en quarantaine", "status": lot.status.value}


@router.patch("/{lot_id}/status", summary="Changer le statut d'un lot")
async def update_lot_status(lot_id: int, data: LotUpdate, db: AsyncSession = Depends(get_db)):
    lot = await db.get(Lot, lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail="Lot introuvable")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(lot, field, value)
    await db.commit()
    return {"message": "Lot mis à jour", "status": lot.status.value}


@router.delete("/{lot_id}", summary="Supprimer un lot")
async def delete_lot(lot_id: int, db: AsyncSession = Depends(get_db)):
    lot = await db.get(Lot, lot_id)
    if not lot:
        raise HTTPException(status_code=404, detail="Lot introuvable")
    await db.delete(lot)
    await db.commit()
    return {"message": "Lot supprimé"}
