"""
Notificaciones por email via Gmail SMTP.

Requiere en .app.env:
  GMAIL_USER=tu@gmail.com
  GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
  NOTIFICATION_EMAIL=destino@gmail.com
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL", "")

_STYLE = """
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: #0f172a; color: #e2e8f0; padding: 24px;
"""
_CARD = """
  background: #1e293b; border: 1px solid #334155;
  border-radius: 10px; padding: 20px; margin-top: 16px;
"""


def send_email(subject: str, body_html: str) -> bool:
    """Envía un email HTML via Gmail SMTP. Devuelve True si se envió correctamente."""
    if not GMAIL_USER or not GMAIL_APP_PASSWORD or not NOTIFICATION_EMAIL:
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"ControlGastosCRC <{GMAIL_USER}>"
    msg["To"] = NOTIFICATION_EMAIL
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            smtp.sendmail(GMAIL_USER, NOTIFICATION_EMAIL, msg.as_string())
        return True
    except Exception:
        return False


def notify_import_result(insertados: int, omitidos: int, errores: list) -> bool:
    """Notifica el resultado de una importación desde Gmail."""
    if insertados == 0 and not errores:
        return True  # nada relevante que notificar

    subject = f"ControlGastosCRC · {insertados} factura(s) importada(s) automáticamente"

    errores_html = ""
    if errores:
        items = "".join(f"<li style='margin:4px 0'>{e}</li>" for e in errores)
        errores_html = f"""
        <div style="{_CARD} border-color:rgba(248,113,113,.3)">
          <strong style="color:#f87171">⚠ Errores ({len(errores)})</strong>
          <ul style="margin:8px 0 0 0;padding-left:20px;color:#94a3b8">{items}</ul>
        </div>"""

    body = f"""
    <html><body style="{_STYLE}">
      <h2 style="color:#818cf8;margin-bottom:4px">📥 Importación automática completada</h2>
      <p style="color:#64748b;font-size:13px">Colegio Ramón y Cajal · Lucía · Curso 25/26</p>
      <div style="{_CARD}">
        <p style="margin:0 0 8px 0">
          <span style="color:#22c55e">✓ <strong>{insertados}</strong> factura(s) nueva(s) importada(s)</span>
        </p>
        <p style="margin:0;color:#64748b">
          ⏭ <strong>{omitidos}</strong> duplicado(s) omitido(s)
        </p>
      </div>
      {errores_html}
      <p style="margin-top:20px;font-size:11px;color:#475569">
        ControlGastosCRC · Notificación automática
      </p>
    </body></html>
    """
    return send_email(subject, body)


def notify_reconciliation(mes_str: str, diferencia: float) -> bool:
    """Notifica cuando un mes tiene diferencia pendiente."""
    subject = f"ControlGastosCRC · Diferencia pendiente en {mes_str}"
    signo = "+" if diferencia > 0 else ""
    color = "#fbbf24" if diferencia > 0 else "#f87171"

    body = f"""
    <html><body style="{_STYLE}">
      <h2 style="color:#818cf8;margin-bottom:4px">⚠ Diferencia detectada</h2>
      <p style="color:#64748b;font-size:13px">Colegio Ramón y Cajal · Lucía · Curso 25/26</p>
      <div style="{_CARD} border-color:{color}33">
        <p style="margin:0 0 6px 0;color:#94a3b8">Mes: <strong style="color:#e2e8f0">{mes_str}</strong></p>
        <p style="margin:0;font-size:22px;font-weight:700;color:{color}">
          {signo}{diferencia:.2f} €
        </p>
        <p style="margin:6px 0 0 0;font-size:12px;color:#64748b">
          {'Lo cobrado es menos de lo esperado' if diferencia > 0 else 'Se cobró más de lo esperado'}
        </p>
      </div>
      <p style="margin-top:20px;font-size:11px;color:#475569">
        ControlGastosCRC · Notificación automática
      </p>
    </body></html>
    """
    return send_email(subject, body)
