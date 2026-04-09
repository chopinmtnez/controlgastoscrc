# ControlGastosCRC — Diseño del sistema

**Fecha:** 2026-04-09  
**Dominio:** controlgastoscrc.albertomartinezmartin.com  
**Alumna:** Lucía Martínez Hernando · Colegio Ramón y Cajal · Curso AY 25/26

---

## Problema que resuelve

El colegio emite facturas PDF por conceptos variables cada mes (mensualidad, comedor, actividades, sesiones PM, natación, etc.) y los cobra descontando ya la beca de la Comunidad de Madrid. El cobro bancario no coincide con la suma bruta de facturas porque la beca se gestiona directamente entre el colegio y la Comunidad. Sin un sistema de control es imposible saber si cada mes cuadra, qué está pendiente de cobrar o qué se ha cobrado de más.

**Fórmula central:**

```
DIFERENCIA = (TOTAL_FACTURAS − BECA) − TOTAL_COBROS

Diferencia > 0  → pendiente de cobrar por el colegio
Diferencia = 0  → cuadrado ✓
Diferencia < 0  → han cobrado de más / beca cubre el exceso
```

---

## Arquitectura

### Stack

- **Backend:** Python 3.12 · FastAPI · Uvicorn · Jinja2 templates · HTMX
- **PDF parsing:** pdfplumber
- **Base de datos:** PostgreSQL 16 (contenedor propio)
- **Auth:** usuario único por variables de entorno · JWT en cookie HTTP-only · passlib (bcrypt)
- **Infraestructura:** Docker Compose · Nginx (existente) · SSL wildcard `*.albertomartinezmartin.com`

### Contenedores Docker

| Servicio | Puerto | Imagen |
|---|---|---|
| `cgcrc-app` | 127.0.0.1:8020 → 8000 | cgcrc-app (custom Python) |
| `cgcrc-db` | 127.0.0.1:15433 → 5432 | postgres:16-alpine |

Ubicación en el VPS: `/opt/controlgastoscrc/`  
PDFs almacenados en: `/opt/controlgastoscrc/pdfs/` (volumen Docker montado)

### Nginx

Nuevo bloque en `/etc/nginx/sites-enabled/controlgastoscrc.albertomartinezmartin.com` reutilizando el certificado wildcard existente en `/etc/ssl/certs/fullchain.pem`.

```
HTTPS → Nginx :443 → proxy_pass http://127.0.0.1:8020 → cgcrc-app :8000
```

---

## Modelo de datos

### Tabla `facturas`

| Campo | Tipo | Descripción |
|---|---|---|
| id | UUID PK | Identificador |
| numero_documento | VARCHAR UNIQUE | Ej: `25031168` |
| tipo | ENUM(YI, YM, RN) | YI=Recibo, YM=Abono, RN=Rectificativo |
| fecha_emision | DATE | Fecha del PDF |
| fecha_vencimiento | DATE | Fecha de vencimiento |
| mes_referencia | DATE | Primer día del mes al que pertenece (editable) |
| total | NUMERIC(10,2) | Total del documento (negativo en abonos YM) |
| pdf_path | VARCHAR | Ruta relativa al PDF en disco |
| creado_en | TIMESTAMP | Fecha de subida |

### Tabla `lineas_factura`

| Campo | Tipo | Descripción |
|---|---|---|
| id | UUID PK | Identificador |
| factura_id | UUID FK → facturas | Factura a la que pertenece |
| descripcion | VARCHAR | Ej: `Early Years PM session`, `Dto. Natación-Lucía` |
| importe_neto | NUMERIC(10,2) | Importe neto de la línea |
| importe_bruto | NUMERIC(10,2) | Importe bruto de la línea |

### Tabla `cobros`

| Campo | Tipo | Descripción |
|---|---|---|
| id | UUID PK | Identificador |
| fecha | DATE | Fecha del cargo bancario |
| importe | NUMERIC(10,2) | Importe cobrado |
| mes_referencia | DATE | Primer día del mes al que se asigna (editable) |
| descripcion | VARCHAR nullable | Nota libre opcional |
| creado_en | TIMESTAMP | Fecha de registro |

### Tabla `beca_config`

| Campo | Tipo | Descripción |
|---|---|---|
| id | UUID PK | Identificador |
| descripcion | VARCHAR | Ej: `Beca CM 25/26` |
| importe_mensual | NUMERIC(10,2) | Ej: 177.00 |
| fecha_inicio | DATE | Ej: 2025-12-01 |
| fecha_fin | DATE | Ej: 2026-06-30 |
| activa | BOOLEAN | Permite desactivar sin borrar |

### Vista calculada `resumen_mensual` (query, no tabla)

```sql
total_facturas  = SUM(facturas.total) por mes_referencia
total_cobros    = SUM(cobros.importe) por mes_referencia
beca            = beca_config.importe_mensual si el mes está en [fecha_inicio, fecha_fin] Y activa=true
neto_esperado   = total_facturas - beca
diferencia      = neto_esperado - total_cobros
```

---

## Flujo de subida de PDF

1. Usuario arrastra o selecciona el PDF en la UI
2. FastAPI recibe el archivo (multipart), lo guarda temporalmente en `/tmp/{uuid}.pdf` para el parseo
3. `pdfplumber` extrae el texto y parsea:
   - Número de documento (campo `Número de Documento` o `Nº de Recibo`)
   - Tipo de documento (`Recibo` → YI, `Recibo de abono` → YM, `Rectificativo` → RN)
   - Fecha de emisión y vencimiento
   - Líneas de concepto con importe neto y bruto
   - Total del documento
