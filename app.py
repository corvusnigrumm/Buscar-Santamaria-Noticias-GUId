import streamlit as st
import datetime
import os
import io
import time
import sys
import base64
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
# CONFIGURACIÓN DE PÁGINA
# ═══════════════════════════════════════════════════════════════

# ── Cargar logo (ícono blindado) ───────────────────────────────
_LOGO_PATH = Path(__file__).parent / "ícono blindado.png"
def _logo_b64():
    with open(_LOGO_PATH, "rb") as f:
        return base64.b64encode(f.read()).decode()

try:
    from PIL import Image as _PILImage
    _pil_logo = _PILImage.open(_LOGO_PATH)
except Exception:
    _pil_logo = "🛡️"

st.set_page_config(
    page_title="B.N.A.S 5.0 — Buscador Santamaria",
    page_icon=_pil_logo,
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Importar el motor principal ─────────────────────────────────
try:
    from buscador_noticias import buscar_noticias, GeneradorExcelIDEAS, CATEGORIAS_GUI, MAPA_CATEGORIAS, FUENTES_RSS
except ImportError:
    st.error("No se encuentra el motor `buscador_noticias.py`. Asegúrate de que esté en el mismo directorio.")
    st.stop()


# ═══════════════════════════════════════════════════════════════
# CSS — Diseño limpio con contraste correcto
# ═══════════════════════════════════════════════════════════════

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;500;600;700;800&display=swap');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0');

/* ── Fuente global ────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Manrope', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

/* ── Proteger Íconos de Streamlit (Material Symbols) ──── */

span[class*="material-symbols"],
i[class*="material-icons"],
span[data-testid="stIconMaterial"],
.stIcon,
button[data-testid="collapsedControl"],
button[data-testid="collapsedControl"] *,
button[kind="header"],
button[kind="header"] * {
    font-family: "Material Symbols Rounded", "Material Icons", sans-serif !important;
}

/* ── Ocultar menú y footer de Streamlit ───────────────── */
footer { visibility: hidden; }
#MainMenu { visibility: hidden; }

/* ── Banner con gradiente verde ───────────────────────── */
.banner {
    background: linear-gradient(135deg, #005931 0%, #217346 50%, #2d8a56 100%);
    padding: 2rem 2.5rem;
    border-radius: 18px;
    margin-bottom: 1.5rem;
    position: relative;
    overflow: hidden;
    box-shadow: 0 8px 30px rgba(0, 89, 49, 0.25);
}
.banner::before {
    content: '';
    position: absolute;
    top: -40%;
    right: -5%;
    width: 250px;
    height: 250px;
    background: radial-gradient(circle, rgba(255,255,255,0.07) 0%, transparent 70%);
    border-radius: 50%;
}
.banner .version {
    display: inline-block;
    background: rgba(255,255,255,0.15);
    padding: 4px 14px;
    border-radius: 100px;
    font-size: 11px;
    font-weight: 700;
    color: #a3f4bc;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 10px;
    border: 1px solid rgba(255,255,255,0.12);
}
.banner h1 {
    color: #ffffff;
    font-weight: 800;
    font-size: 1.8rem;
    margin: 0;
    letter-spacing: -0.01em;
}
.banner .sub {
    color: rgba(255,255,255,0.7);
    font-size: 0.9rem;
    margin-top: 6px;
}

/* ── Badges de info (fondo claro, texto oscuro) ──────── */
.badges { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 1.5rem; }
.badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: #eaf7ef;
    border: 1px solid #bfe0cc;
    border-radius: 100px;
    padding: 6px 14px;
    font-size: 0.78rem;
    font-weight: 600;
    color: #005931;
}

/* ── Tarjeta de estado (fondo blanco, texto oscuro) ──── */
.status-card {
    background: #ffffff;
    border: 1px solid #e2e5e3;
    border-radius: 14px;
    padding: 20px 24px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    margin-bottom: 12px;
}
.status-card .label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #6f7a70;
    margin-bottom: 6px;
}
.status-card .value {
    font-size: 1.5rem;
    font-weight: 800;
    color: #005931;
    display: flex;
    align-items: center;
    gap: 8px;
}
.status-card .dot-pulse {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #28c840;
    animation: pulse 2s infinite;
}
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }

