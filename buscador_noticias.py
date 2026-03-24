# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════╗
║         BUSCADOR DE NOTICIAS — IDEAS                                 ║
║         Fechas 100 % verificadas — Sin fechas falsas                 ║
║         Filtro integrado: bloquea Portafolio & El Tiempo             ║
║         GUI + Excel por categoría                                    ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import io
import os
import re
import sys
import time
import logging
import hashlib
import threading
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from collections import deque
from datetime import datetime, date, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from typing import Optional

try:
    import tkinter as tk
    from tkinter import messagebox
    import customtkinter as ctk
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False
    class DummyCTk:
        pass
    class ctk:
        CTk = DummyCTk

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# ═══════════════════════════════════════════════════════════════
# CONFIGURACIÓN GENERAL
# ═══════════════════════════════════════════════════════════════

ZONA_COLOMBIA = timezone(timedelta(hours=-5))

class _DummyStream:
    def write(self, *a, **k): pass
    def flush(self, *a, **k): pass

if sys.stdout is None:
    sys.stdout = _DummyStream()
if sys.stderr is None:
    sys.stderr = _DummyStream()

if sys.platform == 'win32' and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass
    os.environ['PYTHONIOENCODING'] = 'utf-8'

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("BuscadorNoticias")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
}

TIMEOUT = 12

# ═══════════════════════════════════════════════════════════════
# FUENTES RSS — MULTI-CATEGORÍA
# Cada fuente puede tener múltiples categorías.
# Formato: {"nombre", "url", "categorias": [...]}
# Si un artículo viene de una fuente cuyas categorías coinciden
# con CUALQUIERA de las seleccionadas, se incluye.
# ═══════════════════════════════════════════════════════════════

