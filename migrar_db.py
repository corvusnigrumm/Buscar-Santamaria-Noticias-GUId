import os
import json
import logging
from core.db import DBManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Migracion")

DATA_DIR = os.getenv("BUSCADOR_NOTICIAS_DATA_DIR", "./")
# Leer de la raíz del proyecto antiguo
ARTICULOS_PATH = os.path.join("./", "historial_articulos.json")
MEDIOS_PATH = os.path.join("./", "historial_medios_prohibidos.json")
OLLAMA_PATH = os.path.join("./", "ollama_similitud_cache.json")


def migrar_articulos():
    if not os.path.exists(ARTICULOS_PATH):
        logger.info("No se encontró historial_articulos.json")
        return
        
    try:
        with open(ARTICULOS_PATH, 'r', encoding='utf-8') as f:
            articulos = json.load(f)
            
        logger.info(f"Migrando {len(articulos)} artículos...")
        for data in articulos:
            url = data.get("url", "")
            if not url: continue
            titulo = data.get("titulo", "")
            fuente = data.get("fuente", "")
            categoria = data.get("categoria", "")
            fecha = str(data.get("fecha", ""))
            DBManager.registrar_articulo(url, titulo, fuente, categoria, fecha)
        logger.info("Migración de artículos completada.")
    except Exception as e:
        logger.error(f"Error migrando artículos: {e}")

def migrar_medios():
    if not os.path.exists(MEDIOS_PATH):
        logger.info("No se encontró historial_medios_prohibidos.json")
        return
        
    try:
        with open(MEDIOS_PATH, 'r', encoding='utf-8') as f:
            medios = json.load(f)
            
        logger.info(f"Migrando {len(medios)} medios prohibidos...")
        for data in medios:
            url = data.get("url", "")
            if not url: continue
            nombre = data.get("fuente", "Desconocido")
            DBManager.registrar_medio_prohibido(url, nombre)
        logger.info("Migración de medios completada.")
    except Exception as e:
        logger.error(f"Error migrando medios: {e}")

def migrar_ollama():
    if not os.path.exists(OLLAMA_PATH):
        logger.info("No se encontró ollama_similitud_cache.json")
        return
        
    try:
        with open(OLLAMA_PATH, 'r', encoding='utf-8') as f:
            cache = json.load(f)
            
        logger.info(f"Migrando {len(cache)} registros de Ollama...")
        for key, value in cache.items():
            DBManager.guardar_cache_ollama(key, value)
        logger.info("Migración de Ollama completada.")
    except Exception as e:
        logger.error(f"Error migrando Ollama: {e}")

if __name__ == "__main__":
    logger.info("Iniciando migración de JSON a SQLite...")
    migrar_articulos()
    migrar_medios()
    migrar_ollama()
    logger.info("Migración finalizada exitosamente.")
