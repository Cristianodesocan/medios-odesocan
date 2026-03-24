"""
supabase_loader.py — Sincroniza noticias desde SQLite local → Supabase (schema medios).

Uso:
    python supabase_loader.py              # Sincroniza todo lo pendiente
    python supabase_loader.py --limit 500  # Máximo de registros por ejecución
    python supabase_loader.py --dry-run    # Muestra qué se enviaría sin escribir
"""

import argparse
import json
import logging
import sqlite3
from datetime import datetime
from typing import Optional

import psycopg2
import psycopg2.extras
from psycopg2.extras import Json

from clasificador import clasificar
from config import DB_PATH, LOG_DIR, SUPABASE

log = logging.getLogger("supabase_loader")


def configurar_logging() -> None:
    """Configura logging por defecto si la aplicación aún no lo hizo."""
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_DIR / f"supabase_{datetime.now():%Y%m%d}.log"),
        ],
    )


# ── Conexiones ────────────────────────────────────────────────────────────────

def conectar_supabase() -> psycopg2.extensions.connection:
    missing = [
        key.upper()
        for key, value in SUPABASE.items()
        if key in {"host", "dbname", "user", "password", "schema"} and not value
    ]
    if missing:
        raise RuntimeError(
            "Faltan variables de entorno de Supabase: " + ", ".join(f"SUPABASE_{k}" for k in missing)
        )

    conn = psycopg2.connect(
        host=SUPABASE["host"],
        port=SUPABASE["port"],
        dbname=SUPABASE["dbname"],
        user=SUPABASE["user"],
        password=SUPABASE["password"],
        sslmode=SUPABASE["sslmode"],
    )
    conn.autocommit = False
    log.info("Conexión a Supabase establecida")
    return conn


def conectar_sqlite() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Sincronización ────────────────────────────────────────────────────────────

def _hashes_en_supabase(pg: psycopg2.extensions.connection) -> set[str]:
    """Devuelve el conjunto de url_hash ya presentes en Supabase."""
    schema = SUPABASE["schema"]
    with pg.cursor() as cur:
        cur.execute(f"SELECT url_hash FROM {schema}.noticias")
        return {row[0] for row in cur.fetchall()}


def _noticias_sqlite(
    sq: sqlite3.Connection,
    excluir_hashes: set[str],
    limit: Optional[int],
) -> list[dict]:
    """Lee de SQLite las noticias que aún no están en Supabase."""
    placeholders = ",".join("?" * len(excluir_hashes)) if excluir_hashes else "''"
    query = f"""
        SELECT url, url_hash, medio, titulo, resumen, texto_full,
               fecha_pub, fecha_scrap, fuente, raw_json, temas
        FROM noticias
        {"WHERE url_hash NOT IN (" + placeholders + ")" if excluir_hashes else ""}
        ORDER BY fecha_scrap ASC
        {"LIMIT " + str(limit) if limit else ""}
    """
    params = tuple(excluir_hashes) if excluir_hashes else ()
    rows = sq.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def _normalizar_temas(temas_raw: object) -> list[str]:
    """Normaliza temas y descarta valores vacíos o equivalentes a NA."""
    if temas_raw is None:
        return []

    temas = temas_raw
    if isinstance(temas_raw, str):
        valor = temas_raw.strip()
        if not valor or valor.upper() == "NA" or valor.lower() == "null":
            return []
        try:
            temas = json.loads(valor)
        except json.JSONDecodeError:
            return []

    if isinstance(temas, str):
        temas = [temas]

    if not isinstance(temas, list):
        return []

    return [
        tema.strip()
        for tema in temas
        if isinstance(tema, str) and tema.strip() and tema.strip().upper() != "NA"
    ]


def _purgar_noticias_sin_temas(sq: sqlite3.Connection) -> int:
    """Elimina de SQLite las noticias sin temas clasificables."""
    filas = sq.execute("SELECT id, url_hash, temas FROM noticias").fetchall()
    ids_a_borrar = [
        fila["id"]
        for fila in filas
        if not _normalizar_temas(fila["temas"])
    ]
    if not ids_a_borrar:
        return 0

    placeholders = ",".join("?" * len(ids_a_borrar))
    sq.execute(f"DELETE FROM noticias WHERE id IN ({placeholders})", ids_a_borrar)
    sq.commit()
    log.info("Noticias eliminadas de SQLite por temas vacíos/NA: %d", len(ids_a_borrar))
    return len(ids_a_borrar)


def _temas_para_supabase(noticia: dict) -> list[str]:
    """Devuelve los temas válidos guardados en SQLite."""
    return _normalizar_temas(noticia.get("temas"))


