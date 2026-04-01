# -*- coding: utf-8 -*-
"""Clasificacion Evergreen para Santamaria Noticias usando Ollama.

Modulo local para que PyInstaller lo incluya dentro del proyecto.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Callable, Optional

log = logging.getLogger("IAEvergreen")

# ── Timeout HTTP real para Ollama (segundos) ────────────────────
OLLAMA_TIMEOUT_CHAT = 20   # máximo por artículo
OLLAMA_TIMEOUT_PING = 5    # máximo para verificar si Ollama está activo

TEMAS_OBJETIVO = [
    "salud y bienestar",
    "negocios",
    "finanzas personales",
    "tecnologia util",
    "educacion",
]

PALABRAS_COYUNTURA = [
    "hoy", "ayer", "esta manana", "esta noche", "ultima hora", "ultimas horas",
    "en vivo", "urgente", "breaking", "resultado", "marcador", "partido",
    "elecciones", "accidente", "balacera", "sorteo", "precio del dolar",
    "tasas hoy", "cotizacion", "esta semana", "este lunes", "este martes",
    "este miercoles", "este jueves", "este viernes", "este sabado", "este domingo",
]

PALABRAS_EVERGREEN = [
    "como", "guia", "guia completa", "consejos", "tips", "claves", "pasos",
    "que es", "para que sirve", "beneficios", "ventajas", "errores comunes",
    "habitos", "estrategias", "metodo", "tecnica", "presupuesto", "ahorro",
    "inversion", "finanzas personales", "bienestar", "salud", "rutina",
    "negocio", "emprender", "emprendimiento", "productividad",
]

MAX_RESUMEN_PROMPT = 280
MAX_ARTICULOS_IA = 60


def _texto_norm(texto: str) -> str:
    texto = (texto or "").lower()
    texto = (
        texto.replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    )
    return re.sub(r"\s+", " ", texto).strip()


def _puntaje_rapido(titulo: str, resumen: str) -> Optional[int]:
    texto = _texto_norm(f"{titulo} {resumen}")
    coyuntura = sum(1 for palabra in PALABRAS_COYUNTURA if palabra in texto)
    evergreen = sum(1 for palabra in PALABRAS_EVERGREEN if palabra in texto)

    if coyuntura >= 2:
        return 2
    if evergreen >= 3:
        return 8
    return None


def _metricas_rapidas(titulo: str, resumen: str) -> dict:
    texto = _texto_norm(f"{titulo} {resumen}")
    coyuntura = sum(1 for palabra in PALABRAS_COYUNTURA if palabra in texto)
    evergreen = sum(1 for palabra in PALABRAS_EVERGREEN if palabra in texto)
    return {
        "texto": texto,
        "coyuntura": coyuntura,
        "evergreen": evergreen,
        "score_rapido": _puntaje_rapido(titulo, resumen),
    }


def _prompt_evergreen(titulo: str, resumen: str) -> str:
    temas = ", ".join(TEMAS_OBJETIVO)
    return f"""Eres editor senior de SEO y contenido evergreen para un medio colombiano.

Evalua si este articulo sirve como contenido Evergreen.

ARTICULO
Titulo: {titulo}
Resumen: {resumen[:MAX_RESUMEN_PROMPT]}

TEMAS OBJETIVO
{temas}

REGLAS
- Evergreen verdadero: util dentro de 6 meses, no depende de temporada ni coyuntura puntual.
- Mixto: parte util, pero muy pegado a la actualidad.
- Coyuntura: noticia del dia, suceso puntual, partido, accidente, valor diario, ultima hora.

