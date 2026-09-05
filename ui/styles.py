"""Estilos CSS inyectados: tema oscuro moderno, UI limpia y responsive."""

from __future__ import annotations

import streamlit as st

_CSS = """
<style>
:root {
    --bg: #0b1220;
    --card: #111a2c;
    --card-2: #0f172a;
    --border: #1e293b;
    --text: #e2e8f0;
    --muted: #94a3b8;
    --accent: #6366f1;
    --accent-soft: rgba(99, 102, 241, 0.14);
    --good: #34d399;
}

.stApp {
    max-width: 980px;
    margin: 0 auto;
    background: var(--bg);
    color: var(--text);
}

/* Cabecera de marca */
.app-header {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.1rem 0.8rem;
    padding: 1rem 1.2rem;
    margin-bottom: 0.9rem;
    border-radius: 16px;
    background: linear-gradient(135deg, rgba(99,102,241,0.22), rgba(139,92,246,0.12));
    border: 1px solid var(--border);
}
.app-logo {
    display: inline-flex;
    align-items: center;
}
.app-logo svg {
    width: 44px;
    height: 44px;
    display: block;
}
.app-brand {
    font-size: 1.35rem;
    font-weight: 800;
    letter-spacing: 0.2px;
}
.app-brand + .app-caption {
    width: 100%;
}
.app-caption {
    color: var(--muted);
    font-size: 0.88rem;
    margin-top: 0.05rem;
}

/* Usuario en la barra superior (sin sidebar) */
.top-user {
    text-align: right;
    line-height: 1.35;
    padding: 0 0.2rem;
}
.top-user-name {
    display: block;
    font-weight: 700;
    color: var(--text);
    font-size: 0.95rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.top-user-mail {
    display: block;
    color: var(--muted);
    font-size: 0.72rem;
    word-break: break-all;
}

/* Ocultar la barra lateral (navegación superior) */
[data-testid="stSidebar"],
[data-testid="collapsedControl"] {
    display: none;
}

/* Navegación superior: botones individuales, separados y redondeados.
   En Streamlit 1.63 el segmented_control usa data-testid="stButtonGroup"
   y cada opción es un button[data-variant="segmented_control"]. */
div[data-testid="stButtonGroup"] {
    margin-top: 0.5rem;
}
div[data-testid="stButtonGroup"] > div:last-child {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 0.45rem;
    padding: 0.1rem 0 0.55rem;
    border-bottom: 1px solid var(--border);
}
div[data-testid="stButtonGroup"] button[data-variant="segmented_control"] {
    flex: 1 1 auto;
    min-height: 40px;
    margin: 2px;
    padding: 0.4rem 0.8rem;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    background: var(--card);
    color: var(--text) !important;
    font-weight: 600;
    box-shadow: none;
    transition: background 0.15s ease, color 0.15s ease,
        border-color 0.15s ease, transform 0.15s ease;
}
div[data-testid="stButtonGroup"] button[data-variant="segmented_control"]:hover {
    transform: translateY(-1px);
    border-color: transparent !important;
}
/* Degradado sutil distinto al pasar por encima de cada botón */
div[data-testid="stButtonGroup"] button[data-variant="segmented_control"]:nth-child(1):hover {
    background: linear-gradient(135deg, #4f46e5, #7c3aed);
    color: #fff !important;
}
div[data-testid="stButtonGroup"] button[data-variant="segmented_control"]:nth-child(2):hover {
    background: linear-gradient(135deg, #059669, #10b981);
    color: #fff !important;
}
div[data-testid="stButtonGroup"] button[data-variant="segmented_control"]:nth-child(3):hover {
    background: linear-gradient(135deg, #d97706, #f59e0b);
    color: #fff !important;
}
div[data-testid="stButtonGroup"] button[data-variant="segmented_control"]:nth-child(4):hover {
    background: linear-gradient(135deg, #db2777, #ec4899);
    color: #fff !important;
}
div[data-testid="stButtonGroup"] button[data-variant="segmented_control"]:nth-child(5):hover {
    background: linear-gradient(135deg, #0284c7, #0ea5e9);
    color: #fff !important;
}
div[data-testid="stButtonGroup"] button[data-variant="segmented_control"]:nth-child(6):hover {
    background: linear-gradient(135deg, #0d9488, #14b8a6);
    color: #fff !important;
}
/* Opción seleccionada */
div[data-testid="stButtonGroup"] button[data-variant="segmented_control"][data-selected],
div[data-testid="stButtonGroup"] button[data-variant="segmented_control"][aria-pressed="true"] {
    background: var(--accent) !important;
    color: #fff !important;
    border-color: transparent !important;
}
/* Por si el framework inyecta un resaltado animado detrás de los botones */
div[data-testid="stButtonGroup"] [data-baseweb="selection-indicator"] {
    display: none;
}

/* Tarjeta de login */
.login-logo {
    text-align: center;
    margin-bottom: 0.2rem;
}
.login-logo svg {
    width: 84px;
    height: 84px;
    border-radius: 21px;
    box-shadow: 0 8px 22px rgba(99, 102, 241, 0.35);
}
.login-title {
    font-size: 1.55rem;
    font-weight: 800;
    letter-spacing: -0.3px;
    background: linear-gradient(90deg, #a5b4fc, #34d399);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
}
.login-sub {
    color: var(--muted);
    font-size: 0.9rem;
    margin: 0.5rem 0 0.9rem;
    line-height: 1.5;
}

/* Métricas */
div[data-testid="stMetric"] {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 0.6rem 0.9rem;
}
div[data-testid="stMetricLabel"] { color: var(--muted); }
div[data-testid="stMetricValue"] { color: var(--text); }

/* Badges de estado/tipo */
.badge {
    display: inline-block;
    font-size: 0.76rem;
    font-weight: 700;
    border-radius: 999px;
    padding: 0.18rem 0.65rem;
    margin-right: 0.35rem;
    white-space: nowrap;
    border: 1px solid rgba(255,255,255,0.06);
}

.job-client {
    font-size: 1.02rem;
    font-weight: 700;
    color: var(--text);
}
.job-subtotal {
    font-size: clamp(1.15rem, 4vw, 1.45rem);
    font-weight: 800;
    text-align: right;
    color: var(--good);
    white-space: normal;
    word-break: break-word;
    line-height: 1.1;
}
.job-meta {
    color: var(--muted);
    font-size: 0.82rem;
    line-height: 1.5;
}
.job-done {
    color: var(--good);
    font-weight: 600;
    padding: 0.3rem 0;
}

/* Barra de sección por cliente (lista continua) */
.client-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
    background: var(--accent-soft);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    border-radius: 12px;
    padding: 0.45rem 0.85rem;
    margin: 0.7rem 0 0.4rem;
}
.client-name { font-weight: 700; color: var(--text); }
.client-count { color: var(--muted); font-size: 0.84rem; }
.client-total {
    font-weight: 800; color: var(--good); white-space: nowrap;
    font-size: 0.95rem;
}

/* Tarjetas de recordatorios (próximos / vencidos) */
.alert-card-title {
    font-size: 1.02rem;
    font-weight: 700;
    color: var(--text);
    margin-top: 0.2rem;
}
.alert-card-date {
    color: var(--text);
    font-weight: 600;
    text-align: right;
    font-size: 0.88rem;
}
.alert-card-total {
    font-weight: 800;
    color: var(--good);
    text-align: right;
    font-size: 1.05rem;
}
@media (max-width: 600px) {
    .alert-card-date,
    .alert-card-total {
        text-align: left;
    }
}

/* Tarjetas de trabajo */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 14px;
}

/* Botón primario con acento */
.stButton > button[kind="primary"] {
    background: var(--accent);
    border-radius: 10px;
    font-weight: 600;
}

/* Botón flotante "volver arriba" (solo flecha, siempre visible) */
html {
    scroll-behavior: smooth;
}
#return-to-top {
    position: fixed;
    inset-inline-end: 1rem;
    bottom: 1.1rem;
    z-index: 999;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    padding: 0;
    border: none;
    border-radius: 50%;
    cursor: pointer;
    text-decoration: none;
    font-size: 1.2rem;
    line-height: 1;
    color: #fff;
    background: linear-gradient(135deg, var(--accent), #8b5cf6);
    box-shadow: 0 6px 18px rgba(99, 102, 241, 0.45);
}

@media (max-width: 600px) {
    .job-subtotal { text-align: left; margin-top: 0.25rem; }
    div[data-testid="stMetric"] { padding: 0.4rem 0.6rem; }
    .client-total { font-size: 0.88rem; }
}

/* Scrollbar fina y tenue (web): se aplica a cualquier contenedor que scrollee */
html,
body,
#root,
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stAppViewBlockContainer"],
[data-testid="stMain"],
[data-testid="stMainBlockContainer"] {
    scrollbar-width: thin;
    scrollbar-color: rgba(148, 163, 184, 0.35) transparent;
}
*::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}
*::-webkit-scrollbar-track {
    background: transparent;
}
*::-webkit-scrollbar-thumb {
    background: rgba(148, 163, 184, 0.35);
    border-radius: 6px;
}
*::-webkit-scrollbar-thumb:hover {
    background: rgba(148, 163, 184, 0.55);
}
</style>
"""


def apply_styles() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)