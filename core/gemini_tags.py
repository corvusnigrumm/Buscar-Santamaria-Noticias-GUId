"""
core/gemini_tags.py — Servicio de enriquecimiento con Gemini AI
Extrae tags SEO inteligentes y asigna puntajes de tendencia (0-100)
a cada artículo recolectado por el motor de búsqueda.
"""

import os
import json
import hashlib
import asyncio
from pathlib import Path
from core.logger import logger as log

# ── Caché local para evitar re-procesar artículos ──────────────
_CACHE_DIR = Path(os.environ.get("BUSCADOR_NOTICIAS_DATA_DIR", "./data"))
_CACHE_FILE = _CACHE_DIR / "gemini_tags_cache.json"
_cache: dict = {}

def _cargar_cache():
    global _cache
    try:
        if _CACHE_FILE.exists():
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                _cache = json.load(f)
    except Exception:
        _cache = {}

def _guardar_cache():
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning(f"No se pudo guardar caché de tags Gemini: {e}")

def _hash_articulo(titulo: str, url: str) -> str:
    clave = f"{titulo.strip().lower()}|{url.strip().lower()}"
    return hashlib.md5(clave.encode("utf-8")).hexdigest()


class GeminiTagService:
    """Servicio que enriquece artículos con tags SEO y scoring de tendencias via Gemini."""

    BATCH_SIZE = 15  # artículos por request (balance entre costo y contexto)
    MAX_RPM = 14     # requests por minuto (capa gratuita = 15 RPM, dejamos margen)

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.client = None
        self._disponible = False

        if not self.api_key:
            log.warning("[Gemini] No se encontró GEMINI_API_KEY. Tags deshabilitados.")
            return

        try:
            from google import genai
            self.client = genai.Client(api_key=self.api_key)
            self._disponible = True
            log.info("[Gemini] Servicio de tags AI inicializado correctamente.")
        except ImportError:
            log.warning("[Gemini] Paquete 'google-genai' no instalado. pip install google-genai")
        except Exception as e:
            log.warning(f"[Gemini] Error inicializando cliente: {e}")

    @property
    def disponible(self) -> bool:
        return self._disponible

    def _construir_prompt(self, articulos_batch: list[dict]) -> str:
        """Construye el prompt optimizado para extraer tags y scores."""
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

Para cada artículo a continuación, genera:
1. **tags**: 3 a 5 keywords SEO relevantes y específicos (NO genéricos como "noticias" o "Colombia"). Deben ser términos que la gente buscaría en Google.
2. **trend_score**: Un puntaje de 0 a 100 que mide qué tan tendencia es el tema:
   - 90-100: Tema viral, breaking news, todo el mundo habla de esto
   - 70-89: Tema muy relevante, alta búsqueda en Google Trends
   - 50-69: Tema moderadamente popular, interés sostenido
   - 30-49: Tema de nicho pero con audiencia definida
   - 0-29: Tema de bajo interés general
3. **trend_reason**: Explicación breve (máximo 15 palabras) de por qué asignaste ese puntaje.

ARTÍCULOS:
{bloque}

Responde ÚNICAMENTE con un JSON array válido. Sin markdown, sin texto adicional.
Formato exacto:
[
  {{"id": 0, "tags": ["tag1", "tag2", "tag3"], "trend_score": 75, "trend_reason": "Razón breve"}},
  ...
]"""

    async def _llamar_gemini(self, prompt: str) -> list[dict] | None:
        """Envía prompt a Gemini y parsea la respuesta JSON."""
        if not self.client:
            return None

        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model="gemini-2.0-flash",
                contents=prompt,
            )

            texto = response.text.strip()
            # Limpiar posibles bloques markdown
            if texto.startswith("```"):
                texto = texto.split("\n", 1)[1] if "\n" in texto else texto[3:]
                if texto.endswith("```"):
                    texto = texto[:-3]
                texto = texto.strip()

            return json.loads(texto)

        except json.JSONDecodeError as e:
            log.warning(f"[Gemini] Respuesta no es JSON válido: {e}")
            return None
        except Exception as e:
            log.warning(f"[Gemini] Error en llamada API: {e}")
            return None

    async def generar_tags_batch(self, articulos: list[dict],
                                  callback=None) -> list[dict]:
        """
        Enriquece una lista de artículos con tags y scores de Gemini.
        
        Args:
            articulos: Lista de dicts con al menos 'titulo', 'resumen', 'fuente', 'categoria'.
            callback: Función opcional callback(procesados, total) para progreso.
        
        Returns:
            La misma lista de artículos, ahora con campos 'tags', 'trend_score', 'trend_reason'.
        """
        if not self._disponible:
            log.info("[Gemini] Servicio no disponible. Retornando artículos sin tags.")
            return articulos

        _cargar_cache()

        total = len(articulos)
        procesados = 0
        sin_cache = []
        indices_sin_cache = []

        # Primero llenar desde caché
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
            log.info(f"[Gemini] {procesados}/{total} desde caché. Procesando {len(sin_cache)} artículos nuevos...")
        else:
            log.info(f"[Gemini] {total}/{total} artículos ya en caché. Sin llamadas API.")
            return articulos

        # Procesar en batches
        batches = [
            sin_cache[i:i + self.BATCH_SIZE]
            for i in range(0, len(sin_cache), self.BATCH_SIZE)
        ]

        for batch_idx, batch in enumerate(batches):
            if batch_idx > 0:
                # Rate limiting: esperar para no exceder RPM
                await asyncio.sleep(60.0 / self.MAX_RPM)

            prompt = self._construir_prompt(batch)
            resultados = await self._llamar_gemini(prompt)

            if resultados and isinstance(resultados, list):
                for item in resultados:
                    idx_local = item.get("id", -1)
                    if 0 <= idx_local < len(batch):
                        art = batch[idx_local]
                        art["tags"] = item.get("tags", [])
                        art["trend_score"] = item.get("trend_score", 0)
                        art["trend_reason"] = item.get("trend_reason", "")

                        # Guardar en caché
                        h = _hash_articulo(art.get("titulo", ""), art.get("url", ""))
                        _cache[h] = {
                            "tags": art["tags"],
                            "trend_score": art["trend_score"],
                            "trend_reason": art["trend_reason"],
                        }
            else:
                log.warning(f"[Gemini] Batch {batch_idx + 1}/{len(batches)} sin resultados.")
                for art in batch:
                    art.setdefault("tags", [])
                    art.setdefault("trend_score", 0)
                    art.setdefault("trend_reason", "Sin datos")

            procesados += len(batch)
            if callback:
                callback(procesados, total)

            log.info(f"[Gemini] Progreso: {procesados}/{total} artículos procesados.")

        _guardar_cache()
        log.info(f"[Gemini] ✓ Enriquecimiento completado. {total} artículos con tags y scores.")
        return articulos