/* ── Terminal (fondo oscuro, texto claro) ────────────── */
.term {
    background: #1a1a2e;
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 6px 20px rgba(0,0,0,0.15);
    margin: 10px 0;
}
.term-bar {
    background: #16213e;
    padding: 10px 14px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid rgba(255,255,255,0.06);
}
.term-dots { display: flex; gap: 6px; }
.term-dots span { width: 10px; height: 10px; border-radius: 50%; display: block; }
.term-dots .r { background: #ff5f57; }
.term-dots .y { background: #febc2e; }
.term-dots .g { background: #28c840; }
.term-title {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    font-weight: 600;
    color: rgba(255,255,255,0.45);
    letter-spacing: 0.06em;
    text-transform: uppercase;
}
.term-body {
    padding: 14px 18px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    line-height: 1.8;
    color: #c5cdd8;
    max-height: 260px;
    overflow-y: auto;
}
.term-body .tg { color: #28c840; font-weight: 600; }
.term-body .tb { color: #61afef; font-weight: 600; }
.term-body .ty { color: #e5c07b; font-weight: 600; }
.term-body .tc { color: #56b6c2; font-weight: 600; }
.term-body .td { opacity: 0.35; }

/* ── Cabecera de tabla de resultados (verde con texto blanco) */
.res-header {
    background: linear-gradient(135deg, #005931, #217346);
    padding: 16px 20px;
    border-radius: 14px 14px 0 0;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.res-header h3 { color: #ffffff; font-weight: 700; font-size: 1rem; margin: 0; }
.res-header .cnt {
    background: rgba(255,255,255,0.2);
    padding: 4px 14px;
    border-radius: 100px;
    font-size: 12px;
    font-weight: 700;
    color: #ffffff;
}

/* ── Tarjeta acento (verde con texto blanco) ─────────── */
.accent-box {
    background: linear-gradient(135deg, #005931, #217346);
    border-radius: 18px;
    padding: 24px;
    color: #ffffff;
    box-shadow: 0 6px 20px rgba(0, 89, 49, 0.2);
}
.accent-box h4 { font-weight: 700; font-size: 1.05rem; margin: 10px 0 8px; color: #ffffff; }
.accent-box p { font-size: 0.82rem; line-height: 1.6; color: rgba(255,255,255,0.82); }
.accent-box .divider {
    border-top: 1px solid rgba(255,255,255,0.15);
    margin-top: 16px;
    padding-top: 12px;
}
.accent-box .row {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: rgba(255,255,255,0.75);
}

/* ── Insight card (fondo blanco, texto oscuro) ───────── */
.insight-box {
    background: #ffffff;
    border: 1px solid #e2e5e3;
    border-radius: 18px;
    padding: 24px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.insight-box .tag {
    display: inline-block;
    background: #eaf7ef;
    padding: 4px 12px;
    border-radius: 100px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #005931;
    margin-bottom: 10px;
}

/* ── Section labels (texto oscuro sobre fondo claro) ─── */
.section-lbl {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: #6f7a70;
    margin-bottom: 12px;
}

/* ── Sidebar ──────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: #ffffff !important;
    border-right: 1px solid #e2e5e3 !important;
}

/* ── Botones primarios (blanco sobre verde) ───────────── */
.stButton > button[kind="primary"],
button[data-testid="stBaseButton-primary"] {
    background: linear-gradient(135deg, #005931, #217346) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 14px !important;
    font-weight: 700 !important;
    padding: 12px 24px !important;
    box-shadow: 0 4px 14px rgba(0, 89, 49, 0.25) !important;
    transition: all 0.2s ease !important;
}
.stButton > button[kind="primary"]:hover,
button[data-testid="stBaseButton-primary"]:hover {
    box-shadow: 0 6px 20px rgba(0, 89, 49, 0.35) !important;
    transform: translateY(-1px) !important;
}

/* ── Botón de descarga (blanco sobre verde) ───────────── */
.stDownloadButton > button {
    background: linear-gradient(135deg, #005931, #217346) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 14px !important;
    font-weight: 700 !important;
    padding: 12px 24px !important;
    box-shadow: 0 4px 14px rgba(0, 89, 49, 0.25) !important;
}
.stDownloadButton > button:hover {
    box-shadow: 0 6px 20px rgba(0, 89, 49, 0.35) !important;
    transform: translateY(-1px) !important;
}

/* ── Botones secundarios ──────────────────────────────── */
.stButton > button:not([kind="primary"]) {
    border-radius: 10px !important;
    font-weight: 600 !important;
    border: 1.5px solid #bfc9be !important;
    color: #3f4941 !important;
    background: #ffffff !important;
}
.stButton > button:not([kind="primary"]):hover {
    border-color: #005931 !important;
    color: #005931 !important;
}

/* ── Métricas ─────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e2e5e3;
    border-radius: 14px;
    padding: 12px 16px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.03);
}
[data-testid="stMetricLabel"] {
    font-size: 10px !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.08em !important;
    color: #6f7a70 !important;
}
[data-testid="stMetricValue"] {
    font-weight: 800 !important;
    color: #191c1d !important;
}

/* ── Tabla de datos ───────────────────────────────────── */
.stDataFrame {
    border-radius: 0 0 14px 14px !important;
    overflow: hidden !important;
    border: 1px solid #e2e5e3 !important;
}

/* ── Scrollbar ────────────────────────────────────────── */
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #bfc9be; border-radius: 4px; }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════

try:
    _b64_banner = _logo_b64()
    st.markdown(f"""
    <div class="banner">
        <div style="display:flex; align-items:center; gap:18px;">
            <img src="data:image/png;base64,{_b64_banner}"
                 style="width:64px; height:64px; object-fit:contain; flex-shrink:0;
                        filter: drop-shadow(0 2px 8px rgba(0,0,0,0.35));" />
            <div>
                <div class="version">B.N.A.S 5.0</div>
                <h1 style="margin:4px 0 0;">Buscador Santamaria de Noticias Inteligente</h1>
                <div class="sub">Configure los parámetros de búsqueda para la extracción y análisis de datos de prensa global y local.</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
except Exception:
    st.markdown("""
    <div class="banner">
        <div class="version">B.N.A.S 5.0</div>
        <h1>🛡️ Buscador Santamaria de Noticias Inteligente</h1>
        <div class="sub">Configure los parámetros de búsqueda para la extracción y análisis de datos de prensa global y local.</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("""
<div class="badges">
    <div class="badge">✓ Fechas 100% reales</div>
    <div class="badge">✓ Artículos sin fecha descartados</div>
    <div class="badge">✓ Filtro de dominios corporativos</div>
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# BARRA LATERAL
# ═══════════════════════════════════════════════════════════════

with st.sidebar:
    try:
        _b64 = _logo_b64()
        st.markdown(f"""
        <div style="text-align:center; margin-bottom:20px;">
            <img src="data:image/png;base64,{_b64}"
                 style="width:80px; height:80px; object-fit:contain; margin-bottom:8px;" />
            <div style="font-weight:800; font-size:1.1rem; color:#005931;">B.N.A.S</div>
            <div style="font-size:10px; font-weight:600; color:#6f7a70; letter-spacing:0.08em;
                        text-transform:uppercase; margin-top:3px;">Panel de Control</div>
        </div>
        """, unsafe_allow_html=True)
    except Exception:
        st.markdown("""
        <div style="text-align:center; margin-bottom:20px;">
            <div style="font-weight:800; font-size:1.1rem; color:#005931;">🛡️ B.N.A.S</div>
            <div style="font-size:10px; font-weight:600; color:#6f7a70; letter-spacing:0.08em;
                        text-transform:uppercase; margin-top:3px;">Panel de Control</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div class="section-lbl">1 · Categorías de Búsqueda</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("✓ Marcar Todas", use_container_width=True):
            for cat in CATEGORIAS_GUI:
                st.session_state[f"cat_{cat}"] = True
            st.rerun()
    with col2:
        if st.button("✕ Limpiar", use_container_width=True):
            for cat in CATEGORIAS_GUI:
                st.session_state[f"cat_{cat}"] = False
            st.rerun()

    st.markdown("---")
    categorias_seleccionadas_gui = []

    for cat in CATEGORIAS_GUI:
        if f"cat_{cat}" not in st.session_state:
            st.session_state[f"cat_{cat}"] = True
        is_checked = st.checkbox(cat, key=f"cat_{cat}")
        if is_checked:
            categorias_seleccionadas_gui.append(cat)

    st.markdown("---")
    st.markdown('<div class="section-lbl">2 · Tipo de Noticias</div>', unsafe_allow_html=True)
    tipo_opcion = st.radio(
        "Tipo de noticias:",
        ["🌐 Ambas", "🇨🇴 Nacional", "🌍 Internacional"],
        index=0,
        horizontal=True,
        label_visibility="collapsed"
    )
    mapa_tipo = {"🌐 Ambas": "ambas", "🇨🇴 Nacional": "nacional", "🌍 Internacional": "internacional"}
    tipo_noticias = mapa_tipo.get(tipo_opcion, "ambas")

    st.markdown("")
    filtrar_argentina = st.checkbox("🇦🇷 Filtrar noticias de Argentina", value=True)

    st.markdown("---")
    st.markdown('<div class="section-lbl">3 · Filtros de Fecha</div>', unsafe_allow_html=True)

    usar_fecha = st.checkbox("📅 Filtrar por rango de fechas", value=True)
    if usar_fecha:
        fecha_valores = st.date_input(
            "Rango de fechas",
            value=(datetime.date.today(), datetime.date.today()),
            label_visibility="collapsed"
        )
        if isinstance(fecha_valores, tuple) and len(fecha_valores) == 2:
            fecha_inicio, fecha_fin = fecha_valores
        elif isinstance(fecha_valores, tuple) and len(fecha_valores) == 1:
            fecha_inicio = fecha_fin = fecha_valores[0]
        else:
            fecha_inicio = fecha_fin = fecha_valores
    else:
        fecha_inicio = None
        fecha_fin = None
        st.info("Buscando todas las noticias más recientes sin importar la fecha.")


# ═══════════════════════════════════════════════════════════════
# CUERPO PRINCIPAL
# ═══════════════════════════════════════════════════════════════

col_main, col_aside = st.columns([7, 5])

with col_aside:
    # ── Estado del Sistema ──────────────────────────────
    st.markdown("""
    <div class="status-card">
        <div class="label">Estado del Sistema</div>
        <div class="value">LISTO <div class="dot-pulse"></div></div>
    </div>
    """, unsafe_allow_html=True)

    # ── Métricas ────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Fuentes RSS", f"{len(FUENTES_RSS)}")
    with c2:
        st.metric("Categorías", f"{len(categorias_seleccionadas_gui)}")
    with c3:
        st.metric("Tipo", tipo_noticias.title())

    # ── Terminal ────────────────────────────────────────
    st.markdown("""
    <div class="term">
        <div class="term-bar">
            <div class="term-dots"><span class="r"></span><span class="y"></span><span class="g"></span></div>
            <div class="term-title">Terminal de Proceso</div>
        </div>
        <div class="term-body">
            <div><span class="tg">[READY]</span> Motor B.N.A.S v5.0 inicializado</div>
            <div><span class="tb">[SYNC]</span> Fuentes RSS configuradas ... OK</div>
            <div><span class="tb">[SYNC]</span> Whitelist de dominios cargada ... OK</div>
            <div class="td">──────────────────────────────────────</div>
            <div><span class="ty">[IDLE]</span> Esperando lanzamiento de búsqueda...</div>
            <div class="td">> heartbeat signal active (3000ms)</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


with col_main:
    # ── Botón de búsqueda principal ─────────────────────
    if st.button("📊  INICIAR BÚSQUEDA Y GENERAR EXCEL", type="primary", use_container_width=True):
        if not categorias_seleccionadas_gui:
            st.warning("⚠️ Debes seleccionar al menos una categoría en la barra lateral.")
        else:
            cats_internas = set()
            for cat_gui in categorias_seleccionadas_gui:
                for c in MAPA_CATEGORIAS.get(cat_gui, [cat_gui.lower()]):
                    cats_internas.add(c)
            cats_internas_list = list(cats_internas)

            with st.spinner("🔍 Motor activo — extrayendo y verificando noticias en tiempo real..."):
                sys_stdout_backup = sys.stdout
                sys.stdout = io.StringIO()
                try:
                    t0 = time.time()
                    resultado = buscar_noticias(
                        categorias_seleccionadas=cats_internas_list,
                        fecha_inicio=fecha_inicio,
                        fecha_fin=fecha_fin,
                        verbose=False,
                        tipo_noticias=tipo_noticias,
                        filtrar_argentina=filtrar_argentina,
                    )
                    dt = time.time() - t0
                    resultado['tiempo_ejecucion'] = dt
                    st.session_state['resultado_busqueda'] = resultado
                finally:
                    sys.stdout = sys_stdout_backup


# ═══════════════════════════════════════════════════════════════
# RESULTADOS
# ═══════════════════════════════════════════════════════════════

if 'resultado_busqueda' in st.session_state:
    resultado = st.session_state['resultado_busqueda']
    noticias = resultado.get("noticias", [])
    dt = resultado.get("tiempo_ejecucion", 0)

    st.markdown("---")

    if not noticias:
        st.error(resultado.get("notificacion", "No se encontraron noticias con esos filtros."))
    else:
        # ── Terminal de éxito ───────────────────────────────
        st.markdown(f"""
        <div class="term">
            <div class="term-bar">
                <div class="term-dots"><span class="r"></span><span class="y"></span><span class="g"></span></div>
                <div class="term-title">Resultado de Búsqueda</div>
            </div>
            <div class="term-body">
                <div><span class="tg">[DONE]</span> Búsqueda completada exitosamente</div>
                <div><span class="tc">[TIME]</span> Tiempo: <span class="ty">{dt:.1f}s</span></div>
                <div><span class="tc">[DATA]</span> Artículos únicos: <span class="tg">{len(noticias)}</span></div>
                <div class="td">──────────────────────────────────────</div>
                <div><span class="tg">[XLSX]</span> Excel generado y listo para descarga</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Botón de descarga ───────────────────────────────
        generador = GeneradorExcelIDEAS(noticias)
        excel_name = f"Noticias_Santamaria_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        output = io.BytesIO()
        generador.generar(output)
        output.seek(0)

        st.download_button(
            label="📥 DESCARGAR RESULTADOS (.XLSX)",
            data=output,
            file_name=excel_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            type="primary"
        )

        # ── Tabla de resultados ─────────────────────────────
        st.markdown(f"""
        <div class="res-header">
            <h3>📊 Previsualización de Resultados</h3>
            <div class="cnt">{len(noticias)} artículos</div>
        </div>
        """, unsafe_allow_html=True)

        tabla_preview = []
        for art in noticias:
            tabla_preview.append({
                "Fecha": art.get("fecha_str", ""),
                "Categoría": art.get("categoria", ""),
                "Fuente": art.get("fuente", ""),
                "Título": art.get("titulo", ""),
                "URL": art.get("url", "")
            })

        st.dataframe(tabla_preview, use_container_width=True, height=400)

        # ── Estadísticas bento ──────────────────────────────
        st.markdown("---")

        col_bento1, col_bento2 = st.columns([2, 1])

        with col_bento1:
            st.markdown("""
            <div class="insight-box">
                <div class="tag">Desglose por Categoría</div>
            </div>
            """, unsafe_allow_html=True)

            cat_count = {}
            for art in noticias:
                c = art["categoria"]
                cat_count[c] = cat_count.get(c, 0) + 1

            num_cats = len(cat_count)
            cols_per_row = min(num_cats, 4) if num_cats > 0 else 1
            metric_cols = st.columns(cols_per_row)
            for idx, (c, count) in enumerate(sorted(cat_count.items(), key=lambda x: -x[1])):
                with metric_cols[idx % cols_per_row]:
                    st.metric(c, count)

        with col_bento2:
            fuentes_activas = sum(1 for _, cnt in resultado.get("conteo_fuentes", {}).items() if cnt > 0)
            fuentes_total = len(resultado.get("conteo_fuentes", {}))
            fuentes_caidas = len(resultado.get("fuentes_fallidas", []))

            st.markdown(f"""
            <div class="accent-box">
                <div style="font-size:2rem;">⚡</div>
                <h4>Resumen de Fuentes</h4>
                <p>{fuentes_activas} fuentes activas de {fuentes_total} consultadas.
                   {'%d fuentes caídas.' % fuentes_caidas if fuentes_caidas else 'Todas respondieron.'}</p>
                <div class="divider">
                    <div class="row">
                        <span>Activas</span>
                        <span>{fuentes_activas} / {fuentes_total}</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if resultado.get("fuentes_fallidas"):
                st.error(f"Fuentes caídas: {', '.join(resultado['fuentes_fallidas'])}")
