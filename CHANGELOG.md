# Changelog

Todas las funcionalidades notables.

## [0.6.0] - 2026-09-04

### Añadido
- **Logo de marca "nodos de flujo"** (`assets/icon.svg`): badge redondeado con gradiente índigo→verde y los tres estados conectados. Se usa como favicon (`page_icon`), en la cabecera de la app y en el login (SVG inline).
- **Iconos Material Symbols en la navegación**: las pestañas del `segmented_control` muestran iconos modernos (`dashboard`, `add_circle`, `sticky_note_2`, `notifications`, `history`, `cloud_done`) vía `format_func`, manteniendo los valores planos de `PAGES`. La fuente viene incluida en Streamlit (funciona offline).
- **Menú como botones individuales**: separados entre sí, con bordes redondeados y un **degradado sutil distinto por botón** al pasar el cursor (índigo, esmeralda, ámbar, rosa, celeste, teal); la opción activa usa el acento plano. CSS apuntando a `[data-testid="stButtonGroup"]` + `button[data-variant="segmented_control"]` (el testid antiguo `stSegmentedControl` ya no existe en Streamlit 1.63).
- **Botón flotante "volver arriba"** (↑): ancla nativa (funciona sin JavaScript) con desplazamiento suave; un helper JS en iframe (`st.components.v1.html`, única vía que ejecuta scripts en Streamlit) sube la página al tope tras el login.

### Cambiado
- `app.py`: `page_icon="assets/icon.svg"`, cabecera con logo SVG inline + wordmark, `PAGE_ICONS` para el `format_func` y ancla `#nc-top` para el botón volver arriba.
- `auth/auth.py`: logo SVG en la tarjeta de login.
- `ui/styles.py`: layout de cabecera con logo, logo de login (SVG centrado con sombra) y navegación rediseñada con selectores correctos de Streamlit 1.63.

## [0.5.0] - 2026-09-04

### Cambiado
- **Calendario → Recordatorios**: la pestaña ahora muestra **tarjetas** de próximos y vencidos (cliente, fecha, badges de estado/tipo y total). Cada tarjeta tiene **"Ir al trabajo →"**, que salta al Tablero y **abre el expander** de ese trabajo.
- **Navegación superior programática**: la barra superior es ahora un `st.segmented_control` (valores planos + emojis vía `format_func`) y solo se renderiza la página activa; los saltos usan `_go_page` (réplica del gotcha de Streamlit: no se puede escribir la key del widget tras instanciarse).

### Quitado
- Grilla de calendario mensual (`delivery_markers`, estado de mes y estilos `.cal-*` de la UI).

## [0.4.0] - 2026-09-04

### Añadido
- **Rebranding a NotesControl**: nombre, título de pestaña y mensajes actualizados.
- **Login rediseñado**: tarjeta centrada tipo landing móvil con logo, eslogan, características de la app y botón/ formulario de acceso.
- **Barra superior en lugar de menú lateral**: se elimina el sidebar; el usuario y el botón **Salir** van en la cabecera junto al logo, y la navegación queda arriba mediante pestañas.

### Cambiado
- `auth.auth._render_login_screen` reescrito (modo Google y modo desarrollo dentro de la tarjeta, con los mismos labels).
- `app.py`: cabecera con marca + usuario + salir; avisos de Drive movidos al cuerpo.
- `ui/styles.py`: estilos de login, barra superior y ocultación del sidebar.

## [0.3.1] - 2026-09-04

### Cambiado
- **Fechas directas** al crear y editar un trabajo: los `date_input` (fecha de inicio, entrega estimada y recordatorio) se muestran siempre, sin casillas intermedias. Los opcionales arrancan vacíos (`value=None`).
- **Calendario informativo**: cada día muestra el **nombre del cliente** (no solo un punto), aviso de "Sin trabajos con fechas este mes" y mensaje cuando ningún trabajo tiene fechas.
- **Retirado el "Historial del trabajo"** dentro de cada tarjeta: la pestaña **Historial** global es la única vista de eventos.

## [0.3.0] - 2026-09-04