4. Se detecta el mes de referencia como el mes de la fecha de emisión (editable por el usuario en la preview)
5. Se muestra pantalla de **confirmación previa** con los datos extraídos
6. Si el número de documento ya existe en BD → aviso de duplicado, no se inserta
7. Usuario confirma → el archivo temporal se mueve a `/opt/controlgastoscrc/pdfs/{numero_doc}.pdf` e inserción en `facturas` + `lineas_factura`. Si el usuario cancela o cierra sin confirmar, el temporal se descarta automáticamente.
8. El dashboard se actualiza con HTMX sin recargar la página completa

---

## Pantallas

| Ruta | Descripción |
|---|---|
| `GET /login` | Formulario de login |
| `POST /login` | Valida credenciales, emite JWT en cookie HTTP-only, redirige a `/` |
| `GET /` | **Dashboard**: KPIs del curso + tabla resumen mensual + zona de subida + cobro rápido |
| `GET /facturas` | Listado de todas las facturas con filtro por mes y tipo (YI/YM/RN) |
| `GET /facturas/{id}` | Detalle de factura: líneas de concepto + PDF embebido + enlace descarga |
| `POST /facturas/upload` | Recibe PDF, parsea, devuelve preview (HTMX) |
| `POST /facturas/confirmar` | Confirma inserción tras preview |
| `DELETE /facturas/{id}` | Elimina factura y su PDF del disco |
| `GET /cobros` | Listado de cobros con totales por mes |
| `POST /cobros` | Añadir cobro manual |
| `PUT /cobros/{id}` | Editar cobro |
| `DELETE /cobros/{id}` | Eliminar cobro |
| `GET /beca` | Ver y editar configuración de la beca |
| `PUT /beca/{id}` | Actualizar importe, fechas o estado de la beca |
| `GET /mes/{yyyy-mm}` | Vista detallada de un mes: facturas, cobros y cálculo completo |
| `GET /documentos` | Listado de todos los PDFs subidos con descarga individual |
| `GET /documentos/zip` | Descarga ZIP con todos los PDFs |
| `GET /documentos/{id}/pdf` | Descarga de un PDF concreto |

---

## Autenticación

- Usuario único definido por variables de entorno: `APP_USERNAME` y `APP_PASSWORD_HASH` (hash bcrypt)
- Login: formulario HTML → POST → validación → JWT firmado (HS256) en cookie HTTP-only, SameSite=Strict, Secure
- Expiración del token: 8 horas (renovación automática en cada request)
- Todas las rutas excepto `/login` requieren token válido → redirige a `/login` si ausente o expirado
- Sin registro, sin recuperación de contraseña (cambio directo en `.env`)

---

## KPIs del dashboard

| KPI | Cálculo |
|---|---|
| Pendiente acumulado | Suma de diferencias positivas del curso |
| Total facturado (curso) | SUM(facturas.total) de todos los meses |
| Total cobrado (curso) | SUM(cobros.importe) de todos los meses |
| Beca acumulada | SUM(beca mensual) de los meses transcurridos |

---

## Estructura del proyecto

```
/opt/controlgastoscrc/
├── docker-compose.yml
├── .env                        # APP_USERNAME, APP_PASSWORD_HASH, DB_URL, SECRET_KEY
├── pdfs/                       # PDFs subidos (volumen montado)
└── app/
    ├── Dockerfile
    ├── requirements.txt
    ├── main.py                 # FastAPI app, routers, middleware
    ├── database.py             # SQLAlchemy engine, sesión
    ├── models.py               # Modelos ORM (Factura, LineaFactura, Cobro, BecaConfig)
    ├── schemas.py              # Pydantic schemas
    ├── auth.py                 # JWT, login, dependencia require_auth
    ├── pdf_parser.py           # Lógica de extracción con pdfplumber
    ├── routers/
    │   ├── dashboard.py
    │   ├── facturas.py
    │   ├── cobros.py
    │   ├── beca.py
    │   ├── mes.py
    │   └── documentos.py
    ├── templates/              # Jinja2 HTML
    │   ├── base.html           # Layout con sidebar + topbar
    │   ├── login.html
    │   ├── dashboard.html
    │   ├── facturas.html
    │   ├── factura_detalle.html
    │   ├── factura_preview.html  # Preview post-parseo (HTMX fragment)
    │   ├── cobros.html
    │   ├── beca.html
    │   ├── mes.html
    │   └── documentos.html
    └── static/
        ├── htmx.min.js
        └── style.css
```

---

## Variables de entorno (.env)

```env
APP_USERNAME=alberto
APP_PASSWORD_HASH=<bcrypt hash>
SECRET_KEY=<clave aleatoria 32 bytes>
DATABASE_URL=postgresql://cgcrc:password@cgcrc-db:5432/cgcrc
PDFS_DIR=/pdfs
```

---

## Fuera de alcance (v1)

- Importación automática desde email (Gmail/IMAP) → v2
- Importación automática de cobros desde ING → v2
- Notificaciones (email, Telegram) cuando llega un nuevo cobro → v2
- Multiusuario → no previsto
- App móvil → no previsto

---

## Datos iniciales a cargar

Al arrancar por primera vez se cargarán:

**Cobros históricos (tabla `cobros`):**
| Fecha | Importe | Mes referencia |
|---|---|---|
| 10/10/2025 | 38,00 € | oct-2025 |
| 04/12/2025 | 497,40 € | dic-2025 |
| 09/01/2026 | 119,60 € | ene-2026 |
| 06/02/2026 | 335,65 € | feb-2026 |
| 06/03/2026 | 310,00 € | mar-2026 |
| 07/04/2026 | 272,00 € | abr-2026 |

**Beca (`beca_config`):**
- Descripción: Beca CM 25/26
- Importe: 177,00 €/mes
- Período: 2025-12-01 → 2026-06-30

Los PDFs históricos se subirán manualmente desde la interfaz tras el despliegue.