FUENTES_RSS = [
    # ── COLOMBIA — El Heraldo ─────────────────────────────────────
    {"nombre": "El Heraldo",                "url": "https://www.elheraldo.co/rss.xml",
     "categorias": ["general", "barranquilla", "judicial", "politica", "deportes", "economia", "cultura", "salud", "tecnologia", "internacional"]},

    # ── COLOMBIA — El Colombiano ──────────────────────────────────
    {"nombre": "El Colombiano — Medellín",  "url": "https://www.elcolombiano.com/rss/medellin.xml",
     "categorias": ["general", "medellin"]},
    {"nombre": "El Colombiano — Antioquia", "url": "https://www.elcolombiano.com/rss/antioquia.xml",
     "categorias": ["general", "antioquia"]},
    {"nombre": "El Colombiano — Colombia",  "url": "https://www.elcolombiano.com/rss/colombia.xml",
     "categorias": ["general", "politica", "colombia"]},
    {"nombre": "El Colombiano — Negocios",  "url": "https://www.elcolombiano.com/rss/negocios.xml",
     "categorias": ["economia", "negocios"]},
    {"nombre": "El Colombiano — Deportes",  "url": "https://www.elcolombiano.com/rss/deportes.xml",
     "categorias": ["deportes"]},
    {"nombre": "El Colombiano — Internacional", "url": "https://www.elcolombiano.com/rss/internacional.xml",
     "categorias": ["internacional"]},
    {"nombre": "El Colombiano — Cultura",   "url": "https://www.elcolombiano.com/rss/cultura.xml",
     "categorias": ["cultura"]},
    {"nombre": "El Colombiano — Tendencias","url": "https://www.elcolombiano.com/rss/tendencias.xml",
     "categorias": ["tendencias", "salud"]},
    {"nombre": "El Colombiano — Tecnología","url": "https://www.elcolombiano.com/rss/tecnologia.xml",
     "categorias": ["tecnologia"]},
    {"nombre": "El Colombiano — Política",  "url": "https://www.elcolombiano.com/rss/colombia/politica.xml",
     "categorias": ["politica"]},

    # ── COLOMBIA — El Espectador ──────────────────────────────────
    {"nombre": "El Espectador",             "url": "https://www.elespectador.com/arc/outboundfeeds/rss/",
     "categorias": ["general", "politica", "judicial", "cultura", "colombia"]},
    {"nombre": "El Espectador — Economía",  "url": "https://www.elespectador.com/arc/outboundfeeds/rss/?outputType=xml&_website=el-espectador&section=/economia",
     "categorias": ["economia"]},

    # ── COLOMBIA — La República ───────────────────────────────────
    {"nombre": "La República — Economía",   "url": "https://www.larepublica.co/rss/economia.xml",
     "categorias": ["economia", "negocios"]},
    {"nombre": "La República — Finanzas",   "url": "https://www.larepublica.co/rss/finanzas.xml",
     "categorias": ["economia", "finanzas"]},

    # ── COLOMBIA — Semana ─────────────────────────────────────────
    {"nombre": "Semana",                    "url": "https://www.semana.com/rss/",
     "categorias": ["general", "politica", "economia", "cultura", "deportes", "tecnologia", "salud", "internacional", "judicial"]},

    # ── COLOMBIA — La FM ──────────────────────────────────────────
    {"nombre": "La FM — Actualidad",        "url": "https://www.lafm.com.co/rss/actualidad.xml",
     "categorias": ["general", "politica", "judicial", "colombia"]},

    # ── COLOMBIA — Caracol Radio ──────────────────────────────────
    {"nombre": "Caracol Radio",             "url": "https://caracol.com.co/rss/",
     "categorias": ["general", "politica", "deportes", "economia", "judicial"]},

    # ── COLOMBIA — W Radio ────────────────────────────────────────
    {"nombre": "W Radio",                   "url": "https://www.wradio.com.co/rss/",
     "categorias": ["general", "politica", "deportes", "economia"]},

    # ── LATINOAMÉRICA — Bloomberg Línea ───────────────────────────
    {"nombre": "Bloomberg Línea",           "url": "https://www.bloomberglinea.com/arc/outboundfeeds/rss/?outputType=xml",
     "categorias": ["economia", "negocios", "finanzas", "internacional"]},

    # ── INTERNACIONAL — BBC Mundo ─────────────────────────────────
    {"nombre": "BBC Mundo",                 "url": "https://feeds.bbci.co.uk/mundo/rss.xml",
     "categorias": ["general", "internacional", "politica", "economia", "cultura", "tecnologia", "deportes", "salud"]},

    # ── INTERNACIONAL — DW Español ────────────────────────────────
    {"nombre": "DW Español",                "url": "https://rss.dw.com/xml/rss-es-all",
     "categorias": ["general", "internacional", "politica", "economia", "cultura", "tecnologia"]},

    # ── INTERNACIONAL — France 24  ────────────────────────────────
    {"nombre": "France 24 Español",         "url": "https://www.france24.com/es/rss",
     "categorias": ["general", "internacional", "politica"]},

    # ── INTERNACIONAL — CNN Español ───────────────────────────────
    {"nombre": "CNN Español",               "url": "https://cnnespanol.cnn.com/feed/",
     "categorias": ["general", "internacional", "politica", "economia", "tecnologia", "deportes", "salud"]},

    # ── INTERNACIONAL — EFE ───────────────────────────────────────
    {"nombre": "EFE",                       "url": "https://www.efe.com/efe/rss",
     "categorias": ["general", "internacional"]},

    # ── INTERNACIONAL — Europa Press ──────────────────────────────
    {"nombre": "Europa Press",              "url": "https://www.europapress.es/rss/rss.aspx",
     "categorias": ["general", "internacional", "economia"]},

    # ── INTERNACIONAL — Newsweek ──────────────────────────────────
    {"nombre": "Newsweek",                  "url": "https://www.newsweek.com/rss",
     "categorias": ["general", "internacional", "tecnologia"]},

    # ── INTERNACIONAL — NPR ───────────────────────────────────────
    {"nombre": "NPR",                       "url": "https://feeds.npr.org/1001/rss.xml",
     "categorias": ["general", "internacional"]},

    # ── INTERNACIONAL — The Guardian ──────────────────────────────
    {"nombre": "The Guardian World",        "url": "https://www.theguardian.com/world/rss",
     "categorias": ["internacional"]},

    # ── INTERNACIONAL — NY Times ──────────────────────────────────
    {"nombre": "NY Times World",            "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
     "categorias": ["internacional"]},

    # ── LATINOAMÉRICA — El País América ───────────────────────────
    {"nombre": "El País América",           "url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",
     "categorias": ["general", "internacional", "politica", "economia", "cultura"]},

    # ── LATINOAMÉRICA — Clarín ────────────────────────────────────
    {"nombre": "Clarín",                    "url": "https://www.clarin.com/rss/lo-ultimo/",
     "categorias": ["general", "internacional", "deportes", "economia"]},

    # ── LATINOAMÉRICA — La Nación Argentina ───────────────────────
    {"nombre": "La Nación Argentina",       "url": "https://www.lanacion.com.ar/arcio/rss/",
     "categorias": ["general", "internacional", "economia", "politica"]},

    # ── LATINOAMÉRICA — RPP Perú ──────────────────────────────────
    {"nombre": "RPP Perú",                  "url": "https://rpp.pe/feed",
     "categorias": ["general", "internacional"]},

    # ── COLOMBIA — Google News ────────────────────────────────────
    {"nombre": "Google News — Colombia",    "url": "https://news.google.com/rss/search?q=colombia&hl=es-419&gl=CO&ceid=CO:es-419",
     "categorias": ["general", "colombia"]},
    {"nombre": "Google News — Economía",    "url": "https://news.google.com/rss/search?q=economia+colombia&hl=es-419&gl=CO&ceid=CO:es-419",
     "categorias": ["economia"]},
    {"nombre": "Google News — Deportes",    "url": "https://news.google.com/rss/search?q=deportes+colombia&hl=es-419&gl=CO&ceid=CO:es-419",
     "categorias": ["deportes"]},
    {"nombre": "Google News — Política",    "url": "https://news.google.com/rss/search?q=politica+colombia&hl=es-419&gl=CO&ceid=CO:es-419",
     "categorias": ["politica"]},
    {"nombre": "Google News — Tecnología",  "url": "https://news.google.com/rss/search?q=tecnologia&hl=es-419&gl=CO&ceid=CO:es-419",
     "categorias": ["tecnologia"]},
    {"nombre": "Google News — Salud",       "url": "https://news.google.com/rss/search?q=salud+colombia&hl=es-419&gl=CO&ceid=CO:es-419",
     "categorias": ["salud"]},
    {"nombre": "Google News — Cultura",     "url": "https://news.google.com/rss/search?q=cultura+colombia&hl=es-419&gl=CO&ceid=CO:es-419",
     "categorias": ["cultura"]},
    {"nombre": "Google News — Judicial",    "url": "https://news.google.com/rss/search?q=judicial+justicia+colombia&hl=es-419&gl=CO&ceid=CO:es-419",
     "categorias": ["judicial"]},
]

