import os
import pandas as pd
from datetime import timedelta, timezone
from urllib.parse import urlparse
from core.logger import logger

ZONA_COLOMBIA = timezone(timedelta(hours=-5))
TIMEOUT = 12
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3",
}

# ═══════════════════════════════════════════════════════════════
# FUENTES RSS — MULTI-CATEGORÍA
# ═══════════════════════════════════════════════════════════════
FUENTES_RSS = [
    # ── TENDENCIAS (prioridad alta) ─────────────────────────────
    {"nombre": "Digital Trends Español", "url": "https://es.digitaltrends.com/feed/", "categorias": ["tendencias", "tecnologia"], "tipo": "nacional"},
    {"nombre": "Revista PYM", "url": "https://www.revistapym.com.co/feed", "categorias": ["tendencias", "negocios", "cultura"], "tipo": "nacional"},
    {"nombre": "Cultura Colectiva", "url": "https://news.culturacolectiva.com/feed/", "categorias": ["tendencias", "cultura", "vida"], "tipo": "mundo"},
    {"nombre": "Verne — El País", "url": "https://verne.elpais.com/feed/", "categorias": ["tendencias", "vida", "cultura"], "tipo": "mundo"},
    {"nombre": "Muy Interesante", "url": "https://www.muyinteresante.es/feed", "categorias": ["tendencias", "tecnologia", "salud"], "tipo": "mundo"},
    {"nombre": "Google News — Tendencias", "url": "https://news.google.com/rss/search?q=tendencias+colombia&hl=es-419&gl=CO&ceid=CO:es-419", "categorias": ["tendencias"], "tipo": "nacional"},

    # ── FINANZAS (prioridad alta) ───────────────────────────────
    {"nombre": "La República", "url": "https://www.larepublica.co/rss/", "categorias": ["economia", "negocios", "finanzas"], "tipo": "nacional"},
    {"nombre": "Valora Analitik", "url": "https://www.valoraanalitik.com/feed/", "categorias": ["economia", "finanzas", "negocios"], "tipo": "nacional"},
    {"nombre": "Forbes Colombia", "url": "https://forbes.co/seccion/economia-y-finanzas/", "categorias": ["economia", "finanzas", "negocios"], "tipo": "nacional"},
    {"nombre": "La Nota Económica", "url": "https://lanotaeconomica.com.co/feed/", "categorias": ["economia", "negocios", "mis finanzas", "finanzas"], "tipo": "nacional"},
    {"nombre": "Mis Finanzas Personales", "url": "https://misfinanzaspersonales.co/feed/", "categorias": ["finanzas", "mis finanzas", "economia"], "tipo": "nacional"},
    {"nombre": "Bloomberg Línea", "url": "https://www.bloomberglinea.com/feed/", "categorias": ["finanzas", "economia", "negocios", "mundo"], "tipo": "mundo"},
    {"nombre": "Google News — Finanzas CO", "url": "https://news.google.com/rss/search?q=finanzas+personales+colombia&hl=es-419&gl=CO&ceid=CO:es-419", "categorias": ["finanzas", "mis finanzas"], "tipo": "nacional"},

    # ── ECONOMÍA ────────────────────────────────────────────────
    {"nombre": "El Colombiano — Negocios", "url": "https://www.elcolombiano.com/rss/negocios.xml", "categorias": ["economia", "negocios"], "tipo": "nacional"},
    {"nombre": "Agronegocios", "url": "https://www.agronegocios.co/rss/", "categorias": ["economia", "negocios"], "tipo": "nacional"},
    {"nombre": "FMI — Artículos", "url": "https://www.imf.org/es/news/rss", "categorias": ["economia", "mundo", "finanzas"], "tipo": "mundo"},
    {"nombre": "Banco Mundial — LAC", "url": "https://feeds.worldbank.org/world-bank/rss/press-releases/es", "categorias": ["economia", "mundo"], "tipo": "mundo"},
    {"nombre": "BID — Mejorando Vidas", "url": "https://blogs.iadb.org/feed/", "categorias": ["economia", "mundo"], "tipo": "mundo"},
    {"nombre": "Google News — Economía", "url": "https://news.google.com/rss/search?q=economia+colombia&hl=es-419&gl=CO&ceid=CO:es-419", "categorias": ["economia"], "tipo": "nacional"},

    # ── GENERAL / COLOMBIA ──────────────────────────────────────
    {"nombre": "El Heraldo", "url": "https://www.elheraldo.co/arc/outboundfeeds/rss/", "categorias": ["general", "barranquilla", "politica", "deportes", "economia", "cultura", "salud", "tecnologia", "mundo"], "tipo": "nacional"},
    {"nombre": "El Colombiano — Medellín", "url": "https://www.elcolombiano.com/rss/medellin.xml", "categorias": ["general", "medellin"], "tipo": "nacional"},
    {"nombre": "El Colombiano — Colombia", "url": "https://www.elcolombiano.com/rss/colombia.xml", "categorias": ["general", "politica", "colombia"], "tipo": "nacional"},
    {"nombre": "Semana", "url": "https://www.semana.com/arc/outboundfeeds/rss/?outputType=xml", "categorias": ["general", "politica", "economia", "cultura", "deportes", "tecnologia", "salud", "mundo", "vida", "tendencias"], "tipo": "nacional"},
    {"nombre": "Infobae Colombia", "url": "https://www.infobae.com/arc/outboundfeeds/rss/category/colombia/", "categorias": ["general", "colombia", "politica", "economia", "tecnologia"], "tipo": "nacional"},
    {"nombre": "Google News — Colombia", "url": "https://news.google.com/rss/search?q=colombia&hl=es-419&gl=CO&ceid=CO:es-419", "categorias": ["general", "colombia"], "tipo": "nacional"},

    # ── MUNDO ───────────────────────────────────────────────────
    {"nombre": "BBC Mundo", "url": "https://feeds.bbci.co.uk/mundo/rss.xml", "categorias": ["general", "mundo", "politica", "cultura", "tecnologia", "deportes", "salud", "vida"], "tipo": "mundo"},
    {"nombre": "CNN Español", "url": "https://cnnespanol.cnn.com/feed/", "categorias": ["general", "mundo", "politica", "tecnologia", "deportes", "salud", "vida"], "tipo": "mundo"},
    {"nombre": "El País América", "url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada", "categorias": ["general", "mundo", "politica", "cultura"], "tipo": "mundo"},
    {"nombre": "DW Español", "url": "https://rss.dw.com/xml/rss-sp-all", "categorias": ["mundo", "politica", "economia"], "tipo": "mundo"},
    {"nombre": "France 24 Español", "url": "https://www.france24.com/es/rss", "categorias": ["mundo", "politica"], "tipo": "mundo"},
]

