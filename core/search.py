import asyncio
import aiohttp
from datetime import datetime, timedelta, timezone
import urllib.parse
from core.logger import logger as log

from core.config import (
    FUENTES_RSS, MEDIOS_PROHIBIDOS, CATEGORIAS_RELACIONADAS,
    ZONA_COLOMBIA
)
from core.scraper import fetch_fuente_async
from core.filters import (
    _fecha_a_date_colombia, _es_razon_medio_prohibido, _esta_bloqueado,
    _articulo_es_nacional_colombia, _articulo_cumple_filtro_mundo,
    _articulo_coincide_categoria, _es_tendencia_valida,
    _es_coincidencia_lista_negra, _es_coincidencia_historial,
    _es_coincidencia_indice_repeticion, _agregar_articulo_a_indice,
    _registro_historial_desde_articulo, _cargar_historial_articulos,
    _guardar_historial_articulos, _cargar_historial_medios_prohibidos,
    _guardar_historial_medios_prohibidos, _indexar_historial_articulos,
    _indexar_articulos_repeticion, _expandir_categorias_solicitadas
)

MAX_VALIDACIONES_OLLAMA_POR_BUSQUEDA = 30
VENTANA_LISTA_NEGRA_DIAS = 30
VENTANA_LISTA_NEGRA_DESCARGA_DIAS = 4

LISTA_NEGRA_MEDIOS = []
LISTA_NEGRA_MEDIOS_HASHES = set()
LISTA_NEGRA_MEDIOS_POR_ANCLA = {}

async def _cargar_lista_negra_medios_async(session, fecha_inicio=None, fecha_fin=None, verbose=True):
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
            "nombre": f"{cfg.get('label', '')} Base",
            "url": cfg.get("lista_negra_url", ""),
            "categorias": ["general"],
            "tipo": "nacional",
        })

    tasks = [
        fetch_fuente_async(session, f, fecha_descarga_inicio, fecha_negra_fin)
        for f in fuentes_lista_negra if f["url"]
    ]
    resultados = await asyncio.gather(*tasks, return_exceptions=True)
    
    for r in resultados:
        if isinstance(r, tuple) and len(r) == 4:
            _, _, articulos, lista_negra_f = r
            if articulos: LISTA_NEGRA_MEDIOS.extend(articulos)
            if lista_negra_f: LISTA_NEGRA_MEDIOS.extend(lista_negra_f)

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

async def buscar_noticias_async(categorias_seleccionadas=None, fecha_inicio=None, fecha_fin=None,
                    max_por_fuente=10, max_total=1000, verbose=True,
                    tipo_noticias="ambas", filtrar_argentina=True):

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
        log.info("  BUSCADOR DE NOTICIAS CAPA BRINDADA - ASYNC ENGINE")
        log.info("=" * 60)

    async with aiohttp.ClientSession() as session:
        await _cargar_lista_negra_medios_async(session, fecha_inicio, fecha_fin, verbose)

        todas = []
        fuentes_fallidas = []
        conteo_fuentes = {}
        articulos_vistos_hashes = set()
        articulos_vistos_por_ancla = {}
        historial_articulos = _cargar_historial_articulos()
        historial_hashes, historial_por_ancla = _indexar_historial_articulos(historial_articulos)

        tasks = [fetch_fuente_async(session, f, fecha_inicio, fecha_fin) for f in fuentes]
        resultados = await asyncio.gather(*tasks, return_exceptions=True)

        for fuente, r in zip(fuentes, resultados):
            nombre = fuente["nombre"]
            if isinstance(r, Exception):
                log.error(f"Error al procesar fuente {nombre}: {r}")
                fuentes_fallidas.append(nombre)
                continue
                
            _, responded, articulos_fuente, lista_negra_fuente = r

            if not responded:
                fuentes_fallidas.append(nombre)
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
                log.info(f"  [...] {nombre}... OK {len(nuevos)} articulos")

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

        return {
            "noticias": resultado,
            "total": len(resultado),
            "fuentes_consultadas": len(fuentes) - len(fuentes_fallidas),
            "fuentes_fallidas": fuentes_fallidas,
            "conteo_fuentes": conteo_fuentes,
            "notificacion": None,
        }