# ═══════════════════════════════════════════════════════════════
# DOMINIOS BLOQUEADOS
# ═══════════════════════════════════════════════════════════════

DOMINIOS_BLOQUEADOS = [
    "portafolio.co", "eltiempo.com",
    "blogs.portafolio.co", "amp.portafolio.co", "m.portafolio.co",
    "amp.eltiempo.com", "m.eltiempo.com", "especiales.eltiempo.com",
    "enter.co", "citytv.com.co",
]

FIRMAS_BLOQUEADAS = [
    "portafolio.co", "Portafolio.co",
    "EL TIEMPO", "El Tiempo", "eltiempo.com",
    "Casa Editorial El Tiempo",
]


# ═══════════════════════════════════════════════════════════════
# UTILIDADES DE FECHA — NUNCA datetime.now() COMO FALLBACK
# ═══════════════════════════════════════════════════════════════

def _parsear_fecha_rss(fecha_str):
    """
    Parsea una fecha RSS/Atom. Retorna datetime con tz UTC, o None.
    NUNCA retorna la fecha de hoy como fallback.
    """
    if not fecha_str or not str(fecha_str).strip():
        return None

    fecha_str = str(fecha_str).strip()

    # ── RFC 2822 (estándar RSS) ──
    try:
        dt = parsedate_to_datetime(fecha_str)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # ── Formatos ISO 8601 / Atom ──
    formatos = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
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

    # ── time.struct_time (feedparser-style) ──
    if hasattr(fecha_str, 'tm_year'):
        try:
            dt = datetime(*fecha_str[:6], tzinfo=timezone.utc)
            return dt
        except Exception:
            pass

    return None  # ← NUNCA se inventa una fecha


def _es_fecha_confiable(dt):
    """
    Verifica que la fecha sea razonable:
    - No sea futura (más de 2 horas)
    - No sea más antigua de 2 años
    """
    if dt is None:
        return False
    ahora = datetime.now(timezone.utc)
    return (ahora - timedelta(days=730)) <= dt <= (ahora + timedelta(hours=2))


def _fecha_a_date_colombia(dt):
    """Convierte datetime UTC a date en hora Colombia (UTC-5)."""
    return (dt + timedelta(hours=-5)).date()


def _fecha_display(dt):
    """Formatea datetime UTC como string en hora Colombia."""
    dt_col = dt + timedelta(hours=-5)
    return dt_col.strftime("%Y-%m-%d %H:%M")


# ═══════════════════════════════════════════════════════════════
# FILTRO DE FUENTES BLOQUEADAS
# ═══════════════════════════════════════════════════════════════

import base64

