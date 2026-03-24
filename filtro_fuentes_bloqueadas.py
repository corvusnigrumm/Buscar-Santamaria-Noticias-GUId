"""
╔══════════════════════════════════════════════════════════════════╗
║        FILTRO DE FUENTES BLOQUEADAS — Portafolio & El Tiempo     ║
║        Análisis exhaustivo multicapa en tiempo real              ║
╚══════════════════════════════════════════════════════════════════╝

Capas de detección:
  1. Dominio principal y subdominios
  2. Variantes de URL (www, http, https, mobile, amp)
  3. URLs acortadas / redireccionadas (resolución real)
  4. Metadatos HTML (og:site_name, canonical, publisher)
  5. Contenido textual (firmas, copyright, bylines)
  6. Dominios hermanos del mismo grupo editorial (Casa Editorial El Tiempo)
"""

import re
import urllib.parse
import urllib.request
import socket
from typing import Optional


# ─────────────────────────────────────────────
#  CONFIGURACIÓN CENTRAL DE FUENTES BLOQUEADAS
# ─────────────────────────────────────────────

BLOCKED_SOURCES = {
    "portafolio": {
        "display_name": "Portafolio",
        "domains": [
            "portafolio.co",
            "www.portafolio.co",
            "m.portafolio.co",
            "amp.portafolio.co",
            "blogs.portafolio.co",
            "static.portafolio.co",
        ],
        # Patrones que aparecen en URLs de artículos reales
        "url_patterns": [
            r"portafolio\.co/",
            r"portafolio\.co$",
        ],
        # Firmas y marcas que aparecen en el contenido HTML
        "content_signatures": [
            "portafolio.co",
            "Portafolio.co",
            "Revista Portafolio",
            "PREMIOS PORTAFOLIO",
            "Indicadores Económicos | Portafolio",
            "Noticias económicas de Colombia",  # título exclusivo del sitio
        ],
        # Metaetiquetas og: y twitter: reales del sitio
        "meta_signatures": [
            "portafolio",
            "Portafolio",
        ],
    },

    "eltiempo": {
        "display_name": "El Tiempo",
        "domains": [
            "eltiempo.com",
            "www.eltiempo.com",
            "m.eltiempo.com",
            "amp.eltiempo.com",
            "static.eltiempo.com",
            "especiales.eltiempo.com",
            "blogs.eltiempo.com",
            # Dominios hermanos del mismo grupo (Casa Editorial El Tiempo)
            "enter.co",            # tecnología, mismo grupo
            "citytv.com.co",       # televisión, mismo grupo
            "elempleo.com",        # empleo, mismo grupo (participación)
        ],
        "url_patterns": [
            r"eltiempo\.com/",
            r"eltiempo\.com$",
        ],
        "content_signatures": [
            "eltiempo.com",
            "ELTIEMPO.COM",
            "EL TIEMPO",
            "El Tiempo",
            "club el tiempo vivamos",
            "El Tiempo Play",
            "Casa Editorial El Tiempo",
            "Sigue toda la información",        # frase de cierre típica de El Tiempo
            "Ingrese o regístrese acá para guardar los artículos",  # frase exclusiva
            "Este resumen fue construido con ayuda de IA",          # firma IA El Tiempo
        ],
        "meta_signatures": [
            "eltiempo",
            "El Tiempo",
            "ELTIEMPO",
        ],
    },
}

# IPs conocidas (como capa adicional; se puede expandir con nslookup)
# Estas son aproximaciones — la capa de dominio es la principal
BLOCKED_IP_RANGES: list[str] = []  # Opcional: añadir rangos CIDR si se necesita


# ─────────────────────────────────────────────
#  FUNCIONES DE ANÁLISIS
# ─────────────────────────────────────────────

def _extract_domain(url: str) -> str:
    """Extrae el dominio limpio (sin www, sin puerto) de una URL."""
    try:
        parsed = urllib.parse.urlparse(url.strip())
        netloc = parsed.netloc.lower()
        # Eliminar credenciales si las hay (user:pass@host)
        if "@" in netloc:
            netloc = netloc.split("@", 1)[1]
        # Eliminar puerto
        netloc = netloc.split(":")[0]
        return netloc
    except Exception:
        return ""


