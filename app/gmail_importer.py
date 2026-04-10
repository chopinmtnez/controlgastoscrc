"""
Gmail IMAP importer — descarga PDFs del colegio y los importa automáticamente.

Requiere en .app.env:
  GMAIL_USER=tu@gmail.com
  GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx   (Contraseña de aplicación de Google)
  GMAIL_SENDER_FILTER=Fees.ryc@inspirededu.com  (opcional, por defecto este valor)
"""
import email
import imaplib
import os
import shutil
import tempfile
from datetime import date
from email.header import decode_header

from models import Factura, LineaFactura, TipoDocumento
from pdf_parser import parse_pdf

GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
GMAIL_SENDER_FILTER = os.getenv("GMAIL_SENDER_FILTER", "Fees.ryc@inspirededu.com")
PDFS_DIR = os.getenv("PDFS_DIR", "./pdfs")


def import_from_gmail(db) -> dict:
    """
    Conecta a Gmail via IMAP, busca correos del colegio, descarga adjuntos PDF
    y los importa en la base de datos.

    Devuelve un dict con:
      ok: bool
      insertados: int
      omitidos: int
      errores: list[str]
      error: str  (solo si ok=False)
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        return {
            "ok": False,
            "error": "Gmail no configurado. Añade GMAIL_USER y GMAIL_APP_PASSWORD en .app.env",
        }

    insertados = 0
    omitidos = 0
    errores = []

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        mail.select("INBOX")

        status, messages = mail.search(None, f'FROM "{GMAIL_SENDER_FILTER}"')
        if status != "OK":
            mail.logout()
            return {"ok": False, "error": "Error al buscar correos en Gmail IMAP"}

        ids = [i for i in messages[0].split() if i]
        if not ids:
            mail.logout()
            return {
                "ok": True,
                "insertados": 0,
                "omitidos": 0,
                "errores": [],
                "info": f"No se encontraron correos de {GMAIL_SENDER_FILTER}",
            }

        numeros_existentes = {
            f.numero_documento for f in db.query(Factura.numero_documento).all()
        }
        os.makedirs(PDFS_DIR, exist_ok=True)

        for msg_id in ids:
            try:
                status, data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue

                msg = email.message_from_bytes(data[0][1])

                for part in msg.walk():
                    if part.get_content_type() != "application/pdf":
                        continue
                    raw_fname = part.get_filename()
                    if not raw_fname:
                        continue

                    # Decodificar nombre del archivo si está codificado (RFC 2047)
                    decoded = decode_header(raw_fname)
                    fname_part, charset = decoded[0]
                    if isinstance(fname_part, bytes):
                        fname = fname_part.decode(charset or "utf-8", errors="replace")
                    else:
                        fname = fname_part

                    payload = part.get_payload(decode=True)
                    if not payload:
                        continue

                    # Guardar en archivo temporal
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                    tmp.write(payload)
                    tmp.close()

                    try:
                        parsed = parse_pdf(tmp.name)

                        if parsed.numero_documento in numeros_existentes:
                            os.unlink(tmp.name)
                            omitidos += 1
                            continue

                        dest = os.path.join(PDFS_DIR, f"{parsed.numero_documento}.pdf")
                        shutil.move(tmp.name, dest)

                        # El mes de referencia se toma del mes de emisión
                        mes_ref = date(parsed.fecha_emision.year, parsed.fecha_emision.month, 1)

                        factura = Factura(
                            numero_documento=parsed.numero_documento,
                            tipo=TipoDocumento[parsed.tipo],
                            fecha_emision=parsed.fecha_emision,
                            fecha_vencimiento=parsed.fecha_vencimiento,
                            mes_referencia=mes_ref,
                            total=parsed.total,
                            pdf_path=dest,
                        )
                        db.add(factura)
                        db.flush()

                        for linea in parsed.lineas:
                            db.add(
                                LineaFactura(
                                    factura_id=factura.id,
                                    descripcion=linea.descripcion,
                                    importe_neto=linea.importe_neto,
                                    importe_bruto=linea.importe_bruto,
                                )
                            )

                        numeros_existentes.add(parsed.numero_documento)
                        insertados += 1

                    except Exception as e:
                        try:
                            os.unlink(tmp.name)
                        except Exception:
                            pass
                        errores.append(f"{fname}: {str(e)}")

            except Exception as e:
                msg_id_str = msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)
                errores.append(f"Mensaje {msg_id_str}: {str(e)}")

        db.commit()
        mail.logout()

    except imaplib.IMAP4.error as e:
        return {"ok": False, "error": f"Error de autenticación Gmail: {str(e)}"}
    except ConnectionRefusedError:
        return {"ok": False, "error": "No se pudo conectar a imap.gmail.com. Verifica la conexión a internet."}
    except Exception as e:
        return {"ok": False, "error": f"Error inesperado: {str(e)}"}

    return {
        "ok": True,
        "insertados": insertados,
        "omitidos": omitidos,
        "errores": errores,
    }