def _esta_bloqueado(url, titulo="", descripcion="", fuente_rss=""):
    """Retorna (bloqueado, razón)."""
    url_lower = url.lower()
    fuente_lower = fuente_rss.lower()
    
    if "el tiempo" in fuente_lower or "portafolio" in fuente_lower:
        return True, f"Feed RSS Fuente: {fuente_rss}"
    
    # ── Decodificar URL en base64 de Google News ──
    if "news.google.com/rss/articles/" in url_lower:
        try:
            b64_part = url_lower.split("articles/")[-1].split("?")[0]
            # Reparar padding
            b64_part += "=" * ((4 - len(b64_part) % 4) % 4)
            decodificado = base64.urlsafe_b64decode(b64_part).decode('utf-8', errors='ignore').lower()
            url_lower += " " + decodificado
        except Exception:
            pass

    for dominio in DOMINIOS_BLOQUEADOS:
        if dominio in url_lower:
            return True, f"Dominio: {dominio}"
            
    texto_lower = f"{titulo} {descripcion} {fuente_rss}".lower()
    # Versión minúscula de las firmas
    firmas_lower = [f.lower() for f in FIRMAS_BLOQUEADAS] + [
        "- el tiempo", "| el tiempo", " - el tiempo",
        "- eltiempo", "el tiempo play"
    ]
    
    for firma in firmas_lower:
        if firma in texto_lower:
            return True, f"Firma: '{firma}'"
            
    # Última revisión por fuente oculta en etiqueta source de Google News
    if 'source="el tiempo"' in texto_lower or '>el tiempo</' in texto_lower:
        return True, "Firma oculta RSS: El Tiempo"
        
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


# ═══════════════════════════════════════════════════════════════
# FETCH + PARSE RSS  (stdlib puro — sin feedparser)
# ═══════════════════════════════════════════════════════════════

def _fetch_rss(url, timeout=TIMEOUT):
    """Descarga un feed RSS. Retorna XML string o None."""
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
    except Exception:
        return None


def _parsear_feed(xml_str, nombre_fuente):
    """Parsea RSS/Atom. Descarta artículos sin fecha confiable."""
    articulos = []
    try:
        xml_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', xml_str)
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return []

    ns_atom = {"atom": "http://www.w3.org/2005/Atom"}
    es_atom = "feed" in root.tag.lower()

    items = (root.findall(".//atom:entry", ns_atom) or root.findall(".//entry")) if es_atom else root.findall(".//item")

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

        # ── FECHA REAL — nunca inventada ──
        fecha_dt = _parsear_fecha_rss(fecha_str)
        if not _es_fecha_confiable(fecha_dt):
            continue  # Descartado: fecha ausente o inválida

        # ── Filtro bloqueados ──
        bloqueado, _ = _esta_bloqueado(url, titulo, descripcion, fuente_rss)
        if bloqueado:
            continue

        articulos.append({
            "titulo":     titulo,
            "resumen":    _limpiar_html(descripcion) or titulo,
            "url":        url,
            "fecha_dt":   fecha_dt,  # datetime UTC real
            "fecha_date": _fecha_a_date_colombia(fecha_dt),
            "fecha_str":  _fecha_display(fecha_dt),
            "fuente":     nombre_fuente,
        })

    return articulos


# ═══════════════════════════════════════════════════════════════
# MOTOR DE BÚSQUEDA
# ═══════════════════════════════════════════════════════════════

CATEGORIAS_DISPONIBLES = [
    "general", "economia", "politica", "deportes", "tecnologia",
    "cultura", "judicial", "internacional", "salud", "tendencias",
    "negocios", "finanzas", "colombia",
]


