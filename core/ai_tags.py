import os
import json
import asyncio
import hashlib
import time
import re
import unicodedata
from core.logger import logger as log
from core.filters import DATA_APP_DIR

CACHE_FILE = os.path.join(DATA_APP_DIR, "ai_tags_cache.json")
_cache = {}

def _cargar_cache():
    global _cache
    if not _cache and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                _cache = json.load(f)
        except Exception as e:
            log.warning(f"[Groq AI] Error leyendo caché de tags: {e}")
            _cache = {}

def _guardar_cache():
    if not _cache:
        return
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning(f"[Groq AI] Error guardando caché de tags: {e}")

def _hash_articulo(titulo: str, url: str) -> str:
    clave = f"{titulo.strip().lower()}|{url.strip().lower()}"
    return hashlib.md5(clave.encode("utf-8")).hexdigest()


def _texto_ascii(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", texto).strip()


def _slugify(texto: str, max_palabras: int = 10) -> str:
    tokens = re.findall(r"[a-z0-9]+", _texto_ascii(texto).lower())
    return "-".join(tokens[:max_palabras])


def _recortar(texto: str, max_len: int) -> str:
    texto = re.sub(r"\s+", " ", (texto or "")).strip()
    if len(texto) <= max_len:
        return texto
    return texto[: max_len - 3].rstrip(" ,.;:") + "..."


def _deduplicar_keywords(keywords: list[str]) -> list[str]:
    vistos = set()
    salida = []
    for kw in keywords:
        kw_norm = _texto_ascii(kw).lower()
        if not kw_norm or kw_norm in vistos:
            continue
        vistos.add(kw_norm)
        salida.append(kw.strip())
    return salida


def _keywords_desde_articulo(art: dict) -> list[str]:
    base = []
    categoria = (art.get("categoria") or "").strip().title()
    fuente = (art.get("fuente") or "").strip()
    titulo = art.get("titulo", "")
    tags = art.get("tags", []) or []

    if tags:
        base.extend(tags)

    palabras_titulo = re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñ0-9]{4,}", titulo)
    base.extend(palabras_titulo[:4])

    if categoria:
        base.append(categoria)
    if fuente:
        base.append(fuente)

    return _deduplicar_keywords(base)[:6]


def _clasificar_intencion_busqueda(texto_ref: str, categoria: str, keyword_principal: str) -> tuple[str, str]:
    texto = (texto_ref or "").lower()
    categoria_l = (categoria or "").lower()
    keyword_l = (keyword_principal or "").lower()

    patrones_navegacional = (
        "tn", "tn argentina", "semana", "infobae", "el colombiano", "el heraldo",
        "forbes", "valora analitik", "la republica",
    )
    patrones_transaccional = (
        "comprar", "precio", "cuanto cuesta", "cotizacion", "cotiza", "solicitar",
        "suscribirse", "descargar", "pagar", "tramitar", "inscribirse",
    )
    patrones_comercial = (
        "mejor", "mejores", "vs", "comparativa", "comparacion", "vale la pena",
        "review", "ranking", "top", "alternativas",
    )
    patrones_informacional = (
        "como", "guia", "que es", "para que sirve", "paso a paso", "consejos",
        "tips", "beneficios", "errores comunes", "claves", "tutorial",
    )

    if any(p in texto for p in patrones_transaccional):
        return "transaccional", "Hay verbos de accion o conversion"
    if any(p in texto for p in patrones_comercial):
        return "comercial", "Predomina comparacion o evaluacion"
    if any(p in texto for p in patrones_informacional):
        return "informacional", "Predomina busqueda de explicacion o ayuda"

    if keyword_l and any(marca in keyword_l for marca in patrones_navegacional):
        return "navegacional", "La keyword principal parece de marca o medio"
    if any(p in texto for p in patrones_navegacional):
        return "navegacional", "Se detectan marcas o medios concretos"

    if categoria_l in {"finanzas", "mis finanzas", "economia"} and any(
        p in texto for p in ("subsidio", "credito", "tarjeta", "impuesto", "factura", "devolucion")
    ):
        return "transaccional", "Tema financiero orientado a accion puntual"
    if categoria_l in {"tecnologia", "tendencias", "vida", "salud", "evergreen"}:
        return "informacional", "Categoria asociada a consulta explicativa"

    return "informacional", "Clasificacion por defecto"


