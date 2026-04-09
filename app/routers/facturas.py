import os
import shutil
import tempfile
import uuid
from datetime import date

from typing import List

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import Factura, LineaFactura, TipoDocumento
from pdf_parser import parse_pdf

router = APIRouter(prefix="/facturas")
templates = Jinja2Templates(directory="templates")

PDFS_DIR = os.getenv("PDFS_DIR", "./pdfs")


@router.get("", response_class=HTMLResponse)
async def facturas_list(request: Request, mes: str = None, tipo: str = None, db: Session = Depends(get_db)):
    query = db.query(Factura)
    if mes:
        try:
            year, month = int(mes[:4]), int(mes[5:7])
            query = query.filter(
                Factura.mes_referencia >= date(year, month, 1),
                Factura.mes_referencia < date(year + (month // 12), (month % 12) + 1, 1),
            )
        except Exception:
            pass
    if tipo and tipo in ("YI", "YM", "RN"):
        query = query.filter(Factura.tipo == TipoDocumento[tipo])
    facturas = query.order_by(Factura.fecha_emision.desc()).all()
    return templates.TemplateResponse(
        "facturas.html", {"request": request, "facturas": facturas, "page": "facturas", "mes_filtro": mes, "tipo_filtro": tipo}
    )


@router.get("/subir", response_class=HTMLResponse)
async def facturas_subir(request: Request):
    """Página dedicada de subida de PDFs."""
    return templates.TemplateResponse(
        "factura_subir.html", {"request": request, "page": "facturas"}
    )


@router.post("/upload", response_class=HTMLResponse)
async def facturas_upload(request: Request, pdfs: List[UploadFile] = File(...), db: Session = Depends(get_db)):
    """Recibe uno o varios PDFs, los parsea y devuelve página completa de preview."""
    resultados = []
    numeros_existentes = {f.numero_documento for f in db.query(Factura.numero_documento).all()}

    for pdf in pdfs:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        try:
            content = await pdf.read()
            tmp.write(content)
            tmp.close()
            parsed = parse_pdf(tmp.name)
            duplicado = parsed.numero_documento in numeros_existentes
            resultados.append({
                "ok": True,
                "parsed": parsed,
                "tmp_path": tmp.name,
                "filename": pdf.filename,
                "duplicado": duplicado,
            })
        except Exception as e:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass
            resultados.append({
                "ok": False,
                "error": str(e),
                "filename": pdf.filename,
                "tmp_path": None,
            })

    return templates.TemplateResponse(
        "factura_upload_preview.html",
        {"request": request, "resultados": resultados, "page": "facturas"},
    )


@router.post("/confirmar")
async def facturas_confirmar(request: Request, db: Session = Depends(get_db)):
    """Confirma e inserta en lote los PDFs parseados. Recibe los datos como form multi-value."""
    form = await request.form()

    # Recoger todos los índices
    indices = sorted({k.split("_")[1] for k in form.keys() if k.startswith("tmp_")})

    os.makedirs(PDFS_DIR, exist_ok=True)
    insertados = 0
    omitidos = 0

    for i in indices:
        tmp_path = form.get(f"tmp_{i}")
        numero_documento = form.get(f"numero_{i}")
        tipo = form.get(f"tipo_{i}")
        fecha_emision = form.get(f"fecha_emision_{i}")
        fecha_vencimiento = form.get(f"fecha_vencimiento_{i}") or None
        mes_referencia = form.get(f"mes_referencia_{i}")

        if not tmp_path or not numero_documento:
            continue

        # Saltar duplicados
        existente = db.query(Factura).filter(Factura.numero_documento == numero_documento).first()
        if existente:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            omitidos += 1
            continue

        # Mover PDF al directorio definitivo
        dest = os.path.join(PDFS_DIR, f"{numero_documento}.pdf")
        try:
            shutil.move(tmp_path, dest)
        except Exception:
            omitidos += 1
            continue

        # Re-parsear para obtener líneas
        parsed = parse_pdf(dest)

        # El input type="month" envía "YYYY-MM"; añadimos el día para fromisoformat
        if len(mes_referencia) == 7:
            mes_referencia = mes_referencia + "-01"
        mes_ref = date.fromisoformat(mes_referencia)
        factura = Factura(
            numero_documento=numero_documento,
            tipo=TipoDocumento[tipo],
            fecha_emision=date.fromisoformat(fecha_emision),
            fecha_vencimiento=date.fromisoformat(fecha_vencimiento) if fecha_vencimiento else None,
            mes_referencia=date(mes_ref.year, mes_ref.month, 1),
            total=parsed.total,
            pdf_path=dest,
        )
        db.add(factura)
        db.flush()

        for linea in parsed.lineas:
            db.add(LineaFactura(
                factura_id=factura.id,
                descripcion=linea.descripcion,
                importe_neto=linea.importe_neto,
                importe_bruto=linea.importe_bruto,
            ))

        insertados += 1

    db.commit()
    return RedirectResponse(url=f"/?insertados={insertados}&omitidos={omitidos}", status_code=302)


@router.get("/{factura_id}", response_class=HTMLResponse)
async def factura_detalle(request: Request, factura_id: str, db: Session = Depends(get_db)):
    factura = db.query(Factura).filter(Factura.id == factura_id).first()
    if not factura:
        return RedirectResponse(url="/facturas", status_code=302)
    return templates.TemplateResponse(
        "factura_detalle.html", {"request": request, "factura": factura, "page": "facturas"}
    )


@router.post("/{factura_id}/delete")
async def factura_delete(factura_id: str, db: Session = Depends(get_db)):
    factura = db.query(Factura).filter(Factura.id == factura_id).first()
    if factura:
        try:
            os.unlink(factura.pdf_path)
        except Exception:
            pass
        db.delete(factura)
        db.commit()
    return RedirectResponse(url="/facturas", status_code=302)
