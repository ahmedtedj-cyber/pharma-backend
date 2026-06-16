from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import os
from models.database import get_db
from models.orm import Report
from services.reports import generer_rapport_pdf, generer_rapport_excel, exporter_inspections_csv
from config import settings

router = APIRouter(prefix="/api/reports", tags=["Rapports"])


class GenerateReportRequest(BaseModel):
    report_type: str = "session"   # session | lot | daily | weekly | monthly
    format: str = "pdf"            # pdf | xlsx | csv
    session_id: Optional[int] = None
    lot_id: Optional[int] = None
    period_label: Optional[str] = None


@router.post("/generate", status_code=201, summary="Générer un rapport")
async def generate_report(
    data: GenerateReportRequest,
    db: AsyncSession = Depends(get_db)
):
    """Lance la génération du rapport et retourne son ID."""
    # Enregistrer le rapport en DB avec statut pending
    report = Report(
        report_type=data.report_type,
        format=data.format,
        session_id=data.session_id,
        lot_id=data.lot_id,
        period_label=data.period_label,
        status="pending"
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    try:
        if data.format == "pdf":
            filepath = await generer_rapport_pdf(
                db,
                session_id=data.session_id,
                lot_id=data.lot_id,
                report_type=data.report_type
            )
        elif data.format == "xlsx":
            filepath = await generer_rapport_excel(
                db,
                session_id=data.session_id,
                lot_id=data.lot_id,
                report_type=data.report_type
            )
        elif data.format == "csv":
            filepath = await exporter_inspections_csv(
                db,
                session_id=data.session_id,
                lot_id=data.lot_id
            )
        else:
            raise ValueError(f"Format non supporté : {data.format}")

        # Mettre à jour le rapport
        file_size = os.path.getsize(filepath) / 1024
        report.file_path = filepath
        report.file_size_kb = round(file_size, 1)
        report.status = "ready"
        await db.commit()

        return {
            "report_id": report.id,
            "status": "ready",
            "file_path": filepath,
            "file_size_kb": report.file_size_kb,
            "download_url": f"/api/reports/{report.id}/download"
        }

    except Exception as e:
        report.status = "error"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Erreur génération : {str(e)}")


@router.get("/", summary="Lister les rapports générés")
async def list_reports(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import func
    query = select(Report).order_by(Report.generated_at.desc())
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    query = query.offset((page - 1) * limit).limit(limit)
    rows = await db.execute(query)
    reports = rows.scalars().all()

    return {
        "reports": [
            {
                "id": r.id,
                "report_type": r.report_type,
                "format": r.format,
                "status": r.status,
                "file_size_kb": r.file_size_kb,
                "period_label": r.period_label,
                "session_id": r.session_id,
                "lot_id": r.lot_id,
                "generated_at": r.generated_at.isoformat() if r.generated_at else None,
                "download_url": f"/api/reports/{r.id}/download" if r.status == "ready" else None
            }
            for r in reports
        ],
        "total": total,
        "page": page
    }


@router.get("/{report_id}/download", summary="Télécharger un rapport")
async def download_report(report_id: int, db: AsyncSession = Depends(get_db)):
    report = await db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Rapport introuvable")
    if report.status != "ready" or not report.file_path:
        raise HTTPException(status_code=404, detail="Fichier non disponible")
    if not os.path.exists(report.file_path):
        raise HTTPException(status_code=404, detail="Fichier introuvable sur le disque")

    media_types = {"pdf": "application/pdf", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "csv": "text/csv"}
    media_type = media_types.get(report.format, "application/octet-stream")
    filename = os.path.basename(report.file_path)

    return FileResponse(
        path=report.file_path,
        media_type=media_type,
        filename=filename
    )


@router.delete("/{report_id}", summary="Supprimer un rapport")
async def delete_report(report_id: int, db: AsyncSession = Depends(get_db)):
    report = await db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Rapport introuvable")
    # Supprimer le fichier
    if report.file_path and os.path.exists(report.file_path):
        os.remove(report.file_path)
    await db.delete(report)
    await db.commit()
    return {"message": "Rapport supprimé"}
