"""
scheduler.py — Ejecuta scraping + sync de forma periódica, sin iniciar el dashboard.

Dos modos:
  1. Modo daemon (recomendado para desarrollo/VPS sin cron):
       python scheduler.py

  2. Modo cron (recomendado para producción en Linux/macOS):
       Añade a crontab:  crontab -e
       # Cada día a las 10:00
       0 10 * * * /usr/bin/python3 /ruta/canarias_monitor/scheduler.py >> /ruta/logs/cron.log 2>&1

CRON CHEATSHEET para este proyecto:
  Cada hora:             0 * * * *
  Cada 2 horas:          0 */2 * * *
  Cada 2h (7-23h):       0 7-23/2 * * *
  Cada día a las 6am:    0 6 * * *
  Cada día a las 10am:   0 10 * * *
  Lunes a viernes 7am:   0 7 * * 1-5
"""

import argparse
import logging
import time

import schedule

from scraper import scrapear_todos
from supabase_loader import sincronizar, sincronizar_log

log = logging.getLogger("scheduler")


def configurar_logging() -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def job() -> None:
    configurar_logging()
    log.info("▶ Ejecutando scraping programado…")
    try:
        resultados = scrapear_todos(dry_run=False, extraer_articulos=True)
        nuevas = sum(r.get("nuevas", 0) for r in resultados)
        log.info("✓ Scraping completado — %d noticias nuevas", nuevas)
    except Exception as e:
        log.error("✗ Error en scraping programado: %s", e, exc_info=True)
        return   # No intentar sync si el scraping falló

    # Sincronizar con Supabase tras cada scraping
    try:
        log.info("▶ Sincronizando con Supabase…")
        stats = sincronizar()
        sincronizar_log(resultados)
        log.info("✓ Supabase — %d insertadas / %d errores", stats["insertadas"], stats["errores"])
    except Exception as e:
        log.error("✗ Error en sincronización Supabase: %s", e, exc_info=True)

    # Regenerar dashboard D3 con datos frescos
    try:
        from generate_dashboard import main as generar_dashboard
        generar_dashboard()
        log.info("✓ Dashboard D3 regenerado")
    except Exception as e:
        log.error("✗ Error regenerando dashboard D3: %s", e, exc_info=True)


if __name__ == "__main__":
    configurar_logging()
    parser = argparse.ArgumentParser(description="Scheduler del monitor de medios")
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Ejecuta scraping + sync inmediatamente y termina",
    )
    args = parser.parse_args()

    if args.run_now:
        log.info("Ejecución manual inmediata del scheduler")
        job()
        raise SystemExit(0)

    log.info("Scheduler iniciado en modo headless. No lanza el dashboard. Ctrl+C para detener.")

    # Programar una única ejecución diaria a las 10:00.
    schedule.every().day.at("10:00").do(job)
    log.info("Ejecución programada cada día a las 10:00")

    while True:
        schedule.run_pending()
        proxima = schedule.next_run()
        log.info("Próxima ejecución: %s", proxima)
        time.sleep(60)
