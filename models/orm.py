from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text,
    ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from models.database import Base
import enum


# ── Enums ──────────────────────────────────────────────────────────────────

class DecisionEnum(str, enum.Enum):
    CONFORME = "CONFORME"
    SUSPECT = "SUSPECT"
    NON_CONFORME = "NON_CONFORME"
    NO_OBJECT = "NO_OBJECT"

class ProductTypeEnum(str, enum.Enum):
    COMPRIME = "Comprimé"
    GELULE = "Gélule"
    FLACON = "Flacon"
    AMPOULE = "Ampoule"
    SACHET = "Sachet"
    BOITE = "Boîte"

class LotStatusEnum(str, enum.Enum):
    EN_COURS = "En cours"
    APPROUVE = "Approuvé"
    REJETE = "Rejeté"
    QUARANTAINE = "Quarantaine"
    LIBERE = "Libéré"

class AlertLevelEnum(str, enum.Enum):
    CRITIQUE = "CRITIQUE"
    AVERTISSEMENT = "AVERTISSEMENT"
    INFO = "INFO"

class AlertStatusEnum(str, enum.Enum):
    ACTIVE = "active"
    ACQUITTEE = "acquittee"
    ARCHIVEE = "archivee"

class DefectTypeEnum(str, enum.Enum):
    ETIQUETTE_MANQUANTE = "Étiquette manquante"
    COMPRIME_CASSE = "Comprimé cassé"
    CONTAMINATION = "Contamination surface"
    MAUVAISE_COULEUR = "Mauvaise couleur"
    BOUCHON_DEFECTUEUX = "Bouchon défectueux"
    AUTRE = "Autre"


# ── Tables ─────────────────────────────────────────────────────────────────

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    product_type = Column(SAEnum(ProductTypeEnum), nullable=False)
    description = Column(Text, nullable=True)
    reference_image_path = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    lots = relationship("Lot", back_populates="product")


class Lot(Base):
    __tablename__ = "lots"

    id = Column(Integer, primary_key=True, index=True)
    lot_number = Column(String(100), unique=True, nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    manufacture_date = Column(DateTime(timezone=True), nullable=True)
    expiration_date = Column(DateTime(timezone=True), nullable=True)
    quantity = Column(Integer, default=0)
    inspected_count = Column(Integer, default=0)
    status = Column(SAEnum(LotStatusEnum), default=LotStatusEnum.EN_COURS)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    product = relationship("Product", back_populates="lots")
    inspection_sessions = relationship("InspectionSession", back_populates="lot")


class InspectionSession(Base):
    __tablename__ = "inspection_sessions"

    id = Column(Integer, primary_key=True, index=True)
    lot_id = Column(Integer, ForeignKey("lots.id"), nullable=False)
    camera_index = Column(Integer, default=0)
    conformity_threshold = Column(Float, default=0.80)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    stopped_at = Column(DateTime(timezone=True), nullable=True)
    total_inspected = Column(Integer, default=0)
    total_conforme = Column(Integer, default=0)
    total_suspect = Column(Integer, default=0)
    total_non_conforme = Column(Integer, default=0)
    conformity_rate = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)

    lot = relationship("Lot", back_populates="inspection_sessions")
    results = relationship("InspectionResult", back_populates="session")


class InspectionResult(Base):
    __tablename__ = "inspection_results"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("inspection_sessions.id"), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    decision = Column(SAEnum(DecisionEnum), nullable=False)
    anomaly_score = Column(Float, nullable=True)
    yolo_confidence = Column(Float, nullable=True)
    defect_type = Column(SAEnum(DefectTypeEnum), nullable=True)
    bbox_x1 = Column(Integer, nullable=True)
    bbox_y1 = Column(Integer, nullable=True)
    bbox_x2 = Column(Integer, nullable=True)
    bbox_y2 = Column(Integer, nullable=True)
    annotated_image_path = Column(String(500), nullable=True)
    heatmap_image_path = Column(String(500), nullable=True)
    analysis_duration_ms = Column(Float, nullable=True)

    session = relationship("InspectionSession", back_populates="results")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    level = Column(SAEnum(AlertLevelEnum), nullable=False)
    status = Column(SAEnum(AlertStatusEnum), default=AlertStatusEnum.ACTIVE)
    message = Column(Text, nullable=False)
    product_name = Column(String(200), nullable=True)
    lot_number = Column(String(100), nullable=True)
    lot_id = Column(Integer, ForeignKey("lots.id"), nullable=True)
    session_id = Column(Integer, ForeignKey("inspection_sessions.id"), nullable=True)
    trigger_value = Column(Float, nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    lot = relationship("Lot", foreign_keys=[lot_id])


class AppSettings(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    report_type = Column(String(50), nullable=False)   # session, lot, daily, weekly, monthly
    format = Column(String(10), nullable=False)         # pdf, xlsx
    file_path = Column(String(500), nullable=True)
    file_size_kb = Column(Float, nullable=True)
    period_label = Column(String(200), nullable=True)
    session_id = Column(Integer, nullable=True)
    lot_id = Column(Integer, nullable=True)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String(20), default="pending")      # pending, ready, error