Responde SOLO con JSON valido:
{{
  "score": <1-10>,
  "categoria": "<salud|finanzas|negocios|tecnologia|general|coyuntura>",
  "es_evergreen": <true|false>,
  "razon": "<maximo 18 palabras>"
}}"""


def _crear_cliente_ollama(timeout: int = OLLAMA_TIMEOUT_CHAT):
    """Crea un cliente Ollama con timeout HTTP real (httpx)."""
    import ollama
    return ollama.Client(timeout=timeout)


def _llamar_ollama(prompt: str, modelo: str) -> Optional[dict]:
    try:
        import ollama  # noqa: F401 — verificar que está instalado
    except ImportError:
        return None

    try:
        cliente = _crear_cliente_ollama(timeout=OLLAMA_TIMEOUT_CHAT)
        respuesta = cliente.chat(
            model=modelo,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0, "num_predict": 96},
        )
        texto = respuesta["message"]["content"].strip()
        match = re.search(r"\{.*\}", texto, re.DOTALL)
        if not match:
            return None
        return json.loads(match.group())
    except Exception as exc:
        nombre_exc = type(exc).__name__
        log.warning(f"Ollama fallo ({nombre_exc}): {exc}")
        return None


def _resultado_fallback(titulo: str, resumen: str) -> dict:
    texto = _texto_norm(f"{titulo} {resumen}")
    coyuntura = sum(1 for palabra in PALABRAS_COYUNTURA if palabra in texto)
    evergreen = sum(1 for palabra in PALABRAS_EVERGREEN if palabra in texto)

    if coyuntura >= 2:
        return {
            "score": 2,
            "categoria": "coyuntura",
            "es_evergreen": False,
            "razon": "predomina la coyuntura",
            "via": "fallback",
        }
    if evergreen >= 2:
        return {
            "score": 7,
            "categoria": "general",
            "es_evergreen": True,
            "razon": "senales evergreen detectadas",
            "via": "fallback",
        }

    return {
        "score": 4,
        "categoria": "general",
        "es_evergreen": False,
        "razon": "sin evidencia evergreen suficiente",
        "via": "fallback",
    }


def analizar_articulo(titulo: str, resumen: str, modelo: str = "llama3.2", usar_ia: bool = True) -> dict:
    metricas = _metricas_rapidas(titulo, resumen)
    score_rapido = metricas["score_rapido"]
    if score_rapido is not None and score_rapido <= 3:
        return {
            "score": score_rapido,
            "categoria": "coyuntura",
            "es_evergreen": False,
            "razon": "prefiltro de coyuntura",
            "via": "prefiltro",
        }

    # Fast path para evitar mandar a Ollama artículos claramente evergreen.
    if score_rapido is not None and score_rapido >= 8:
        return {
            "score": score_rapido,
            "categoria": "general",
            "es_evergreen": True,
            "razon": "prefiltro evergreen claro",
            "via": "prefiltro",
        }

    if not usar_ia:
        return _resultado_fallback(titulo, resumen)

    resultado = _llamar_ollama(_prompt_evergreen(titulo, resumen), modelo)
    if resultado:
        resultado.setdefault("score", 5)
        resultado.setdefault("categoria", "general")
        resultado.setdefault("es_evergreen", resultado.get("score", 0) >= 6)
        resultado.setdefault("razon", "")
        resultado["via"] = "ia"
        return resultado

    return _resultado_fallback(titulo, resumen)


def filtrar_y_puntuar_evergreen(
    articulos: list,
    score_minimo: int = 6,
    modelo: str = "llama3.2",
    usar_ia: bool = True,
    max_articulos: int = 250,
    max_articulos_ia: int = MAX_ARTICULOS_IA,
    callback_progreso: Optional[Callable[[int, int, str], None]] = None,
) -> list:
    if not articulos:
        return []

    ollama_disponible = False
    if usar_ia:
        try:
            cliente_ping = _crear_cliente_ollama(timeout=OLLAMA_TIMEOUT_PING)
            cliente_ping.list()
            ollama_disponible = True
            log.info(f"Ollama disponible. Modelo: {modelo}")
        except Exception as exc:
            nombre_exc = type(exc).__name__
            log.warning(f"Ollama no disponible ({nombre_exc}). Se usara fallback por reglas.")
            usar_ia = False

    total = min(len(articulos), max_articulos)
    aprobados = []
    candidatos_ia = []
    revisados = articulos[:total]

    for art in revisados:
        titulo = art.get("titulo", "")
        resumen = art.get("resumen", titulo)
        metricas = _metricas_rapidas(titulo, resumen)
        score_rapido = metricas["score_rapido"]

        if score_rapido is not None and score_rapido <= 3:
            continue

        if score_rapido is not None and score_rapido >= 8:
            evaluacion = {
                "score": score_rapido,
                "categoria": "general",
                "es_evergreen": True,
                "razon": "prefiltro evergreen claro",
                "via": "prefiltro",
            }
            enriquecido = {
                **art,
                "ia_score": evaluacion.get("score", 0),
                "ia_categoria": evaluacion.get("categoria", "general"),
                "ia_es_evergreen": evaluacion.get("es_evergreen", False),
                "ia_razon": evaluacion.get("razon", ""),
                "ia_via": evaluacion.get("via", "fallback"),
                "evergreen_score": evaluacion.get("score", 0),
            }
            if evaluacion["score"] >= score_minimo:
                aprobados.append(enriquecido)
            continue

        prioridad = (metricas["evergreen"] * 3) - (metricas["coyuntura"] * 2)
        candidatos_ia.append((prioridad, art))

    candidatos_ia.sort(key=lambda item: item[0], reverse=True)
    limite_ia = max(0, min(len(candidatos_ia), max_articulos_ia if ollama_disponible else 0))
    total_a_procesar = limite_ia or len(candidatos_ia)
    timeouts_consecutivos = 0

    for idx, (_, art) in enumerate(candidatos_ia, start=1):
        titulo = art.get("titulo", "")
        resumen = art.get("resumen", titulo)

        # ── Progreso visible ────────────────────────────────────
        if callback_progreso:
            callback_progreso(idx, total_a_procesar, titulo[:80])
        # Siempre imprimir por stdout para que sea visible en la GUI
        print(f"    [IA] ({idx}/{total_a_procesar}) {titulo[:75]}...", flush=True)

        usar_ollama_en_este = ollama_disponible and idx <= limite_ia

        # Si hay 3+ timeouts seguidos, desactivar Ollama para el resto
        if timeouts_consecutivos >= 3 and usar_ollama_en_este:
            log.warning("  [!] 3 timeouts consecutivos — desactivando Ollama para el resto del lote.")
            print("    [!] 3 timeouts consecutivos. Cambiando a modo reglas rapidas.", flush=True)
            ollama_disponible = False
            usar_ollama_en_este = False
            timeouts_consecutivos = 0

        t0 = time.time()
        evaluacion = analizar_articulo(
            titulo=titulo,
            resumen=resumen,
            modelo=modelo,
            usar_ia=usar_ollama_en_este,
        )
        dt = time.time() - t0

        # Detectar timeouts para el circuito de corte
        if usar_ollama_en_este and evaluacion.get("via") == "fallback":
            timeouts_consecutivos += 1
        else:
            timeouts_consecutivos = 0

        # Log del resultado de cada artículo
        via = evaluacion.get("via", "?")
        score = evaluacion.get("score", 0)
        es_eg = "✓" if evaluacion.get("es_evergreen") else "✗"
        print(f"        → score={score} eg={es_eg} via={via} ({dt:.1f}s)", flush=True)

        enriquecido = {
            **art,
            "ia_score": evaluacion.get("score", 0),
            "ia_categoria": evaluacion.get("categoria", "general"),
            "ia_es_evergreen": evaluacion.get("es_evergreen", False),
            "ia_razon": evaluacion.get("razon", ""),
            "ia_via": evaluacion.get("via", "fallback"),
            "evergreen_score": evaluacion.get("score", 0),
        }

        if evaluacion.get("score", 0) >= score_minimo and evaluacion.get("es_evergreen", False):
            aprobados.append(enriquecido)

        if usar_ollama_en_este and idx % 10 == 0:
            time.sleep(0.1)

    aprobados.sort(key=lambda art: art.get("ia_score", 0), reverse=True)
    print(f"    [IA] Finalizado. {len(aprobados)} articulos Evergreen aprobados.", flush=True)
    return aprobados