def sincronizar(
    dry_run: bool = False,
    limit: Optional[int] = None,
) -> dict:
    """
    Lee noticias de SQLite y las inserta en Supabase (upsert por url_hash).
    Devuelve estadísticas: total_locales, pendientes, insertadas, errores.
    """
    configurar_logging()
    sq = conectar_sqlite()
    pg = conectar_supabase()
    schema = SUPABASE["schema"]
    stats = {
        "total_locales": 0,
        "eliminadas": 0,
        "pendientes": 0,
        "insertadas": 0,
        "errores": 0,
    }

    try:
        stats["eliminadas"] = _purgar_noticias_sin_temas(sq)

        # Total en SQLite
        stats["total_locales"] = sq.execute("SELECT COUNT(*) FROM noticias").fetchone()[0]
        log.info("Total noticias en SQLite: %d", stats["total_locales"])

        # Qué ya está en Supabase
        ya_subidas = _hashes_en_supabase(pg)
        log.info("Ya en Supabase: %d", len(ya_subidas))

        # Pendientes
        pendientes = _noticias_sqlite(sq, ya_subidas, limit)
        stats["pendientes"] = len(pendientes)
        log.info("Pendientes de sincronizar: %d", stats["pendientes"])

        if dry_run:
            for n in pendientes:
                print(f"  [DRY-RUN] {n['medio']} | {n['titulo'][:70]}")
            return stats

        if not pendientes:
            log.info("Nada que sincronizar.")
            return stats

        # Insertar en lotes de 200
        lote_size = 200
        insert_sql = f"""
            INSERT INTO {schema}.noticias
                (url, url_hash, medio, titulo, resumen, texto_full,
                 fecha_pub, fecha_scrap, fuente, raw_json, temas)
            VALUES %s
            ON CONFLICT (url_hash) DO NOTHING
        """

        for i in range(0, len(pendientes), lote_size):
            lote = pendientes[i : i + lote_size]
            valores = [
                (
                    n["url"],
                    n["url_hash"],
                    n["medio"],
                    n["titulo"],
                    n.get("resumen"),
                    n.get("texto_full"),
                    n.get("fecha_pub"),
                    n.get("fecha_scrap"),
                    n["fuente"],
                    Json(json.loads(n["raw_json"])) if n.get("raw_json") else None,
                    _temas_para_supabase(n),
                )
                for n in lote
            ]
            try:
                with pg.cursor() as cur:
                    psycopg2.extras.execute_values(cur, insert_sql, valores)
                pg.commit()
                stats["insertadas"] += len(lote)
                log.info(
                    "  ✓ Lote %d-%d insertado (%d registros)",
                    i + 1,
                    i + len(lote),
                    len(lote),
                )
            except Exception as e:
                pg.rollback()
                stats["errores"] += len(lote)
                log.error("Error en lote %d-%d: %s", i + 1, i + len(lote), e, exc_info=True)

        log.info(
            "Sincronización completada — %d insertadas / %d errores",
            stats["insertadas"],
            stats["errores"],
        )

    finally:
        sq.close()
        pg.close()

    return stats


def actualizar_temas_vacios() -> int:
    """Reclasifica en Supabase los registros sin temas y elimina los no clasificables."""
    configurar_logging()
    pg = conectar_supabase()
    schema = SUPABASE["schema"]
    actualizados = 0
    eliminados = 0
    try:
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"SELECT url_hash, titulo, resumen FROM {schema}.noticias WHERE temas IS NULL")
            filas = cur.fetchall()

        if not filas:
            log.info("No hay registros sin temas en Supabase.")
            return 0

        log.info("Reclasificando %d registros sin temas…", len(filas))
        with pg.cursor() as cur:
            for fila in filas:
                temas = clasificar(fila["titulo"] or "", fila["resumen"] or "")
                if temas:
                    cur.execute(
                        f"UPDATE {schema}.noticias SET temas = %s WHERE url_hash = %s",
                        (temas, fila["url_hash"]),
                    )
                    actualizados += 1
                else:
                    cur.execute(
                        f"DELETE FROM {schema}.noticias WHERE url_hash = %s",
                        (fila["url_hash"],),
                    )
                    eliminados += 1
        pg.commit()
        log.info("Temas actualizados: %d registros", actualizados)
        if eliminados:
            log.info("Noticias eliminadas en Supabase por temas vacíos/NA: %d", eliminados)
    except Exception as e:
        pg.rollback()
        log.error("Error actualizando temas: %s", e, exc_info=True)
    finally:
        pg.close()
    return actualizados


def sincronizar_log(run_stats: list[dict]) -> None:
    """
    Copia el scraping_log de SQLite a Supabase.
    Solo inserta las entradas con status='ok' aún no presentes.
    """
    configurar_logging()
    sq = conectar_sqlite()
    pg = conectar_supabase()
    schema = SUPABASE["schema"]

    try:
        # Fechas de inicio ya en Supabase
        with pg.cursor() as cur:
            cur.execute(f"SELECT inicio::text FROM {schema}.scraping_log")
            ya_en_pg = {row[0][:19] for row in cur.fetchall()}  # truncar a segundos

        filas = sq.execute(
            "SELECT medio, inicio, fin, total, nuevas, errores, status "
            "FROM scraping_log WHERE status = 'ok'"
        ).fetchall()

        pendientes = [
            dict(r) for r in filas
            if (r["inicio"] or "")[:19] not in ya_en_pg
        ]

        if not pendientes:
            return

        valores = [
            (r["medio"], r["inicio"], r["fin"], r["total"], r["nuevas"], r["errores"], r["status"])
            for r in pendientes
        ]
        with pg.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                f"""INSERT INTO {schema}.scraping_log
                    (medio, inicio, fin, total, nuevas, errores, status)
                    VALUES %s ON CONFLICT DO NOTHING""",
                valores,
            )
        pg.commit()
        log.info("scraping_log: %d entradas sincronizadas", len(pendientes))

    except Exception as e:
        pg.rollback()
        log.error("Error sincronizando scraping_log: %s", e, exc_info=True)
    finally:
        sq.close()
        pg.close()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    configurar_logging()
    parser = argparse.ArgumentParser(description="Sincroniza SQLite → Supabase (schema medios)")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Máximo de noticias a enviar por ejecución",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra pendientes sin escribir en Supabase",
    )
    args = parser.parse_args()

    stats = sincronizar(dry_run=args.dry_run, limit=args.limit)
    if not args.dry_run:
        sincronizar_log([])
        actualizar_temas_vacios()

    print("\nResumen:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
