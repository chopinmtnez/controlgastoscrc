"""
Tareas automáticas programadas (APScheduler).

Cada día a las 10:00 hora Madrid:
  1. tarea_ing()    — sincroniza cobros desde ING via Enable Banking
  2. tarea_gmail()  — importa facturas PDF desde Gmail

Notificaciones por email si hay cambios o desajustes.
"""
import logging
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from database import SessionLocal
from models import CuentaBanco
import enable_banking as eb
from gmail_importer import import_from_gmail
from notifier import send_email, notify_import_result
from resumen import calcular_resumen_curso, calcular_kpis
from decimal import Decimal
from datetime import datetime

log = logging.getLogger("scheduler")

CURSO_INICIO = date(2025, 10, 1)
CURSO_FIN = date(2026, 6, 30)
MADRID = pytz.timezone("Europe/Madrid")


# ── ING ───────────────────────────────────────────────────────────────────────

def tarea_ing():
    """Sincroniza cobros ING y notifica si hay novedades o desajustes."""
    log.info("▶ Tarea ING: iniciando sincronización automática")
    db = SessionLocal()
    try:
        from models import Cobro

        cuenta = db.query(CuentaBanco).first()
        if not cuenta or cuenta.estado != "conectado" or not cuenta.account_id:
            log.info("ING no conectado, tarea omitida")
            return

        try:
            transactions = eb.get_transactions(cuenta.account_id)
            candidatos = eb.filter_cobros(transactions)
        except Exception as e:
            log.error(f"Error al obtener transacciones ING: {e}")
            _notificar_error("ING", str(e))
            return

        importados = 0
        cobros_nuevos = []

        for tx in candidatos:
            fecha_str = tx.get("booking_date") or tx.get("value_date")
            if not fecha_str:
                continue
            try:
                fecha = date.fromisoformat(fecha_str)
            except ValueError:
                continue

            amount = tx["_amount"]
            description = tx.get("_description", "")[:255]
            mes_referencia = date(fecha.year, fecha.month, 1)

            existe = db.query(Cobro).filter(
                Cobro.fecha == fecha,
                Cobro.importe == amount,
                Cobro.mes_referencia == mes_referencia,
            ).first()

            if existe:
                continue

            cobro = Cobro(
                fecha=fecha,
                importe=amount,
                mes_referencia=mes_referencia,
                descripcion=f"ING · {description}" if description else "ING · carga automática",
            )
            db.add(cobro)
            cobros_nuevos.append((fecha, amount, description))
            importados += 1

        cuenta.ultimo_sync = datetime.utcnow()
        cuenta.error = None
        db.commit()

        log.info(f"ING: {importados} cobros nuevos importados")

        # Calcular estado de reconciliación actual
        hoy = date.today()
        mes_actual = date(hoy.year, hoy.month, 1)
        todos = calcular_resumen_curso(db, CURSO_INICIO, CURSO_FIN)
        resumenes = [r for r in todos if r.mes <= mes_actual]
        kpis = calcular_kpis(resumenes)
        pendiente = kpis["pendiente_acumulado"]

        if importados > 0 or pendiente != Decimal("0"):
            _notificar_ing(importados, cobros_nuevos, pendiente, resumenes)

    except Exception as e:
        log.error(f"Error inesperado en tarea ING: {e}")
    finally:
        db.close()


