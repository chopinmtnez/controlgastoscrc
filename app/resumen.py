"""Lógica de cálculo del resumen mensual y previsión inteligente."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict

from sqlalchemy.orm import Session

from models import BecaConfig, Cobro, Factura, LineaFactura

# Palabras clave para categorizar líneas de factura
_KW_BASE     = ("EARLY YEARS AM", "EARLY YEARS PM", "ESCOLARIDAD", "AM SESSION", "PM SESSION")
_KW_NATACION = ("NATACI", "NATACIÓN", "NATACION", "SWIMMING")
_KW_COMEDOR  = ("LUNCH", "COMEDOR", "COMIDA")


@dataclass
class ResumenMes:
    mes: date
    total_facturas: Decimal
    total_cobros: Decimal
    beca: Decimal
    neto_esperado: Decimal
    diferencia: Decimal

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
        meses = {1:"ene",2:"feb",3:"mar",4:"abr",5:"may",6:"jun",
                 7:"jul",8:"ago",9:"sep",10:"oct",11:"nov",12:"dic"}
        return f"{meses[self.mes.month]}-{str(self.mes.year)[2:]}"


@dataclass
class PrevisionMes:
    """Previsión inteligente para un mes futuro."""
    mes: date
    base: Decimal          # cuota AM/PM session estimada
    natacion: Decimal      # natación estimada (puede ser 0)
    comedor: Decimal       # comedor estimado (puede ser 0)
    extras: Decimal        # otros cargos estimados (material, seguro…)
    total_estimado: Decimal
    beca: Decimal
    neto_estimado: Decimal
    notas: list[str] = field(default_factory=list)  # advertencias o info

    @property
    def mes_str(self) -> str:
        meses = {1:"ene",2:"feb",3:"mar",4:"abr",5:"may",6:"jun",
                 7:"jul",8:"ago",9:"sep",10:"oct",11:"nov",12:"dic"}
        return f"{meses[self.mes.month]}-{str(self.mes.year)[2:]}"


def _beca_para_mes(mes: date, becas: list[BecaConfig]) -> Decimal:
    for beca in becas:
        if beca.activa and beca.fecha_inicio <= mes <= beca.fecha_fin:
            return Decimal(str(beca.importe_mensual))
    return Decimal("0")


def _categorize(descripcion: str) -> str:
    d = descripcion.upper()
    if any(k in d for k in _KW_BASE):
        return "base"
    if any(k in d for k in _KW_NATACION):
        return "natacion"
    if any(k in d for k in _KW_COMEDOR):
        return "comedor"
    return "extra"


def _meses_rango(desde: date, hasta: date) -> list[date]:
    meses = []
    mes = date(desde.year, desde.month, 1)
    while mes <= date(hasta.year, hasta.month, 1):
        meses.append(mes)
        mes = date(mes.year + (mes.month == 12), (mes.month % 12) + 1, 1)
    return meses


# ─────────────────────────────────────────────────────────────────────────────

def calcular_resumen_curso(db: Session, desde: date, hasta: date) -> list[ResumenMes]:
    becas = db.query(BecaConfig).all()
    meses = _meses_rango(desde, hasta)

    facturas_por_mes: dict[date, Decimal] = {}
    for f in db.query(Factura).all():
        key = date(f.mes_referencia.year, f.mes_referencia.month, 1)
        facturas_por_mes[key] = facturas_por_mes.get(key, Decimal("0")) + Decimal(str(f.total))

    cobros_por_mes: dict[date, Decimal] = {}
    for c in db.query(Cobro).all():
        key = date(c.mes_referencia.year, c.mes_referencia.month, 1)
        cobros_por_mes[key] = cobros_por_mes.get(key, Decimal("0")) + Decimal(str(c.importe))

    resultado = []
    for mes in meses:
        total_facturas = facturas_por_mes.get(mes, Decimal("0"))
        total_cobros   = cobros_por_mes.get(mes, Decimal("0"))
        beca           = _beca_para_mes(mes, becas)
        neto_esperado  = total_facturas - beca
        diferencia     = neto_esperado - total_cobros
        resultado.append(ResumenMes(
            mes=mes, total_facturas=total_facturas, total_cobros=total_cobros,
            beca=beca, neto_esperado=neto_esperado, diferencia=diferencia,
        ))
    return resultado


def calcular_kpis(resumenes: list[ResumenMes]) -> dict:
    hoy = date.today()
    mes_actual = date(hoy.year, hoy.month, 1)
    return {
        "pendiente_acumulado": sum(r.diferencia for r in resumenes),
        "total_facturado":     sum(r.total_facturas for r in resumenes),
        "total_cobrado":       sum(r.total_cobros for r in resumenes),
        "beca_acumulada":      sum(r.beca for r in resumenes if r.mes <= mes_actual),
    }


# ─────────────────────────────────────────────────────────────────────────────

def calcular_prevision_inteligente(db: Session, meses_futuros: list[date]) -> list[PrevisionMes]:
    """
    Analiza las facturas históricas línea a línea para estimar cada mes futuro:
    - Cuota base (AM session): valor más frecuente observado
    - Natación: media del coste neto real por mes (incluyendo descuentos)
    - Comedor: media del coste neto real por mes
    - Extras: se descarta (imprevisibles: seguro, material, matrícula...)
    - Beca: de BecaConfig activa para ese mes
    """
    if not meses_futuros:
        return []

    becas = db.query(BecaConfig).all()

    # Recopilar todos los datos históricos por mes
    por_mes: dict[date, dict] = defaultdict(lambda: {
        "base": Decimal("0"),
        "natacion": Decimal("0"),
        "comedor": Decimal("0"),
        "extra": Decimal("0"),
    })

    facturas = (
        db.query(Factura)
        .filter(Factura.total > 0)  # ignorar facturas de ajuste/cero
        .all()
    )

    for f in facturas:
        mes_key = date(f.mes_referencia.year, f.mes_referencia.month, 1)
        for lf in f.lineas:
            cat = _categorize(lf.descripcion)
            por_mes[mes_key][cat] += Decimal(str(lf.importe_bruto))

    if not por_mes:
        # Sin historial, devolver previsión básica
        beca_fallback = _beca_para_mes(meses_futuros[0], becas)
        base_fb = Decimal("449")
        return [
            PrevisionMes(
                mes=m, base=base_fb, natacion=Decimal("0"),
                comedor=Decimal("0"), extras=Decimal("0"),
                total_estimado=base_fb - _beca_para_mes(m, becas),
                beca=_beca_para_mes(m, becas),
                neto_estimado=base_fb - _beca_para_mes(m, becas),
                notas=["Sin historial suficiente"],
            )
            for m in meses_futuros
        ]

    meses_hist = list(por_mes.keys())

    # ── Cuota base: valor más común entre los meses históricos ──
    bases = [por_mes[m]["base"] for m in meses_hist if por_mes[m]["base"] > 0]
    if bases:
        # Redondear a decenas para agrupar valores similares
        freq: dict[Decimal, int] = defaultdict(int)
        for b in bases:
            freq[b.quantize(Decimal("1"), rounding=ROUND_HALF_UP)] += 1
        base_estimada = max(freq, key=lambda k: freq[k])
    else:
        base_estimada = Decimal("449")

    # ── Natación: media del neto mensual histórico ──
    natacion_vals = [por_mes[m]["natacion"] for m in meses_hist]
    natacion_media = (
        sum(natacion_vals) / len(natacion_vals) if natacion_vals else Decimal("0")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # ── Comedor: media del neto mensual histórico ──
    comedor_vals = [por_mes[m]["comedor"] for m in meses_hist]
    comedor_media = (
        sum(comedor_vals) / len(comedor_vals) if comedor_vals else Decimal("0")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # ── Detectar si algún mes históricamente tuvo natación / comedor ──
    meses_num_con_natacion = {m.month for m in meses_hist if por_mes[m]["natacion"] != 0}
    meses_num_con_comedor  = {m.month for m in meses_hist if por_mes[m]["comedor"] != 0}

    # ── Construir previsión para cada mes futuro ──
    resultado = []
    for mes in meses_futuros:
        notas = []

        # Natación: usar media histórica si ese mes-del-año tuvo natación
        tiene_natacion = mes.month in meses_num_con_natacion
        natacion_est = natacion_media if tiene_natacion else Decimal("0")

        # Comedor: usar media histórica si ese mes-del-año tuvo comedor
        tiene_comedor = mes.month in meses_num_con_comedor
        comedor_est = comedor_media if tiene_comedor else Decimal("0")

        # Si comedor es alto (>50€) probablemente fue carga extraordinaria
        # repartida en varios meses de golpe — avisar
        if tiene_comedor and comedor_media > Decimal("50"):
            notas.append("Comedor estimado (puede ya estar pagado de antemano)")

        beca_mes = _beca_para_mes(mes, becas)
        total_est = (base_estimada + natacion_est + comedor_est).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        neto_est = (total_est - beca_mes).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        resultado.append(PrevisionMes(
            mes=mes,
            base=base_estimada,
            natacion=natacion_est,
            comedor=comedor_est,
            extras=Decimal("0"),
            total_estimado=total_est,
            beca=beca_mes,
            neto_estimado=neto_est,
            notas=notas,
        ))

    return resultado
