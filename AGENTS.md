# AGENTS.md - NotesControl (App Web Móvil / Streamlit)

## Descripción
App web responsive (PWA-lite) para registrar y seguir trabajos freelance (Por Hora / Por Servicio). Se usa desde el navegador del móvil. **Nada crítico vive solo en el dispositivo**: los datos se respaldan en Google Drive para sobrevivir a pérdida/deterioro del teléfono.

## Stack y Plataforma
- **Python + Streamlit** (≥ 1.42), desplegada gratis en Streamlit Community Cloud.
- **Login**: `st.login("google")` + `st.user` (OAuth 2.0 en `.streamlit/secrets.toml`).
- **Respaldo**: Google Drive API con scope `drive.file` (carpeta oculta `appDataFolder`), no local de forma exclusiva.
- Modelo de persistencia desacoplado: **Patrón Repositorio** obligatorio. La lógica de negocio nunca conoce la capa física (JSON local / Drive). Uso de Safe-Write (shadow-write a archivo temporal antes de reemplazar, con `try/except`).

## Gotchas críticos (el agente los suele errar)
- El login OAuth de Streamlit otorga **identidad (perfil/email) pero NO acceso al Drive**. El respaldo en Drive requiere una autorización separada con scope `drive.file`; no asumir que `st.user` basta.
- El **email de sesión es la clave de partición de datos**: cada usuario lee/escribe solo su propio archivo.
- En el plan gratuito, una app con autenticación cuenta como la única *app privada* permitida.

## Flujo de Estados (validar transiciones, no saltarse)
1. **Pendiente** → 2. **En Progreso** → 3. **Completado (Local, no en producción)** → 4. **En Producción** → 5. **Realizado y Pagado**.

## Modelo de Datos
- **Documento versionado** (`schema_version`): `{"schema_version": 2, "jobs": [...], "notes": [...]}` y los repositorios **migran** formatos v1 (lista plana) sin pérdida. No usar nunca `load_records/save_records`: la API es `load_document()`/`save_document()`.
- **Job**: ID, Cliente/Empresa, Tipo (`Por Hora` | `Por Servicio`), Estado, fechas (creación/entrega estimada/recordatorio/completado/pago), cálculo de costo, `notes` (texto plano), `note_ids` (notas enlazadas del bloc), `history` (eventos `{ts, evento, detalle}`).
- **Note** (bloc global): ID, título, contenido plano, `updated_at`, `linked_job_ids`. Presentar el contenido siempre vía `services/parser_notas.py` (títulos/pasos/código); el dato guardado nunca se altera.
- Costo: `Por Hora` → tarifa por hora + horas invertidas; `Por Servicio` → precio fijo acordado.
- Al marcar **Completado** un trabajo por horas: congelar el contador y calcular el subtotal.
- **Notas editables en cualquier estado** (aunque el costo esté congelado a partir de Completado).

## UI y presentación
- **Navegación superior** (sin sidebar): `st.segmented_control` con valores planos (`PAGES` = Tablero/Nuevo/Bloc/Recordatorios/Historial/Respaldo) y emojis vía `format_func`. Solo se renderiza la página activa (if/elif). Para saltos programáticos se usa `_go_page` (resetea el widget antes de instanciarlo) + `_focus_job` (si el Tablero lo recibe, abre el expander de esa tarjeta): **nunca** escribir `_page_nav` tras instanciarse (error Streamlit).
- Páginas: **Tablero** (lista continua con barras por empresa, insensible a mayúsculas, secciones pendientes/completados, métricas y filtros), **Nuevo**, **Bloc**, **Recordatorios** (tarjetas con "Ir al trabajo →" desde próximos/vencidos), **Historial** (global), **Respaldo** (JSON + CSV).
- **Logo de marca**: `assets/icon.svg` (badge "nodos de flujo"). Se usa como `page_icon`, en la cabecera (`app.py`) y en el login (`auth/auth.py`) inlineando el SVG leído del archivo; no cambiar a emojis ni duplicar la marca en inline.
- **Iconos del menú**: Material Symbols (`:material/…:`) vía `format_func` del `segmented_control` (fuente offline incluida en Streamlit); los **valores planos de `PAGES` no cambian** (los tests los comparan). Iconos válidos se verifican contra `streamlit.material_icon_names.ALL_MATERIAL_ICONS`.
- **CSS del menú**: en Streamlit 1.63 el `segmented_control` renderiza `div[data-testid="stButtonGroup"]` y cada opción es `button[data-variant="segmented_control"]` (con `[data-selected]`/`[aria-pressed="true"]` al estar activa). El testid antiguo `stSegmentedControl` ya **no existe**: cualquier estilo del menú debe apuntar a `stButtonGroup`. El hover de cada botón usa `:nth-child(1..6)` con un degradado propio.
- **Tema oscuro moderno** (CSS en `ui/styles.py` + `base="dark"` en config); cambios de estilo van en el CSS global, no en inline de cada componente.
- Las funciones de render de `ui/components.py` **no reciben `service`**: usan el global fijado con `cmp.bind_service(svc)` desde `app.py`. No revertir a pasar `service` por parámetro.
- Control de estado **inline** en cada tarjeta ("▶ Avanzar a: …"); `created_at` es **editable manualmente** (por defecto hoy). Las fechas son `date_input` **directos** (sin checkboxes): los opcionales (entrega/recordatorio) usan `value=None` para quedar vacíos; cada widget tiene tecla única (`borrar_`, `entrega_`, `record_`, `creacion_`) — nunca reutilizar la misma key para dos widgets.
- El **historial por trabajo** quedó retirado: basta con la pestaña **Historial** global.
- Los recordatorios son **solo dentro de la app** (sin notificaciones nativas); el calendario usa `reminder_date` (o la entrega estimada como respaldo).

## Tests (gotcha)
- Los tests de UI (`AppTest`) deben seleccionar widgets por **`label`**, nunca por índice: el buscador del dashboard, el formulario nuevo, el bloc y los calendarios/expansores compiten por los índices `text_input[0]`, etc.
- `APP_DATA_ROOT` aísla los datos por test; los tests de servicio usan la API de documento.

## MCP y Skills
- Las reglas de Context7, invoice PDF e interfaz web viven en `SKILLS.md`; consultarlo antes de implementar librerías externas (Pydantic v2, google-api-python-client, Rich).

## Convención de mantenimiento
- `README.md` y `CHANGELOG.md` deben actualizarse a medida que se avance con el proyecto, en cada funcionalidad nueva.