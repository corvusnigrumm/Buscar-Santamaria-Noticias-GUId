
# ARCHIVO CORREGIDO - PROYECTO BUSCADOR DE NOTICIAS
# Incluye fixes críticos de importación, concurrencia, fechas y filtros

# =========================
# FIX 1: IMPORT SEGURO DE customtkinter
# =========================
try:
    import customtkinter as ctk
except ImportError:
    class Dummy:
        def __init__(self, *a, **k): pass
    class ctk:
        CTk = Dummy
        CTkToplevel = Dummy
        CTkFrame = Dummy

# =========================
# FIX 2: NORMALIZACIÓN ROBUSTA DE DOMINIOS
# =========================
from urllib.parse import urlparse

def normalize_domain(url):
    try:
        domain = urlparse(url).netloc.lower()
        for prefix in ["www.", "m.", "amp."]:
            if domain.startswith(prefix):
                domain = domain[len(prefix):]
        return domain
    except:
        return ""

# =========================
# FIX 3: FILTRO CASE-INSENSITIVE
# =========================
def check_content_signatures(text, signatures):
    text = text.lower()
    return any(sig.lower() in text for sig in signatures)

# =========================
# FIX 4: CONCURRENCIA CORRECTA (MAPEO FUTUROS)
# =========================
from concurrent.futures import ThreadPoolExecutor, as_completed

def fetch_all(fuentes, fetch_func):
    resultados = []
    futuros_map = {}

    with ThreadPoolExecutor(max_workers=5) as executor:
        for fuente in fuentes:
            futuro = executor.submit(fetch_func, fuente)
            futuros_map[futuro] = fuente

        for futuro in as_completed(futuros_map):
            fuente = futuros_map[futuro]
            try:
                data = futuro.result()
                resultados.append((fuente["nombre"], data))
            except Exception as e:
                print(f"Error en {fuente['nombre']}: {e}")

    return resultados

# =========================
# FIX 5: DESPLAZAMIENTO REAL DE FECHAS
# =========================
from datetime import timedelta

def calcular_rango_desplazado(inicio, fin):
    delta = fin - inicio
    nuevo_inicio = fin
    nuevo_fin = fin + delta
    return nuevo_inicio, nuevo_fin

# =========================
# FIX 6: REDIRECCIÓN MÁS ROBUSTA
# =========================
import requests

def resolve_redirect(url):
    try:
        r = requests.get(url, allow_redirects=True, timeout=5)
        return r.url
    except:
        return url

print("Archivo de correcciones generado correctamente.")