def _normalize_url(url: str) -> str:
    """Normaliza una URL para comparación (minúsculas, sin trailing slash)."""
    url = url.strip().lower()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def _check_domain(domain: str) -> tuple[bool, Optional[str]]:
    """
    Verifica si un dominio pertenece a alguna fuente bloqueada.
    Retorna (bloqueado, nombre_fuente).
    """
    domain = domain.lower().strip()

    for source_key, source_data in BLOCKED_SOURCES.items():
        for blocked_domain in source_data["domains"]:
            # Coincidencia exacta
            if domain == blocked_domain:
                return True, source_data["display_name"]
            # El dominio termina con el dominio bloqueado (cubre subdominios)
            if domain.endswith("." + blocked_domain):
                return True, source_data["display_name"]
            # El dominio bloqueado está contenido (para "portafolio.co" dentro de cualquier variante)
            root = blocked_domain.lstrip("www.").lstrip("m.").lstrip("amp.")
            if domain.endswith(root) and len(root) > 8:
                return True, source_data["display_name"]

    return False, None


def _check_url_patterns(url: str) -> tuple[bool, Optional[str]]:
    """Verifica patrones regex en la URL completa."""
    url_lower = url.lower()
    for source_key, source_data in BLOCKED_SOURCES.items():
        for pattern in source_data["url_patterns"]:
            if re.search(pattern, url_lower):
                return True, source_data["display_name"]
    return False, None


def _check_content_signatures(text: str) -> tuple[bool, Optional[str]]:
    """
    Busca firmas textuales en el contenido HTML o texto de un artículo.
    Útil cuando la URL ya fue acortada o redirigida.
    """
    for source_key, source_data in BLOCKED_SOURCES.items():
        for sig in source_data["content_signatures"]:
            if sig in text:
                return True, source_data["display_name"]
    return False, None


def _check_meta_tags(html: str) -> tuple[bool, Optional[str]]:
    """
    Analiza metatags HTML: og:site_name, og:url, canonical, twitter:site.
    """
    meta_patterns = [
        r'og:site_name["\s]+content=["\']([^"\']+)["\']',
        r'content=["\']([^"\']+)["\'][^>]+property=["\']og:site_name["\']',
        r'twitter:site["\s]+content=["\']@?([^"\']+)["\']',
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']publisher["\'][^>]+content=["\']([^"\']+)["\']',
    ]

    extracted_values = []
    for pattern in meta_patterns:
        matches = re.findall(pattern, html, re.IGNORECASE)
        extracted_values.extend(matches)

    for value in extracted_values:
        value_lower = value.lower()
        for source_key, source_data in BLOCKED_SOURCES.items():
            for sig in source_data["meta_signatures"]:
                if sig.lower() in value_lower:
                    return True, source_data["display_name"]

            # También verificar si el valor es una URL del dominio bloqueado
            extracted_domain = _extract_domain(value)
            if extracted_domain:
                blocked, name = _check_domain(extracted_domain)
                if blocked:
                    return True, name

    return False, None


def _resolve_redirect(url: str, timeout: int = 5) -> str:
    """
    Resuelve redirecciones HTTP para detectar URLs acortadas
    que apunten a Portafolio o El Tiempo.
    Retorna la URL final (o la original si falla).
    """
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; NewsFilter/1.0)"},
            method="HEAD"
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.geturl()
    except Exception:
        return url


# ─────────────────────────────────────────────
#  FUNCIÓN PRINCIPAL DE FILTRO
# ─────────────────────────────────────────────

