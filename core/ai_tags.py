import os
import json
import asyncio
import hashlib
import time
from util.logger import log
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
Genera para cada artículo: tags (3-5 keywords SEO relevantes), trend_score (0-100), y trend_reason (máximo 15 palabras).

ARTÍCULOS:
{bloque}

Responde ÚNICAMENTE con un JSON object válido que contenga un array llamado "resultados".
Formato exacto:
{{
  "resultados": [
    {{"id": 0, "tags": ["tag1", "tag2"], "trend_score": 75, "trend_reason": "Razón breve"}}
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

                        h = _hash_articulo(art.get("titulo", ""), art.get("url", ""))
                        _cache[h] = {
                            "tags": art["tags"],
                            "trend_score": art["trend_score"],
                            "trend_reason": art["trend_reason"],
                        }
            else:
                log.warning(f"[Groq AI] Batch {batch_idx + 1}/{len(batches)} sin resultados.")
                for art in batch:
                    art.setdefault("tags", [])
                    art.setdefault("trend_score", 0)
                    art.setdefault("trend_reason", "Sin datos")

            procesados += len(batch)
            if callback:
                callback(procesados, total)

            log.info(f"[Groq AI] Progreso: {procesados}/{total} artículos procesados.")

        _guardar_cache()
        log.info(f"[Groq AI] ✓ Enriquecimiento completado. {total} artículos con tags y scores.")
        return articulos
