"""Parser ligero de notas de trabajo (guía paso a paso + fragmentos de código).

Interpreta un texto plano como el cuaderno de un proyecto (por ejemplo, notas
de configuraciones de Odoo): reconoce títulos (``#TÍTULO`` / ``***título***`),
separa líneas de *pasos* (instrucciones, ``Ajustes → ...``, viñetas) de
bloques de *código* (XML/Python indentado o etiquetado) y produce bloques con
estilo para presentarlos de forma ordenada en la app.

La presentación se deriva del texto plano: el dato guardado no se altera.
"""

from __future__ import annotations

import re
from typing import List

TITLE_A = re.compile(r"^#{1,5}\s*(.+?)\s*$")
# *** Titulo ***  ó  ****Titulo****  (asteriscos envolventes)
TITLE_B = re.compile(r"^\*{2,6}\s*(.+?)\s*\*{2,6}$")

# Marcas habituales de instrucción / guía
_STEP_HINTS = (
    "→",
    "->",
    "ajustes",
    "configurar",
    "guardar",
    "crear",
    "añadir",
    "agregar",
    "buscar",
    "abrir",
    "ve a",
    "entra",
    "activa",
    "marcar",
    "seleccionar",
    "cambiar",
    "pegar",
    "escribir",
    "dominio",
    "modelo:",
    "nombre:",
    "título",
    "- ",
    "•",
    "1.",
    "2.",
    "3.",
    "4.",
    "5.",
    "paso",
)

# Marcas habituales de código
_CODE_PATTERN = re.compile(
    r"^(<|</|\s+\[|\s+\(|for\s+|if\s+|while\s+|def\s+|import\s+|from\s+|"
    r"class\s+|return\s+|record|records|orders|route\s*=|env\[|raise\s+|"
    r"\.write\(|\.search\(|\.execute\(|xpath|t-|:attribute|\{[\"']|\[\(4,)",
    re.IGNORECASE,
)


def _match_title(line: str):
    m = TITLE_A.match(line)
    if m:
        return m.group(1).strip()
    m = TITLE_B.match(line)
    if m:
        return m.group(1).strip()
    return None


def _categorize(line: str) -> str:
    s = line.strip()
    if not s:
        return "texto"
    if line.startswith((" ", "\t")):
        return "codigo"
    if _CODE_PATTERN.match(s):
        return "codigo"
    low = s.lower()
    if any(s.startswith(m) or m in low for m in _STEP_HINTS):
        return "pasos"
    return "texto"


def parse(text: str) -> List[dict]:
    """Convierte el texto en una lista de bloques para presentar.

    Cada bloque: {"tipo": "titulo"|"pasos"|"codigo"|"texto",
                  "titulo": str (último título visto), "lineas": [str], ...}
    """
    blocks: List[dict] = []
    last_title = ""
    current: None | dict = None

    def flush() -> None:
        nonlocal current
        if current is not None:
            blocks.append(current)
        current = None

    for line in text.splitlines():
        title = _match_title(line)
        if title is not None:
            flush()
            last_title = title
            current = {"tipo": "titulo", "titulo": "", "lineas": [title]}
            continue
        if not line.strip():
            continue  # separadores en blanco no crean contenido
        cat = _categorize(line)
        if current is None or current["tipo"] == "titulo" or current["tipo"] != cat:
            flush()
            current = {"tipo": cat, "titulo": last_title, "lineas": []}
        current["lineas"].append(line)

    flush()
    return blocks


def count_sections(text: str) -> int:
    """Número de títulos detectados (útiles para la vista previa)."""
    return sum(1 for b in parse(text) if b["tipo"] == "titulo")