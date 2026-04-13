import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, Column, Date, DateTime, Enum, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database import Base


class TipoDocumento(PyEnum):
    YI = "YI"
    YM = "YM"
    RN = "RN"


class Factura(Base):
    __tablename__ = "facturas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    numero_documento = Column(String, unique=True, nullable=False, index=True)
    tipo = Column(Enum(TipoDocumento), nullable=False)
    fecha_emision = Column(Date, nullable=False)
    fecha_vencimiento = Column(Date, nullable=True)
    mes_referencia = Column(Date, nullable=False)
    total = Column(Numeric(10, 2), nullable=False)
    pdf_path = Column(String, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow)

    lineas = relationship("LineaFactura", back_populates="factura", cascade="all, delete-orphan")


class LineaFactura(Base):
    __tablename__ = "lineas_factura"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    factura_id = Column(UUID(as_uuid=True), ForeignKey("facturas.id"), nullable=False)
    descripcion = Column(String, nullable=False)
    importe_neto = Column(Numeric(10, 2), nullable=False)
    importe_bruto = Column(Numeric(10, 2), nullable=False)

    factura = relationship("Factura", back_populates="lineas")


class Cobro(Base):
    __tablename__ = "cobros"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fecha = Column(Date, nullable=False)
    importe = Column(Numeric(10, 2), nullable=False)
    mes_referencia = Column(Date, nullable=False)
    descripcion = Column(String, nullable=True)
    creado_en = Column(DateTime, default=datetime.utcnow)


class BecaConfig(Base):
    __tablename__ = "beca_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    descripcion = Column(String, nullable=False)
    importe_mensual = Column(Numeric(10, 2), nullable=False)
    fecha_inicio = Column(Date, nullable=False)
    fecha_fin = Column(Date, nullable=False)
    activa = Column(Boolean, default=True)


class CursoConfig(Base):
    """Configuración del curso escolar activo."""
    __tablename__ = "curso_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String, nullable=False)        # e.g. "Curso 2025/26"
    fecha_inicio = Column(Date, nullable=False)
    fecha_fin = Column(Date, nullable=False)
    activo = Column(Boolean, default=False)
    creado_en = Column(DateTime, default=datetime.utcnow)


class ActivityLog(Base):
    """Registro de actividad de la aplicación."""
    __tablename__ = "activity_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    tipo = Column(String, nullable=False)      # scheduler / manual / config / sistema
    accion = Column(String, nullable=False)    # ing_sync, gmail_import, factura_upload…
    origen = Column(String, nullable=True)     # automático / usuario
    ok = Column(Boolean, default=True)
    resumen = Column(String, nullable=True)    # Resumen legible
    detalle = Column(String, nullable=True)    # JSON con detalles adicionales


class CuentaBanco(Base):
    """Conexión Open Banking con ING via Enable Banking (una sola por app)."""
    __tablename__ = "cuenta_banco"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aspsp_name = Column(String, nullable=True)       # ej: "ING"
    aspsp_country = Column(String, default="ES")
    session_id = Column(String, nullable=True)       # Enable Banking session_id
    account_id = Column(String, nullable=True)       # Enable Banking account_id
    iban_display = Column(String, nullable=True)     # Últimos 4 dígitos del IBAN
    oauth_state = Column(String, nullable=True)      # Almacenamiento temporal OAuth
    estado = Column(String, default="no_conectado")  # no_conectado/pendiente/conectado/expirado
    ultimo_sync = Column(DateTime, nullable=True)
    error = Column(String, nullable=True)
    creado_en = Column(DateTime, default=datetime.utcnow)
