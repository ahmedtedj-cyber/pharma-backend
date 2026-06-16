from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
from models.database import get_db
from models.orm import Product, Lot, ProductTypeEnum, LotStatusEnum

router = APIRouter(prefix="/api/products", tags=["Produits"])


# ── Schémas ───────────────────────────────────────────────────────────────

class ProductCreate(BaseModel):
    name: str
    code: str
    product_type: ProductTypeEnum
    description: Optional[str] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    product_type: Optional[ProductTypeEnum] = None
    description: Optional[str] = None


# ── Routes ────────────────────────────────────────────────────────────────

@router.get("/", summary="Lister tous les produits")
async def list_products(
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    query = select(Product).order_by(Product.name)
    if search:
        query = query.where(Product.name.ilike(f"%{search}%"))
    rows = await db.execute(query)
    products = rows.scalars().all()

    result = []
    for p in products:
        # Compter les lots
        lot_count_q = select(func.count()).select_from(Lot).where(Lot.product_id == p.id)
        lot_count = (await db.execute(lot_count_q)).scalar()
        result.append({
            "id": p.id,
            "name": p.name,
            "code": p.code,
            "product_type": p.product_type.value,
            "description": p.description,
            "lot_count": lot_count,
            "created_at": p.created_at.isoformat() if p.created_at else None
        })
    return {"products": result, "count": len(result)}


@router.get("/{product_id}", summary="Détail d'un produit")
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produit introuvable")

    lots_q = select(Lot).where(Lot.product_id == product_id).order_by(Lot.created_at.desc())
    lots_rows = await db.execute(lots_q)
    lots = lots_rows.scalars().all()

    return {
        "id": product.id,
        "name": product.name,
        "code": product.code,
        "product_type": product.product_type.value,
        "description": product.description,
        "lots": [
            {
                "id": l.id,
                "lot_number": l.lot_number,
                "status": l.status.value,
                "quantity": l.quantity,
                "inspected_count": l.inspected_count,
                "manufacture_date": l.manufacture_date.isoformat() if l.manufacture_date else None,
                "expiration_date": l.expiration_date.isoformat() if l.expiration_date else None,
            }
            for l in lots
        ]
    }


@router.post("/", status_code=201, summary="Créer un produit")
async def create_product(data: ProductCreate, db: AsyncSession = Depends(get_db)):
    # Vérifier code unique
    existing = await db.execute(select(Product).where(Product.code == data.code))
    if existing.scalar():
        raise HTTPException(status_code=409, detail=f"Code produit '{data.code}' déjà utilisé")

    product = Product(**data.model_dump())
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return {"id": product.id, "name": product.name, "code": product.code}


@router.put("/{product_id}", summary="Modifier un produit")
async def update_product(product_id: int, data: ProductUpdate, db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produit introuvable")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(product, field, value)
    await db.commit()
    return {"message": "Produit mis à jour", "id": product_id}


@router.delete("/{product_id}", summary="Supprimer un produit")
async def delete_product(product_id: int, db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produit introuvable")
    await db.delete(product)
    await db.commit()
    return {"message": "Produit supprimé"}
