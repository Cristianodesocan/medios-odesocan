"""
backfill_test.py — Script experimental para probar scraping regresivo.

Objetivo:
  - No toca el scheduler ni el scraper principal.
  - Permite ensayar backfill por rangos de fecha para medios concretos.
  - De momento implementa una estrategia simple basada en sitemap por fechas
    y filtrado por dominio/fecha objetivo.

Uso:
  python backfill_test.py --medio atlanticohoy --desde 2025-09-16 --hasta 2026-03-16 --dry-run
  python backfill_test.py --medio canariasahora --desde 2025-09-16 --hasta 2026-03-16
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from clasificador import clasificar
from config import DB_PATH, LOG_DIR, MEDIOS
from scraper import ClienteHTTP, configurar_logging, init_db, url_hash

log = logging.getLogger("backfill_test")


BACKFILL_SOURCES = {
    "atlanticohoy": {
        "kind": "sitemap",
        "robots": "https://www.atlanticohoy.com/robots.txt",
        "sitemaps": [
            "https://www.atlanticohoy.com/sitemap.xml",
            "https://www.atlanticohoy.com/sitemap_index.xml",
            "https://www.atlanticohoy.com/post-sitemap.xml",
        ],
        "allowed_hosts": {"www.atlanticohoy.com", "atlanticohoy.com"},
    },
    "canariasahora": {
        "kind": "sitemap",
        "robots": "https://www.eldiario.es/robots.txt",
        "sitemaps": [
            "https://www.eldiario.es/sitemap.xml",
            "https://www.eldiario.es/sitemap_index.xml",
        ],
        "allowed_hosts": {"www.eldiario.es", "eldiario.es"},
        "path_must_contain": ["/canariasahora/"],
    },
}


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _extraer_urls_sitemap(xml_text: str) -> tuple[list[str], list[dict]]:
    soup = BeautifulSoup(xml_text, "xml")
    sub_sitemaps = []
    urls = []

    for nodo in soup.find_all("sitemap"):
        loc = nodo.find("loc")
        lastmod = nodo.find("lastmod")
        if loc and loc.text:
            sub_sitemaps.append((loc.text.strip(), lastmod.text.strip() if lastmod and lastmod.text else None))

    for nodo in soup.find_all("url"):
        loc = nodo.find("loc")
        lastmod = nodo.find("lastmod")
        news = nodo.find("news:news") or nodo.find("news")
        publication_date = None
        news_title = None
        if news:
            pub_node = news.find("news:publication_date") or news.find("publication_date")
            title_node = news.find("news:title") or news.find("title")
            publication_date = pub_node.text.strip() if pub_node and pub_node.text else None
            news_title = title_node.text.strip() if title_node and title_node.text else None
        if loc and loc.text:
            urls.append(
                {
                    "url": loc.text.strip(),
                    "lastmod": lastmod.text.strip() if lastmod and lastmod.text else None,
                    "publication_date": publication_date,
                    "title": news_title,
                }
            )

    return [loc for loc, _ in sub_sitemaps], urls


def _sitemaps_desde_robots(medio_id: str, cliente: ClienteHTTP) -> list[str]:
    robots_url = BACKFILL_SOURCES[medio_id].get("robots")
    if not robots_url:
        return []

    texto = cliente.get(robots_url, usar_cache=False, es_feed=True)
    if not texto:
        return []

    encontrados = []
    for linea in texto.splitlines():
        if linea.lower().startswith("sitemap:"):
            url = linea.split(":", 1)[1].strip()
            if url:
                encontrados.append(url)
    return encontrados


def _iso_to_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    texto = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(texto).date()
    except ValueError:
        return None


def _permitida(url: str, medio_id: str) -> bool:
    cfg = BACKFILL_SOURCES[medio_id]
    parsed = urlparse(url)
    if parsed.netloc not in cfg.get("allowed_hosts", set()):
        return False
    for fragmento in cfg.get("path_must_contain", []):
        if fragmento not in parsed.path:
            return False
    return True


def _titulo_desde_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for selector in ["meta[property='og:title']", "title", "h1"]:
        nodo = soup.select_one(selector)
        if not nodo:
            continue
        if nodo.name == "meta":
            contenido = nodo.get("content", "").strip()
            if contenido:
                return contenido
        else:
            texto = nodo.get_text(" ", strip=True)
            if texto:
                return texto
    return ""


def _resumen_desde_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for selector in ["meta[property='og:description']", "meta[name='description']"]:
        nodo = soup.select_one(selector)
        if nodo:
            contenido = nodo.get("content", "").strip()
            if contenido:
                return contenido[:800]
    parrafo = soup.select_one("article p, main p, p")
    return parrafo.get_text(" ", strip=True)[:800] if parrafo else ""


def _fecha_desde_url(url: str) -> Optional[date]:
    match = re.search(r"/(20\d{2})/(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])/", url)
    if not match:
        return None
    yyyy, mm, dd = match.groups()
    return date(int(yyyy), int(mm), int(dd))


def _ya_existe(conn: sqlite3.Connection, url: str) -> bool:
    row = conn.execute("SELECT 1 FROM noticias WHERE url_hash = ?", (url_hash(url),)).fetchone()
    return row is not None


def _guardar(conn: sqlite3.Connection, noticia: dict) -> bool:
    temas = clasificar(noticia["titulo"], noticia.get("resumen", ""))
    if not temas:
        return False

    conn.execute(
        """INSERT INTO noticias
           (url, url_hash, medio, titulo, resumen, texto_full,
            fecha_pub, fecha_scrap, fuente, raw_json, temas)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            noticia["url"],
            url_hash(noticia["url"]),
            noticia["medio"],
            noticia["titulo"],
            noticia.get("resumen"),
            noticia.get("texto_full"),
            noticia.get("fecha_pub"),
            datetime.now(timezone.utc).isoformat(),
            noticia["fuente"],
            json.dumps(noticia.get("raw"), ensure_ascii=False),
            json.dumps(temas, ensure_ascii=False),
        ),
    )
    conn.commit()
    return True