def _notificar_ing(importados, cobros_nuevos, pendiente, resumenes):
    _STYLE = "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;padding:24px"
    _CARD = "background:#1e293b;border:1px solid #334155;border-radius:10px;padding:20px;margin-top:16px"

    # Sección cobros nuevos
    if cobros_nuevos:
        filas = "".join(
            f"<tr><td style='padding:4px 8px;color:#94a3b8'>{f.strftime('%d/%m/%Y')}</td>"
            f"<td style='padding:4px 8px;color:#22c55e;font-weight:600'>{float(a):.2f} €</td>"
            f"<td style='padding:4px 8px;color:#64748b'>{d[:60]}</td></tr>"
            for f, a, d in cobros_nuevos
        )
        cobros_html = f"""
        <div style="{_CARD}">
          <p style="margin:0 0 10px 0;color:#22c55e;font-weight:600">✓ {importados} cobro(s) nuevo(s) importado(s)</p>
          <table style="border-collapse:collapse;width:100%">{filas}</table>
        </div>"""
    else:
        cobros_html = ""

    # Sección reconciliación
    if pendiente != Decimal("0"):
        color = "#fbbf24" if pendiente > 0 else "#f87171"
        signo = "+" if pendiente > 0 else ""
        texto = "pendiente de cobrar" if pendiente > 0 else "cobrado en exceso"
        meses_desajuste = [
            r for r in resumenes if r.diferencia != 0
        ]
        filas_rec = "".join(
            f"<tr><td style='padding:4px 8px;color:#94a3b8'>{r.mes_str}</td>"
            f"<td style='padding:4px 8px;color:{'#fbbf24' if r.diferencia>0 else '#f87171'};font-weight:600'>"
            f"{'+'if r.diferencia>0 else ''}{float(r.diferencia):.2f} €</td>"
            f"<td style='padding:4px 8px;color:#64748b'>{r.estado.replace('_',' ')}</td></tr>"
            for r in meses_desajuste
        )
        rec_html = f"""
        <div style="{_CARD};border-color:{color}44">
          <p style="margin:0 0 4px 0;color:#94a3b8">Saldo acumulado</p>
          <p style="margin:0 0 10px 0;font-size:22px;font-weight:700;color:{color}">{signo}{float(pendiente):.2f} € <span style="font-size:13px;font-weight:400">{texto}</span></p>
          <table style="border-collapse:collapse;width:100%">{filas_rec}</table>
        </div>"""
    else:
        rec_html = f"""
        <div style="{_CARD};border-color:#22c55e44">
          <p style="margin:0;color:#22c55e">✓ Todo cuadra · saldo acumulado 0,00 €</p>
        </div>"""

    asunto_parts = []
    if importados > 0:
        asunto_parts.append(f"{importados} cobro(s) nuevo(s)")
    if pendiente != Decimal("0"):
        signo = "+" if pendiente > 0 else ""
        asunto_parts.append(f"saldo {signo}{float(pendiente):.2f} €")
    subject = "ControlGastosCRC · ING · " + (" · ".join(asunto_parts) if asunto_parts else "sin cambios")

    body = f"""
    <html><body style="{_STYLE}">
      <h2 style="color:#818cf8;margin-bottom:4px">🏦 Sincronización ING automática</h2>
      <p style="color:#64748b;font-size:13px">Colegio Ramón y Cajal · Lucía · {date.today().strftime('%d/%m/%Y')}</p>
      {cobros_html}
      {rec_html}
      <p style="margin-top:20px;font-size:11px;color:#475569">ControlGastosCRC · Notificación automática diaria</p>
    </body></html>
    """
    send_email(subject, body)


# ── Gmail ─────────────────────────────────────────────────────────────────────

def tarea_gmail():
    """Importa PDFs del colegio desde Gmail y notifica si hay facturas nuevas."""
    log.info("▶ Tarea Gmail: revisando correo del colegio")
    db = SessionLocal()
    try:
        resultado = import_from_gmail(db)

        if not resultado.get("ok"):
            log.error(f"Error Gmail: {resultado.get('error')}")
            _notificar_error("Gmail", resultado.get("error", "Error desconocido"))
            return

        insertados = resultado.get("insertados", 0)
        omitidos = resultado.get("omitidos", 0)
        errores = resultado.get("errores", [])

        log.info(f"Gmail: {insertados} facturas nuevas, {omitidos} omitidas")

        if insertados > 0 or errores:
            notify_import_result(insertados, omitidos, errores)

    except Exception as e:
        log.error(f"Error inesperado en tarea Gmail: {e}")
    finally:
        db.close()


# ── Error genérico ────────────────────────────────────────────────────────────

def _notificar_error(origen: str, mensaje: str):
    _STYLE = "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;padding:24px"
    _CARD = "background:#1e293b;border:1px solid rgba(248,113,113,.3);border-radius:10px;padding:20px;margin-top:16px"
    body = f"""
    <html><body style="{_STYLE}">
      <h2 style="color:#f87171;margin-bottom:4px">⚠ Error en tarea automática · {origen}</h2>
      <p style="color:#64748b;font-size:13px">{date.today().strftime('%d/%m/%Y')}</p>
      <div style="{_CARD}"><p style="margin:0;color:#94a3b8">{mensaje}</p></div>
      <p style="margin-top:20px;font-size:11px;color:#475569">ControlGastosCRC · Notificación automática</p>
    </body></html>
    """
    send_email(f"ControlGastosCRC · Error en tarea {origen}", body)


# ── Scheduler ─────────────────────────────────────────────────────────────────

def iniciar_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=MADRID)

    # ING: cada día a las 10:00 hora Madrid
    scheduler.add_job(
        tarea_ing,
        CronTrigger(hour=10, minute=0, timezone=MADRID),
        id="ing_sync",
        replace_existing=True,
        name="Sincronización ING diaria",
    )

    # Gmail: cada día a las 10:05 hora Madrid (5 min después para no solapar)
    scheduler.add_job(
        tarea_gmail,
        CronTrigger(hour=10, minute=5, timezone=MADRID),
        id="gmail_import",
        replace_existing=True,
        name="Importación Gmail diaria",
    )

    scheduler.start()
    log.info("Scheduler iniciado · ING 10:00 · Gmail 10:05 · Europe/Madrid")
    return scheduler
