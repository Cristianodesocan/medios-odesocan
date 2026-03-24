"""
clasificador.py — Clasifica noticias por tema con un enfoque híbrido.

Señales utilizadas:
  - coincidencias literales de keywords en título y resumen
  - coincidencias aproximadas por lemas/tokens
  - pistas estructurales en la URL y la sección
  - similitud semántica con prototipos de tema (si spaCy tiene vectores)

La salida sigue siendo multietiqueta y compatible con el flujo existente.
"""

from __future__ import annotations

import math
import re
import unicodedata
from functools import lru_cache
from typing import Iterable
from urllib.parse import unquote, urlparse

from config import TEMAS

try:
    import spacy
except ImportError:  # pragma: no cover - fallback defensivo
    spacy = None


SCORE_MINIMO = 2.6

# Pistas adicionales para cubrir lenguaje periodistico que no estaba en las
# keywords literales originales.
EXTRA_THEME_HINTS: dict[str, tuple[str, ...]] = {
    "migracion": (
        "ruta canaria",
        "salvamento maritimo",
        "frontera sur",
    ),
    "economia": (
        "igic",
        "ipc",
        "cesta de la compra",
        "mercado laboral",
    ),
    "presupuestos": (
        "cuentas publicas",
        "marco financiero",
        "fondos europeos",
    ),
    "violencia_genero": (
        "violencia sexual",
        "agresion machista",
        "igualdad",
    ),
    "politica": (
        "clavijo",
        "diputacion del comun",
        "debate de la nacionalidad canaria",
        "gobierno central",
    ),
    "medio_ambiente": (
        "aemet",
        "temporal",
        "borrasca",
        "oleaje",
        "lluvia",
        "viento",
        "nieve",
        "terremoto",
        "terremotos",
        "sismo",
        "sismica",
        "volcan",
        "fosil",
        "botanico",
        "calima",
    ),
    "vivienda": (
        "viviendas",
        "inmueble",
        "promocion residencial",
    ),
    "sanidad": (
        "ministerio de sanidad",
        "covid persistente",
        "dependencia",
        "endometriosis",
        "salud publica",
    ),
    "salud_mental": (
        "bienestar psicologico",
        "salud emocional",
    ),
    "turismo": (
        "visitacion",
        "destino",
    ),
}


URL_THEME_HINTS: dict[str, tuple[str, ...]] = {
    "migracion": ("migraciones",),
    "economia": ("economia",),
    "presupuestos": ("presupuestos", "marco-financiero", "fondos"),
    "violencia_genero": ("igualdad", "violencia-machista", "violencia-genero"),
    "politica": ("politica", "parlamento-canario"),
    "medio_ambiente": (
        "medio-ambiente",
        "medio_ambiente",
        "ciencia-y-medio-ambiente",
        "ciencia_y_medio_ambiente",
        "tiempo-canarias",
        "patrimonio-canarias",
    ),
    "vivienda": ("vivienda", "urbanismo"),
    "sanidad": ("sanidad", "salud"),
    "salud_mental": ("salud-mental", "salud_mental"),
    "turismo": ("turismo",),
}


def _cargar_modelo():
    if spacy is None:
        return None
    for modelo in ("es_core_news_md", "es_core_news_sm"):
        try:
            return spacy.load(modelo, disable=["parser", "ner"])
        except OSError:
            continue
    return spacy.blank("es")


_NLP = _cargar_modelo()
_HAS_VECTORS = bool(_NLP and getattr(_NLP.vocab, "vectors_length", 0))