def recolectar_desde_sitemaps(
    medio_id: str,
    desde: date,
    hasta: date,
    cliente: ClienteHTTP,
    dry_run: bool = False,
) -> list[dict]:
    declarados = _sitemaps_desde_robots(medio_id, cliente)
    if declarados:
        log.info("Sitemaps detectados en robots.txt para %s: %d", medio_id, len(declarados))
    pendientes = declarados or list(BACKFILL_SOURCES[medio_id]["sitemaps"])
    visitados: set[str] = set()
    urls_candidatas: dict[str, dict] = {}

    while pendientes:
        sitemap_url = pendientes.pop(0)
        if sitemap_url in visitados:
            continue
        visitados.add(sitemap_url)

        xml_text = cliente.get(sitemap_url, usar_cache=False, es_feed=True)
        if not xml_text:
            continue

        sub_sitemaps, urls = _extraer_urls_sitemap(xml_text)
        pendientes.extend(sub_sitemaps)

        for item in urls:
            url = item["url"]
            lastmod = item.get("publication_date") or item.get("lastmod")
            if not _permitida(url, medio_id):
                continue

            fecha = _iso_to_date(lastmod) or _fecha_desde_url(url)
            if fecha and (fecha < desde or fecha > hasta):
                continue

            urls_candidatas[url] = item

    noticias = []
    for url, item in sorted(urls_candidatas.items()):
        lastmod = item.get("publication_date") or item.get("lastmod")
        titulo = (item.get("title") or "").strip()
        resumen = ""

        if not titulo or not dry_run:
            html = cliente.get(url, usar_cache=False)
            if not html:
                continue
            if not titulo:
                titulo = _titulo_desde_html(html)
            resumen = _resumen_desde_html(html)

        if not titulo:
            continue

        fecha_pub = lastmod
        noticias.append(
            {
                "medio": medio_id,
                "url": url,
                "titulo": titulo,
                "resumen": resumen,
                "texto_full": None,
                "fecha_pub": fecha_pub,
                "fuente": "backfill",
                "raw": {"sitemap_lastmod": lastmod, "origen": "backfill_test"},
            }
        )

    return noticias


def backfill_medio(
    medio_id: str,
    desde: date,
    hasta: date,
    dry_run: bool,
) -> dict:
    if medio_id not in BACKFILL_SOURCES:
        raise ValueError(f"Medio sin estrategia de backfill: {medio_id}")
    if medio_id not in MEDIOS:
        raise ValueError(f"Medio no configurado en config.py: {medio_id}")

    configurar_logging()
    conn = init_db(DB_PATH)
    cliente = ClienteHTTP()
    stats = {"medio": medio_id, "candidatas": 0, "nuevas": 0, "descartadas": 0}

    try:
        noticias = recolectar_desde_sitemaps(medio_id, desde, hasta, cliente, dry_run=dry_run)
        stats["candidatas"] = len(noticias)
        log.info("Backfill %s: %d candidatas entre %s y %s", medio_id, len(noticias), desde, hasta)

        for noticia in noticias:
            if _ya_existe(conn, noticia["url"]):
                continue
            if dry_run:
                print(f"[DRY-RUN] {noticia['medio']} | {noticia['titulo'][:90]}")
                continue
            try:
                if _guardar(conn, noticia):
                    stats["nuevas"] += 1
                else:
                    stats["descartadas"] += 1
            except Exception as exc:
                log.warning("No se pudo guardar %s: %s", noticia["url"], exc)
    finally:
        cliente.close()
        conn.close()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Prueba de backfill histórico")
    parser.add_argument("--medio", required=True, choices=sorted(BACKFILL_SOURCES.keys()))
    parser.add_argument("--desde", required=True, help="Fecha inicial YYYY-MM-DD")
    parser.add_argument("--hasta", required=True, help="Fecha final YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    desde = _parse_date(args.desde)
    hasta = _parse_date(args.hasta)
    if desde > hasta:
        raise SystemExit("--desde no puede ser posterior a --hasta")

    t0 = time.time()
    stats = backfill_medio(args.medio, desde, hasta, args.dry_run)
    elapsed = time.time() - t0
    print("\nResumen:")
    print(f"  medio: {stats['medio']}")
    print(f"  candidatas: {stats['candidatas']}")
    print(f"  nuevas: {stats['nuevas']}")
    print(f"  descartadas: {stats['descartadas']}")
    print(f"  tiempo: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
