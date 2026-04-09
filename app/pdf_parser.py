import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

import pdfplumber
from dateutil import parser as dateutil_parser


@dataclass
class LineaPDF:
    descripcion: str
    importe_neto: Decimal
    importe_bruto: Decimal


@dataclass
class FacturaPDF:
    numero_documento: str
    tipo: str  # YI, YM, RN
    fecha_emision: date
    fecha_vencimiento: Optional[date]
    total: Decimal
    lineas: list[LineaPDF] = field(default_factory=list)


def _parse_amount(text: str) -> Decimal:
    cleaned = text.strip().replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0")


def _parse_date(text: str) -> Optional[date]:
    if not text:
        return None
    try:
        return dateutil_parser.parse(text.strip(), dayfirst=True).date()
    except Exception:
        return None


def parse_pdf(pdf_path: str) -> FacturaPDF:
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    # --- Número de documento y tipo ---
    doc_match = re.search(
        r"(?:N[uú]mero de Documento|N[°º]?\s*de Recibo|N[°º]?\s*Recibo)\s+([\d]+)\s*/\s*(YI|YM|RN)",
        full_text,
        re.IGNORECASE,
    )
    if not doc_match:
        raise ValueError(f"No se pudo extraer el número de documento del PDF: {pdf_path}")

    numero_documento = doc_match.group(1)
    tipo = doc_match.group(2).upper()

    # --- Fechas ---
    emision_match = re.search(
        r"(?:Fecha de [Ee]misi[oó]n|Fecha [Ee]misi[oó]n)\s+(\d{1,2}[\s/\-]\w+[\s/\-]\d{4})",
        full_text,
    )
    fecha_emision = _parse_date(emision_match.group(1)) if emision_match else None
    if not fecha_emision:
        raise ValueError(f"No se pudo extraer la fecha de emisión del PDF: {pdf_path}")

    vencimiento_match = re.search(
        r"(?:Fecha de [Vv]encimiento|Vencimiento)\s+(\d{1,2}[\s/\-]\w+[\s/\-]\d{4})",
        full_text,
    )
    fecha_vencimiento = _parse_date(vencimiento_match.group(1)) if vencimiento_match else None

    # --- Total ---
    # Buscar "Total  549.00" o "Total\n549.00" al final del documento
    total_match = re.search(r"Total\s+([-]?[\d]+[.,][\d]{2})\s*(?:EUR)?", full_text)
    total = _parse_amount(total_match.group(1)) if total_match else Decimal("0")

    # --- Líneas de concepto ---
    # El texto del PDF incluye líneas como:
    # "Early Years PM session 88.00 0.00 88.00"
    # "Natación-Lucía 38.00 38.00"
    # "Dto. Natación-Lucía -38.00 -38.00"
    # Están al final del texto extraído del PDF
    lineas = _extract_lineas(full_text)

    return FacturaPDF(
        numero_documento=numero_documento,
        tipo=tipo,
        fecha_emision=fecha_emision,
        fecha_vencimiento=fecha_vencimiento,
        total=total,
        lineas=lineas,
    )


def _extract_lineas(text: str) -> list[LineaPDF]:
    """
    Extrae las líneas de concepto del texto del PDF.

    Hay dos formatos posibles:

    Formato A (nuevo, con columna IVA%):
      "Material Escolar-Lucía  29.75  21.00%  6.25  36.00"
      "Seguro Previsión Escolar-Lucía  69.35  0.00%  69.35"
    El porcentaje con decimales (21.00%, 0.00%) distingue estas líneas de las
    líneas de resumen de impuestos (ESR...) que usan 21% sin decimales.

    Formato B (antiguo, sin columna IVA%):
      "Natación-Lucía  38.00  38.00"
      "Early Years PM session  88.00  0.00  88.00"
    """
    # Patrón A: requiere IVA con dos decimales + % (ej: 21.00%, 0.00%)
    # El grupo del impuesto es opcional (no existe cuando IVA=0%)
    pattern_a = re.compile(
        r"^(.+?)"
        r"\s+([-]?\d+[.,]\d{2})"       # importe_neto
        r"\s+\d+[.,]\d{2}%"            # IVA% con decimales (no capturar)
        r"(?:\s+[-]?\d+[.,]\d{2})?"    # impuesto (opcional, no capturar)
        r"\s+([-]?\d+[.,]\d{2})\s*$",  # importe_bruto
        re.MULTILINE,
    )

    # Patrón B: sin IVA%, descripción debe empezar con letra (no con código alfanumérico tipo ESR025)
    pattern_b = re.compile(
        r"^([A-Za-záéíóúÁÉÍÓÚñÑüÜ][A-Za-záéíóúÁÉÍÓÚñÑüÜ0-9\s\-\.]+?)"
        r"\s+([-]?\d+[.,]\d{2})"       # importe_neto
        r"(?:\s+[-]?\d+[.,]\d{2})?"    # número intermedio (opcional)
        r"\s+([-]?\d+[.,]\d{2})\s*$",  # importe_bruto
        re.MULTILINE,
    )

    skip_words = {
        "total", "comentarios", "iva", "descripción", "descripcion",
        "importe", "fecha", "pagina", "página", "subtotal", "n.i.f",
        "divisa", "ref", "moneda",
    }

    # Regex para códigos de impuesto como ESR025, ESR004, etc.
    _tax_code = re.compile(r"^[A-Z]{2,}\d+")

    def _skip(desc: str) -> bool:
        if len(desc) < 3:
            return True
        first = desc.lower().split()[0].rstrip(".")
        if first in skip_words:
            return True
        # Descartar líneas de resumen de impuestos (ESR025, ESR004…)
        if _tax_code.match(desc):
            return True
        return False

    lineas = []

    # Intentar primero el patrón A (con IVA%)
    matches_a = [
        (m.group(1).strip(), m.group(2), m.group(3))
        for m in pattern_a.finditer(text)
        if not _skip(m.group(1).strip())
    ]

    if matches_a:
        for desc, neto, bruto in matches_a:
            lineas.append(LineaPDF(
                descripcion=desc,
                importe_neto=_parse_amount(neto),
                importe_bruto=_parse_amount(bruto),
            ))
    else:
        # Fallback al patrón B (formato antiguo sin IVA%)
        for m in pattern_b.finditer(text):
            desc = m.group(1).strip()
            if _skip(desc):
                continue
            lineas.append(LineaPDF(
                descripcion=desc,
                importe_neto=_parse_amount(m.group(2)),
                importe_bruto=_parse_amount(m.group(3)),
            ))

    return lineas