def es_fuente_bloqueada(
    url: str = "",
    titulo: str = "",
    contenido_html: str = "",
    fuente_texto: str = "",
    resolver_redireccion: bool = True,
    verbose: bool = False,
) -> dict:
    """
    Sistema de filtro exhaustivo multicapa.

    Parámetros:
        url              : URL del artículo (puede ser acortada)
        titulo           : Título del artículo (para detección textual)
        contenido_html   : HTML completo de la página (para metatags y firmas)
        fuente_texto     : Nombre de la fuente como texto plano ("El Tiempo", etc.)
        resolver_redireccion : Si True, resuelve redirecciones HTTP (requiere red)
        verbose          : Si True, imprime el log de detección por capas

    Retorna un dict:
        {
          "bloqueado": bool,
          "fuente_detectada": str | None,
          "capa_deteccion": str | None,   # qué capa lo detectó
          "url_final": str,               # URL después de resolver redirección
          "razon": str,                   # descripción legible
        }
    """
    resultado = {
        "bloqueado": False,
        "fuente_detectada": None,
        "capa_deteccion": None,
        "url_final": url,
        "razon": "Fuente permitida",
    }

    def _log(msg):
        if verbose:
            print(f"  [FILTRO] {msg}")

    # ── CAPA 0: Nombre de fuente explícito ─────────────────────────────────
    if fuente_texto:
        bloqueado, nombre = _check_content_signatures(fuente_texto)
        if bloqueado:
            resultado.update({
                "bloqueado": True,
                "fuente_detectada": nombre,
                "capa_deteccion": "nombre_fuente_explicito",
                "razon": f"Fuente '{nombre}' está en lista de bloqueo (nombre explícito)",
            })
            _log(f"BLOQUEADO en Capa 0 — Nombre explícito: {nombre}")
            return resultado

    # ── CAPA 1: Dominio de la URL original ────────────────────────────────
    if url:
        domain = _extract_domain(url)
        if domain:
            bloqueado, nombre = _check_domain(domain)
            if bloqueado:
                resultado.update({
                    "bloqueado": True,
                    "fuente_detectada": nombre,
                    "capa_deteccion": "dominio_url_original",
                    "razon": f"Dominio '{domain}' pertenece a {nombre}",
                })
                _log(f"BLOQUEADO en Capa 1 — Dominio: {domain} → {nombre}")
                return resultado

    # ── CAPA 2: Patrones regex en URL ─────────────────────────────────────
    if url:
        bloqueado, nombre = _check_url_patterns(url)
        if bloqueado:
            resultado.update({
                "bloqueado": True,
                "fuente_detectada": nombre,
                "capa_deteccion": "patron_regex_url",
                "razon": f"URL contiene patrón de {nombre}",
            })
            _log(f"BLOQUEADO en Capa 2 — Patrón regex URL → {nombre}")
            return resultado

    # ── CAPA 3: Resolución de redirecciones ───────────────────────────────
    if url and resolver_redireccion:
        _log(f"Resolviendo redirección de: {url[:80]}...")
        url_final = _resolve_redirect(url)
        resultado["url_final"] = url_final

        if url_final != url:
            _log(f"URL final: {url_final[:80]}")
            domain_final = _extract_domain(url_final)
            bloqueado, nombre = _check_domain(domain_final)
            if not bloqueado:
                bloqueado, nombre = _check_url_patterns(url_final)

            if bloqueado:
                resultado.update({
                    "bloqueado": True,
                    "fuente_detectada": nombre,
                    "capa_deteccion": "resolucion_redireccion",
                    "razon": f"URL redirige a {nombre} ({url_final[:60]}...)",
                })
                _log(f"BLOQUEADO en Capa 3 — Redirección → {nombre}")
                return resultado

    # ── CAPA 4: Metatags HTML ─────────────────────────────────────────────
    if contenido_html:
        bloqueado, nombre = _check_meta_tags(contenido_html)
        if bloqueado:
            resultado.update({
                "bloqueado": True,
                "fuente_detectada": nombre,
                "capa_deteccion": "metatags_html",
                "razon": f"Metatags HTML identifican la fuente como {nombre}",
            })
            _log(f"BLOQUEADO en Capa 4 — Metatags → {nombre}")
            return resultado

    # ── CAPA 5: Firmas textuales en contenido/título ──────────────────────
    texto_combinado = f"{titulo} {contenido_html}"
    if texto_combinado.strip():
        bloqueado, nombre = _check_content_signatures(texto_combinado)
        if bloqueado:
            resultado.update({
                "bloqueado": True,
                "fuente_detectada": nombre,
                "capa_deteccion": "firmas_textuales_contenido",
                "razon": f"Contenido contiene firmas textuales de {nombre}",
            })
            _log(f"BLOQUEADO en Capa 5 — Firmas en contenido → {nombre}")
            return resultado

    _log("PERMITIDO — Ninguna capa detectó coincidencia con fuentes bloqueadas.")
    return resultado


# ─────────────────────────────────────────────
#  FILTRO DE LISTAS (batch)
# ─────────────────────────────────────────────

