"""
diagnose_texto_full.py — Diagnóstico rápido de por qué falla texto_full.

Uso:
  python diagnose_texto_full.py --medio atlanticohoy --limit 5
  python diagnose_texto_full.py --url https://www.ejemplo.com/noticia.html
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from config import DB_PATH
from scraper import ClienteHTTP

log = logging.getLogger("diagnose_texto_full")

PAYWALL_MARKERS = [
    "suscr",
    "premium",
    "subscriber",
    "paywall",
    "contenido exclusivo",
    "hazte socio",
    "inicia sesión para seguir leyendo",
    "regístrate para seguir leyendo",
]

COOKIE_MARKERS = [
    "cookies",
    "consent",
    "consentimiento",
    "privacy",
    "privacidad",
    "cmp",
    "onetrust",
    "didomi",
]

ARTICLE_SELECTORS = [
    "article",
    "[class*='article-body']",
    "[class*='entry-content']",
    "[class*='news-body']",
    "main",
    ".content",
]


def configurar_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def _normalizar(texto: str) -> str:
    return " ".join(texto.lower().split())


def _marcadores_presentes(html: str, markers: list[str]) -> list[str]:
    texto = _normalizar(html)
    return [marker for marker in markers if marker in texto]


def _schema_article_body(soup: BeautifulSoup) -> int:
    for script in soup.select("script[type='application/ld+json']"):
        try:
            data = json.loads(script.get_text(strip=True))
        except json.JSONDecodeError:
            continue
        blobs = data if isinstance(data, list) else [data]
        for blob in blobs:
            if isinstance(blob, dict) and blob.get("articleBody"):
                return len(str(blob["articleBody"]))
    return 0


def _analisis_html(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    selector_hits: dict[str, dict[str, int]] = {}
    for selector in ARTICLE_SELECTORS:
        nodo = soup.select_one(selector)
        if not nodo:
            continue
        parrafos = [p.get_text(" ", strip=True) for p in nodo.find_all("p")]
        largos = [p for p in parrafos if len(p) > 40]
        selector_hits[selector] = {
            "parrafos": len(parrafos),
            "parrafos_largos": len(largos),
            "chars": sum(len(p) for p in largos),
        }

    total_parrafos = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    largos_global = [p for p in total_parrafos if len(p) > 40]
    scripts = len(soup.find_all("script"))

    return {
        "title": soup.title.get_text(" ", strip=True) if soup.title else "",
        "selector_hits": selector_hits,
        "parrafos_total": len(total_parrafos),
        "parrafos_largos_total": len(largos_global),
        "chars_parrafos_largos": sum(len(p) for p in largos_global),
        "scripts": scripts,
        "schema_article_body_chars": _schema_article_body(soup),
        "paywall_markers": _marcadores_presentes(html, PAYWALL_MARKERS),
        "cookie_markers": _marcadores_presentes(html, COOKIE_MARKERS),
    }


def _newspaper_chars(url: str, html: str) -> int:
    try:
        from newspaper import Article
    except ImportError:
        return 0

    try:
        art = Article(url, language="es")
        art.set_html(html)
        art.parse()
        return len(art.text or "")
    except Exception:
        return 0


def _diagnostico_probable(analysis: dict[str, Any], newspaper_len: int) -> str:
    if newspaper_len > 120 or analysis["schema_article_body_chars"] > 120:
        return "El contenido existe en el HTML; falla la heuristica/selectores del extractor."
    if analysis["paywall_markers"]:
        return "Probable paywall o muro de registro."
    if analysis["cookie_markers"] and analysis["parrafos_largos_total"] < 3:
        return "Probable bloqueo por consentimiento/capa de cookies."
    if analysis["parrafos_largos_total"] < 3 and analysis["scripts"] > 20:
        return "Probable contenido cargado por JavaScript o render incompleto."
    if analysis["selector_hits"] and max(v["chars"] for v in analysis["selector_hits"].values()) < 120:
        return "Hay contenedor, pero sin cuerpo suficiente; revisar selectores especificos del medio."
    if not analysis["selector_hits"]:
        return "No se encontro contenedor claro de articulo; revisar estructura HTML."
    return "Causa no concluyente; revisar HTML guardado/manualmente."


def _urls_desde_db(medio: str | None, limit: int) -> list[tuple[str, str, str]]:
    conn = sqlite3.connect(DB_PATH)
    try:
        query = """
            SELECT medio, url, titulo
            FROM noticias
            WHERE (texto_full IS NULL OR trim(coalesce(texto_full, '')) = '')
        """
        params: list[Any] = []
        if medio:
            query += " AND medio = ?"
            params.append(medio)
        query += " ORDER BY fecha_scrap DESC LIMIT ?"
        params.append(limit)
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


def diagnosticar_url(url: str, titulo: str = "", medio: str = "") -> dict[str, Any]:
    cliente = ClienteHTTP()
    try:
        html = cliente.get(url, usar_cache=False)
    finally:
        cliente.close()

    if not html:
        return {
            "medio": medio,
            "titulo": titulo,
            "url": url,
            "error": "No se pudo descargar HTML",
        }

    analysis = _analisis_html(html)
    newspaper_len = _newspaper_chars(url, html)
    return {
        "medio": medio,
        "titulo": titulo or analysis["title"],
        "url": url,
        "newspaper_chars": newspaper_len,
        "schema_article_body_chars": analysis["schema_article_body_chars"],
        "parrafos_largos_total": analysis["parrafos_largos_total"],
        "chars_parrafos_largos": analysis["chars_parrafos_largos"],
        "scripts": analysis["scripts"],
        "paywall_markers": analysis["paywall_markers"],
        "cookie_markers": analysis["cookie_markers"],
        "selector_hits": analysis["selector_hits"],
        "diagnostico": _diagnostico_probable(analysis, newspaper_len),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnostica por que falta texto_full")
    parser.add_argument("--medio", help="Filtra por medio")
    parser.add_argument("--limit", type=int, default=5, help="Numero maximo de URLs a revisar")
    parser.add_argument("--url", help="Diagnostica una URL concreta")
    args = parser.parse_args()

    configurar_logging()

    casos: list[tuple[str, str, str]]
    if args.url:
        casos = [("", args.url, "")]
    else:
        casos = _urls_desde_db(args.medio, args.limit)

    if not casos:
        print("No hay URLs pendientes de diagnostico.")
        return

    for medio, url, titulo in casos:
        print("\n---")
        print(f"medio: {medio}")
        print(f"titulo: {titulo}")
        print(f"url: {url}")
        resultado = diagnosticar_url(url=url, titulo=titulo, medio=medio)
        if resultado.get("error"):
            print(f"error: {resultado['error']}")
            continue
        print(f"diagnostico: {resultado['diagnostico']}")
        print(f"newspaper_chars: {resultado['newspaper_chars']}")
        print(f"schema_article_body_chars: {resultado['schema_article_body_chars']}")
        print(f"parrafos_largos_total: {resultado['parrafos_largos_total']}")
        print(f"chars_parrafos_largos: {resultado['chars_parrafos_largos']}")
        print(f"scripts: {resultado['scripts']}")
        print(f"paywall_markers: {', '.join(resultado['paywall_markers']) or '-'}")
        print(f"cookie_markers: {', '.join(resultado['cookie_markers']) or '-'}")
        print("selector_hits:")
        for selector, stats in resultado["selector_hits"].items():
            print(
                f"  {selector}: parrafos={stats['parrafos']} "
                f"largos={stats['parrafos_largos']} chars={stats['chars']}"
            )


if __name__ == "__main__":
    main()