def buscar_noticias(categorias_seleccionadas=None, fecha_filtro=None,
                    max_por_fuente=20, max_total=200, verbose=True):
    """
    Busca noticias de fuentes RSS.

    Args:
        categorias_seleccionadas: lista de strings (ej: ["economia", "politica"]).
                                  None = todas.
        fecha_filtro: date. Si se indica, solo artículos de ese día exacto.
        max_por_fuente: máx artículos por fuente RSS.
        max_total: máx artículos en resultado final.
        verbose: imprimir progreso.

    Returns:
        dict con resultado.
    """
    if categorias_seleccionadas:
        cats_lower = set(c.lower() for c in categorias_seleccionadas)
    else:
        cats_lower = None

    # Seleccionar fuentes que coincidan con al menos 1 categoría
    fuentes = []
    for f in FUENTES_RSS:
        if cats_lower is None:
            fuentes.append(f)
        else:
            if any(c in cats_lower for c in f["categorias"]):
                fuentes.append(f)

    if verbose:
        log.info("")
        log.info("=" * 60)
        log.info("  BUSCADOR DE NOTICIAS — FECHAS VERIFICADAS")
        log.info("=" * 60)
        fecha_info = fecha_filtro.strftime("%Y-%m-%d") if fecha_filtro else "Todas"
        log.info(f"  Fuentes seleccionadas: {len(fuentes)}")
        log.info(f"  Filtro de fecha: {fecha_info}")
        log.info("=" * 60)

    todas = []
    fuentes_fallidas = []
    conteo_fuentes = {}
    titulos_vistos = set()

    for fuente in fuentes:
        nombre = fuente["nombre"]
        if verbose:
            log.info(f"  ⟳ {nombre}...")

        xml_str = _fetch_rss(fuente["url"])
        if xml_str is None:
            fuentes_fallidas.append(nombre)
            if verbose:
                log.info(f"    ✗ Sin respuesta")
            continue

        articulos = _parsear_feed(xml_str, nombre)

        # Filtrar por fecha exacta si se pidió
        if fecha_filtro:
            articulos = [a for a in articulos if a["fecha_date"] == fecha_filtro]

        # Asignar categoría principal (la primera que coincida con la selección)
        for art in articulos:
            if cats_lower:
                for cat in fuente["categorias"]:
                    if cat in cats_lower:
                        art["categoria"] = cat.upper()
                        break
                else:
                    art["categoria"] = fuente["categorias"][0].upper()
            else:
                art["categoria"] = fuente["categorias"][0].upper()

        # Deduplicación por título normalizado
        nuevos = []
        for art in articulos[:max_por_fuente]:
            t_norm = _normalizar(art["titulo"])[:80]
            if t_norm and t_norm not in titulos_vistos:
                titulos_vistos.add(t_norm)
                nuevos.append(art)

        todas.extend(nuevos)
        conteo_fuentes[nombre] = len(nuevos)
        if verbose:
            log.info(f"    ✓ {len(nuevos)} artículos con fecha verificada")

        time.sleep(0.2)

    # Ordenar por fecha (más recientes primero)
    todas.sort(key=lambda a: a["fecha_dt"], reverse=True)

    # Limitar
    resultado = todas[:max_total]

    # Notificación
    notificacion = None
    if len(resultado) == 0:
        if fecha_filtro:
            fmt = fecha_filtro.strftime("%d/%m/%Y")
            ahora_col = _fecha_a_date_colombia(datetime.now(timezone.utc))
            if fecha_filtro > ahora_col:
                notificacion = f"⚠ La fecha {fmt} es futura. No hay noticias aún."
            else:
                notificacion = (
                    f"📭 Sin noticias para el {fmt}.\n"
                    f"   Se consultaron {len(fuentes) - len(fuentes_fallidas)} fuentes.\n"
                    f"   Las fuentes pueden no tener artículos de esa fecha."
                )
        else:
            notificacion = "⚠ No se encontraron noticias con los criterios seleccionados."
        if verbose:
            log.warning(f"  {notificacion}")

    if verbose:
        log.info(f"\n  ► TOTAL: {len(resultado)} artículos con fecha verificada")

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
    """Genera un Excel con una hoja por categoría + hoja resumen."""

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
            left=Side(style='hair', color=self.GRIS_BORDE), right=Side(style='hair', color=self.GRIS_BORDE),
            top=Side(style='hair', color=self.GRIS_BORDE), bottom=Side(style='hair', color=self.GRIS_BORDE))
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
        for ci, (v, clr) in enumerate([(f"TOTAL", "FFFFFF"), (total, "FFD700")], 1):
            c = ws.cell(row=rt, column=ci, value=v)
            c.font = Font(name=self.FONT_NAME, size=11, bold=True, color=clr)
            c.fill = PatternFill(start_color=self.NEGRO, end_color=self.NEGRO, fill_type='solid')
            c.alignment = Alignment(horizontal='center', vertical='center')
            c.border = borde

        ws.column_dimensions['A'].width = 30
        ws.column_dimensions['B'].width = 15
        ws.freeze_panes = "A2"

    def _hoja_datos(self, ws, articulos):
        headers = [("FUENTE","FF4444"),("TÍTULO","FFD700"),("RESUMEN CORTO","00CC66"),("URL","00CCCC"),("FECHA","FF66FF")]
        for ci, (h, c) in enumerate(headers, 1):
            cell = ws.cell(row=1, column=ci, value=h)
            cell.font = Font(name=self.FONT_NAME, bold=True, size=10, color=c)
            cell.fill = PatternFill(start_color=self.NEGRO, end_color=self.NEGRO, fill_type='solid')
            cell.alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 28

        borde = Border(
            left=Side(style='hair', color=self.GRIS_BORDE), right=Side(style='hair', color=self.GRIS_BORDE),
            top=Side(style='hair', color=self.GRIS_BORDE), bottom=Side(style='hair', color=self.GRIS_BORDE))
        fn = Font(name=self.FONT_NAME, size=9, color="333333")
        fl = Font(name=self.FONT_NAME, size=9, color="0563C1", underline='single')
        al = Alignment(vertical='center', wrap_text=True)
        fp = PatternFill(start_color=self.GRIS_CLARO, end_color=self.GRIS_CLARO, fill_type='solid')
        fi = PatternFill(start_color=self.BLANCO, end_color=self.BLANCO, fill_type='solid')

        arts = sorted(articulos, key=lambda a: a.get("fecha_dt") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

        for idx, art in enumerate(arts):
            row = idx + 2
            fill = fp if idx % 2 == 0 else fi

            c = ws.cell(row=row, column=1, value=art.get("fuente", ""))
            c.font = Font(name=self.FONT_NAME, size=9, bold=True, color="333333")
            c.alignment = Alignment(horizontal='center', vertical='center'); c.fill = fill; c.border = borde

            c = ws.cell(row=row, column=2, value=art.get("titulo", ""))
            c.font = fn; c.alignment = al; c.fill = fill; c.border = borde

            resumen = art.get("resumen", "")
            if len(resumen) > 150: resumen = resumen[:147] + "..."
            c = ws.cell(row=row, column=3, value=resumen)
            c.font = Font(name=self.FONT_NAME, size=8, color="666666"); c.alignment = al; c.fill = fill; c.border = borde

            c = ws.cell(row=row, column=4, value=art.get("url", ""))
            c.font = fl; c.alignment = al; c.fill = fill; c.border = borde
            try: c.hyperlink = art["url"]
            except Exception: pass

            c = ws.cell(row=row, column=5, value=art.get("fecha_str", ""))
            c.font = fn; c.alignment = Alignment(horizontal='center', vertical='center'); c.fill = fill; c.border = borde
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
    n = 1
    while True:
        nombre = f"TABLA DE NOTICIAS {n}.xlsx"
        if not os.path.exists(nombre):
            return nombre
        n += 1


CATEGORIAS_GUI = [
    "General", "Economía", "Política", "Deportes", "Tecnología",
    "Cultura", "Judicial", "Internacional", "Salud", "Tendencias",
    "Negocios", "Finanzas", "Colombia",
]

# Mapeo GUI → categorías internas (minúsculas)
MAPA_CATEGORIAS = {
    "General": ["general"],
    "Economía": ["economia"],
    "Política": ["politica"],
    "Deportes": ["deportes"],
    "Tecnología": ["tecnologia"],
    "Cultura": ["cultura"],
    "Judicial": ["judicial"],
    "Internacional": ["internacional"],
    "Salud": ["salud"],
    "Tendencias": ["tendencias"],
    "Negocios": ["negocios"],
    "Finanzas": ["finanzas"],
    "Colombia": ["colombia"],
}

if GUI_AVAILABLE:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")


class RedirectText:
    def __init__(self, text_ctrl):
        self.output = text_ctrl
        self.after = text_ctrl.after
    def write(self, string):
        self.after(0, self._escribir, string)
    def _escribir(self, string):
        self.output.insert("end", string)
        self.output.see("end")
    def flush(self):
        pass


class AppNoticiasIDEAS(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Buscador de Noticias — IDEAS")
        self.geometry("900x750")
        try:
            self.iconbitmap("nuevo_logo.ico")
        except Exception:
            pass
        self.vars_categorias = {}
        self.create_widgets()
        sys.stdout = RedirectText(self.consola)
        sys.stderr = RedirectText(self.consola)
        self.mostrar_bienvenida()

    def mostrar_bienvenida(self):
        print("  ╔══════════════════════════════════════════════════════╗")
        print("  ║       BUSCADOR DE NOTICIAS — IDEAS                  ║")
        print("  ║  Fechas 100% verificadas — Sin fechas falsas        ║")
        print("  ╚══════════════════════════════════════════════════════╝")
        print()
        print("  Programa diseñado por Sebastian Rozo.")
        print("  Todos los derechos reservados.")
        print()
        print("  ✔ Las fechas son REALES (leídas del artículo)")
        print("  ✔ Si la fecha no se puede verificar → artículo descartado")
        print("  ✔ Filtro automático de El Tiempo / Portafolio\n")

    def create_widgets(self):
        lbl_titulo = ctk.CTkLabel(self, text="Buscador de Noticias IDEAS", font=ctk.CTkFont(size=24, weight="bold"))
        lbl_titulo.pack(pady=(20, 10))

        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=10)

        panel_opciones = ctk.CTkFrame(main_frame, fg_color="transparent")
        panel_opciones.pack(fill="x", pady=(0, 15))

        # ── Panel Izquierdo: Categorías ──
        panel_izq = ctk.CTkFrame(panel_opciones)
        panel_izq.pack(side="left", fill="both", expand=True, padx=(0, 10))

        ctk.CTkLabel(panel_izq, text="1. Selecciona las Categorías", font=ctk.CTkFont(weight="bold")).pack(pady=10)

        self.scroll_cat = ctk.CTkScrollableFrame(panel_izq, width=300, height=180)
        self.scroll_cat.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        for cat in CATEGORIAS_GUI:
            var = ctk.BooleanVar(value=True)
            ctk.CTkCheckBox(self.scroll_cat, text=cat, variable=var).pack(anchor="w", pady=3, padx=5)
            self.vars_categorias[cat] = var

        fr_btn = ctk.CTkFrame(panel_izq, fg_color="transparent")
        fr_btn.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkButton(fr_btn, text="Seleccionar Todas", width=120,
                       command=lambda: self._marcar(True)).pack(side="left", padx=5)
        ctk.CTkButton(fr_btn, text="Deseleccionar", width=120, fg_color="gray",
                       hover_color="#555555", command=lambda: self._marcar(False)).pack(side="right", padx=5)

        # ── Panel Derecho: Filtros + Fecha + Botón ──
        panel_der = ctk.CTkFrame(panel_opciones)
        panel_der.pack(side="right", fill="both", expand=True, padx=(10, 0))

        ctk.CTkLabel(panel_der, text="2. Filtros Adicionales", font=ctk.CTkFont(weight="bold")).pack(pady=10)

        # Selector de fecha
        fr_fecha = ctk.CTkFrame(panel_der, fg_color="transparent")
        fr_fecha.pack(fill="x", padx=20, pady=(5, 10))
        
        self.var_usar_fecha = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(fr_fecha, text="Filtrar por fecha exacta", 
                      variable=self.var_usar_fecha, font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0, 5))

        fr_inp = ctk.CTkFrame(fr_fecha, fg_color="transparent")
        fr_inp.pack(fill="x", pady=(3, 0))
        
        try:
            from tkcalendar import DateEntry
            from datetime import date
            self.entry_fecha = DateEntry(fr_inp, width=15,
                                       background='#1f538d', foreground='white', borderwidth=0,
                                       font=('Century Gothic', 11),
                                       date_pattern='y-mm-dd', state="readonly")
            self.entry_fecha.pack(side="left", padx=(0, 8), pady=3)
        except ImportError:
            self.entry_fecha = ctk.CTkEntry(fr_inp, placeholder_text="YYYY-MM-DD (ej: 2026-03-23)", width=200)
            self.entry_fecha.pack(side="left", padx=(0, 8))
            ctk.CTkButton(fr_inp, text="Hoy", width=60, fg_color="#444444", hover_color="#666666",
                           command=self._poner_hoy).pack(side="left", padx=(0, 5))
            ctk.CTkButton(fr_inp, text="✕", width=35, fg_color="#882222", hover_color="#AA4444",
                           command=lambda: self.entry_fecha.delete(0, "end")).pack(side="left")

        ctk.CTkLabel(fr_fecha,
                      text="Si desactivas el switch, mostrará noticias recientes sin importar el día.",
                      font=ctk.CTkFont(size=10), text_color="gray").pack(anchor="w", pady=(3, 0))

        # Info sobre fechas
        ctk.CTkLabel(panel_der,
                      text="⚠ Solo artículos con fecha REAL verificada.\n   Artículos sin fecha confiable son descartados.",
                      font=ctk.CTkFont(size=10), text_color="#FFAA00").pack(padx=20, pady=(5, 10), anchor="w")

        # Botón principal
        self.btn_ejecutar = ctk.CTkButton(
            panel_der, text="▶ INICIAR BÚSQUEDA Y GENERAR EXCEL",
            font=ctk.CTkFont(size=14, weight="bold"), height=50,
            command=self.ejecutar_scraper)
        self.btn_ejecutar.pack(fill="x", padx=20, pady=(10, 20))

        # ── Consola ──
        ctk.CTkLabel(main_frame, text="3. Registro del Proceso (Logs en vivo)", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self.consola = ctk.CTkTextbox(main_frame, font=ctk.CTkFont(family="Consolas", size=11), wrap="word")
        self.consola.pack(fill="both", expand=True, pady=(5, 0))

    def _marcar(self, estado):
        for v in self.vars_categorias.values():
            v.set(estado)

    def _poner_hoy(self):
        hoy = datetime.now(ZONA_COLOMBIA).strftime("%Y-%m-%d")
        self.entry_fecha.delete(0, "end")
        self.entry_fecha.insert(0, hoy)

    def ejecutar_scraper(self):
        seleccionadas = [cat for cat, var in self.vars_categorias.items() if var.get()]
        if not seleccionadas:
            messagebox.showwarning("Atención", "Debes seleccionar al menos una categoría.")
            return

        fecha_obj = None
        if self.var_usar_fecha.get():
            fecha_txt = self.entry_fecha.get().strip()
            if fecha_txt:
                try:
                    fecha_obj = datetime.strptime(fecha_txt, "%Y-%m-%d").date()
                except ValueError:
                    messagebox.showwarning("Fecha inválida", "Formato: YYYY-MM-DD\nEjemplo: 2026-03-23")
                    return

        self.btn_ejecutar.configure(state="disabled")
        self.consola.delete("0.0", "end")
        self.mostrar_bienvenida()

        hilo = threading.Thread(target=self._proceso, args=(seleccionadas, fecha_obj), daemon=True)
        hilo.start()

    def _proceso(self, seleccionadas, fecha_filtro):
        try:
            # Mapear categorías GUI → internas
            cats_internas = set()
            for cat_gui in seleccionadas:
                for c in MAPA_CATEGORIAS.get(cat_gui, [cat_gui.lower()]):
                    cats_internas.add(c)

            nombre_archivo = _siguiente_nombre_tabla()

            fecha_info = fecha_filtro.strftime("%Y-%m-%d") if fecha_filtro else "Todas (más recientes)"
            print()
            print("  ═" * 30)
            print(f"  Categorías seleccionadas: {len(seleccionadas)}")
            print(f"  Categorías internas: {', '.join(sorted(cats_internas))}")
            print(f"  Filtro de fecha: {fecha_info}")
            print(f"  Archivo de salida: {nombre_archivo}")
            print("  ═" * 30)
            print()

            resultado = buscar_noticias(
                categorias_seleccionadas=list(cats_internas),
                fecha_filtro=fecha_filtro,
                verbose=True,
            )

            noticias = resultado["noticias"]

            if noticias:
                generador = GeneradorExcelIDEAS(noticias)
                generador.generar(nombre_archivo)

                print()
                print("  ═" * 30)
                print("  RESUMEN FINAL")
                print("  ═" * 30)

                por_cat = {}
                for art in noticias:
                    cat = art["categoria"]
                    por_cat[cat] = por_cat.get(cat, 0) + 1
                for cat, cnt in sorted(por_cat.items(), key=lambda x: -x[1]):
                    bar = "█" * min(cnt, 30)
                    print(f"  {cat:<20} {cnt:>4}  {bar}")

                print()
                for fuente, cnt in sorted(resultado["conteo_fuentes"].items(), key=lambda x: -x[1]):
                    if cnt > 0:
                        print(f"  {fuente:<30} {cnt:>4} noticias")

                print(f"\n  TOTAL: {len(noticias)} artículos con fecha verificada")
                print(f"  Archivo: {nombre_archivo}")
                if resultado["fuentes_fallidas"]:
                    print(f"  Fuentes sin respuesta: {', '.join(resultado['fuentes_fallidas'])}")
                print()

                total_f = len(noticias)
                self.after(0, lambda: self._msg(
                    "Proceso Terminado",
                    f"Búsqueda finalizada.\n\nTotal: {total_f} artículos con fecha verificada.\nGuardado en: {nombre_archivo}",
                    "info"))
            else:
                msg = resultado.get("notificacion", "No se encontraron noticias.")
                log.warning(msg)
                self.after(0, lambda: self._msg("Sin resultados", msg, "warning"))

        except Exception as e:
            log.error(f"Error: {e}")
            err = str(e)
            self.after(0, lambda: self._msg("Error", f"Error inesperado:\n{err}", "error"))
        finally:
            self.after(0, lambda: self.btn_ejecutar.configure(state="normal"))

    def _msg(self, titulo, mensaje, tipo):
        self.bell()
        if tipo == "info":
            messagebox.showinfo(titulo, mensaje)
        elif tipo == "warning":
            messagebox.showwarning(titulo, mensaje)
        elif tipo == "error":
            messagebox.showerror(titulo, mensaje)


if __name__ == "__main__":
    if GUI_AVAILABLE:
        app = AppNoticiasIDEAS()
        app.mainloop()
    else:
        print("La interfaz gráfica (CustomTkinter) no está disponible en este entorno.")
