# GUI libs son opcionales (no existen en Streamlit Cloud / Linux)
try:
    import customtkinter as ctk
    import tkinter as tk
    GUI_AVAILABLE = True
except (ImportError, OSError):
    ctk = None
    tk = None
    GUI_AVAILABLE = False
import threading
from queue import Queue
import html
import os
import json
import subprocess
import re
import unicodedata
import hashlib
import urllib.parse
from core.config import *
from core.config import _normalize_domain
from difflib import SequenceMatcher
import sys
from core.logger import logger as log

# ═══════════════════════════════════════════════════════════════
# CONSTANTES DE DATOS Y RUTAS
# ═══════════════════════════════════════════════════════════════
BASE_APP_DIR = os.path.dirname(os.path.abspath(
    sys.executable if getattr(sys, "frozen", False) else
    os.path.dirname(__file__)
))

def _resolver_directorio_datos():
    env_dir = os.environ.get("BUSCADOR_NOTICIAS_DATA_DIR")
    if env_dir:
        d = os.path.abspath(env_dir)
        os.makedirs(d, exist_ok=True)
        return d
    # En modo frozen, buscar carpeta data/ junto al .exe
    if getattr(sys, "frozen", False):
        d = os.path.join(BASE_APP_DIR, "data")
        os.makedirs(d, exist_ok=True)
        return d
    # En modo script, junto al proyecto
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(d, exist_ok=True)
    return d

DATA_APP_DIR = _resolver_directorio_datos()

HISTORIAL_ARTICULOS_PATH = os.path.join(DATA_APP_DIR, "historial_articulos.json")
HISTORIAL_MEDIOS_PROHIBIDOS_PATH = os.path.join(DATA_APP_DIR, "historial_medios_prohibidos.json")
MAX_HISTORIAL_ARTICULOS = 4000
MAX_HISTORIAL_MEDIOS_PROHIBIDOS = 12000

def _expandir_categorias_solicitadas(categorias):
    if not categorias:
        return set()
    expandidas = set(categorias)
    for cat in list(expandidas):
        expandidas.update(CATEGORIAS_RELACIONADAS.get(cat, set()))
    return expandidas


def _resolver_categoria_solicitada(categorias_fuente, categorias_solicitadas):
    if not categorias_solicitadas:
        return None
    fuente_set = set(categorias_fuente or [])
    for cat in categorias_solicitadas:
        if cat in fuente_set:
            return cat
        relacionadas = CATEGORIAS_RELACIONADAS.get(cat, set())
        if relacionadas and fuente_set.intersection(relacionadas):
            return cat
    return None


PALABRAS_TENDENCIA_VALIDAS = (
    "tendencia", "tendencias", "viral", "virales", "redes", "sociales",
    "entretenimiento", "famosos", "streaming", "moda", "belleza",
    "lifestyle", "hogar", "bienestar", "apps", "tecnologia",
)

PALABRAS_TENDENCIA_EXCLUIDAS = (
    "dolar", "euro", "trm", "cotizacion", "apertura", "inflacion", "tasas",
    "petro", "elecciones", "votacion", "congreso", "judicial", "captur",
    "asesin", "accidente", "balacera", "partido", "liga", "vs ",
    "previa", "marcador", "gol", "clima", "temperaturas",
)

PALABRAS_RUIDO_GENERAL = (
    "partido", "liga", "vs ", "previa", "marcador", "gol", "penal",
    "captur", "captura", "asesin", "balacera", "fiscalia", "juez",
    "tribunal", "accidente", "choque", "hurto",
)

CATEGORIA_REGLAS = {
    "salud": {
        "include": ("salud", "medico", "medica", "medicina", "hospital", "clinica", "vacuna", "tratamiento", "sintomas",
                    "bienestar", "nutricion", "ejercicio", "salud mental", "psicologia", "cancer", "diabetes",
                    "obesidad", "paciente", "pacientes", "sindrome", "enfermedad", "enfermedades", "virus", "epidemia"),
        "exclude": PALABRAS_RUIDO_GENERAL + ("dolar", "euro", "gasolina", "supermercados"),
    },
    "vida": {
        "include": ("vida", "hogar", "familia", "pareja", "viaje", "viajes", "vacaciones", "mascota", "mascotas",
                    "cocina", "receta", "descanso", "hotel", "estilo de vida", "habitos", "bienestar", "convivencia"),
        "exclude": PALABRAS_RUIDO_GENERAL + ("dolar", "euro", "inflacion", "elecciones"),
    },
    "tendencias": {
        "include": ("tendencia", "tendencias", "viral", "virales", "redes", "streaming", "famos", "moda",
                    "belleza", "lifestyle", "hogar", "consumo", "tecnologia", "app", "apps", "entretenimiento"),
        "exclude": PALABRAS_TENDENCIA_EXCLUIDAS,
    },
    "negocios": {
        "include": ("empresa", "empresas", "negocio", "negocios", "mercado", "industria", "comercio", "startup",
                    "startups", "emprendimiento", "inversion", "alianza", "ventas", "consumo", "supermercados",
                    "clientes", "empresarial"),
        "exclude": PALABRAS_RUIDO_GENERAL,
    },
    "finanzas": {
        "include": ("finanzas", "banco", "banca", "credito", "deuda", "ahorro", "inversion", "bolsa",
                    "dolar", "euro", "inflacion", "tasa", "tasas", "trm", "divisa", "cotizacion",
                    "mercado", "hacienda", "tributaria", "tributario"),
        "exclude": PALABRAS_RUIDO_GENERAL,
    },
    "mis finanzas": {
        "include": ("finanzas personales", "ahorro", "ahorrar", "tarjeta", "credito", "subsidio", "dian", "impuesto",
                    "renta", "pension", "cesant", "presupuesto", "factura", "devolucion", "iva", "bolsillo", "pagar"),
        "exclude": PALABRAS_RUIDO_GENERAL,
    },
    "tecnologia": {
        "include": ("tecnologia", "ia", "inteligencia artificial", "app", "apps", "celular", "iphone", "android",
                    "samsung", "internet", "starlink", "robotica", "software", "digital", "startup", "ciberseguridad", "datos"),
        "exclude": PALABRAS_RUIDO_GENERAL,
    },
    "cultura": {
        "include": ("cultura", "cine", "musica", "libro", "libros", "teatro", "arte", "artista", "festival",
                    "museo", "concierto", "pelicula", "peliculas", "serie", "series", "literatura", "danza", "netflix"),
        "exclude": PALABRAS_RUIDO_GENERAL + ("dolar", "inflacion", "gasolina"),
    },
}


