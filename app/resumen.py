"""Lógica de cálculo del resumen mensual y previsión inteligente."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict, Counter

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
    Análisis de facturas históricas línea a línea para estimar meses futuros.

    Estrategia:
    - Base (AM+PM): precios unitarios únicos de las N facturas más recientes.
      Detecta automáticamente nuevas cuotas incorporadas (ej: PM session en la
      regularización de abril: 3 líneas de 88€ → precio unitario = 88€).
    - Natación: importe bruto más frecuente (38€) menos el descuento parcial
      más frecuente (19€ = 50% de descuento de profesora), excluyendo las
      reversiones completas (38-38=0) que son regularizaciones, no descuentos.
    - Comedor: precio unitario más frecuente entre líneas individuales (95€).
    - Sin restricción por mes-calendario (solo tenemos un curso completo).
    - Extras (seguro, material, matrícula): no se estiman, son imprevisibles.
    """
    if not meses_futuros:
        return []

    becas = db.query(BecaConfig).all()
    facturas = (
        db.query(Factura)
        .filter(Factura.total > 0)
        .all()
    )

    if not facturas:
        base_fb = Decimal("449")
        return [
            PrevisionMes(
                mes=m, base=base_fb, natacion=Decimal("0"),
                comedor=Decimal("0"), extras=Decimal("0"),
                total_estimado=base_fb,
                beca=_beca_para_mes(m, becas),
                neto_estimado=base_fb - _beca_para_mes(m, becas),
                notas=["Sin historial suficiente"],
            )
            for m in meses_futuros
        ]

    facturas_sorted = sorted(facturas, key=lambda f: f.mes_referencia)

    # ── Recopilar líneas de natación ─────────────────────────────────────────
    nat_positivos: list[Decimal] = []   # cargos brutos (ej: 38€)
    nat_negativos: list[Decimal] = []   # descuentos/reversiones (ej: -19€, -38€)

    # ── Recopilar líneas de comedor ──────────────────────────────────────────
    comedor_items: list[Decimal] = []

    for f in facturas_sorted:
        for lf in f.lineas:
            cat = _categorize(lf.descripcion)
            amt = Decimal(str(lf.importe_bruto))
            if cat == "natacion":
                if amt > 0:
                    nat_positivos.append(amt)
                elif amt < 0:
                    nat_negativos.append(amt)
            elif cat == "comedor" and amt > 0:
                comedor_items.append(amt)

    # ── Base: precios unitarios únicos de las N facturas más recientes ───────
    # Se buscan los importes únicos (set) por factura para detectar el precio
    # unitario sin contar el número de cuotas atrasadas en regularizaciones.
    # Ejemplo: abril tiene 3× PM session (88€) → precio unitario detectado = 88€.
    N_RECIENTES = 3
    facturas_recientes = facturas_sorted[-N_RECIENTES:]
    base_unitarios: set[Decimal] = set()
    for f in facturas_recientes:
        for lf in f.lineas:
            if _categorize(lf.descripcion) == "base":
                amt = Decimal(str(lf.importe_bruto)).quantize(Decimal("1"))
                if amt > 0:
                    base_unitarios.add(amt)

    if base_unitarios:
        base_estimada = sum(base_unitarios)
    else:
        # Fallback: moda histórica de importes brutos de líneas base
        all_base: list[Decimal] = []
        for f in facturas_sorted:
            for lf in f.lineas:
                if _categorize(lf.descripcion) == "base":
                    amt = Decimal(str(lf.importe_bruto))
                    if amt > 0:
                        all_base.append(amt.quantize(Decimal("1")))
        if all_base:
            freq_base = Counter(all_base)
            base_estimada = max(freq_base, key=lambda k: freq_base[k])
        else:
            base_estimada = Decimal("449")

    # ── Natación: bruto típico − descuento parcial típico ───────────────────
    # Se excluyen las reversiones completas (|dto| == bruto → regularización 0€).
    # Los descuentos parciales (|dto| < bruto) son el descuento real de profesora.
    if nat_positivos:
        freq_pos = Counter(x.quantize(Decimal("0.01")) for x in nat_positivos)
        gross_nat = max(freq_pos, key=lambda k: freq_pos[k])

        # Solo descuentos parciales (no reversiones completas)
        partial_discounts = [abs(x) for x in nat_negativos if abs(x) < gross_nat]
        if partial_discounts:
            freq_disc = Counter(x.quantize(Decimal("0.01")) for x in partial_discounts)
            discount_nat = max(freq_disc, key=lambda k: freq_disc[k])
            natacion_media = (gross_nat - discount_nat).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            natacion_media = gross_nat  # sin descuento detectado → usar bruto

        if natacion_media < 0:
            natacion_media = Decimal("0")
        estimar_natacion = True
    else:
        natacion_media = Decimal("0")
        estimar_natacion = False

    # ── Comedor: precio unitario más frecuente ───────────────────────────────
    if comedor_items:
        freq_com = Counter(x.quantize(Decimal("1")) for x in comedor_items)
        comedor_unit = max(freq_com, key=lambda k: freq_com[k])
        estimar_comedor = True
    else:
        comedor_unit = Decimal("0")
        estimar_comedor = False

    # ── Construir previsión para cada mes futuro ─────────────────────────────
    resultado = []
    for mes in meses_futuros:
        natacion_est = natacion_media if estimar_natacion else Decimal("0")
        comedor_est  = comedor_unit  if estimar_comedor  else Decimal("0")

        beca_mes  = _beca_para_mes(mes, becas)
        total_est = (base_estimada + natacion_est + comedor_est).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        neto_est  = (total_est - beca_mes).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        resultado.append(PrevisionMes(
            mes=mes,
            base=base_estimada,
            natacion=natacion_est,
            comedor=comedor_est,
            extras=Decimal("0"),
            total_estimado=total_est,
            beca=beca_mes,
            neto_estimado=neto_est,
            notas=[],
        ))

    return resultado