def _normalizar(texto: str) -> str:
    """Minúsculas + quitar tildes para comparación robusta."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _fragmentos(texto: str) -> tuple[str, ...]:
    return tuple(tok for tok in re.split(r"[^a-z0-9]+", _normalizar(texto)) if len(tok) > 2)


@lru_cache(maxsize=4096)
def _doc(texto: str):
    if not _NLP or not texto:
        return None
    return _NLP(texto)


def _tokens_texto(texto: str) -> set[str]:
    doc = _doc(texto)
    if doc is not None:
        tokens = set()
        for token in doc:
            if token.is_space or token.is_punct:
                continue
            base = token.lemma_ if token.lemma_ and token.lemma_ != "-PRON-" else token.text
            base_norm = _normalizar(base)
            if base_norm and len(base_norm) > 2 and any(ch.isalpha() for ch in base_norm):
                tokens.add(base_norm)
        if tokens:
            return tokens
    return set(_fragmentos(texto))


def _segmentos_url(url: str) -> tuple[str, ...]:
    if not url:
        return ()
    path = unquote(urlparse(url).path)
    segmentos = []
    for parte in path.split("/"):
        parte = _normalizar(parte.strip())
        parte = parte.replace("_", "-")
        if parte:
            segmentos.append(parte)
    return tuple(segmentos)


def _score_pista(texto_norm: str, tokens: set[str], pista: str, base: float) -> tuple[float, bool]:
    pista_norm = _normalizar(pista)
    partes = _fragmentos(pista_norm)
    if not partes:
        return 0.0, False

    es_compuesta = len(partes) > 1
    if pista_norm and pista_norm in texto_norm:
        return base * (1.25 if es_compuesta else 1.0), True

    cobertura = sum(1 for parte in partes if parte in tokens)
    if cobertura == len(partes):
        return base * (0.75 if es_compuesta else 0.55), False
    if es_compuesta and cobertura >= max(2, math.ceil(len(partes) * 0.6)):
        return base * 0.45, False

    return 0.0, False


def _score_url(theme_id: str, url: str) -> tuple[float, bool]:
    if not url:
        return 0.0, False

    path_norm = _normalizar(unquote(urlparse(url).path)).replace("_", "-")
    segmentos = _segmentos_url(url)
    score = 0.0
    fuerte = False

    for pista in URL_THEME_HINTS.get(theme_id, ()):
        pista_norm = _normalizar(pista).replace("_", "-")
        if any(seg == pista_norm for seg in segmentos):
            score = max(score, 2.4)
            fuerte = True
        elif pista_norm in path_norm:
            score = max(score, 1.4)

    return score, fuerte


@lru_cache(maxsize=None)
def _doc_prototipo(theme_id: str):
    if not _HAS_VECTORS:
        return None
    cfg = TEMAS[theme_id]
    semillas = [cfg["label"], *cfg["keywords"], *EXTRA_THEME_HINTS.get(theme_id, ())]
    texto = ". ".join(dict.fromkeys(_normalizar(semilla) for semilla in semillas if semilla))
    return _doc(texto)


def clasificar_detallado(titulo: str, resumen: str = "", url: str = "") -> dict[str, float]:
    """
    Devuelve los scores por tema. Sirve para depuración o ajustes del clasificador.
    """
    titulo_norm = _normalizar(titulo)
    resumen_norm = _normalizar(resumen or "")
    url_norm = _normalizar(url)
    titulo_tokens = _tokens_texto(titulo_norm)
    resumen_tokens = _tokens_texto(resumen_norm)
    texto_total_norm = " ".join(part for part in (titulo_norm, resumen_norm) if part).strip()
    doc_total = _doc(texto_total_norm) if texto_total_norm else None

    scores: dict[str, float] = {}

    for tema_id, cfg in TEMAS.items():
        peso_titulo = float(cfg.get("peso_titulo", 2))
        score = 0.0
        coincidencias = 0

        score_url, url_fuerte = _score_url(tema_id, url_norm)
        score += score_url
        if score_url:
            coincidencias += 1

        pistas_base = tuple(dict.fromkeys(cfg["keywords"]))
        pistas_extra = tuple(
            pista for pista in EXTRA_THEME_HINTS.get(tema_id, ()) if pista not in pistas_base
        )

        for pista in pistas_base:
            s_titulo, exacta_titulo = _score_pista(titulo_norm, titulo_tokens, pista, peso_titulo)
            s_resumen, exacta_resumen = _score_pista(resumen_norm, resumen_tokens, pista, 1.15)
            score += s_titulo + s_resumen
            if s_titulo or s_resumen:
                coincidencias += 1
                if exacta_titulo and exacta_resumen:
                    score += 0.15

        for pista in pistas_extra:
            s_titulo, exacta_titulo = _score_pista(titulo_norm, titulo_tokens, pista, peso_titulo + 0.8)
            s_resumen, exacta_resumen = _score_pista(resumen_norm, resumen_tokens, pista, 1.35)
            score += s_titulo + s_resumen
            if s_titulo or s_resumen:
                coincidencias += 1
                if exacta_titulo and exacta_resumen:
                    score += 0.15

        if coincidencias >= 2:
            score += 0.35

        if _HAS_VECTORS and doc_total is not None:
            prototipo = _doc_prototipo(tema_id)
            if prototipo is not None and doc_total.vector_norm and prototipo.vector_norm:
                similitud = doc_total.similarity(prototipo)
                if similitud >= 0.64:
                    score += (similitud - 0.64) * 4.0

        umbral = SCORE_MINIMO - 0.4 if url_fuerte else SCORE_MINIMO
        if score >= umbral:
            scores[tema_id] = round(score, 3)

    return dict(sorted(scores.items(), key=lambda item: item[1], reverse=True))


def clasificar(titulo: str, resumen: str = "", url: str = "") -> list[str]:
    """
    Devuelve lista de claves de tema ordenadas por relevancia.
    """
    return list(clasificar_detallado(titulo, resumen=resumen, url=url))