### Añadido
- **Rediseño visual oscuro moderno**: tema *dark* con tarjetas, acentos índigo/verde y tipografía responsive (CSS global en `ui/styles.py` + `base="dark"`), encabezado de marca y métricas en cuatríada.
- **Tablero como lista continua (Opción B)**: barras por empresa (`client-bar`) sin acordeones, tarjetas compactas y control de estado **inline** ("▶ Avanzar a: …") sin abrir la tarjeta.
- **Fecha de inicio editable**: `created_at` se puede fijar manualmente al crear o editar (por defecto hoy), y se muestra en la tarjeta junto a entrega/recordatorio.
- **Vista previa en vivo con el parser** en el editor de notas y el formulario nuevo (títulos/pasos/código al escribir), gracias a que los widgets dentro de `st.form` escriben a `session_state`.
- Teclas de widget únicas (`borrar_`, `entrega_`, `record_`, `creacion_`) que eliminan el error `StreamlitDuplicateElementKey`.

### Cambiado
- `ui/components.py` usa un servicio **global** fijado con `bind_service(svc)` desde `app.py`; las funciones de render ya no reciben `service`.
- Tests ampliados a 22, incluida una regresión de teclas duplicadas (activar fecha + eliminar) y retro-fecha de creación.
- `JobService.create_job`/`update_details` aceptan `created_at` opcional.

## [0.2.0] - 2026-09-04

### Añadido
- **Modelo de datos versionado** (`schema_version`): el documento unifica trabajos y notas (`{"schema_version": 2, "jobs": [], "notes": []}`); los repositorios migran formatos antiguos (lista v1) sin pérdida.
- **Entidad Note y Bloc de notas global**: CRUD de notas, importación desde `.txt` o pegado, y **enlaces** de notas a trabajos (las notas son editables en cualquier estado).
- **Parser de notas** (`services/parser_notas.py`): presentación derivada del texto plano que reconoce títulos (`#`/`***`), pasos (→, "Ajustes → …", viñetas) y bloques de código XML/Python.
- **Historial de actividad**: eventos (creado/editado/horas/estado/notas) por trabajo y vista global cronológica.
- **Tablero agrupado por empresa**: secciones pendientes/en-progreso y completados, agrupación insensible a mayúsculas con orden por actividad más reciente, búsqueda de cliente.
- **Calendario** de entregas y recordatorios (estado mensual en `session_state`, vencidos en rojo) y panel próximos/vencidos (30 días).
- **Exportación CSV** (utf-8-sig, compatible con Excel/Sheets) junto a la copia universal JSON.

### Cambiado
- `JobService` reescrito sobre la API de documento (`load_document`/`save_document`); repositorios `base`, `local_json`, `drive` y `mirror` migrados al documento v2.
- UI reorganizada en pestañas: Tablero, Nuevo, Bloc, Calendario, Historial, Respaldo.
- Tests ampliados (19) e índices de widgets del smoke test sustituidos por selección por `label`.

## [0.1.0] - 2026-09-04

### Añadido
- App web Streamlit responsive (navegador móvil) con login de Google (`st.login("google")` + `st.user`).
- Máquina de estados estricta: Pendiente → En Progreso → Completado (Local) → En Producción → Realizado y Pagado.
- Modelo de trabajos Por Hora / Por Servicio con cálculo de subtotal y **congelado del contador** al marcar Completado.
- Patrón Repositorio: `BaseRepository` con implementación local (JSON + **Safe-Write**/shadow-write) y respaldo en **Google Drive** (scope `drive.file`, carpeta oculta `appDataFolder`) con restauración automática y degradación elegante.
- Partición de datos por email de sesión.
- Tablero con métricas, filtros por estado/tipo, tarjetas de acción por trabajo y exportación JSON.
- Modo desarrollo sin credenciales para pruebas locales.
- Test suite (pytest): estados, persistencia, espejo Drive y smoke test de UI con `AppTest`.
- README y plantilla de secrets (`.streamlit/secrets.toml.example`).

### Seguridad
- Credenciales y tokens nunca se versionan (`.gitignore`).
- Scopes mínimos (`drive.file`), tokens por usuario en `.credentials/`.