def enriquecer_metadatos_seo(articulo: dict) -> dict:
    art = dict(articulo)
    titulo = (art.get("titulo") or "").strip()
    resumen = (art.get("resumen") or "").strip()
    categoria = (art.get("categoria") or "General").strip()
    tags = art.get("tags", []) or []
    trend_score = int(art.get("trend_score", 0) or 0)

    keywords = _keywords_desde_articulo({**art, "tags": tags})
    keyword_principal = keywords[0] if keywords else categoria.title()

    seo_title = _recortar(f"{titulo} | {categoria.title()} | Santamaria", 67)
    meta_seed = resumen or titulo
    meta_description = _recortar(
        f"{meta_seed} Claves SEO sobre {keyword_principal.lower()} y contexto de {categoria.lower()}.",
        158,
    )

    texto_ref = _texto_ascii(f"{titulo} {resumen} {' '.join(tags)}").lower()
    senales_evergreen = (
        "como", "guia", "consejos", "tips", "que es", "para que sirve",
        "beneficios", "errores comunes", "paso a paso", "claves", "habitos",
    )
    senales_coyuntura = (
        "hoy", "ayer", "ultima hora", "urgente", "en vivo", "esta semana",
        "trm", "dolar", "partido", "elecciones", "accidente",
    )
    evergreen_score = 35
    evergreen_score += min(40, sum(12 for s in senales_evergreen if s in texto_ref))
    evergreen_score -= min(30, sum(10 for s in senales_coyuntura if s in texto_ref))
    evergreen_score += min(15, max(0, 80 - trend_score) // 8)
    evergreen_score = max(0, min(100, evergreen_score))

    if evergreen_score >= 75:
        evergreen_intent = "alto"
        angle = "Guia practica de alto potencial evergreen"
    elif evergreen_score >= 55:
        evergreen_intent = "medio"
        angle = "Enfoque explicativo con oportunidad de actualizar"
    else:
        evergreen_intent = "bajo"
        angle = "Mas cercano a tendencia o coyuntura"

    search_intent, search_intent_reason = _clasificar_intencion_busqueda(
        texto_ref,
        categoria,
        keyword_principal,
    )

    art["focus_keywords"] = keywords
    art["seo_title"] = seo_title
    art["seo_slug"] = _slugify(keyword_principal or titulo or categoria)
    art["meta_description"] = meta_description
    art["seo_angle"] = angle
    art["search_intent"] = search_intent
    art["search_intent_reason"] = search_intent_reason
    art["evergreen_score"] = evergreen_score
    art["evergreen_intent"] = evergreen_intent
    return art

class GeminiTagService:
    """Servicio que enriquece artículos con tags SEO y scoring de tendencias via Groq AI (Llama 3).
       Mantenemos el nombre de clase 'GeminiTagService' por compatibilidad con el resto del código."""

    BATCH_SIZE = 15  # artículos por request
    MAX_RPM = 25     # requests por minuto permitidos por Groq

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        self.client = None
        self._disponible = False

        # Intentar leer desde Streamlit secrets (para Streamlit Cloud)
        if not self.api_key:
            try:
                import streamlit as st
                if "GROQ_API_KEY" in st.secrets:
                    self.api_key = st.secrets["GROQ_API_KEY"]
            except Exception as e:
                log.warning(f"No se pudieron leer Streamlit secrets: {e}")

        if not self.api_key:
            log.warning("[Groq AI] No se encontró GROQ_API_KEY. Tags deshabilitados.")
            return

        try:
            from groq import AsyncGroq
            self.client = AsyncGroq(api_key=self.api_key)
            self._disponible = True
            log.info("[Groq AI] Servicio de tags AI inicializado correctamente.")
        except ImportError:
            log.warning("[Groq AI] Paquete 'groq' no instalado. pip install groq")
        except Exception as e:
            log.warning(f"[Groq AI] Error inicializando cliente: {e}")

    @property
    def disponible(self) -> bool:
        return self._disponible

    def _construir_prompt(self, articulos_batch: list[dict]) -> str:
        articulos_texto = []
        for i, art in enumerate(articulos_batch):
            articulos_texto.append(
                f"[{i}] TÍTULO: {art.get('titulo', '')}\n"
                f"    RESUMEN: {art.get('resumen', '')[:200]}\n"
                f"    FUENTE: {art.get('fuente', '')}\n"
                f"    CATEGORÍA: {art.get('categoria', '')}"
            )
        bloque = "\n\n".join(articulos_texto)

        return f"""Eres un analista SEO experto en tendencias de noticias en Colombia y Latinoamérica.
Genera para cada artículo: tags (3-5 keywords SEO relevantes), trend_score (0-100), trend_reason (máximo 15 palabras) y seo_angle (máximo 12 palabras).

ARTÍCULOS:
{bloque}

Responde ÚNICAMENTE con un JSON object válido que contenga un array llamado "resultados".
Formato exacto:
{{
  "resultados": [
    {{"id": 0, "tags": ["tag1", "tag2"], "trend_score": 75, "trend_reason": "Razón breve", "seo_angle": "Guia practica"}}
  ]
}}"""

    async def _llamar_ai(self, prompt: str) -> list[dict] | None:
        if not self.client:
            return None

        try:
            response = await self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                response_format={"type": "json_object"},
                temperature=0.3
            )

            texto = response.choices[0].message.content.strip()
            data = json.loads(texto)
            return data.get("resultados", [])

        except json.JSONDecodeError as e:
            log.warning(f"[Groq AI] Respuesta no es JSON válido: {e}")
            return None
        except Exception as e:
            log.warning(f"[Groq AI] Error en llamada API: {e}")
            return None

    async def generar_tags_batch(self, articulos: list[dict], callback=None) -> list[dict]:
        if not self._disponible:
            log.info("[Groq AI] Servicio no disponible. Retornando artículos sin tags.")
            return articulos

        _cargar_cache()

        total = len(articulos)
        procesados = 0
        sin_cache = []
        indices_sin_cache = []

        for i, art in enumerate(articulos):
            h = _hash_articulo(art.get("titulo", ""), art.get("url", ""))
            if h in _cache:
                cached = _cache[h]
                art["tags"] = cached.get("tags", [])
                art["trend_score"] = cached.get("trend_score", 0)
                art["trend_reason"] = cached.get("trend_reason", "")
                art["seo_angle"] = cached.get("seo_angle", "")
                art.update(enriquecer_metadatos_seo(art))
                procesados += 1
            else:
                sin_cache.append(art)
                indices_sin_cache.append(i)

        if sin_cache:
            log.info(f"[Groq AI] {procesados}/{total} desde caché. Procesando {len(sin_cache)} artículos nuevos...")
        else:
            log.info(f"[Groq AI] {total}/{total} artículos ya en caché. Sin llamadas API.")
            return articulos

        batches = [
            sin_cache[i:i + self.BATCH_SIZE]
            for i in range(0, len(sin_cache), self.BATCH_SIZE)
        ]

        for batch_idx, batch in enumerate(batches):
            if batch_idx > 0:
                await asyncio.sleep(60.0 / self.MAX_RPM)

            prompt = self._construir_prompt(batch)
            resultados = await self._llamar_ai(prompt)

            if resultados and isinstance(resultados, list):
                for item in resultados:
                    idx_local = item.get("id", -1)
                    if 0 <= idx_local < len(batch):
                        art = batch[idx_local]
                        art["tags"] = item.get("tags", [])
                        art["trend_score"] = item.get("trend_score", 0)
                        art["trend_reason"] = item.get("trend_reason", "")
                        art["seo_angle"] = item.get("seo_angle", "")
                        art.update(enriquecer_metadatos_seo(art))

                        h = _hash_articulo(art.get("titulo", ""), art.get("url", ""))
                        _cache[h] = {
                            "tags": art["tags"],
                            "trend_score": art["trend_score"],
                            "trend_reason": art["trend_reason"],
                            "seo_angle": art.get("seo_angle", ""),
                        }
            else:
                log.warning(f"[Groq AI] Batch {batch_idx + 1}/{len(batches)} sin resultados.")
                for art in batch:
                    art.setdefault("tags", [])
                    art.setdefault("trend_score", 0)
                    art.setdefault("trend_reason", "Sin datos")
                    art.setdefault("seo_angle", "")
                    art.update(enriquecer_metadatos_seo(art))

            procesados += len(batch)
            if callback:
                callback(procesados, total)

            log.info(f"[Groq AI] Progreso: {procesados}/{total} artículos procesados.")

        _guardar_cache()
        log.info(f"[Groq AI] ✓ Enriquecimiento completado. {total} artículos con tags y scores.")
        return articulos
