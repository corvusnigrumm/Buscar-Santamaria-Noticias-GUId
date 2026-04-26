#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EXTRACTOR DE NOTICIAS RSS — COLOMBIA
-------------------------------------
Extrae noticias de feeds RSS de los principales medios colombianos
e internacionales en español, con filtros de calidad incluidos.

Uso directo:
    python extractor_rss.py

Como módulo:
    from extractor_rss import RSSExtractor
    noticias = RSSExtractor().extraer()

Salida:
    Lista de dicts con: titulo, url, fuente, categorias, fecha, resumen

Requisitos: Solo librería estándar de Python (sin dependencias externas)
"""

import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import List, Dict, Optional

# ─────────────────────────────────────────────
# ZONA HORARIA
# ─────────────────────────────────────────────
ZONA_COLOMBIA = timezone(timedelta(hours=-5))

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

# ─────────────────────────────────────────────
# FUENTES RSS
# ─────────────────────────────────────────────
FUENTES_RSS = [
    # ── NACIONALES ──────────────────────────────────────
    {"nombre": "El Heraldo",
     "url": "https://www.elheraldo.co/arc/outboundfeeds/rss/",
     "categorias": ["general", "colombia", "politica", "economia", "cultura", "deportes", "salud", "tecnologia"],
     "tipo": "nacional"},

    {"nombre": "El Colombiano — Colombia",
     "url": "https://www.elcolombiano.com/rss/colombia.xml",
     "categorias": ["general", "colombia", "politica"], "tipo": "nacional"},
    {"nombre": "El Colombiano — Negocios",
     "url": "https://www.elcolombiano.com/rss/negocios.xml",
     "categorias": ["economia", "negocios"], "tipo": "nacional"},
    {"nombre": "El Colombiano — Deportes",
     "url": "https://www.elcolombiano.com/rss/deportes.xml",
     "categorias": ["deportes"], "tipo": "nacional"},
    {"nombre": "El Colombiano — Tecnologia",
     "url": "https://www.elcolombiano.com/rss/tecnologia.xml",
     "categorias": ["tecnologia"], "tipo": "nacional"},

    {"nombre": "El Espectador",
     "url": "https://www.elespectador.com/arc/outboundfeeds/discover/?outputType=xml",
     "categorias": ["general", "colombia", "politica", "judicial"],
     "tipo": "nacional"},

    {"nombre": "La Republica",
     "url": "https://www.larepublica.co/rss/",
     "categorias": ["economia", "negocios", "finanzas"], "tipo": "nacional"},

    {"nombre": "Semana",
     "url": "https://www.semana.com/arc/outboundfeeds/rss/?outputType=xml",
     "categorias": ["general", "colombia", "politica", "economia", "cultura", "deportes", "tecnologia", "salud"],
     "tipo": "nacional"},

    {"nombre": "La FM",
     "url": "https://www.lafm.com.co/rss/actualidad.xml",
     "categorias": ["general", "politica", "judicial", "colombia"], "tipo": "nacional"},

    {"nombre": "Caracol Radio",
     "url": "https://caracol.com.co/arc/outboundfeeds/google-news-feed/?outputType=xml",
     "categorias": ["general", "colombia", "deportes", "economia"], "tipo": "nacional"},

    {"nombre": "Infobae Colombia",
     "url": "https://www.infobae.com/arc/outboundfeeds/rss/category/colombia/",
     "categorias": ["general", "colombia", "politica", "economia", "tecnologia"],
     "tipo": "nacional"},

    {"nombre": "Minuto 30",
     "url": "https://www.minuto30.com/feed/",
     "categorias": ["general", "colombia"], "tipo": "nacional"},

    {"nombre": "Kienyke",
     "url": "https://www.kienyke.com/feed",
     "categorias": ["general", "virales", "cultura"], "tipo": "nacional"},

    {"nombre": "La Nota Economica",
     "url": "https://lanotaeconomica.com.co/feed/",
     "categorias": ["economia", "negocios", "mis finanzas"], "tipo": "nacional"},

    {"nombre": "Valora Analitik",
     "url": "https://www.valoraanalitik.com/feed/",
     "categorias": ["economia", "finanzas", "negocios"], "tipo": "nacional"},

    {"nombre": "Mis Finanzas Personales",
     "url": "https://misfinanzaspersonales.co/feed/",
     "categorias": ["mis finanzas"], "tipo": "nacional"},

    {"nombre": "Asuntos Legales",
     "url": "https://www.asuntoslegales.com.co/rss/",
     "categorias": ["justicia", "judicial", "economia"], "tipo": "nacional"},

    {"nombre": "RTVC Noticias",
     "url": "https://www.rtvcnoticias.com/rss.xml",
     "categorias": ["general", "colombia", "politica", "cultura", "deportes"], "tipo": "nacional"},

    # ── GOOGLE NEWS — COLOMBIA ───────────────────────────
    {"nombre": "GNews — Colombia",
     "url": "https://news.google.com/rss/search?q=colombia&hl=es-419&gl=CO&ceid=CO:es-419",
     "categorias": ["general", "colombia"], "tipo": "nacional"},
    {"nombre": "GNews — Economia",
     "url": "https://news.google.com/rss/search?q=economia+colombia&hl=es-419&gl=CO&ceid=CO:es-419",
     "categorias": ["economia"], "tipo": "nacional"},
    {"nombre": "GNews — Politica",
     "url": "https://news.google.com/rss/search?q=politica+colombia&hl=es-419&gl=CO&ceid=CO:es-419",
     "categorias": ["politica"], "tipo": "nacional"},
    {"nombre": "GNews — Deportes",
     "url": "https://news.google.com/rss/search?q=deportes+colombia&hl=es-419&gl=CO&ceid=CO:es-419",
     "categorias": ["deportes"], "tipo": "nacional"},
    {"nombre": "GNews — Tecnologia",
     "url": "https://news.google.com/rss/search?q=tecnologia+colombia&hl=es-419&gl=CO&ceid=CO:es-419",
     "categorias": ["tecnologia"], "tipo": "nacional"},
    {"nombre": "GNews — Salud",
     "url": "https://news.google.com/rss/search?q=salud+colombia&hl=es-419&gl=CO&ceid=CO:es-419",
     "categorias": ["salud"], "tipo": "nacional"},
    {"nombre": "GNews — Bogota",
     "url": "https://news.google.com/rss/search?q=bogota+noticias&hl=es-419&gl=CO&ceid=CO:es-419",
     "categorias": ["bogota"], "tipo": "nacional"},
    {"nombre": "GNews — Virales",
     "url": "https://news.google.com/rss/search?q=viral+tendencia+colombia&hl=es-419&gl=CO&ceid=CO:es-419",
     "categorias": ["virales"], "tipo": "nacional"},
    {"nombre": "GNews — Mis Finanzas",
     "url": "https://news.google.com/rss/search?q=devolucion+iva+OR+dian+OR+subsidio+colombia&hl=es-419&gl=CO&ceid=CO:es-419",
     "categorias": ["mis finanzas"], "tipo": "nacional"},
    {"nombre": "GNews — Motor",
     "url": "https://news.google.com/rss/search?q=carros+autos+motor+colombia&hl=es-419&gl=CO&ceid=CO:es-419",
     "categorias": ["motor"], "tipo": "nacional"},

    # ── INTERNACIONALES ──────────────────────────────────
    {"nombre": "BBC Mundo",
     "url": "https://feeds.bbci.co.uk/mundo/rss.xml",
     "categorias": ["internacional", "general", "salud", "tecnologia", "cultura"], "tipo": "internacional"},
    {"nombre": "DW Espanol",
     "url": "https://rss.dw.com/xml/rss-es-all",
     "categorias": ["internacional", "general", "politica", "cultura"], "tipo": "internacional"},
    {"nombre": "CNN Espanol",
     "url": "https://cnnespanol.cnn.com/feed/",
     "categorias": ["internacional", "general", "tecnologia", "salud"], "tipo": "internacional"},
    {"nombre": "El Pais America",
     "url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",
     "categorias": ["internacional", "cultura", "politica"], "tipo": "internacional"},
    {"nombre": "ESPN Deportes",
     "url": "https://espndeportes.espn.com/espn/rss/news",
     "categorias": ["deportes"], "tipo": "internacional"},
]

# ─────────────────────────────────────────────
# FILTROS DE CALIDAD
# ─────────────────────────────────────────────
DOMINIOS_BLOQUEADOS = {
    "portafolio.co", "eltiempo.com", "citytv.com.co",
    "cronista.com", "enter.co",
}

PATRONES_SPAM = [
    r"ingresa.{0,20}(whatsapp|telegram|canal)",
    r"suscr[ií]be(te)?.{0,20}(nuestro|canal|newsletter)",
    r"click.{0,20}(link|enlace|aqui|aqu[ií])",
    r"\bpublicidad\b",
]
_SPAM_RE = [re.compile(p, re.IGNORECASE) for p in PATRONES_SPAM]


def _normalizar_dominio(url: str) -> str:
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
        for prefix in ("www.", "m.", "amp."):
            if netloc.startswith(prefix):
                netloc = netloc[len(prefix):]
        return netloc
    except Exception:
        return ""


def _limpiar_html(texto: str) -> str:
    if not texto:
        return ""
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"&[a-z]{2,6};", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _es_spam(titulo: str) -> bool:
    return any(p.search(titulo) for p in _SPAM_RE)


def _parece_ingles(titulo: str) -> bool:
    """Detecta si un titulo esta claramente en ingles."""
    titulo = titulo.lower()
    marcadores_en = {"the ", " and ", " with ", " from ", " after ", " about ", " warns ", " says "}
    marcadores_es = {" el ", " la ", " los ", " de ", " y ", " con ", " por ", " una "}
    hits_en = sum(1 for m in marcadores_en if m in titulo)
    hits_es = sum(1 for m in marcadores_es if m in titulo)
    return hits_en >= 3 and hits_es <= 1


def _parsear_fecha(fecha_str: str) -> Optional[datetime]:
    if not fecha_str:
        return None
    try:
        return parsedate_to_datetime(fecha_str).astimezone(ZONA_COLOMBIA)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(fecha_str[:19], fmt)
        except Exception:
            pass
    return None


# ─────────────────────────────────────────────
# EXTRACTOR PRINCIPAL
# ─────────────────────────────────────────────
class RSSExtractor:
    def __init__(self, timeout: int = TIMEOUT):
        self.timeout = timeout

    def _descargar_feed(self, url: str) -> Optional[str]:
        """Descarga el contenido XML de un feed RSS."""
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                # Detectar encoding
                for enc in ("utf-8", "utf-8-sig", "latin-1", "iso-8859-1"):
                    try:
                        return raw.decode(enc)
                    except Exception:
                        continue
                return raw.decode("utf-8", errors="replace")
        except Exception as e:
            return None

    def _parsear_feed(self, xml_str: str, fuente: Dict) -> List[Dict]:
        """Parsea un XML RSS/Atom y devuelve lista de articulos."""
        articulos = []
        try:
            # Limpiar declaraciones de namespace problemáticas
            xml_str = re.sub(r'<\?xml[^>]+\?>', '', xml_str, count=1)
            root = ET.fromstring(xml_str.encode("utf-8", errors="replace"))
        except ET.ParseError:
            try:
                # Segundo intento: eliminar caracteres problematicos
                xml_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', xml_str)
                root = ET.fromstring(xml_str.encode("utf-8", errors="replace"))
            except Exception:
                return []

        # Soporte RSS 2.0 y Atom
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item") or root.findall(".//atom:entry", ns)

        for item in items:
            def _get(tag, ns_prefix=""):
                node = item.find(f"{ns_prefix}{tag}")
                return _limpiar_html(node.text or "") if node is not None else ""

            titulo  = _get("title")
            url     = _get("link") or _get("guid")
            resumen = _get("description") or _get("summary")
            fecha_s = _get("pubDate") or _get("published") or _get("updated")

            # Validaciones básicas
            if not titulo or len(titulo) < 15:
                continue
            if not url or not url.startswith("http"):
                continue
            if _es_spam(titulo):
                continue
            if _parece_ingles(titulo):
                continue

            dominio = _normalizar_dominio(url)
            if dominio in DOMINIOS_BLOQUEADOS:
                continue

            articulos.append({
                "titulo":     titulo,
                "url":        url,
                "fuente":     fuente["nombre"],
                "categorias": fuente["categorias"],
                "tipo":       fuente.get("tipo", "nacional"),
                "fecha":      _parsear_fecha(fecha_s).isoformat() if _parsear_fecha(fecha_s) else fecha_s,
                "resumen":    resumen[:300] if resumen else "",
                "dominio":    dominio,
            })

        return articulos

    def extraer(
        self,
        fuentes: List[Dict] = None,
        max_por_fuente: int = 10,
        solo_nacionales: bool = False,
    ) -> List[Dict]:
        """
        Extrae noticias de todos los feeds RSS configurados.

        Args:
            fuentes:         Lista de fuentes (por defecto usa FUENTES_RSS global).
            max_por_fuente:  Maximo de articulos por fuente.
            solo_nacionales: Si True, omite fuentes internacionales.

        Returns:
            Lista de dicts con las noticias extraidas, sin duplicados por URL.
        """
        if fuentes is None:
            fuentes = FUENTES_RSS

        if solo_nacionales:
            fuentes = [f for f in fuentes if f.get("tipo") == "nacional"]

        todas = []
        urls_vistas = set()

        for i, fuente in enumerate(fuentes, 1):
            nombre = fuente["nombre"]
            print(f"  [{i:02d}/{len(fuentes)}] {nombre}...", end=" ", flush=True)

            xml_str = self._descargar_feed(fuente["url"])
            if not xml_str:
                print("ERROR (sin respuesta)")
                continue

            articulos = self._parsear_feed(xml_str, fuente)

            nuevos = 0
            for art in articulos[:max_por_fuente]:
                if art["url"] not in urls_vistas:
                    urls_vistas.add(art["url"])
                    todas.append(art)
                    nuevos += 1

            print(f"{nuevos} noticias")
            time.sleep(0.2)

        # Ordenar por fecha descendente (mas recientes primero)
        def _sort_key(a):
            try:
                return a.get("fecha") or ""
            except Exception:
                return ""

        todas.sort(key=_sort_key, reverse=True)
        return todas


# ─────────────────────────────────────────────
# EJECUCION DIRECTA
# ─────────────────────────────────────────────
if __name__ == "__main__":
    from collections import Counter

    print("=" * 55)
    print("  EXTRACTOR RSS — NOTICIAS COLOMBIA")
    print("=" * 55)

    extractor = RSSExtractor()
    noticias  = extractor.extraer(max_por_fuente=10)

    # Resumen por categoria
    todas_cats = []
    for n in noticias:
        todas_cats.extend(n.get("categorias", []))
    conteo = Counter(todas_cats)

    print("\n" + "=" * 55)
    print(f"  TOTAL: {len(noticias)} noticias unicas")
    print("=" * 55)
    for cat, cnt in conteo.most_common(15):
        print(f"  {cat:<18} {cnt:>4} articulos")
    print("=" * 55)

    # Guardar JSON
    ts          = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"noticias_rss_{ts}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(noticias, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] Guardado en: {output_file}")
