import streamlit as st
import datetime
import os
import io
import time
import sys

# Configuramos la página de Streamlit
st.set_page_config(
    page_title="Buscador IDEAS",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Footer default oculto desde configuración de Streamlit. No ocultamos header para no tapar botón del sidebar.

# Importar el motor principal
try:
    from buscador_noticias import buscar_noticias, GeneradorExcelIDEAS, CATEGORIAS_GUI, MAPA_CATEGORIAS
except ImportError:
    st.error("No se encuentra el motor `buscador_noticias.py`. Asegúrate de que esté en el mismo directorio.")
    st.stop()


# ── INTERFAZ STREAMLIT ──────────────────────────────────────────

st.title("Buscador de Noticias en Tiempo Real — IDEAS")
st.markdown("""
<div style='background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 25px;'>
    <b>✓ Fechas 100% reales</b> (Nunca <code>datetime.now()</code> como fallback)<br>
    <b>✓ Artículos sin fecha exacta son descartados automáticamente</b><br>
    <b>✓ Filtro integrado de dominios corporativos</b>
</div>
""", unsafe_allow_html=True)


# -- Barra Lateral --
with st.sidebar:
    st.header("1. Categorías")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Marcar Todas"):
            for cat in CATEGORIAS_GUI:
                st.session_state[f"cat_{cat}"] = True
            st.rerun()
    with col2:
        if st.button("Limpiar Todas"):
            for cat in CATEGORIAS_GUI:
                st.session_state[f"cat_{cat}"] = False
            st.rerun()

    # Checkboxes de categorías
    st.markdown("---")
    categorias_seleccionadas_gui = []
    
    for cat in CATEGORIAS_GUI:
        # Inicializar estado si no existe
        if f"cat_{cat}" not in st.session_state:
            st.session_state[f"cat_{cat}"] = True
            
        is_checked = st.checkbox(cat, key=f"cat_{cat}")
        if is_checked:
            categorias_seleccionadas_gui.append(cat)
            
    st.markdown("---")
    st.header("2. Filtros Adicionales")
    
    # Checkbox para usar fecha o no (Streamlit date_input no permite valores None vacío fácilmente)
    usar_fecha = st.checkbox("Filtrar por fecha exacta", value=True)
    if usar_fecha:
        fecha_filtro = st.date_input("Selecciona la fecha", datetime.date.today())
    else:
        fecha_filtro = None
        st.info("Buscando todas las noticias más recientes sin importar la fecha exacta.")


# -- Cuerpo Principal --

if st.button("▶ INICIAR BÚSQUEDA Y GENERAR EXCEL", type="primary", use_container_width=True):
    if not categorias_seleccionadas_gui:
        st.warning("⚠️ Debes seleccionar al menos una categoría.")
    else:
        # Mapear GUI a internas
        cats_internas = set()
        for cat_gui in categorias_seleccionadas_gui:
            for c in MAPA_CATEGORIAS.get(cat_gui, [cat_gui.lower()]):
                cats_internas.add(c)
                
        cats_internas_list = list(cats_internas)
        
        st.markdown("---")
        
        with st.spinner("🔍 Buscando y verificando noticias en tiempo real... (esto puede tardar unos segundos)"):
            sys_stdout_backup = sys.stdout
            sys.stdout = io.StringIO()
            try:
                t0 = time.time()
                resultado = buscar_noticias(
                    categorias_seleccionadas=cats_internas_list,
                    fecha_filtro=fecha_filtro,
                    verbose=False
                )
                dt = time.time() - t0
                resultado['tiempo_ejecucion'] = dt
                st.session_state['resultado_busqueda'] = resultado
            finally:
                sys.stdout = sys_stdout_backup

# -- Resultados Fuera del Botón --
if 'resultado_busqueda' in st.session_state:
    resultado = st.session_state['resultado_busqueda']
    noticias = resultado.get("noticias", [])
    dt = resultado.get("tiempo_ejecucion", 0)
    
    st.markdown("---")
    
    if not noticias:
        st.error(resultado.get("notificacion", "No se encontraron noticias con esos filtros."))
    else:
        st.success(f"✅ Búsqueda terminada en {dt:.1f} segundos. Se encontraron **{len(noticias)}** artículos únicos.")
        
        # Generar Excel en Memoria
        generador = GeneradorExcelIDEAS(noticias)
        excel_name = f"Noticias_IDEAS_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
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
        
        st.markdown("---")
        
        st.subheader("📊 Previsualización de Resultados")
        
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
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Noticias por Categoría:**")
            cat_count = {}
            for art in noticias:
                c = art["categoria"]
                cat_count[c] = cat_count.get(c, 0) + 1
            for c, count in sorted(cat_count.items(), key=lambda x: -x[1]):
                st.write(f"- {c}: {count}")
        with col2:
            st.markdown("**Fuentes Exitosas:**")
            for f, count in sorted(resultado.get("conteo_fuentes", {}).items(), key=lambda x: -x[1]):
                if count > 0:
                    st.write(f"- {f}: {count}")
            
            if resultado.get("fuentes_fallidas"):
                st.error(f"Fuentes caídas o lentas: {', '.join(resultado['fuentes_fallidas'])}")
