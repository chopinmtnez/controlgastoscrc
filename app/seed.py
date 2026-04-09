"""Script para cargar los datos iniciales (cobros históricos y beca)."""
import os
import sys
from datetime import date
from decimal import Decimal

sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, create_tables
from models import BecaConfig, Cobro


COBROS_HISTORICOS = [
    {"fecha": date(2025, 10, 10), "importe": Decimal("38.00"),  "mes_referencia": date(2025, 10, 1), "descripcion": "Cobro oct-25"},
    {"fecha": date(2025, 12,  4), "importe": Decimal("497.40"), "mes_referencia": date(2025, 12, 1), "descripcion": "Cobro dic-25"},
    {"fecha": date(2026,  1,  9), "importe": Decimal("119.60"), "mes_referencia": date(2026,  1, 1), "descripcion": "Cobro ene-26"},
    {"fecha": date(2026,  2,  6), "importe": Decimal("335.65"), "mes_referencia": date(2026,  2, 1), "descripcion": "Cobro feb-26"},
    {"fecha": date(2026,  3,  6), "importe": Decimal("310.00"), "mes_referencia": date(2026,  3, 1), "descripcion": "Cobro mar-26"},
    {"fecha": date(2026,  4,  7), "importe": Decimal("272.00"), "mes_referencia": date(2026,  4, 1), "descripcion": "Cobro abr-26"},
]

BECA = {
    "descripcion": "Beca CM 25/26",
    "importe_mensual": Decimal("177.00"),
    "fecha_inicio": date(2025, 12, 1),
    "fecha_fin": date(2026, 6, 30),
    "activa": True,
}


def seed():
    create_tables()
    db = SessionLocal()
    try:
        if db.query(Cobro).count() == 0:
            for c in COBROS_HISTORICOS:
                db.add(Cobro(**c))
            print(f"✓ {len(COBROS_HISTORICOS)} cobros históricos insertados")
        else:
            print("· Cobros ya existentes, omitiendo")

        if db.query(BecaConfig).count() == 0:
            db.add(BecaConfig(**BECA))
            print("✓ Beca CM 25/26 insertada")
        else:
            print("· Beca ya existente, omitiendo")

        db.commit()
        print("✓ Seed completado")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
