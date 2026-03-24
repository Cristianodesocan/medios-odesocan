"""
generate_dashboard.py — Regenera el HTML del dashboard D3 con datos frescos de la BD local.

Uso:
    python generate_dashboard.py               # Sobreescribe el HTML original
    python generate_dashboard.py --dry-run     # Muestra estadísticas sin escribir
    python generate_dashboard.py --output /ruta/output.html
"""

import argparse
import json
import logging
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from config import BASE_DIR, DB_PATH, MEDIOS, TEMAS

log = logging.getLogger("generate_dashboard")

DASHBOARD_HTML = BASE_DIR / "dashboard_medios_odesocan.html"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _configurar_logging() -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def _normalizar_temas(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(t).strip() for t in parsed if str(t).strip()]
    except (json.JSONDecodeError, TypeError):
        pass
    s = str(raw).strip()
    return [s] if s else []


# ── Lectura de BD ─────────────────────────────────────────────────────────────

def cargar_noticias() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT medio, titulo, temas, url, fecha_scrap
        FROM noticias
        WHERE titulo IS NOT NULL AND titulo != ''
        ORDER BY fecha_scrap DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    for r in rows:
        r["temas_list"] = _normalizar_temas(r["temas"])
    return rows


# ── Construcción de los arrays JS ─────────────────────────────────────────────

def construir_datos(noticias: list[dict]) -> dict:

    # MM — totales por medio
    medio_counts: dict[str, int] = defaultdict(int)
    for n in noticias:
        medio_counts[n["medio"]] += 1

    MM = [
        {"medio": m, "total": medio_counts.get(m, 0), "color": cfg["color"]}
        for m, cfg in MEDIOS.items()
        if medio_counts.get(m, 0) > 0
    ]
    MM.sort(key=lambda x: -x["total"])

    # TM — totales por tema
    tema_counts: dict[str, int] = defaultdict(int)
    for n in noticias:
        for t in n["temas_list"]:
            if t in TEMAS:
                tema_counts[t] += 1

    TM = [
        {"tema": t, "n": tema_counts.get(t, 0), "color": cfg["color"]}
        for t, cfg in TEMAS.items()
    ]
    TM.sort(key=lambda x: -x["n"])

    # HM — matriz medio × tema (heatmap)
    hm: dict[tuple, int] = defaultdict(int)
    for n in noticias:
        for t in n["temas_list"]:
            if t in TEMAS:
                hm[(n["medio"], t)] += 1

    HM = [
        {"medio": medio, "tema": tema, "n": count}
        for (medio, tema), count in hm.items()
        if count > 0
    ]

    # TD — actividad por hora del día
    td: dict[tuple, int] = defaultdict(int)
    for n in noticias:
        if not n.get("fecha_scrap"):
            continue
        try:
            ts = n["fecha_scrap"].replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts)
            hora_key = dt.strftime("%Y-%m-%dT%H:00")
            td[(n["medio"], hora_key)] += 1
        except (ValueError, AttributeError):
            continue

    TD = [
        {"medio": medio, "hora": hora, "n": count}
        for (medio, hora), count in td.items()
    ]
    TD.sort(key=lambda x: (x["hora"], x["medio"]))

    # NW — noticias clasificadas (máx. 500 más recientes)
    NW = [
        {
            "titulo": n["titulo"],
            "medio":  n["medio"],
            "temas":  n["temas_list"],
            "url":    n["url"] or "#",
        }
        for n in noticias
        if n["temas_list"]
    ][:500]

    return {"MM": MM, "TM": TM, "HM": HM, "TD": TD, "NW": NW}


# ── Inyección en el HTML ───────────────────────────────────────────────────────

def generar_html(datos: dict, output: Path, dry_run: bool = False) -> None:
    html = DASHBOARD_HTML.read_text(encoding="utf-8")

    MM, TM, HM, TD, NW = datos["MM"], datos["TM"], datos["HM"], datos["TD"], datos["NW"]

    total       = sum(m["total"] for m in MM)
    num_medios  = len(MM)
    num_temas   = len([t for t in TM if t["n"] > 0])
    fecha_gen   = datetime.now().strftime("%d.%m.%Y")

    # Bloque de datos JS que sustituirá al existente
    nuevo_bloque = (
        f"const MM={json.dumps(MM, ensure_ascii=False)};\n"
        f"const CM=Object.fromEntries(MM.map(d=>[d.medio,d.color]));\n"
        f"const TM={json.dumps(TM, ensure_ascii=False)}.sort((a,b)=>b.n-a.n);\n"
        f"const CT=Object.fromEntries(TM.map(d=>[d.tema,d.color]));\n"
        f"const HM={json.dumps(HM, ensure_ascii=False)};\n"
        f"const TD={json.dumps(TD, ensure_ascii=False)};\n"
        f"const NW={json.dumps(NW, ensure_ascii=False)};"
    )

    # Reemplaza desde "const MM=" hasta justo antes de "const LM="
    html_nuevo = re.sub(
        r'const MM=\[[\s\S]*?const NW=\[[\s\S]*?\];',
        nuevo_bloque,
        html,
        count=1,
    )

    if html_nuevo == html:
        log.warning("No se encontró el bloque de datos para reemplazar — revisa el HTML.")
        return

    # Actualiza badges de cabecera
    html_nuevo = re.sub(r'(<span>)\d+(</span> noticias)', rf'\g<1>{total}\g<2>', html_nuevo)
    html_nuevo = re.sub(r'(<span>)\d+(</span> medios)',   rf'\g<1>{num_medios}\g<2>', html_nuevo)
    html_nuevo = re.sub(r'(<span>)\d+(</span> temáticas)',rf'\g<1>{num_temas}\g<2>', html_nuevo)

    # Actualiza el footer
    html_nuevo = re.sub(
        r'· \d+ registros · [\d.]+\.\d{4}',
        f'· {total} registros · {fecha_gen}',
        html_nuevo,
    )

    if dry_run:
        log.info("[DRY-RUN] Se generaría → %s (%d noticias, %d medios, %d temas)",
                 output, total, num_medios, num_temas)
        return

    output.write_text(html_nuevo, encoding="utf-8")
    log.info("✓ Dashboard actualizado → %s  [%d noticias · %d medios · %d temas activos]",
             output, total, num_medios, num_temas)


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main(output: Path | None = None, dry_run: bool = False) -> None:
    _configurar_logging()
    out = output or DASHBOARD_HTML

    log.info("Cargando noticias desde BD…")
    noticias = cargar_noticias()
    log.info("%d noticias en BD", len(noticias))

    datos = construir_datos(noticias)
    generar_html(datos, out, dry_run=dry_run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Regenera el dashboard D3 con datos frescos")
    parser.add_argument("--output",   type=Path, default=None,  help="Ruta de salida (por defecto sobreescribe el original)")
    parser.add_argument("--dry-run",  action="store_true",       help="Muestra estadísticas sin escribir nada")
    args = parser.parse_args()
    main(output=args.output, dry_run=args.dry_run)
