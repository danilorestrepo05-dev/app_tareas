# NotesControl

App web responsive (para el navegador del móvil) para registrar y seguir trabajos **freelance por hora o por servicio**, con login con Google. Los datos de cada usuario se guardan de forma automática en un **repositorio privado de GitHub**, por lo que sobreviven a reinicios del servidor y a la pérdida o deterioro del teléfono.

> **Nada crítico vive solo en el dispositivo**: los datos se guardan por usuario en un repositorio privado de GitHub y puedes exportarlos (JSON/CSV) desde la app.

## ✨ Funcionalidades

- **Login con Google** (OAuth 2.0) y partición de datos por email: cada usuario solo ve/escribe sus trabajos.
- **Flujo de estados estricto** (no se pueden saltar etapas):
  1. Pendiente → 2. En Progreso → 3. Completado (Local) → 4. En Producción → 5. Realizado y Pagado.
  - Con el botón **"◀ Volver a"** se retrocede un estado para corregir avances; prohibido desde "Realizado y Pagado".
- **Costos**:
  - `Por Hora`: tarifa por hora + horas invertidas (contador acumulable).
  - `Por Servicio`: precio fijo acordado.
  - Al marcar **Completado** un trabajo por horas se **congela el contador** y se calcula el subtotal (no vuelve a cambiar).
  - El precio de un trabajo cuenta como **Pendiente** hasta que llega a **Realizado y Pagado**; solo entonces pasa a **Facturado**.
- **Tablero agrupado por empresa**: lista continua con barras por cliente ("📌 Pendientes" y "✅ Completados"), tarjetas compactas con el estado visible, botones **"▶ Avanzar a: …" / "◀ Volver a: …"** en la propia tarjeta y filtros por estado/tipo + búsqueda de cliente; métricas de trabajos, activos, facturado y pendiente.
- **Fecha de inicio editable**: al crear (o editar) puedes fijar manualmente la fecha de creación (por defecto hoy); se muestra en la tarjeta junto a entrega/recordatorio.
- **Tema oscuro moderno** responsive, pensado para el móvil.
- **Historial de actividad**: cada creación, edición, horas o cambio de estado deja un evento; vista global cronológica.
- **Notas por trabajo + Bloc de notas global**: escribe apuntes y código, impórtalos desde un `.txt` o pegándolos, y **enlaza** notas del bloc a trabajos. El texto se **presenta parseado** (títulos, pasos y bloques de código).
- **Recordatorios en tarjetas**: próximos (30 días) y vencidos, con cliente, fecha, estado y total; al tocar **"Ir al trabajo →"** te lleva a la tarjeta del trabajo en el Tablero.
- **Exportación**: copia universal **JSON** del documento y hoja de cálculo **CSV** (compatible Excel/Sheets).
- **Persistencia duradera**: los datos viven en un **repositorio privado de GitHub** (un archivo `data/<email>.json` por usuario, escrito vía API). Si GitHub no responde, la app sigue con una copia local en caché y **avisa** (nunca borra datos en silencio).
- **Modo desarrollo** sin credenciales para probar localmente.

## 🧱 Arquitectura

- **Patrón Repositorio**: la lógica de negocio (`services/`) nunca conoce la capa física. `repositories/` implementa `BaseRepository` con persistencia en **GitHub privado** (`repositories/github.py`, vía Contents API, con copia local en caché) y **JSON local** (`repositories/local_json.py`, con *Safe-Write* / shadow-write) como respaldo cuando no hay token configurado.
- **Documento versionado**: el almacenamiento es un JSON único `{"schema_version": 2, "jobs": [...], "notes": [...]}`. Los repositorios **migran** formatos antiguos (lista v1) sin pérdida.
- **Safe-Write**: los JSON se escriben primero a archivo temporal y se reemplazan atómicamente (`os.replace`), con `try/except` defensivo.
- **Presentación derivada del texto**: las notas se guardan como texto plano y se muestran con un **parser ligero** (`services/parser_notas.py`) que reconoce títulos (`#`/`***`), pasos (→, "Ajustes → …", viñetas) y bloques de código (XML/Python indentado).
- **Seguridad**: identidad vía `st.login("google")` + `st.user`; sin secretos en el repositorio.