def filtrar_articulos(
    articulos: list[dict],
    campo_url: str = "url",
    campo_titulo: str = "titulo",
    campo_fuente: str = "fuente",
    campo_html: str = "html",
    resolver_redireccion: bool = False,
    verbose: bool = False,
) -> tuple[list[dict], list[dict]]:
    """
    Filtra una lista de artículos.

    Parámetros:
        articulos          : Lista de dicts con datos de artículos
        campo_url          : Nombre del campo que contiene la URL
        campo_titulo       : Nombre del campo que contiene el título
        campo_fuente       : Nombre del campo con nombre de la fuente
        campo_html         : Nombre del campo con HTML (opcional)
        resolver_redireccion: Resolver redirecciones HTTP (más lento)
        verbose            : Mostrar log detallado

    Retorna:
        (articulos_permitidos, articulos_bloqueados)
    """
    permitidos = []
    bloqueados = []

    for i, articulo in enumerate(articulos):
        resultado = es_fuente_bloqueada(
            url=articulo.get(campo_url, ""),
            titulo=articulo.get(campo_titulo, ""),
            contenido_html=articulo.get(campo_html, ""),
            fuente_texto=articulo.get(campo_fuente, ""),
            resolver_redireccion=resolver_redireccion,
            verbose=verbose,
        )

        articulo["_filtro"] = resultado  # Adjuntar resultado al artículo

        if resultado["bloqueado"]:
            bloqueados.append(articulo)
            if verbose:
                print(f"  [{i+1}] ❌ BLOQUEADO: {articulo.get(campo_titulo, 'Sin título')[:60]}")
                print(f"       Razón: {resultado['razon']}")
        else:
            permitidos.append(articulo)
            if verbose:
                print(f"  [{i+1}] ✅ PERMITIDO: {articulo.get(campo_titulo, 'Sin título')[:60]}")

    return permitidos, bloqueados


# ─────────────────────────────────────────────
#  DEMO / PRUEBAS EN TIEMPO REAL
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 65)
    print("  SISTEMA DE FILTRO — Portafolio & El Tiempo")
    print("  Análisis multicapa en tiempo real")
    print("=" * 65)

    casos_prueba = [
        # ── Casos que DEBEN ser bloqueados ──────────────────────────────
        {
            "titulo": "Ecopetrol anuncia resultados del Q1 2025",
            "url": "https://www.portafolio.co/energia/ecopetrol-resultados-489589",
            "fuente": "",
        },
        {
            "titulo": "Reforma tributaria: lo que debe saber",
            "url": "https://www.eltiempo.com/economia/reforma-tributaria-3540000",
            "fuente": "",
        },
        {
            "titulo": "Artículo en subdominio de blogs",
            "url": "https://blogs.portafolio.co/finanzas/tip-del-dia",
            "fuente": "",
        },
        {
            "titulo": "Artículo sin URL, fuente explícita",
            "url": "",
            "fuente": "El Tiempo",
        },
        {
            "titulo": "Artículo de El Tiempo vía nombre",
            "url": "",
            "fuente": "Portafolio",
        },
        {
            "titulo": "Artículo con firma en contenido",
            "url": "https://ejemplo-agregador.com/noticia-123",
            "fuente": "",
            "html": '<meta property="og:site_name" content="EL TIEMPO" /><p>Noticias</p>',
        },

        # ── Casos que DEBEN ser PERMITIDOS ──────────────────────────────
        {
            "titulo": "Colombia enfrenta déficit fiscal en 2025",
            "url": "https://www.semana.com/economia/articulo/deficit-fiscal-2025",
            "fuente": "Semana",
        },
        {
            "titulo": "BanRep sube tasas de interés",
            "url": "https://larepublica.co/economia/banrep-tasas-2025",
            "fuente": "La República",
        },
        {
            "titulo": "Inflación en Colombia cede al 4,8%",
            "url": "https://www.dinero.com/economia/inflacion-colombia-2025",
            "fuente": "Dinero",
        },
        {
            "titulo": "Reuters: Oil prices rise amid tensions",
            "url": "https://www.reuters.com/business/energy/oil-prices-2025",
            "fuente": "Reuters",
        },
    ]

    articulos_permitidos, articulos_bloqueados = filtrar_articulos(
        articulos=casos_prueba,
        campo_html="html",
        resolver_redireccion=False,  # True para resolver acortadores (requiere red)
        verbose=True,
    )

    print("\n" + "─" * 65)
    print(f"  RESUMEN FINAL")
    print("─" * 65)
    print(f"  Total artículos analizados : {len(casos_prueba)}")
    print(f"  ✅ Permitidos              : {len(articulos_permitidos)}")
    print(f"  ❌ Bloqueados              : {len(articulos_bloqueados)}")

    if articulos_bloqueados:
        print("\n  Artículos bloqueados:")
        for a in articulos_bloqueados:
            f = a["_filtro"]
            print(f"    • {a['titulo'][:55]}")
            print(f"      Fuente: {f['fuente_detectada']} | Capa: {f['capa_deteccion']}")

    if articulos_permitidos:
        print("\n  Artículos permitidos:")
        for a in articulos_permitidos:
            print(f"    • {a['titulo'][:55]}")
