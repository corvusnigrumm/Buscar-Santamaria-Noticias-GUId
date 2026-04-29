import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import re
import urllib.parse
import time
import html
import base64
from datetime import datetime, timedelta, timezone, date
from email.utils import parsedate_to_datetime

from core.logger import logger
from core.config import HEADERS, TIMEOUT, ZONA_COLOMBIA, FUENTES_RSS
from core.filters import (
    _limpiar_html, _normalizar, _parece_ingles_puro, 
    _extraer_palabras_clave, _construir_huella_repeticion, 
    _extraer_tokens_relevantes, _esta_bloqueado, _es_razon_medio_prohibido,
    _extraer_destinos_google_news
)

async def fetch_rss_async(session, url, max_retries=3):
    """Descarga el contenido de la URL de forma asíncrona usando aiohttp."""
    for attempt in range(max_retries):
        try:
            async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as resp:
                if resp.status == 429:
                    await asyncio.sleep(1.5 ** attempt)
                    continue
                if resp.status != 200:
                    return None
                contenido = await resp.read()
                encoding = "utf-8"
                ct = resp.headers.get("Content-Type", "")
                if "charset=" in ct:
                    encoding = ct.split("charset=")[-1].strip().split(";")[0]
                try:
                    return contenido.decode(encoding)
                except Exception:
                    return contenido.decode("utf-8", errors="replace")
        except Exception:
            pass
    return None

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

def parsear_feed(xml_str, nombre_fuente):
    articulos = []
    lista_negra = []
    try:
        xml_str = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", xml_str)
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return articulos, lista_negra

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
                lista_negra.append(art_data)
            continue

        articulos.append(art_data)

    return articulos, lista_negra

def parsear_forbes_economia_html(html_str, nombre_fuente):
    articulos = []
    lista_negra = []
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
                lista_negra.append(art_data)
            continue

        articulos.append(art_data)

    return articulos, lista_negra

async def fetch_fuente_async(session, fuente, fecha_inicio, fecha_fin):
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
    lista_negra_fuente = []
    responded = False
    
    for u in urls_to_fetch:
        xml_str = await fetch_rss_async(session, u)
        if xml_str:
            responded = True
            if nombre == "Forbes Colombia" and "economia-y-finanzas" in u:
                arts, ln = parsear_forbes_economia_html(xml_str, nombre)
            else:
                arts, ln = parsear_feed(xml_str, nombre)
            articulos_fuente.extend(arts)
            lista_negra_fuente.extend(ln)
        if is_google and len(urls_to_fetch) > 1:
            await asyncio.sleep(0.5)

    return nombre, responded, articulos_fuente, lista_negra_fuente