```
app.py                 # Punto de entrada (pestañas Tablero/Nuevo/Bloc/Recordatorios/Historial/Respaldo)
auth/                  # Login (st.login)
core/models.py         # Job + Note + máquina de estados + evento/historial
services/job_service.py# Reglas de negocio, agrupación, recordatorios, CSV
services/parser_notas.py# Parser de títulos/pasos/código para presentar notas
repositories/          # BaseRepository + GitHub privado (Contents API) + JSON local
ui/                    # Estilos responsive y componentes web
tests/                 # Tests (pytest + AppTest de Streamlit)
```

## 🚀 Puesta en marcha local

Requisitos: Python ≥ 3.11.

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt   # + requirements-dev.txt para tests
streamlit run app.py
```

Abre `http://localhost:8501`. Sin secretos, la app entra en **modo desarrollo** (login simulado).

## ☁️ Configuración de Google

### 1. Proyecto en Google Cloud Console
1. Crea un proyecto en <https://console.cloud.google.com>.
2. **Pantalla de consentimiento**: tipo *Externo*; añade tu email como *test user* (o publica la app).
3. **Credenciales → Crear credenciales → ID de cliente OAuth** (tipo *web*), con estos **URIs de redireccionamiento**:
   - Local: `http://localhost:8501/oauth2callback` y `http://localhost:8501`.
   - Producción: `https://TU-APP.streamlit.app/oauth2callback` y `https://TU-APP.streamlit.app`.

### 2. Secrets
Copia `.streamlit/secrets.toml.example` a `.streamlit/secrets.toml` y rellena:

```toml
[auth]
redirect_uri = ".../oauth2callback"   # o http://localhost:8501/oauth2callback
cookie_secret = "cadena-aleatoria-larga"

[auth.google]
client_id = "...apps.googleusercontent.com"
client_secret = "GOCSPX-..."
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

# Persistencia duradera (opcional local; obligatorio en Cloud)
[github]
token = "gho_..."                     # obtenlo en local: gh auth token (scope repo)
repo = "TU-USUARIO/notascontrol-data"
```

> ⚠️ **Token de GitHub**: el valor de `gh auth token` tiene scope `repo` y da acceso real a tu cuenta. Guárdalo solo en los Secrets de Streamlit Cloud y en tu `secrets.toml` local (ambos **no versionados**); no lo subas al repositorio. Sin `[github]`, la app usa el JSON local del contenedor (efímero).

## 🚢 Desplegar en Streamlit Community Cloud

1. Sube el repositorio a GitHub.
2. En <https://share.streamlit.io> → **Nueva app** → selecciona el repo y `app.py`.
3. En **Settings → Secrets** pega el contenido de `secrets.toml` (rellenado: `[auth]` **y** `[github]` con tu token de GitHub). Con `[github]` los datos se persisten en el repo privado y sobreviven a reinicios; sin él, solo se guardan en el contenedor (**efímero**, riesgo de pérdida).
4. Cuando pida la URL del login, asegúrate de que `redirect_uri` del cliente OAuth es `https://TU-APP.streamlit.app/oauth2callback`.

## 🧪 Tests

```bash
pytest tests -q
```

Cubren la máquina de estados (transiciones estrictas, congelado/descongelado del subtotal, volver atrás), el Safe-Write, la migración de formato v1→v2, la agrupación por empresa, las métricas de dinero (pendiente vs. facturado), recordatorios/vencidos, el bloc de notas y enlaces, el parser, la exportación CSV, la retro-fecha, el repositorio GitHub (lectura/escritura vía Contents API con caché local, conflictos de sha y degradación) y un smoke test de la UI con `AppTest` (navegación por pestañas, fechas y saltos a trabajos desde recordatorios).