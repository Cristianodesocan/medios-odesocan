# Monitor de Medios Canarios

Pipeline de scraping, NLP y visualización de prensa canaria.

## Estructura del proyecto

```text
canarias_monitor/
│
├── config.py          ← Medios, temáticas, rutas y parámetros
├── scraper.py         ← Recolector RSS + HTML (este módulo)
├── scheduler.py       ← Ejecución periódica
├── nlp.py             ← (próximo) Clasificación y TF-IDF
├── dashboard.py       ← App Dash interactiva conectada a Supabase
│
├── requirements.txt
├── data/
│   ├── noticias.db    ← SQLite con todas las noticias
│   └── html_cache/    ← Caché de páginas descargadas
└── logs/
    └── scraper_YYYYMMDD.log
```

## Instalación

```bash
# 1. Crear entorno virtual
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scriptsctivate         # Windows

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. (Opcional) Modelo spaCy en español para el módulo NLP
python -m spacy download es_core_news_md
```

## Configuración de Supabase

La sincronización con Supabase ya no lee credenciales desde `config.py`. Debes definirlas en variables de entorno o en un fichero `.env` dentro de esta carpeta.

```bash
cat > .env <<'EOF'
SUPABASE_HOST=aws-1-eu-west-1.pooler.supabase.com
SUPABASE_PORT=5432
SUPABASE_DBNAME=postgres
SUPABASE_USER=tu_usuario
SUPABASE_PASSWORD=tu_password
SUPABASE_SCHEMA=medios
SUPABASE_SSLMODE=require
EOF
```

Si solo quieres scrapear en SQLite local, no hace falta configurar Supabase.

## Uso

### Scraping manual

```bash
# Todos los medios
python scraper.py

# Un medio específico
python scraper.py --medio canarias7

# Prueba sin guardar en BD
python scraper.py --dry-run

# Con extracción de texto completo de cada artículo (más lento)
python scraper.py --articulos

# Ver medios configurados
python scraper.py --lista-medios
```

### Modo daemon (scheduler automático)

```bash
python scheduler.py
# Ejecuta cada día a las 10:00 y, al terminar el scraping, sincroniza los pendientes con Supabase

# Ejecutar ahora mismo una vez y salir
python scheduler.py --run-now
```

### Cron (producción en Linux/macOS)

```bash
crontab -e

# Añadir esta línea (ajusta las rutas):
0 10 * * * /ruta/a/.venv/bin/python /ruta/a/canarias_monitor/scheduler.py >> /ruta/a/logs/cron.log 2>&1
```

### Dashboard interactivo

Requiere que Supabase esté configurado y accesible.

```bash
python dashboard.py
```

Se abrirá en:

```text
http://127.0.0.1:8050
```

Variables opcionales:

```bash
DASH_HOST=0.0.0.0
DASH_PORT=8050
DASH_DEBUG=1
```

El dashboard incluye:

- filtros por medio, tema, fecha y texto libre
- KPIs de volumen, medios activos, tema dominante y último scrape
- gráficos de evolución temporal, peso por medio, temas dominantes y cruce tema x medio
- nube de palabras con titulares, resúmenes y texto completo
- tabla con enlaces directos a las noticias almacenadas en Supabase

## Consultar la BD directamente

```python
import sqlite3, pandas as pd

conn = sqlite3.connect("data/noticias.db")

# Todas las noticias de hoy
df = pd.read_sql("""
    SELECT medio, titulo, fecha_pub, url
    FROM noticias
    WHERE date(fecha_scrap) = date('now')
    ORDER BY fecha_pub DESC
""", conn)

# Noticias por medio
df.groupby("medio").size()
```

## Añadir un nuevo medio

Edita `config.py` y añade una entrada en el diccionario `MEDIOS`:

```python
"nuevo_medio": {
    "nombre":  "Nombre del Medio",
    "color":   "#hex_color",
    "url":     "https://www.ejemplo.com",
    "rss": [
        "https://www.ejemplo.com/feed/",
    ],
    "tipo": "rss_only",   # o "html_only" o "rss+html"
    "selectores": {},      # solo si tipo incluye "html"
},
```

## Próximos módulos

- **nlp.py**: tokenización con spaCy, TF-IDF, clasificación temática automática, análisis de sentimiento