def _texto_categoria_norm(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    return _normalizar_texto_medio(texto)


def _contar_patrones_texto(texto, patrones):
    return sum(1 for patron in patrones if _texto_contiene_patron(texto, patron))


def _articulo_es_nacional_colombia(articulo, fuente):
    texto = _texto_categoria_norm(
        f"{articulo.get('titulo', '')} {articulo.get('resumen', '')} "
        f"{articulo.get('url', '')} {articulo.get('fuente', '')}"
    )
    if not texto:
        return False

    score_colombia_texto = _contar_patrones_texto(texto, MARCADORES_COLOMBIA)
    score_extranjero = _contar_patrones_texto(texto, MARCADORES_EXTRANJERO)

    if score_colombia_texto == 0:
        return False

    score_colombia = score_colombia_texto

    categorias_fuente = set(fuente.get("categorias", []))
    if categorias_fuente.intersection(MARCADORES_FUENTE_LOCAL):
        score_colombia += 1

    fuente_norm = _texto_categoria_norm(fuente.get("nombre", ""))
    if any(_texto_contiene_patron(fuente_norm, marcador) for marcador in MARCADORES_FUENTE_LOCAL):
        score_colombia += 1

    if score_extranjero >= 2 and score_colombia <= 1:
        return False
    if score_extranjero > score_colombia + 1:
        return False
    return True


def _parece_ingles_filtro_mundo(titulo, descripcion):
    texto = _normalizar_para_repeticion(f"{titulo} {descripcion}")
    if len(texto) < 35:
        return False

    tokens = set(texto.split())
    english_tokens = {
        "the", "and", "with", "from", "after", "about", "officials",
        "warn", "warns", "warning", "latest", "report", "reports",
        "market", "markets", "global", "health", "social", "mental",
        "risk", "risks", "said", "says", "outlook", "government",
        "economy", "economic", "official", "officially", "city",
    }
    spanish_tokens = {
        "el", "la", "los", "las", "de", "del", "y", "para", "con",
        "por", "una", "uno", "unos", "unas", "salud", "riesgos",
        "bogota", "colombia", "alcaldia", "gobierno", "mental",
    }
    hits_en = len(tokens.intersection(english_tokens))
    hits_es = len(tokens.intersection(spanish_tokens))
    return hits_en >= 3 and hits_es <= 1


def _articulo_cumple_filtro_mundo(articulo):
    return not (
        _parece_ingles_puro(
            articulo.get("titulo", ""),
            articulo.get("resumen", ""),
        ) or _parece_ingles_filtro_mundo(
            articulo.get("titulo", ""),
            articulo.get("resumen", ""),
        )
    )


def _texto_contiene_patron(texto, patron):
    patron = _texto_categoria_norm(patron)
    if not patron:
        return False
    if " " in patron:
        return patron in texto
    return re.search(r"\b" + re.escape(patron) + r"\b", texto) is not None


def _articulo_coincide_categoria(categoria, titulo="", resumen="", fuente="", categorias_fuente=None):
    categorias_fuente = set(categorias_fuente or [])
    texto = _texto_categoria_norm(f"{titulo} {resumen} {fuente}")
    if not texto:
        return False

    regla = CATEGORIA_REGLAS.get(categoria)
    if not regla:
        return categoria in categorias_fuente

    include = regla.get("include", ())
    exclude = regla.get("exclude", ())
    include_hits = sum(1 for palabra in include if _texto_contiene_patron(texto, palabra))
    exclude_hits = sum(1 for palabra in exclude if _texto_contiene_patron(texto, palabra))

    if categoria in categorias_fuente and include_hits >= 1 and exclude_hits == 0:
        return True

    if include_hits >= 2 and exclude_hits == 0:
        return True

    if include_hits >= 1 and categoria in categorias_fuente and exclude_hits <= 1:
        return True

    return False


def _es_tendencia_valida(titulo="", resumen="", fuente=""):
    texto = unicodedata.normalize("NFKD", f"{titulo} {resumen} {fuente}").encode("ascii", "ignore").decode("ascii")
    texto = _normalizar_texto_medio(texto)
    if not texto:
        return False
    if any(p in texto for p in PALABRAS_TENDENCIA_EXCLUIDAS):
        return False
    if any(p in texto for p in PALABRAS_TENDENCIA_VALIDAS):
        return True
    fuente_norm = unicodedata.normalize("NFKD", fuente).encode("ascii", "ignore").decode("ascii")
    return "tendencias" in _normalizar_texto_medio(fuente_norm)

def _extraer_palabras_clave(texto):
    if not texto: return set()
    cifras = set(re.findall(r'\b\d+(?:[\.,]\d+)?\b', texto))
    palabras = set(re.findall(r'\b[a-záéíóúñ]{7,}\b', texto.lower()))
    comunes = {"colombia", "nacional", "gobierno", "general", "informes", "durante", "noticias", "presenta", "también", "nuestro", "después", "algunos"}
    return cifras.union(palabras - comunes)

def _normalizar_texto_medio(texto):
    if not texto:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()


def _extraer_tokens_relevantes(texto):
    if not texto:
        return set()
    tokens = set(re.findall(r"\b[a-zÃ¡Ã©Ã­Ã³ÃºÃ±]{5,}\b", texto.lower()))
    stop = {
        "colombia", "noticias", "general", "mundo", "ultima", "ultimas",
        "sobre", "desde", "hasta", "entre", "contra", "porque", "donde",
        "cuando", "todos", "todas", "tras", "segun", "nuevo", "nueva",
        "este", "esta", "estos", "estas",
    }
    return tokens - stop


def _normalizar_para_repeticion(texto):
    texto = _limpiar_html(texto or "")
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    texto = texto.lower()
    texto = re.sub(r"https?://\S+", " ", texto)
    texto = re.sub(r"[^a-z0-9\s]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def _raiz_simple_token(token):
    token = (token or "").strip().lower()
    sufijos = (
        "amientos", "imiento", "imientos", "aciones", "adoras", "adores",
        "adoras", "adora", "adores", "antes", "ancia", "encias", "encia",
        "idades", "idad", "mente", "ciones", "cion", "siones", "sion",
        "arios", "arias", "ario", "aria", "logias", "logia", "ismos",
        "istas", "ismos", "istas", "ables", "ible", "ibles", "ables",
        "anzas", "anza", "icos", "icas", "ico", "ica", "ales", "ados",
        "adas", "idos", "idas", "ando", "iendo", "oras", "ores", "osa",
        "oso", "ivas", "ivos", "iva", "ivo", "es", "s",
    )
    for sufijo in sufijos:
        if len(token) - len(sufijo) >= 5 and token.endswith(sufijo):
            return token[:-len(sufijo)]
    return token


def _extraer_tokens_repeticion(texto):
    texto = _normalizar_para_repeticion(texto)
    tokens = {
        _raiz_simple_token(token)
        for token in re.findall(r"\b[a-z0-9]{5,}\b", texto)
    }
    stop = {
        "colombia", "noticias", "general", "ultima", "ultimas", "mundo",
        "fuente", "video", "fotos", "tras", "sobre", "desde", "hasta",
        "entre", "porque", "nuevo", "nueva", "este", "esta", "estos",
        "estas", "hoy", "ayer",
    }
    stop_raices = {_raiz_simple_token(token) for token in stop}
    return {token for token in tokens if token and token not in stop_raices}


def _tokens_repeticion_desde_url(url):
    if not url:
        return []
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return []
    slug = urllib.parse.unquote(parsed.path or "")
    slug = slug.replace("-", " ").replace("_", " ").replace("/", " ")
    slug = _normalizar_para_repeticion(slug)
    tokens = []
    for token in slug.split():
        if len(token) < 5 or token.isdigit():
            continue
        raiz = _raiz_simple_token(token)
        if raiz:
            tokens.append(raiz)
    return tokens


def _extraer_frases_repeticion(titulo, url=""):
    texto = _normalizar_para_repeticion(titulo)
    tokens_titulo = [_raiz_simple_token(t) for t in texto.split() if len(t) >= 4 and not t.isdigit()]
    tokens_slug = _tokens_repeticion_desde_url(url)
    stop = {
        "colombia", "santander", "bogota", "medellin", "cartagena", "semana",
        "santa", "tiempo", "portafolio", "citytv", "visit", "visitant",
        "articul", "notici", "colomb", "ubic", "hor", "debe", "saber",
        "recorr", "miles", "mismo", "mism", "larg", "largo",
    }

    frases = []
    for fuente_tokens in (tokens_titulo, tokens_slug):
        n_tokens = len(fuente_tokens)
        for size in (5, 4, 3):
            if n_tokens < size:
                continue
            for i in range(0, n_tokens - size + 1):
                ventana = fuente_tokens[i:i + size]
                if sum(1 for t in ventana if t and t not in stop) < max(2, size - 1):
                    continue
                frase = " ".join(ventana).strip()
                if len(frase) >= 18:
                    frases.append(frase)
    frases = sorted(set(frases), key=lambda x: (-len(x), x))
    return frases[:10]


def _seleccionar_claves_repeticion(titulo, resumen_limpio, url, tokens_repeticion):
    titulo_tokens = set(_extraer_tokens_repeticion(titulo))
    slug_tokens = set(_tokens_repeticion_desde_url(url))
    resumen_tokens = set(_extraer_tokens_repeticion(resumen_limpio))
    tokens_base = set(tokens_repeticion or set())

    score = {}
    for token in tokens_base:
        valor = len(token)
        if token in titulo_tokens:
            valor += 5
        if token in slug_tokens:
            valor += 4
        if token in resumen_tokens:
            valor += 2
        if token in MARCADORES_COLOMBIA or token in MARCADORES_EXTRANJERO:
            valor -= 2
        score[token] = valor

    claves = sorted(tokens_base, key=lambda t: (-score.get(t, 0), -len(t), t))
    return claves[:12]


def _construir_huella_repeticion(titulo, resumen, url=""):
    resumen_limpio = _limpiar_html(resumen) or titulo or ""
    titulo_norm = _normalizar_para_repeticion(titulo)[:180]
    resumen_norm = _normalizar_para_repeticion(resumen_limpio)[:420]
    slug_tokens = _tokens_repeticion_desde_url(url)
    slug_norm = " ".join(slug_tokens)[:180]
    texto_repeticion = f"{titulo_norm} {resumen_norm} {slug_norm}".strip()
    tokens_repeticion = _extraer_tokens_repeticion(f"{titulo} {resumen_limpio} {slug_norm}")
    claves_repeticion = _seleccionar_claves_repeticion(titulo, resumen_limpio, url, tokens_repeticion)
    firma_tokens_repeticion = " ".join(sorted(tokens_repeticion))[:420]
    firma_claves_repeticion = " ".join(claves_repeticion)[:240]
    frases_repeticion = _extraer_frases_repeticion(titulo, url)
    anclas = sorted(tokens_repeticion, key=lambda t: (-len(t), t))[:6]
    hash_repeticion = hashlib.sha1(texto_repeticion.encode("utf-8", errors="ignore")).hexdigest()
    return {
        "resumen_limpio": resumen_limpio,
        "texto_repeticion": texto_repeticion,
        "tokens_repeticion": tokens_repeticion,
        "claves_repeticion": claves_repeticion,
        "slug_repeticion": slug_norm,
        "firma_tokens_repeticion": firma_tokens_repeticion,
        "firma_claves_repeticion": firma_claves_repeticion,
        "frases_repeticion": frases_repeticion,
        "anclas_repeticion": anclas,
        "hash_repeticion": hash_repeticion,
    }


def _registro_historial_desde_articulo(articulo):
    return {
        "titulo": articulo.get("titulo", ""),
        "fuente": articulo.get("fuente", ""),
        "url": articulo.get("url", ""),
        "fecha": articulo.get("fecha_str", ""),
        "t_norm": articulo.get("t_norm", ""),
        "texto_repeticion": articulo.get("texto_repeticion", ""),
        "hash_repeticion": articulo.get("hash_repeticion", ""),
        "tokens_repeticion": sorted(articulo.get("tokens_repeticion", set())),
        "claves_repeticion": list(articulo.get("claves_repeticion", [])),
        "slug_repeticion": articulo.get("slug_repeticion", ""),
        "firma_tokens_repeticion": articulo.get("firma_tokens_repeticion", ""),
        "firma_claves_repeticion": articulo.get("firma_claves_repeticion", ""),
        "frases_repeticion": list(articulo.get("frases_repeticion", [])),
        "anclas_repeticion": list(articulo.get("anclas_repeticion", [])),
    }


def _cargar_historial_articulos():
    if not os.path.exists(HISTORIAL_ARTICULOS_PATH):
        return []
    try:
        with open(HISTORIAL_ARTICULOS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            return []
        historial = []
        for item in data:
            if not isinstance(item, dict) or not item.get("hash_repeticion"):
                continue
            item["tokens_repeticion"] = set(item.get("tokens_repeticion", []))
            item["claves_repeticion"] = list(item.get("claves_repeticion", []))
            item["frases_repeticion"] = list(item.get("frases_repeticion", []))
            item["anclas_repeticion"] = list(item.get("anclas_repeticion", []))
            historial.append(item)
        return historial
    except Exception:
        return []


def _cargar_historial_medios_prohibidos():
    if not os.path.exists(HISTORIAL_MEDIOS_PROHIBIDOS_PATH):
        return []
    try:
        with open(HISTORIAL_MEDIOS_PROHIBIDOS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            return []
        historial = []
        for item in data:
            if not isinstance(item, dict) or not item.get("hash_repeticion"):
                continue
            item["tokens_repeticion"] = set(item.get("tokens_repeticion", []))
            item["claves_repeticion"] = list(item.get("claves_repeticion", []))
            item["frases_repeticion"] = list(item.get("frases_repeticion", []))
            item["anclas_repeticion"] = list(item.get("anclas_repeticion", []))
            historial.append(item)
        return historial
    except Exception:
        return []


def _guardar_historial_articulos(historial):
    try:
        serializable = []
        for item in historial[-MAX_HISTORIAL_ARTICULOS:]:
            row = dict(item)
            row["tokens_repeticion"] = sorted(row.get("tokens_repeticion", set()))
            row["claves_repeticion"] = list(row.get("claves_repeticion", []))
            row["frases_repeticion"] = list(row.get("frases_repeticion", []))
            row["anclas_repeticion"] = list(row.get("anclas_repeticion", []))
            serializable.append(row)
        with open(HISTORIAL_ARTICULOS_PATH, "w", encoding="utf-8") as fh:
            json.dump(serializable, fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        log.warning(f"No se pudo guardar historial de articulos: {exc}")


def _guardar_historial_medios_prohibidos(historial):
    try:
        serializable = []
        for item in historial[-MAX_HISTORIAL_MEDIOS_PROHIBIDOS:]:
            row = dict(item)
            row["tokens_repeticion"] = sorted(row.get("tokens_repeticion", set()))
            row["claves_repeticion"] = list(row.get("claves_repeticion", []))
            row["frases_repeticion"] = list(row.get("frases_repeticion", []))
            row["anclas_repeticion"] = list(row.get("anclas_repeticion", []))
            serializable.append(row)
        with open(HISTORIAL_MEDIOS_PROHIBIDOS_PATH, "w", encoding="utf-8") as fh:
            json.dump(serializable, fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        log.warning(f"No se pudo guardar historial de medios prohibidos: {exc}")


def _agregar_articulo_a_indice(articulo, hashes, por_ancla):
    hash_rep = articulo.get("hash_repeticion", "")
    if hash_rep:
        hashes.add(hash_rep)
    for clave in articulo.get("claves_repeticion", [])[:10]:
        if clave and len(clave) >= 5:
            por_ancla.setdefault(f"clave::{clave}", []).append(articulo)
    for ancla in articulo.get("anclas_repeticion", []):
        por_ancla.setdefault(ancla, []).append(articulo)
    for frase in articulo.get("frases_repeticion", [])[:6]:
        if len(frase) >= 18:
            por_ancla.setdefault(frase, []).append(articulo)


def _indexar_articulos_repeticion(articulos):
    hashes = set()
    por_ancla = {}
    for item in articulos:
        _agregar_articulo_a_indice(item, hashes, por_ancla)
    return hashes, por_ancla


def _indexar_historial_articulos(historial):
    return _indexar_articulos_repeticion(historial)


def _obtener_candidatos_repeticion(articulo, por_ancla, max_candidatos=80):
    candidatos = {}
    claves_busqueda = list(articulo.get("anclas_repeticion", []))
    claves_busqueda.extend(
        f"clave::{clave}"
        for clave in articulo.get("claves_repeticion", [])[:10]
        if clave and len(clave) >= 5
    )
    claves_busqueda.extend(frase for frase in articulo.get("frases_repeticion", [])[:6] if len(frase) >= 18)
    for ancla in claves_busqueda:
        for item in por_ancla.get(ancla, []):
            clave = item.get("hash_repeticion", f"id-{id(item)}")
            candidatos[clave] = item
            if len(candidatos) >= max_candidatos:
                return list(candidatos.values())
    return list(candidatos.values())


def _metricas_similitud_articulos(articulo, referencia):
    art_t_norm = articulo.get("t_norm", "")
    ref_t_norm = referencia.get("t_norm", "")
    titulo_ratio = 0.0
    if art_t_norm and ref_t_norm and abs(len(art_t_norm) - len(ref_t_norm)) <= 60:
        titulo_ratio = SequenceMatcher(None, art_t_norm, ref_t_norm).ratio()

    art_texto = articulo.get("texto_repeticion", "")
    ref_texto = referencia.get("texto_repeticion", "")
    texto_ratio = 0.0
    if art_texto and ref_texto:
        texto_ratio = SequenceMatcher(None, art_texto[:720], ref_texto[:720]).ratio()

    art_firma = articulo.get("firma_tokens_repeticion", "")
    ref_firma = referencia.get("firma_tokens_repeticion", "")
    firma_ratio = 0.0
    if art_firma and ref_firma:
        firma_ratio = SequenceMatcher(None, art_firma, ref_firma).ratio()

    art_firma_claves = articulo.get("firma_claves_repeticion", "")
    ref_firma_claves = referencia.get("firma_claves_repeticion", "")
    firma_claves_ratio = 0.0
    if art_firma_claves and ref_firma_claves:
        firma_claves_ratio = SequenceMatcher(None, art_firma_claves, ref_firma_claves).ratio()

    art_tokens = set(articulo.get("tokens_repeticion", set())) or set(articulo.get("tokens_relevantes", set()))
    ref_tokens = set(referencia.get("tokens_repeticion", set())) or set(referencia.get("tokens_relevantes", set()))
    inter = art_tokens.intersection(ref_tokens)
    union = art_tokens.union(ref_tokens)
    jaccard = (len(inter) / len(union)) if union else 0.0

    art_claves = set(articulo.get("claves_repeticion", []))
    ref_claves = set(referencia.get("claves_repeticion", []))
    claves_inter = art_claves.intersection(ref_claves)
    claves_union = art_claves.union(ref_claves)
    claves_jaccard = (len(claves_inter) / len(claves_union)) if claves_union else 0.0

    art_frases = {
        frase for frase in articulo.get("frases_repeticion", [])
        if frase and len(frase) >= 18
    }
    ref_frases = {
        frase for frase in referencia.get("frases_repeticion", [])
        if frase and len(frase) >= 18
    }
    frases_comunes = art_frases.intersection(ref_frases)

    art_slug_tokens = set((articulo.get("slug_repeticion", "") or "").split())
    ref_slug_tokens = set((referencia.get("slug_repeticion", "") or "").split())
    slug_inter = art_slug_tokens.intersection(ref_slug_tokens)

    return {
        "titulo_ratio": titulo_ratio,
        "texto_ratio": texto_ratio,
        "firma_ratio": firma_ratio,
        "firma_claves_ratio": firma_claves_ratio,
        "inter": inter,
        "union": union,
        "jaccard": jaccard,
        "claves_inter": claves_inter,
        "claves_jaccard": claves_jaccard,
        "frases_comunes": frases_comunes,
        "slug_inter": slug_inter,
    }


def _es_articulo_muy_parecido(articulo, referencia):
    hash_art = articulo.get("hash_repeticion", "")
    hash_ref = referencia.get("hash_repeticion", "")
    if hash_art and hash_ref and hash_art == hash_ref:
        return True

    metricas = _metricas_similitud_articulos(articulo, referencia)
    titulo_ratio = metricas["titulo_ratio"]
    texto_ratio = metricas["texto_ratio"]
    firma_ratio = metricas["firma_ratio"]
    firma_claves_ratio = metricas["firma_claves_ratio"]
    inter = metricas["inter"]
    jaccard = metricas["jaccard"]
    claves_inter = metricas["claves_inter"]
    claves_jaccard = metricas["claves_jaccard"]
    frases_comunes = metricas["frases_comunes"]
    slug_inter = metricas["slug_inter"]

    if titulo_ratio >= 0.95:
        return True
    if texto_ratio >= 0.92:
        return True
    if any(len(frase) >= 22 for frase in frases_comunes):
        return True
    if len(frases_comunes) >= 2:
        return True
    if len(frases_comunes) >= 1 and len(inter) >= 4:
        return True
    if len(slug_inter) >= 4 and len(inter) >= 5 and titulo_ratio >= 0.50:
        return True
    if len(slug_inter) >= 5 and len(inter) >= 5:
        return True
    if len(claves_inter) >= 4:
        return True
    if len(claves_inter) >= 3 and (firma_claves_ratio >= 0.62 or claves_jaccard >= 0.34):
        return True
    if titulo_ratio >= 0.88 and texto_ratio >= 0.84 and len(inter) >= 4:
        return True
    if len(inter) >= 7 and jaccard >= 0.30:
        return True
    if len(inter) >= 5 and (firma_ratio >= 0.70 or jaccard >= 0.38):
        return True
    if len(inter) >= 4 and titulo_ratio >= 0.70 and (texto_ratio >= 0.66 or firma_ratio >= 0.68):
        return True
    if len(inter) >= 6 and titulo_ratio >= 0.55 and firma_ratio >= 0.58:
        return True
    if len(inter) >= 5 and titulo_ratio >= 0.45 and (firma_ratio >= 0.48 or firma_claves_ratio >= 0.58):
        return True

    return False


def _es_coincidencia_prohibida_extrema(articulo, referencia):
    metricas = _metricas_similitud_articulos(articulo, referencia)
    inter = metricas["inter"]
    claves_inter = metricas["claves_inter"]

    if len(claves_inter) >= 3 and len(inter) >= 4:
        return True
    if len(claves_inter) >= 2 and len(metricas["slug_inter"]) >= 3:
        return True
    if len(inter) >= 5 and metricas["jaccard"] >= 0.20:
        return True
    if len(inter) >= 4 and metricas["firma_ratio"] >= 0.46:
        return True
    if len(inter) >= 4 and metricas["firma_claves_ratio"] >= 0.52:
        return True
    if len(metricas["frases_comunes"]) >= 1 and len(inter) >= 3:
        return True
    if len(inter) >= 6:
        return True
    return False


def _es_caso_borde_repeticion(articulo, referencia):
    metricas = _metricas_similitud_articulos(articulo, referencia)
    inter = metricas["inter"]
    if metricas["frases_comunes"]:
        return True
    if len(metricas["claves_inter"]) >= 2:
        return True
    if len(metricas["slug_inter"]) >= 4 and len(inter) >= 4:
        return True
    if len(inter) >= 5 and (metricas["firma_ratio"] >= 0.48 or metricas["jaccard"] >= 0.22):
        return True
    if metricas["titulo_ratio"] >= 0.42 and len(inter) >= 4:
        return True
    return False


def _es_coincidencia_indice_repeticion(articulo, hashes, por_ancla, max_candidatos=80):
    hash_rep = articulo.get("hash_repeticion", "")
    if hash_rep and hash_rep in hashes:
        return True

    for referencia in _obtener_candidatos_repeticion(articulo, por_ancla, max_candidatos=max_candidatos):
        if _es_articulo_muy_parecido(articulo, referencia):
            return True

    return False


def _es_coincidencia_historial(articulo, historial_hashes, historial_por_ancla):
    return _es_coincidencia_indice_repeticion(
        articulo,
        historial_hashes,
        historial_por_ancla,
        max_candidatos=60,
    )


def _cargar_cache_ollama_similitud():
    global OLLAMA_SIMILITUD_CACHE
    if OLLAMA_SIMILITUD_CACHE is not None:
        return OLLAMA_SIMILITUD_CACHE
    if not os.path.exists(OLLAMA_SIMILITUD_CACHE_PATH):
        OLLAMA_SIMILITUD_CACHE = {}
        return OLLAMA_SIMILITUD_CACHE
    try:
        with open(OLLAMA_SIMILITUD_CACHE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        OLLAMA_SIMILITUD_CACHE = data if isinstance(data, dict) else {}
    except Exception:
        OLLAMA_SIMILITUD_CACHE = {}
    return OLLAMA_SIMILITUD_CACHE


def _guardar_cache_ollama_similitud():
    if OLLAMA_SIMILITUD_CACHE is None:
        return
    try:
        with open(OLLAMA_SIMILITUD_CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump(OLLAMA_SIMILITUD_CACHE, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _resolver_ollama_cli():
    global OLLAMA_CLI_PATH
    if OLLAMA_CLI_PATH is not None:
        return OLLAMA_CLI_PATH
    candidatos = [
        "ollama",
        r"C:\Users\photo\AppData\Local\Programs\Ollama\ollama.exe",
        r"C:\Program Files\Ollama\ollama.exe",
    ]
    for candidato in candidatos:
        try:
            proc = subprocess.run(
                [candidato, "--version"],
                capture_output=True,
                text=True,
                timeout=4,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if proc.returncode == 0:
                OLLAMA_CLI_PATH = candidato
                return OLLAMA_CLI_PATH
        except Exception:
            continue
    OLLAMA_CLI_PATH = ""
    return OLLAMA_CLI_PATH


def _fetch_texto_url(url, timeout=8, accept_html=False):
    import urllib.error
    headers = dict(HEADERS)
    if accept_html:
        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            contenido = resp.read()
            encoding = "utf-8"
            ct = resp.headers.get("Content-Type", "")
            if "charset=" in ct:
                encoding = ct.split("charset=")[-1].strip().split(";")[0]
            try:
                return contenido.decode(encoding)
            except Exception:
                return contenido.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extraer_texto_html_articulo(html_str):
    if not html_str:
        return ""
    texto = re.sub(r"(?is)<script.*?>.*?</script>", " ", html_str)
    texto = re.sub(r"(?is)<style.*?>.*?</style>", " ", texto)
    texto = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", texto)
    texto = re.sub(r"(?is)<!--.*?-->", " ", texto)
    texto = re.sub(r"(?is)<(br|p|div|li|h1|h2|h3|article|section)[^>]*>", "\n", texto)
    texto = re.sub(r"(?is)<[^>]+>", " ", texto)
    texto = html.unescape(texto)
    lineas = []
    vistos = set()
    for linea in texto.splitlines():
        limpia = re.sub(r"\s+", " ", linea).strip()
        if len(limpia) < 60:
            continue
        limpia_norm = _normalizar_para_repeticion(limpia)
        if not limpia_norm or limpia_norm in vistos:
            continue
        if "cookies" in limpia_norm or "suscrib" in limpia_norm or "whatsapp" in limpia_norm:
            continue
        vistos.add(limpia_norm)
        lineas.append(limpia)
        if len(" ".join(lineas)) >= CONTENIDO_PROFUNDO_MAX_CHARS:
            break
    return " ".join(lineas)[:CONTENIDO_PROFUNDO_MAX_CHARS]


def _obtener_contexto_profundo_articulo(articulo):
    url = articulo.get("url", "")
    if not url:
        return articulo.get("resumen", "")
    with CONTENIDO_ARTICULOS_LOCK:
        if url in CONTENIDO_ARTICULOS_CACHE:
            return CONTENIDO_ARTICULOS_CACHE[url]
    html_str = _fetch_texto_url(url, timeout=7, accept_html=True)
    contenido = _extraer_texto_html_articulo(html_str)
    if not contenido:
        contenido = articulo.get("resumen_limpio") or articulo.get("resumen") or articulo.get("titulo", "")
    with CONTENIDO_ARTICULOS_LOCK:
        CONTENIDO_ARTICULOS_CACHE[url] = contenido[:CONTENIDO_PROFUNDO_MAX_CHARS]
    return CONTENIDO_ARTICULOS_CACHE[url]


def _dictamen_ollama_mismo_tema(articulo, referencia):
    global OLLAMA_VALIDACIONES_RESTANTES
    ollama_cli = _resolver_ollama_cli()
    if not ollama_cli or OLLAMA_VALIDACIONES_RESTANTES <= 0:
        return False

    cache = _cargar_cache_ollama_similitud()
    hash_a = articulo.get("hash_repeticion", "")
    hash_b = referencia.get("hash_repeticion", "")
    cache_key = "|".join(sorted([hash_a or articulo.get("url", ""), hash_b or referencia.get("url", "")]))
    if cache_key in cache:
        return bool(cache[cache_key])

    contexto_a = _obtener_contexto_profundo_articulo(articulo)
    contexto_b = _obtener_contexto_profundo_articulo(referencia)
    prompt = (
        "Responde solo SI o NO.\n"
        "Determina si estas dos noticias tratan del mismo hecho, tema central o contenido editorial claramente derivado, "
        "aunque el titular haya sido reescrito.\n\n"
        f"NOTICIA A\nTitulo: {articulo.get('titulo', '')}\nResumen: {articulo.get('resumen_limpio', articulo.get('resumen', ''))}\n"
        f"URL: {articulo.get('url', '')}\nContenido: {contexto_a}\n\n"
        f"NOTICIA B\nTitulo: {referencia.get('titulo', '')}\nResumen: {referencia.get('resumen_limpio', referencia.get('resumen', ''))}\n"
        f"URL: {referencia.get('url', '')}\nContenido: {contexto_b}\n"
    )

    try:
        proc = subprocess.run(
            [ollama_cli, "run", "llama3.2", prompt],
            capture_output=True,
            text=True,
            timeout=OLLAMA_TIMEOUT_SEGUNDOS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        salida = (proc.stdout or "").strip().lower()
        verdict = salida.startswith("si") or salida.startswith("sí")
    except Exception:
        verdict = False

    OLLAMA_VALIDACIONES_RESTANTES -= 1
    cache[cache_key] = bool(verdict)
    _guardar_cache_ollama_similitud()
    return verdict


def _medio_prohibido_por_texto(url="", titulo="", descripcion="", fuente_rss=""):
    destinos_google = _extraer_destinos_google_news(url)
    netlocs = [_normalize_domain(url)]
    for destino in destinos_google:
        netloc_destino = _normalize_domain(destino)
        if netloc_destino and netloc_destino not in netlocs:
            netlocs.append(netloc_destino)

    netloc = netlocs[0] if netlocs else ""
    fuente_norm = _normalizar_texto_medio(fuente_rss)
    titulo_lower = (titulo or "").lower().strip()
    texto_norm = _normalizar_texto_medio(f"{titulo} {descripcion} {fuente_rss} {' '.join(destinos_google)}")
    separadores = (" - ", " — ", " | ", " – ", " :: ")
    es_msn = any("msn.com" in nl for nl in netlocs)

    for medio_key, cfg in MEDIOS_PROHIBIDOS.items():
        for dominio in cfg["dominios"]:
            if any(nl == dominio or nl.endswith(f".{dominio}") for nl in netlocs if nl):
                return medio_key, f"Dominio bloqueado: {dominio}"

        for alias in cfg.get("source_aliases", []):
            if fuente_norm == _normalizar_texto_medio(alias):
                return medio_key, f"Feed RSS Fuente exacta: {fuente_rss}"

        for alias in cfg.get("title_aliases", []):
            alias_lower = alias.lower()
            if any(titulo_lower.endswith(f"{sep}{alias_lower}") for sep in separadores):
                return medio_key, f"Filtro en TÃ­tulo: {cfg.get('label', '')}"

        for firma in cfg.get("signatures", []):
            firma_norm = _normalizar_texto_medio(firma)
            if firma_norm and firma_norm in texto_norm:
                return medio_key, f"Firma especÃ­fica: '{cfg.get('label', '')}'"

        if es_msn:
            for alias in [cfg.get("label", ""), *cfg.get("source_aliases", []), *cfg.get("title_aliases", [])]:
                alias_norm = _normalizar_texto_medio(alias)
                if not alias_norm:
                    continue
                patrones_msn = (
                    f"publicado por {alias_norm}",
                    f"por {alias_norm}",
                    f"de {alias_norm}",
                    f"fuente {alias_norm}",
                    f"{alias_norm} en msn",
                    f"msn {alias_norm}",
                )
                if any(patron in texto_norm for patron in patrones_msn):
                    return medio_key, f"MSN sindicado de {cfg['label']}"

    return None, ""


def _es_razon_medio_prohibido(razon):
    razon_norm = _normalizar_texto_medio(razon)
    if not razon_norm:
        return False
    for cfg in MEDIOS_PROHIBIDOS.values():
        if _normalizar_texto_medio(cfg["label"]) in razon_norm:
            return True
        for dominio in cfg["dominios"]:
            if dominio in razon_norm:
                return True
    return False


FIRMAS_BLOQUEADAS = [
    # FIX BUG 3: "El Tiempo" (periódico) se quitó de la lista de texto porque es
    # indistinguible de la palabra española "el tiempo" (the weather / the time).
    # El bloqueo de El Tiempo se hace por dominio (eltiempo.com) y por frases
    # específicas del periódico, NO por la cadena genérica "el tiempo".
    "portafolio.co", "Portafolio.co",
    "eltiempo.com",
    "Casa Editorial El Tiempo",
    "ELTIEMPO.COM",
]

# ═══════════════════════════════════════════════════════════════
# UTILIDADES DE FECHA
# ═══════════════════════════════════════════════════════════════

def _parsear_fecha_rss(fecha_str):
    if not fecha_str or not str(fecha_str).strip():
        return None
    fecha_str = str(fecha_str).strip()
    try:
        dt = parsedate_to_datetime(fecha_str)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    formatos = [
        "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
        "%a, %d %b %Y %H:%M:%S %Z",
    ]
    for fmt in formatos:
        try:
            dt = datetime.strptime(fecha_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            continue
    if hasattr(fecha_str, 'tm_year'):
        try:
            return datetime(*fecha_str[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def _es_fecha_confiable(dt):
    if dt is None:
        return False
    ahora = datetime.now(timezone.utc)
    return (ahora - timedelta(days=730)) <= dt <= (ahora + timedelta(hours=2))


def _a_zona_colombia(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZONA_COLOMBIA)


def _fecha_a_date_colombia(dt):
    dt_col = _a_zona_colombia(dt)
    return dt_col.date() if dt_col else None


def _fecha_display(dt):
    dt_col = _a_zona_colombia(dt)
    return dt_col.strftime("%Y-%m-%d %H:%M") if dt_col else ""


def _decodificar_payload_google_news(url):
    if not url:
        return ""
    url_lower = url.lower()
    if "news.google.com/rss/articles/" not in url_lower:
        return ""
    try:
        b64_part = url.split("articles/")[-1].split("?")[0]
        b64_part += "=" * ((4 - len(b64_part) % 4) % 4)
        payload = base64.urlsafe_b64decode(b64_part).decode("utf-8", errors="ignore")
        payload = urllib.parse.unquote(payload)
        return re.sub(r"[\x00-\x1f\x7f]+", " ", payload).strip()
    except Exception:
        return ""


def _extraer_destinos_google_news(url):
    payload = _decodificar_payload_google_news(url)
    if not payload:
        return []
    destinos = []
    for match in re.finditer(r"https?://[^\s\"'<>]+", payload, re.IGNORECASE):
        candidato = match.group(0).rstrip(").,;")
        if candidato not in destinos:
            destinos.append(candidato)
    return destinos


def _extraer_fecha_desde_url(url):
    if not url:
        return None
    patrones = [
        r"/(20\d{2})/(0[1-9]|1[0-2])/([0-2]\d|3[01])(?:/|$)",
        r"[-_/](20\d{2})[-_/](0[1-9]|1[0-2])[-_/]([0-2]\d|3[01])(?:[-_/]|$)",
    ]
    for patron in patrones:
        match = re.search(patron, url)
        if not match:
            continue
        try:
            y, m, d = map(int, match.groups())
            return date(y, m, d)
        except ValueError:
            continue
    return None


# ═══════════════════════════════════════════════════════════════
# FILTRO DE FUENTES BLOQUEADAS
# ═══════════════════════════════════════════════════════════════

import base64

def _esta_bloqueado(url, titulo="", descripcion="", fuente_rss="", filtrar_argentina=True):
    """
    Retorna (bloqueado, razón).

    FIX 1: Las URLs de Google News (news.google.com/rss/articles/...) son
            redirecciones a fuentes externas. Se excluyen del check de
            DOMINIOS_PERMITIDOS porque su dominio es siempre news.google.com,
            que intencionalmente no está en la whitelist.

    FIX 2: Se eliminó el "el_tiempo" con guión bajo (false positive).

    FIX 3: "ingresa a nuestro grupo de whatsapp" eliminado — phrase demasiado
            genérica que bloqueaba fuentes legítimas.
    """
    url_lower = url.lower()
    fuente_lower = fuente_rss.lower()

    medio_key, razon_medio = _medio_prohibido_por_texto(url, titulo, descripcion, fuente_rss)
    if medio_key:
        return True, razon_medio

    # ── Bloqueo explícito por nombre de fuente RSS ──────────────────────
    # Sólo bloqueamos si la fuente dice EXACTAMENTE "el tiempo" o "portafolio"
    # como nombre de medio, no si aparece en cualquier contexto.
    if fuente_lower in ("el tiempo", "portafolio", "portafolio.co",
                        "eltiempo.com", "el tiempo play", "citytv", "city tv"):
        return True, f"Feed RSS Fuente exacta: {fuente_rss}"

    t_lower = titulo.lower()
    if t_lower.endswith(" - el tiempo") or t_lower.endswith(" — el tiempo") or \
       t_lower.endswith(" | el tiempo") or t_lower.endswith("- eltiempo.com"):
        return True, "Filtro en Título: El Tiempo"

    if t_lower.endswith(" - portafolio") or t_lower.endswith(" — portafolio") or \
       t_lower.endswith(" | portafolio") or t_lower.endswith("- portafolio.co"):
        return True, "Filtro en Título: Portafolio"

    # ── Frases EXCLUSIVAS de El Tiempo y Portafolio ─────────────────────
    if t_lower.endswith(" - citytv") or t_lower.endswith(" â€” citytv") or \
       t_lower.endswith(" | citytv") or t_lower.endswith(" - city tv"):
        return True, "Filtro en TÃ­tulo: CityTV"

    texto_lower = f"{titulo} {descripcion} {fuente_rss}".lower()
    frases_prohibidas = [
        "artículo exclusivo para suscriptores de el tiempo",
        "sigue a el tiempo en whatsapp",
        "el tiempo play",
        "casa editorial el tiempo",
        "portafolio digital",
        "suscríbete a portafolio",
        "suscríbete a el tiempo",
        "el tiempoplay",
        "fuente: el tiempo",
        "por el tiempo",
        # FIX: "el_tiempo" con guión bajo ELIMINADO (generaba falsos positivos)
        # FIX: "ingresa a nuestro grupo de whatsapp" ELIMINADO (demasiado genérico)
    ]
    for frase in frases_prohibidas:
        if frase in texto_lower:
            return True, f"Frase bloqueada (El Tiempo/Portafolio): {frase}"

    # ── Decodificar URL base64 de Google News ───────────────────────────
    if "news.google.com/rss/articles/" in url_lower:
        try:
            b64_part = url_lower.split("articles/")[-1].split("?")[0]
            b64_part += "=" * ((4 - len(b64_part) % 4) % 4)
            decodificado = base64.urlsafe_b64decode(b64_part).decode('utf-8', errors='ignore').lower()
            dominios_prohibidos = []
            for cfg in MEDIOS_PROHIBIDOS.values():
                dominios_prohibidos.extend(cfg["dominios"])
            for dom_bloq in dominios_prohibidos:
                if dom_bloq in decodificado:
                    return True, f"Google News redirige a dominio bloqueado: {dom_bloq}"
        except Exception:
            pass

    # ── FIX 1: Whitelist (DOMINIOS_PERMITIDOS) ──────────────────────────
    # Las URLs de Google News redirect (news.google.com/rss/articles/...)
    # NO se pasan por la whitelist porque su netloc siempre es news.google.com,
    # que fue excluido intencionalmente. El destino real ya fue verificado arriba.
    try:
        netloc = _normalize_domain(url)

        es_gnews_redirect = "news.google.com" in netloc

        if not es_gnews_redirect:
            # Para fuentes directas, aplicar whitelist normalmente
            if DOMINIOS_PERMITIDOS and netloc not in DOMINIOS_PERMITIDOS:
                return True, f"Dominio no está en BD permitida: {netloc}"
    except Exception:
        pass

    if "redmas.com.co" in url_lower or "cronista.com" in url_lower:
        return True, "Filtro manual redmas/cronista"

    for dominio in DOMINIOS_BLOQUEADOS:
        if dominio in url_lower:
            return True, f"Dominio bloqueado: {dominio}"

    # ── Filtro de Argentina (opcional) ──────────────────────────────────
    if filtrar_argentina:
        for dominio in DOMINIOS_ARGENTINA:
            if dominio in url_lower:
                return True, f"Dominio Argentina: {dominio}"

    # ── Firmas textuales ─────────────────────────────────────────────────
    # FIX BUG 3: Solo usamos patrones muy específicos que no existen en español normal.
    # "el tiempo" genérico fue ELIMINADO (falso positivo con "el tiempo libre", etc.)
    # El bloqueo principal es por dominio (DOMINIOS_BLOQUEADOS / whitelist).
    firmas_especificas = [
        "eltiempo.com", "portafolio.co", "portafolio.co",
        "casa editorial el tiempo",
        "el tiempo play", "eltiempoplay",
        "suscríbete a el tiempo", "suscríbete a portafolio",
    ]
    for firma in firmas_especificas:
        if firma in texto_lower:
            return True, f"Firma específica: '{firma}'"

    if 'source="el tiempo"' in texto_lower or '>el tiempo</' in texto_lower:
        return True, "Firma oculta RSS: El Tiempo"
    if 'source="citytv"' in texto_lower or '>citytv</' in texto_lower:
        return True, "Firma oculta RSS: CityTV"

    return False, ""


# ═══════════════════════════════════════════════════════════════
# UTILIDADES DE TEXTO
# ═══════════════════════════════════════════════════════════════

def _limpiar_html(texto):
    if not texto:
        return ""
    limpio = re.sub(r'<[^>]+>', '', texto)
    return re.sub(r'\s+', ' ', limpio).strip()[:300]


def _normalizar(texto):
    if not texto:
        return ""
    texto = texto.lower().strip()
    texto = re.sub(r'[^\w\s]', '', texto)
    return re.sub(r'\s+', ' ', texto)


def _parece_ingles_puro(titulo, descripcion):
    """
    FIX 2: Reemplaza el filtro anterior " the "/" of "/" is " que era
    demasiado agresivo y bloqueaba artículos legítimos de Infobae, Forbes,
    El Heraldo, etc. que mencionan marcas o medios en inglés.

    Ahora sólo descarta un artículo si:
    - Tiene ≥4 marcadores lingüísticos del inglés en el título, Y
    - No tiene ninguna vocal española (á,é,í,ó,ú,ñ,ü,¿,¡), Y
    - Tiene longitud suficiente para el análisis.
    """
    MARCADORES_EN = [" the ", " is ", " are ", " was ", " were ",
                     " has ", " have ", " with ", " and ", " that ",
                     " this ", " from ", " their "]
    texto = f"{titulo} {descripcion}".lower()
    conteo = sum(1 for m in MARCADORES_EN if m in texto)
    tiene_espanol = any(c in texto for c in 'áéíóúñü¿¡')
    return conteo >= 4 and not tiene_espanol and len(texto) > 60


# ═══════════════════════════════════════════════════════════════
# FETCH + PARSE RSS
# ═══════════════════════════════════════════════════════════════

def _fetch_rss(url, timeout=TIMEOUT, max_retries=3):
    import urllib.error
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                contenido = resp.read()
                encoding = "utf-8"
                ct = resp.headers.get("Content-Type", "")
                if "charset=" in ct:
                    encoding = ct.split("charset=")[-1].strip().split(";")[0]
                try:
                    return contenido.decode(encoding)
                except Exception:
                    return contenido.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(1.5 ** attempt)
                continue
            return None
        except Exception:
            return None
    return None


def _parsear_feed(xml_str, nombre_fuente):
    """
    Parsea RSS/Atom. Descarta artículos sin fecha confiable.

    FIX 2: El filtro de idioma inglés ' the '/' of '/' is ' fue ELIMINADO.
    Era la causa principal de que Infobae, Forbes y El Heraldo no aparecieran:
    sus artículos sobre marcas mundoes, Netflix, Apple, FMI, etc.
    contenían estas palabras y se descartaban silenciosamente.

    Ahora se usa _parece_ingles_puro() que requiere ≥4 marcadores Y ausencia
    de caracteres del español — mucho más preciso.
    """
    articulos = []
    try:
        xml_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', xml_str)
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return []

    ns_atom = {"atom": "http://www.w3.org/2005/Atom"}
    es_atom = "feed" in root.tag.lower()

    items = (
        root.findall(".//atom:entry", ns_atom) or root.findall(".//entry")
    ) if es_atom else root.findall(".//item")

    for item in items:
        def _get(tag, ns_tag=None):
            el = item.find(tag)
            if el is None and ns_tag:
                el = item.find(ns_tag, ns_atom)
            return (el.text or "").strip() if el is not None else ""

        if es_atom:
            titulo = _get("title") or _get("atom:title", "atom:title")
            url = ""
            link_el = item.find("link") or item.find("{http://www.w3.org/2005/Atom}link")
            if link_el is not None:
                url = link_el.get("href", "") or link_el.text or ""
            fecha_str = _get("updated") or _get("published") or _get("{http://www.w3.org/2005/Atom}updated")
            descripcion = _get("summary") or _get("content")
            fuente_rss = _get("source") or _get("atom:source", "atom:source") or ""
        else:
            titulo = _get("title")
            url = _get("link") or _get("guid")
            fecha_str = _get("pubDate") or _get("dc:date") or _get("{http://purl.org/dc/elements/1.1/}date")
            descripcion = _get("description") or _get("summary")
            fuente_rss = _get("source") or ""

        if not titulo or not url:
            continue

        fecha_dt = _parsear_fecha_rss(fecha_str)
        if not _es_fecha_confiable(fecha_dt):
            continue

        fecha_url = None
        for candidata in _extraer_destinos_google_news(url) or [url]:
            fecha_url = _extraer_fecha_desde_url(candidata)
            if fecha_url:
                break
        if fecha_url and _fecha_a_date_colombia(fecha_dt) != fecha_url:
            fecha_dt_url = datetime(
                fecha_url.year,
                fecha_url.month,
                fecha_url.day,
                12,
                0,
                tzinfo=ZONA_COLOMBIA,
            ).astimezone(timezone.utc)
            if _es_fecha_confiable(fecha_dt_url):
                fecha_dt = fecha_dt_url

        # FIX 2: Filtro de idioma mejorado (mucho más permisivo con español legítimo)
        if _parece_ingles_puro(titulo, descripcion):
            continue

        t_norm = _normalizar(titulo)[:80]
        resumen_limpio = _limpiar_html(descripcion) or titulo
        art_claves = _extraer_palabras_clave(titulo + " " + descripcion)
        huella_repeticion = _construir_huella_repeticion(titulo, resumen_limpio, url)

        art_data = {
            "titulo":     titulo,
            "resumen":    resumen_limpio,
            "url":        url,
            "fecha_dt":   fecha_dt,
            "fecha_date": _fecha_a_date_colombia(fecha_dt),
            "fecha_str":  _fecha_display(fecha_dt),
            "fuente":     nombre_fuente,
            "t_norm":     t_norm,
            "claves":     art_claves,
            "tokens_relevantes": _extraer_tokens_relevantes(f"{titulo} {descripcion}"),
            **huella_repeticion,
        }

        bloqueado, razon = _esta_bloqueado(url, titulo, descripcion, fuente_rss, filtrar_argentina=False)
        if bloqueado:
            if _es_razon_medio_prohibido(razon):
                LISTA_NEGRA_MEDIOS.append(art_data)
            continue

        articulos.append(art_data)

    return articulos


def _parsear_forbes_economia_html(html_str, nombre_fuente):
    articulos = []
    vistos = set()
    patron = re.compile(
        r'<a[^>]+href="(?P<href>/\d{4}/\d{2}/\d{2}/economia-y-finanzas/[^"]+)"[^>]*>(?P<inner>.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )

    for match in patron.finditer(html_str):
        href = match.group("href")
        if href in vistos:
            continue

        titulo = re.sub(r"<[^>]+>", " ", match.group("inner"))
        titulo = html.unescape(re.sub(r"\s+", " ", titulo)).strip()
        if not titulo:
            continue

        vistos.add(href)
        url = urllib.parse.urljoin("https://forbes.co", href)

        fecha_match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/economia-y-finanzas/", href)
        if not fecha_match:
            continue

        try:
            y, m, d = map(int, fecha_match.groups())
            fecha_dt = datetime(y, m, d, 12, 0, tzinfo=timezone.utc)
        except ValueError:
            continue

        if not _es_fecha_confiable(fecha_dt):
            continue

        t_norm = _normalizar(titulo)[:80]
        huella_repeticion = _construir_huella_repeticion(titulo, titulo, url)
        art_data = {
            "titulo": titulo,
            "resumen": titulo,
            "url": url,
            "fecha_dt": fecha_dt,
            "fecha_date": _fecha_a_date_colombia(fecha_dt),
            "fecha_str": _fecha_display(fecha_dt),
            "fuente": nombre_fuente,
            "t_norm": t_norm,
            "claves": _extraer_palabras_clave(titulo),
            "tokens_relevantes": _extraer_tokens_relevantes(titulo),
            **huella_repeticion,
        }

        bloqueado, razon = _esta_bloqueado(url, titulo, "", "", filtrar_argentina=False)
        if bloqueado:
            if _es_razon_medio_prohibido(razon):
                LISTA_NEGRA_MEDIOS.append(art_data)
            continue

        articulos.append(art_data)

    return articulos


def _cargar_lista_negra_medios(fecha_inicio=None, fecha_fin=None, verbose=True):
    global LISTA_NEGRA_MEDIOS_HASHES, LISTA_NEGRA_MEDIOS_POR_ANCLA
    LISTA_NEGRA_MEDIOS.clear()
    LISTA_NEGRA_MEDIOS_HASHES = set()
    LISTA_NEGRA_MEDIOS_POR_ANCLA = {}

    historial_medios = _cargar_historial_medios_prohibidos()
    if historial_medios:
        LISTA_NEGRA_MEDIOS.extend(historial_medios)

    fecha_ref = fecha_fin or fecha_inicio or _fecha_a_date_colombia(datetime.now(timezone.utc))
    fecha_negra_fin = fecha_fin or fecha_ref
    fecha_negra_inicio = fecha_inicio or fecha_ref
    fecha_negra_inicio = min(fecha_negra_inicio, fecha_negra_fin) - timedelta(days=VENTANA_LISTA_NEGRA_DIAS)
    fecha_descarga_inicio = max(
        fecha_negra_inicio,
        fecha_negra_fin - timedelta(days=VENTANA_LISTA_NEGRA_DESCARGA_DIAS),
    )

    fuentes_lista_negra = []
    for cfg in MEDIOS_PROHIBIDOS.values():
        fuentes_lista_negra.append({
            "nombre": f"{cfg['label']} Base",
            "url": cfg["lista_negra_url"],
            "categorias": ["general"],
            "tipo": "nacional",
        })

    with ThreadPoolExecutor(max_workers=min(3, len(fuentes_lista_negra))) as executor:
        futuro_a_fuente = {
            executor.submit(_fetch_fuente, f, fecha_descarga_inicio, fecha_negra_fin): f
            for f in fuentes_lista_negra
        }
        for futuro in as_completed(futuro_a_fuente):
            try:
                _, _, articulos = futuro.result()
            except Exception:
                articulos = []
            if articulos:
                LISTA_NEGRA_MEDIOS.extend(articulos)

    LISTA_NEGRA_MEDIOS_HASHES, LISTA_NEGRA_MEDIOS_POR_ANCLA = _indexar_articulos_repeticion(LISTA_NEGRA_MEDIOS)
    if LISTA_NEGRA_MEDIOS:
        historial_actualizado = []
        hashes_historial = set()
        for item in LISTA_NEGRA_MEDIOS:
            hash_rep = item.get("hash_repeticion", "")
            if not hash_rep or hash_rep in hashes_historial:
                continue
            historial_actualizado.append(_registro_historial_desde_articulo(item))
            hashes_historial.add(hash_rep)
        _guardar_historial_medios_prohibidos(historial_actualizado)

    if verbose:
        log.info(
            f"  [✓] {len(LISTA_NEGRA_MEDIOS)} noticias en lista negra de medios bloqueados "
            f"(memoria {VENTANA_LISTA_NEGRA_DIAS}d / descarga {VENTANA_LISTA_NEGRA_DESCARGA_DIAS}d)."
        )


def _es_coincidencia_lista_negra(articulo, lista_negra_hashes, lista_negra_por_ancla):
    if _es_coincidencia_indice_repeticion(
        articulo,
        lista_negra_hashes,
        lista_negra_por_ancla,
        max_candidatos=90,
    ):
        return True

    candidatos = _obtener_candidatos_repeticion(articulo, lista_negra_por_ancla, max_candidatos=28)
    for referencia in candidatos[:12]:
        if _es_coincidencia_prohibida_extrema(articulo, referencia):
            return True

    for referencia in candidatos[:8]:
        if not _es_caso_borde_repeticion(articulo, referencia):
            continue
        if _dictamen_ollama_mismo_tema(articulo, referencia):
            return True
    return False


# ═══════════════════════════════════════════════════════════════
# MOTOR DE BÚSQUEDA
# ═══════════════════════════════════════════════════════════════

CATEGORIAS_DISPONIBLES = [
    "general", "economia", "politica", "deportes", "tecnologia",
    "cultura", "judicial", "justicia", "mundo", "salud",
    "tendencias", "negocios", "finanzas", "colombia",
    "motor", "vida", "virales", "bogota", "mis finanzas",
]

from concurrent.futures import ThreadPoolExecutor, as_completed


def _fetch_fuente(fuente, fecha_inicio, fecha_fin):
    """Descarga y parsea una fuente RSS completa. Diseñado para ejecución paralela."""
    nombre = fuente["nombre"]
    url_base = fuente["url"]
    is_google = "news.google.com/rss/search?q=" in url_base

    urls_to_fetch = []
    if is_google and fecha_inicio and fecha_fin:
        delta = (fecha_fin - fecha_inicio).days
        for d in range(0, delta + 1):
            dia_actual = fecha_inicio + timedelta(days=d)
            dia_siguiente = dia_actual + timedelta(days=1)
            f_ini_str = dia_actual.strftime("%Y-%m-%d")
            f_fin_str = dia_siguiente.strftime("%Y-%m-%d")
            partes = url_base.split("&hl=")
            q_part = partes[0]
            resto = "&hl=" + partes[1] if len(partes) > 1 else ""
            fechas_query = urllib.parse.quote(f" after:{f_ini_str} before:{f_fin_str}")
            urls_to_fetch.append(q_part + fechas_query + resto)
    else:
        urls_to_fetch.append(url_base)

    articulos_fuente = []
    responded = False
    for u in urls_to_fetch:
        xml_str = _fetch_rss(u)
        if xml_str:
            responded = True
            if nombre == "Forbes Colombia" and "economia-y-finanzas" in u:
                arts = _parsear_forbes_economia_html(xml_str, nombre)
            else:
                arts = _parsear_feed(xml_str, nombre)
            articulos_fuente.extend(arts)
        if is_google and len(urls_to_fetch) > 1:
            time.sleep(1.0)

    return nombre, responded, articulos_fuente


def buscar_noticias(categorias_seleccionadas=None, fecha_inicio=None, fecha_fin=None,
                    max_por_fuente=10, max_total=1000, verbose=True,
                    tipo_noticias="ambas", filtrar_argentina=True):
    global OLLAMA_VALIDACIONES_RESTANTES
    OLLAMA_VALIDACIONES_RESTANTES = MAX_VALIDACIONES_OLLAMA_POR_BUSQUEDA

    if categorias_seleccionadas:
        cats_ordenadas = [c.lower() for c in categorias_seleccionadas]
    else:
        cats_ordenadas = []

    cats_filtrado = list(cats_ordenadas)
    cats_filtrado_set = set(cats_filtrado) if cats_filtrado else None
    cats_expandidas = _expandir_categorias_solicitadas(cats_filtrado) if cats_filtrado else set()

    fuentes = []
    for fuente in FUENTES_RSS:
        if tipo_noticias != "ambas" and fuente.get("tipo", "nacional") != tipo_noticias:
            continue
        if not cats_filtrado:
            fuentes.append(fuente)
            continue

        coincide_categoria = any(c in cats_expandidas for c in fuente["categorias"]) if cats_expandidas else False
        if coincide_categoria:
            fuentes.append(fuente)

    if verbose:
        log.info("")
        log.info("=" * 60)
        log.info("  BUSCADOR DE NOTICIAS CAPA BRINDADA - V.6")
        log.info("=" * 60)
        log.info("  [!] Descargando lista negra de El Tiempo, Portafolio y CityTV...")

    _cargar_lista_negra_medios(fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, verbose=verbose)

    if fecha_inicio and fecha_fin:
        if fecha_inicio == fecha_fin:
            fecha_info = fecha_inicio.strftime("%Y-%m-%d")
        else:
            fecha_info = f"{fecha_inicio.strftime('%Y-%m-%d')} a {fecha_fin.strftime('%Y-%m-%d')}"
    else:
        fecha_info = "Todas"

    tipo_info = {
        "nacional": "Nacional",
        "mundo": "Mundo",
        "ambas": "Ambas",
    }.get(tipo_noticias, tipo_noticias)

    if verbose:
        log.info(f"  [OK] {len(LISTA_NEGRA_MEDIOS)} noticias en lista negra.")
        log.info(f"  Fuentes seleccionadas: {len(fuentes)}")
        log.info(f"  Tipo de noticias: {tipo_info}")
        log.info(f"  Filtro Argentina: {'Si' if filtrar_argentina else 'No'}")
        log.info(f"  Filtro de fecha: {fecha_info}")
        log.info("=" * 60)

    todas = []
    fuentes_fallidas = []
    conteo_fuentes = {}
    articulos_vistos_hashes = set()
    articulos_vistos_por_ancla = {}
    historial_articulos = _cargar_historial_articulos()
    historial_hashes, historial_por_ancla = _indexar_historial_articulos(historial_articulos)

    fuentes_google = [f for f in fuentes if "news.google.com/rss/search?q=" in f["url"]]
    fuentes_directas = [f for f in fuentes if "news.google.com/rss/search?q=" not in f["url"]]

    resultados_directos = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futuro_a_fuente = {
            executor.submit(_fetch_fuente, f, fecha_inicio, fecha_fin): f
            for f in fuentes_directas
        }
        for futuro in as_completed(futuro_a_fuente):
            try:
                nombre, responded, articulos = futuro.result()
                resultados_directos[nombre] = (responded, articulos)
            except Exception:
                fuente = futuro_a_fuente[futuro]
                resultados_directos[fuente["nombre"]] = (False, [])

    resultados_google = {}
    for fuente in fuentes_google:
        try:
            nombre, responded, articulos = _fetch_fuente(fuente, fecha_inicio, fecha_fin)
            resultados_google[nombre] = (responded, articulos)
        except Exception:
            resultados_google[fuente["nombre"]] = (False, [])

    todos_resultados = {**resultados_directos, **resultados_google}

    for fuente in fuentes:
        nombre = fuente["nombre"]
        responded, articulos_fuente = todos_resultados.get(nombre, (False, []))

        if not responded:
            fuentes_fallidas.append(nombre)
            if verbose:
                log.info(f"  [...] {nombre}...")
                log.info("    x Sin respuesta")
            continue

        articulos = articulos_fuente

        if filtrar_argentina:
            articulos = [
                art for art in articulos
                if not _esta_bloqueado(
                    art["url"],
                    art["titulo"],
                    art.get("resumen", ""),
                    "",
                    filtrar_argentina=True,
                )[0]
            ]

        if fecha_inicio and fecha_fin:
            articulos = [a for a in articulos if fecha_inicio <= a["fecha_date"] <= fecha_fin]

        if tipo_noticias == "nacional":
            articulos = [a for a in articulos if _articulo_es_nacional_colombia(a, fuente)]
        elif tipo_noticias == "mundo":
            articulos = [a for a in articulos if _articulo_cumple_filtro_mundo(a)]

        articulos_filtrados_categoria = []
        for art in articulos:
            if cats_filtrado_set:
                categoria_articulo = None
                for cat in cats_filtrado:
                    relacionadas = CATEGORIAS_RELACIONADAS.get(cat, set())
                    if cat not in fuente["categorias"] and not set(fuente["categorias"]).intersection(relacionadas):
                        continue
                    if _articulo_coincide_categoria(
                        cat,
                        titulo=art.get("titulo", ""),
                        resumen=art.get("resumen", ""),
                        fuente=art.get("fuente", ""),
                        categorias_fuente=fuente["categorias"],
                    ):
                        categoria_articulo = cat
                        break

                if not categoria_articulo:
                    continue
                art["categoria"] = categoria_articulo.upper()
            else:
                art["categoria"] = fuente["categorias"][0].upper()

            articulos_filtrados_categoria.append(art)

        articulos = articulos_filtrados_categoria

        nuevos = []
        for art in articulos[:max_por_fuente]:
            art_t_norm = art.get("t_norm", "")
            if not art_t_norm:
                continue

            if art.get("categoria") == "TENDENCIAS":
                if not _es_tendencia_valida(
                    art.get("titulo", ""),
                    art.get("resumen", ""),
                    art.get("fuente", ""),
                ):
                    continue

            if _es_coincidencia_lista_negra(
                art,
                LISTA_NEGRA_MEDIOS_HASHES,
                LISTA_NEGRA_MEDIOS_POR_ANCLA,
            ):
                continue

            if _es_coincidencia_historial(art, historial_hashes, historial_por_ancla):
                continue

            if not _es_coincidencia_indice_repeticion(
                art,
                articulos_vistos_hashes,
                articulos_vistos_por_ancla,
                max_candidatos=30,
            ):
                _agregar_articulo_a_indice(art, articulos_vistos_hashes, articulos_vistos_por_ancla)
                nuevos.append(art)

        todas.extend(nuevos)
        conteo_fuentes[nombre] = len(nuevos)
        if verbose:
            log.info(f"  [...] {nombre}...")
            log.info(f"    OK {len(nuevos)} articulos con fecha verificada")

    todas.sort(key=lambda a: a["fecha_dt"], reverse=True)
    todas.sort(key=lambda a: 0 if a.get("categoria") == "TENDENCIAS" else (1 if a.get("categoria") == "ECONOMIA" else 2))
    resultado = todas[:max_total]

    if resultado:
        historial_actualizado = historial_articulos[:]
        hashes_historial = set(historial_hashes)
        for art in resultado:
            hash_rep = art.get("hash_repeticion", "")
            if not hash_rep or hash_rep in hashes_historial:
                continue
            historial_actualizado.append(_registro_historial_desde_articulo(art))
            hashes_historial.add(hash_rep)
        _guardar_historial_articulos(historial_actualizado)

    notificacion = None
    if len(resultado) == 0:
        if fecha_inicio and fecha_fin:
            if fecha_inicio == fecha_fin:
                fmt = fecha_inicio.strftime("%d/%m/%Y")
            else:
                fmt = f"del {fecha_inicio.strftime('%d/%m/%Y')} al {fecha_fin.strftime('%d/%m/%Y')}"
            ahora_col = _fecha_a_date_colombia(datetime.now(timezone.utc))
            if fecha_inicio > ahora_col:
                notificacion = f"Rango {fmt} es futuro. No hay noticias aun."
            else:
                notificacion = (
                    f"Sin noticias para el rango {fmt}.\n"
                    f"   Se consultaron {len(fuentes) - len(fuentes_fallidas)} fuentes.\n"
                    f"   Las fuentes pueden no tener articulos de esas fechas."
                )
        else:
            notificacion = "No se encontraron noticias con los criterios seleccionados."
        if verbose:
            log.warning(f"  {notificacion}")

    if verbose:
        log.info(f"\n  TOTAL: {len(resultado)} articulos con fecha verificada")

    return {
        "noticias": resultado,
        "total": len(resultado),
        "fuentes_consultadas": len(fuentes) - len(fuentes_fallidas),
        "fuentes_fallidas": fuentes_fallidas,
        "conteo_fuentes": conteo_fuentes,
        "notificacion": notificacion,
    }

# ═══════════════════════════════════════════════════════════════
# GENERADOR DE EXCEL — UNA HOJA POR CATEGORÍA
# ═══════════════════════════════════════════════════════════════

class GeneradorExcelIDEAS:
    FONT_NAME = "Century Gothic"
    NEGRO = "000000"
    BLANCO = "FFFFFF"
    GRIS_CLARO = "F5F5F5"
    GRIS_BORDE = "CCCCCC"
    COLORES_TAB = [
        "FF4444", "FFD700", "00CC66", "00CCCC", "FF66FF",
        "FF8800", "4488FF", "AA44FF", "44DDAA", "DD4488",
        "88CC00", "0088DD", "FF6644", "6644FF", "44FF88",
    ]

    def __init__(self, articulos):
        self.articulos = articulos
        self.wb = Workbook()

    def generar(self, nombre_archivo):
        log.info("")
        log.info("=" * 60)
        log.info("  Generando Excel (una hoja por categoría)...")
        log.info("=" * 60)

        por_cat = {}
        for art in self.articulos:
            cat = art.get("categoria", "GENERAL")
            por_cat.setdefault(cat, []).append(art)

        cats_ord = sorted(por_cat.keys())

        ws_res = self.wb.active
        ws_res.title = "RESUMEN"
        ws_res.sheet_properties.tabColor = self.NEGRO
        self._hoja_resumen(ws_res, por_cat, cats_ord)

        for i, cat in enumerate(cats_ord):
            nombre_hoja = cat[:31]
            ws = self.wb.create_sheet(title=nombre_hoja)
            ws.sheet_properties.tabColor = self.COLORES_TAB[i % len(self.COLORES_TAB)]
            self._hoja_datos(ws, por_cat[cat])
            log.info(f"  ✓ Hoja '{nombre_hoja}': {len(por_cat[cat])} artículos")

        self.wb.save(nombre_archivo)
        log.info(f"  ✓ Guardado: {nombre_archivo}")
        log.info(f"  ✓ Total: {len(self.articulos)} en {len(cats_ord)} hojas")
        return nombre_archivo

    def _hoja_resumen(self, ws, por_cat, cats_ord):
        headers = [("CATEGORÍA", "FFFFFF"), ("ARTÍCULOS", "FFD700")]
        for ci, (h, c) in enumerate(headers, 1):
            cell = ws.cell(row=1, column=ci, value=h)
            cell.font = Font(name=self.FONT_NAME, bold=True, size=11, color=c)
            cell.fill = PatternFill(start_color=self.NEGRO, end_color=self.NEGRO, fill_type='solid')
            cell.alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 30
        borde = Border(
            left=Side(style='hair', color=self.GRIS_BORDE),
            right=Side(style='hair', color=self.GRIS_BORDE),
            top=Side(style='hair', color=self.GRIS_BORDE),
            bottom=Side(style='hair', color=self.GRIS_BORDE))
        fp = PatternFill(start_color=self.GRIS_CLARO, end_color=self.GRIS_CLARO, fill_type='solid')
        fi = PatternFill(start_color=self.BLANCO, end_color=self.BLANCO, fill_type='solid')
        total = 0
        for idx, cat in enumerate(cats_ord):
            row = idx + 2
            cnt = len(por_cat[cat])
            total += cnt
            fill = fp if idx % 2 == 0 else fi
            c = ws.cell(row=row, column=1, value=cat)
            c.font = Font(name=self.FONT_NAME, size=10, bold=True, color="333333")
            c.alignment = Alignment(horizontal='left', vertical='center')
            c.fill = fill; c.border = borde
            c = ws.cell(row=row, column=2, value=cnt)
            c.font = Font(name=self.FONT_NAME, size=10, color="333333")
            c.alignment = Alignment(horizontal='center', vertical='center')
            c.fill = fill; c.border = borde
        rt = len(cats_ord) + 2
        for ci, (v, clr) in enumerate([("TOTAL", "FFFFFF"), (total, "FFD700")], 1):
            c = ws.cell(row=rt, column=ci, value=v)
            c.font = Font(name=self.FONT_NAME, size=11, bold=True, color=clr)
            c.fill = PatternFill(start_color=self.NEGRO, end_color=self.NEGRO, fill_type='solid')
            c.alignment = Alignment(horizontal='center', vertical='center')
            c.border = borde
        ws.column_dimensions['A'].width = 30
        ws.column_dimensions['B'].width = 15
        ws.freeze_panes = "A2"

    def _hoja_datos(self, ws, articulos):
        headers = [("FUENTE","FF4444"),("TÍTULO","FFD700"),("RESUMEN CORTO","00CC66"),
                   ("URL","00CCCC"),("FECHA","FF66FF")]
        for ci, (h, c) in enumerate(headers, 1):
            cell = ws.cell(row=1, column=ci, value=h)
            cell.font = Font(name=self.FONT_NAME, bold=True, size=10, color=c)
            cell.fill = PatternFill(start_color=self.NEGRO, end_color=self.NEGRO, fill_type='solid')
            cell.alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 28
        borde = Border(
            left=Side(style='hair', color=self.GRIS_BORDE),
            right=Side(style='hair', color=self.GRIS_BORDE),
            top=Side(style='hair', color=self.GRIS_BORDE),
            bottom=Side(style='hair', color=self.GRIS_BORDE))
        fn = Font(name=self.FONT_NAME, size=9, color="333333")
        fl = Font(name=self.FONT_NAME, size=9, color="0563C1", underline='single')
        al = Alignment(vertical='center', wrap_text=True)
        fp = PatternFill(start_color=self.GRIS_CLARO, end_color=self.GRIS_CLARO, fill_type='solid')
        fi = PatternFill(start_color=self.BLANCO, end_color=self.BLANCO, fill_type='solid')
        arts = sorted(articulos,
                      key=lambda a: a.get("fecha_dt") or datetime.min.replace(tzinfo=timezone.utc),
                      reverse=True)
        for idx, art in enumerate(arts):
            row = idx + 2
            fill = fp if idx % 2 == 0 else fi
            c = ws.cell(row=row, column=1, value=art.get("fuente", ""))
            c.font = Font(name=self.FONT_NAME, size=9, bold=True, color="333333")
            c.alignment = Alignment(horizontal='center', vertical='center')
            c.fill = fill; c.border = borde
            c = ws.cell(row=row, column=2, value=art.get("titulo", ""))
            c.font = fn; c.alignment = al; c.fill = fill; c.border = borde
            resumen = art.get("resumen", "")
            if len(resumen) > 150: resumen = resumen[:147] + "..."
            c = ws.cell(row=row, column=3, value=resumen)
            c.font = Font(name=self.FONT_NAME, size=8, color="666666")
            c.alignment = al; c.fill = fill; c.border = borde
            c = ws.cell(row=row, column=4, value=art.get("url", ""))
            c.font = fl; c.alignment = al; c.fill = fill; c.border = borde
            try: c.hyperlink = art["url"]
            except Exception: pass
            c = ws.cell(row=row, column=5, value=art.get("fecha_str", ""))
            c.font = fn
            c.alignment = Alignment(horizontal='center', vertical='center')
            c.fill = fill; c.border = borde
            ws.row_dimensions[row].height = 22
        ws.column_dimensions['A'].width = 22
        ws.column_dimensions['B'].width = 55
        ws.column_dimensions['C'].width = 45
        ws.column_dimensions['D'].width = 50
        ws.column_dimensions['E'].width = 18
        uf = len(arts) + 1
        if uf > 1: ws.auto_filter.ref = f"A1:E{uf}"
        ws.freeze_panes = "A2"


# ═══════════════════════════════════════════════════════════════
# GUI — CustomTkinter
# ═══════════════════════════════════════════════════════════════

def _siguiente_nombre_tabla():
    carpeta = os.path.join(BASE_APP_DIR, "Noticias")
    os.makedirs(carpeta, exist_ok=True)
    n = 1
    while True:
        nombre = os.path.join(carpeta, f"TABLA DE NOTICIAS {n}.xlsx")
        if not os.path.exists(nombre):
            return nombre
        n += 1


CATEGORIAS_GUI = [
    "Tendencias", "Finanzas", "Economía", "General", "Política",
    "Deportes", "Tecnología", "Cultura", "Mundo", "Salud",
    "Negocios", "Colombia", "Vida", "Bogotá", "Mis Finanzas",
]

MAPA_CATEGORIAS = {
    "Tendencias": ["tendencias"],
    "Finanzas": ["finanzas"],
    "Economía": ["economia"],
    "General": ["general"],
    "Política": ["politica"],
    "Deportes": ["deportes"],
    "Tecnología": ["tecnologia"],
    "Cultura": ["cultura"],
    "Mundo": ["mundo"],
    "Salud": ["salud"],
    "Negocios": ["negocios"],
    "Colombia": ["colombia"],
    "Vida": ["vida"],
    "Bogotá": ["bogota"],
    "Mis Finanzas": ["mis finanzas"],
}

