"""Lógica de cálculo del resumen mensual."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from models import BecaConfig, Cobro, Factura


@dataclass
class ResumenMes:
    mes: date  # primer día del mes
    total_facturas: Decimal
    total_cobros: Decimal
    beca: Decimal
    neto_esperado: Decimal
    diferencia: Decimal  # neto_esperado - total_cobros

    @property
    def estado(self) -> str:
        if self.total_facturas == 0 and self.total_cobros == 0:
            return "sin_datos"
        if self.diferencia > 0:
            return "pendiente"
        if self.diferencia < 0:
            return "cobrado_mas"
        return "ok"

    @property
    def mes_str(self) -> str:
        meses = {
            1: "ene", 2: "feb", 3: "mar", 4: "abr",
            5: "may", 6: "jun", 7: "jul", 8: "ago",
            9: "sep", 10: "oct", 11: "nov", 12: "dic",
        }
        return f"{meses[self.mes.month]}-{str(self.mes.year)[2:]}"


def _beca_para_mes(mes: date, becas: list[BecaConfig]) -> Decimal:
    for beca in becas:
        if beca.activa and beca.fecha_inicio <= mes <= beca.fecha_fin:
            return Decimal(str(beca.importe_mensual))
    return Decimal("0")


def calcular_resumen_curso(db: Session, desde: date, hasta: date) -> list[ResumenMes]:
    """Calcula el resumen mensual para todos los meses del curso."""
    becas = db.query(BecaConfig).all()

    # Generar lista de meses
    meses = []
    mes = date(desde.year, desde.month, 1)
    while mes <= date(hasta.year, hasta.month, 1):
        meses.append(mes)
        if mes.month == 12:
            mes = date(mes.year + 1, 1, 1)
        else:
            mes = date(mes.year, mes.month + 1, 1)

    # Facturas agrupadas por mes
    facturas = db.query(Factura).all()
    facturas_por_mes: dict[date, Decimal] = {}
    for f in facturas:
        key = date(f.mes_referencia.year, f.mes_referencia.month, 1)
        facturas_por_mes[key] = facturas_por_mes.get(key, Decimal("0")) + Decimal(str(f.total))

    # Cobros agrupados por mes
    cobros = db.query(Cobro).all()
    cobros_por_mes: dict[date, Decimal] = {}
    for c in cobros:
        key = date(c.mes_referencia.year, c.mes_referencia.month, 1)
        cobros_por_mes[key] = cobros_por_mes.get(key, Decimal("0")) + Decimal(str(c.importe))

    resultado = []
    for mes in meses:
        total_facturas = facturas_por_mes.get(mes, Decimal("0"))
        total_cobros = cobros_por_mes.get(mes, Decimal("0"))
        beca = _beca_para_mes(mes, becas)
        neto_esperado = total_facturas - beca
        diferencia = neto_esperado - total_cobros

        resultado.append(ResumenMes(
            mes=mes,
            total_facturas=total_facturas,
            total_cobros=total_cobros,
            beca=beca,
            neto_esperado=neto_esperado,
            diferencia=diferencia,
        ))

    return resultado


def calcular_kpis(resumenes: list[ResumenMes]) -> dict:
    hoy = date.today()
    mes_actual = date(hoy.year, hoy.month, 1)

    total_facturado = sum(r.total_facturas for r in resumenes)
    total_cobrado = sum(r.total_cobros for r in resumenes)
    beca_acumulada = sum(
        r.beca for r in resumenes if r.mes <= mes_actual
    )
    pendiente_acumulado = sum(
        r.diferencia for r in resumenes if r.diferencia > 0
    )

    return {
        "pendiente_acumulado": pendiente_acumulado,
        "total_facturado": total_facturado,
        "total_cobrado": total_cobrado,
        "beca_acumulada": beca_acumulada,
    }
