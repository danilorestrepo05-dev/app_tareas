# Capacidades Avanzadas y Reglas de Contexto (Skills)

Este documento define el conjunto de habilidades avanzadas que el agente debe desplegar de forma autónoma usando Streamlit (UI web móvil), el ecosistema OpenCode y el protocolo MCP.

---

## 🛠️ 1. Uso Obligatorio de MCP Context7
Para garantizar código moderno, sin APIs deprecadas y libre de alucinaciones en el stack seleccionado (Streamlit ≥ 1.42, Pydantic v2, google-api-python-client, Streamlit Community Cloud), el agente adoptará la siguiente directriz:

*   **Regla Automática**: El agente invocará proactivamente el servidor MCP de `context7` (`context7_query-docs` o `context7_resolve-library-id`) cuando deba codificar autenticación/oauth, integración con Google API, validaciones de Pydantic o la capa de la librería externa.
*   **Prioridad de Origen**: No se utilizarán códigos basados puramente en el conocimiento estático del modelo si implican dependencias de versiones que cambian frecuentemente (p. ej. `st.login`, scopes de Drive). Siempre se contrastará contra la documentación provista por el servidor MCP.

---

## 🔐 2. Autenticación y Respaldo en Google (web)
*   **Identidad vs. Alcances**: `st.login("google")` + `st.user` dan identidad (perfil/email). El **backup en Drive es independiente**: requiere autorización separada con el scope `drive.file` (carpeta oculta `appDataFolder`). Nunca asumir que el login de Streamlit otorga acceso al Drive.
*   **Partición por usuario**: el email de sesión define el archivo de datos de cada usuario; la interfaz solo muestra y escribe lo del usuario autenticado.
*   **Resiliencia**: si Drive no está disponible, operar contra la copia local en caché y reintentar la sincronización; nunca perder la escritura.

---

## 🏗️ 3. Persistencia Segura y Desacoplada
*   **Capa de Abstracción**: El agente creará una interfaz `BaseRepository` pura. Cualquier cambio de almacenamiento físico (memoria, JSON local, Drive, base de datos relacional) solo requerirá escribir una nueva clase concreta sin alterar la UI ni los servicios.
*   **Escritura Atómica (Shadow-Writing)**: Al guardar datos (local o Drive), implementar un proceso defensivo con bloques `try/except`. Los datos se escriben en un archivo temporal intermedio antes de sustituir al almacenamiento real, evitando pérdida o corrupción por interrupciones.
*   **Clave de `st.session_state`**: cachear el repositorio por email de sesión; recargar permisos y dualidad local/Drive al cambiar de usuario.

---

## 🤖 4. Automatización de Flujos de Trabajo
*   **Generador Automatizado de Invoices**: Habilidad para compilar datos de trabajos en estado "En Producción" y exportar automáticamente archivos limpios en formato PDF estructurados dinámicamente (descargable vía web).
*   **Transiciones de Estado Inteligentes**: Al marcar un trabajo por horas como "Completado", el sistema debe congelar automáticamente el contador de horas y calcular el subtotal financiero.

---

## 🎨 5. Interfaz Web Móvil (Streamlit)
*   **UX móvil**: UI responsive pensada para el navegador del teléfono; `st.expander`, columnas compactas y botones de acción claros para cada estado.
*   **Estado visual**: uso de `st.badge`/colores consistentes por estado del trabajo (ej. Amarillo para Pendiente, Verde para Realizado y Pagado).
*   **Tablero agrupado por empresa**: agrupar en `session`/reportes por cliente insensible a mayúsculas (`.strip().lower()`), grupos ordenados por actividad más reciente y, dentro, trabajos recientes primero; secciones de pendientes y completados.
*   **Notas presentadas desde el texto plano**: nunca reescribir el contenido guardado; renderizar vía `services/parser_notas.py` (títulos `#`/`***`, pasos con "→"/"Ajustes →", código XML/Python indentado) con `st.markdown` para pasos y `st.code` para código.
*   **Calendario en HTML**: tabla generada con `calendar.Calendar`, marcadores por día y vencidos en rojo; estado del mes en `session_state`.
*   **Tests AppTest**: seleccionar widgets por **label**, no por índice (el buscador del dashboard compite con el formulario nuevo y el bloc).