DOMINIOS_ARGENTINA = [
    "clarin.com", "lanacion.com.ar", "perfil.com",
    "lavoz.com.ar", "ole.com.ar", "mdzol.com",
    "la100.cienradios.com", "elle.clarin.com",
]

DOMINIOS_BLOQUEADOS = [
    "portafolio.co", "eltiempo.com",
    "blogs.portafolio.co", "amp.portafolio.co", "m.portafolio.co",
    "amp.eltiempo.com", "m.eltiempo.com", "especiales.eltiempo.com",
    "enter.co", "citytv.com.co", "cronista.com",
]

MEDIOS_PROHIBIDOS = {
    "el_tiempo": {
        "dominios": ["eltiempo.com", "m.eltiempo.com", "amp.eltiempo.com"],
        "signatures": ["casa editorial el tiempo", "el tiempo play"],
    },
    "portafolio": {
        "dominios": ["portafolio.co", "blogs.portafolio.co"],
        "signatures": ["portafolio digital", "suscribete a portafolio"],
    }
}

CATEGORIAS_RELACIONADAS = {
    "tendencias": {"tendencias", "vida", "cultura", "tecnologia"},
    "vida": {"vida", "salud", "cultura", "tendencias"},
    "salud": {"salud", "vida", "tendencias"},
    "negocios": {"negocios", "economia", "finanzas", "mis finanzas"},
    "finanzas": {"finanzas", "mis finanzas", "economia", "negocios"},
    "mis finanzas": {"mis finanzas", "finanzas", "economia"},
    "tecnologia": {"tecnologia", "tendencias"},
    "economia": {"economia", "finanzas", "negocios", "mis finanzas"},
}

MARCADORES_COLOMBIA = ("colombia", "colombiano", "bogota", "medellin", "cali", "barranquilla", "dian", "minsalud")
MARCADORES_EXTRANJERO = ("estados unidos", "ee uu", "mexico", "argentina", "españa", "china")

PALABRAS_RUIDO_GENERAL = ("partido", "liga", "vs ", "previa", "marcador", "gol", "penal", "captur", "asesin")

def _normalize_domain(url):
    try:
        domain = urlparse(url).netloc.lower()
    except Exception:
        return ""
    for prefix in ("www.", "m.", "amp."):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    return domain

def cargar_dominios_permitidos():
    dominios = set()
    dir_actual = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    excel_path = os.path.join(dir_actual, 'Fuentes_SEO.xlsx')
    
    try:
        if os.path.exists(excel_path):
            dfs = pd.read_excel(excel_path, sheet_name=None, header=None)
            for sheet, df in dfs.items():
                for r in range(df.shape[0]):
                    for c in range(df.shape[1]):
                        val = str(df.iloc[r, c]).strip()
                        if "http" in val:
                            for part in val.split():
                                if "http" in part:
                                    try:
                                        dominios.add(_normalize_domain(part))
                                    except: pass
    except Exception as e:
        logger.warning(f"No se pudo cargar Fuentes_SEO.xlsx: {e}")

    # Fallback
    if len(dominios) < 10:
        for f in FUENTES_RSS:
            try:
                nl = _normalize_domain(f["url"])
                if "news.google" not in nl:
                    dominios.add(nl)
            except: pass

    if "news.google.com" in dominios:
        dominios.remove("news.google.com")
        
    return dominios

DOMINIOS_PERMITIDOS = cargar_dominios_permitidos()
