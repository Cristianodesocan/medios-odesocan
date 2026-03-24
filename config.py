"""
config.py — Configuración central del monitor de medios canarios
Edita este fichero para añadir medios, ajustar temas o cambiar rutas.
"""

import os
from pathlib import Path

# ── Rutas ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data"
DB_PATH    = DATA_DIR / "noticias.db"
CACHE_DIR  = DATA_DIR / "html_cache"
LOG_DIR    = BASE_DIR / "logs"

for d in [DATA_DIR, CACHE_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Medios canarios ───────────────────────────────────────────────────────────
# Cada medio tiene:
#   rss   → lista de feeds RSS/Atom (vacía si no tiene)
#   url   → portada para scraping HTML directo
#   color → para el dashboard
#   tipo  → "rss_only" | "html_only" | "rss+html"
#   selectores → CSS selectors para extraer titulares del HTML (si aplica)
#   html_url_regex / html_url_excludes → filtros opcionales sobre URLs HTML

MEDIOS = {
    "canarias7": {
        "nombre":  "Canarias7",
        "color":   "#1a5fa8",
        "url":     "https://www.canarias7.es",
        "rss": [
            "https://www.canarias7.es/rss/2.0/",
        ],
        "tipo": "rss+html",
        # Cuota reducida: RSS ya trae ~50 items; sin límite dominaría el total
        "max_items": 20,
        "selectores": {
            "titular": "h2.article-title a, h3.article-title a, article h2 a",
            "resumen": "p.article-summary, div.article-body p:first-of-type",
        },
    },
    "laprovincia": {
        "nombre":  "La Provincia",
        "color":   "#d63b2f",
        "url":     "https://www.laprovincia.es",
        "rss": [],
        "tipo": "html_only",   # RSS devuelve 404
        "max_items": 30,
        # Plataforma CDS Prensa Ibérica: h6 también usado en modNews
        "selectores": {
            "titular": "h2 a, h3 a, h6 a",
            "resumen": ".ft-mol-subtitle, p",
        },
        # Solo URLs con patrón /seccion/YYYY/MM/DD/slug-XXXXXXXX.html
        "html_url_regex": r"https://www\.laprovincia\.es/[\w/-]+/\d{4}/\d{2}/\d{2}/[\w-]+-\d+\.html",
    },
    "eldia": {
        "nombre":  "El Día",
        "color":   "#2e7d32",
        "url":     "https://www.eldia.es",
        "rss": [],
        "tipo": "html_only",   # RSS devuelve 404
        "max_items": 30,
        # Misma plataforma CDS Prensa Ibérica — URL regex filtra navegación y ticker
        "selectores": {
            "titular": "h2 a, h3 a",
            "resumen": ".ft-mol-subtitle, p",
        },
        "html_url_regex": r"https://www\.eldia\.es/[\w/-]+/\d{4}/\d{2}/\d{2}/[\w-]+-\d+\.html",
    },
    "diariodeavisos": {
        "nombre":  "Diario de Avisos",
        "color":   "#6a1b9a",
        "url":     "https://diariodeavisos.elespanol.com",
        "rss": [
            "https://diariodeavisos.elespanol.com/feed/",
        ],
        "tipo": "rss+html",
        "max_items": 25,
        # WordPress + Astra: clases entry-title y entry-extracto confirmadas en DOM
        "selectores": {
            "titular": "h2.entry-title a, .entry-title a",
            "resumen": ".entry-extracto, .entry-excerpt",
        },
    },
    "laopinion": {
        "nombre":  "La Opinión de Tenerife",
        "color":   "#e65100",
        "url":     "https://www.laopinion.es",
        "rss": [],
        "tipo": "html_only",   # RSS redirige a epe.es (grupo editorial, no el medio)
        "max_items": 25,
        "selectores": {
            "titular": "h2 a, h3 a, .article-title a",
            "resumen": ".article-summary, p.subtitle",
        },
    },
    "elpueblocanario": {
        "nombre":  "El Pueblo Canario",
        "color":   "#00838f",
        "url":     "https://www.elpueblocanario.es",
        "rss": [],
        "tipo": "html_only",   # robots.txt bloquea el feed RSS
        "max_items": 25,
        "selectores": {
            "titular": "h2 a, h3 a, .entry-title a, article a",
            "resumen": ".entry-excerpt, .entry-summary, p.lead",
        },
    },
    "canariasnoticias": {
        "nombre":  "Canarias Noticias",
        "color":   "#558b2f",
        "url":     "https://www.canariosnoticias.es",
        "rss": [],
        "tipo": "html_only",   # robots.txt bloquea el feed RSS
        "max_items": 25,
        "selectores": {
            "titular": "h2 a, h3 a, .entry-title a, article a",
            "resumen": ".entry-excerpt, .entry-summary, p.lead",
        },
    },
    "canariasahora": {
        "nombre":  "Canarias Ahora",
        "color":   "#c62828",
        "url":     "https://www.eldiario.es/canariasahora/",
        "rss": [],
        "tipo": "html_only",   # La portada opera dentro de eldiario.es (React SPA)
        # React SPA: el DOM llega vacío con httpx → necesita Playwright
        "playwright": True,
        "max_items": 25,
        "selectores": {
            "titular": "p.title a, a.post-title, .ni-title a",
            "resumen": "p",
        },
        "html_url_regex": r"^https://www\.eldiario\.es/canariasahora/.+_\d+_\d+\.html(?:$|[?#])",
        "html_url_excludes": [
            "/busqueda/",
            "/autores/",
            "/contacto/",
            "/que_es/",
            "/aviso_legal/",
            "/politica_de_privacidad/",
        ],
    },
    "atlanticohoy": {
        "nombre":  "Atlántico Hoy",
        "color":   "#00695c",
        "url":     "https://www.atlanticohoy.com/",
        "rss": [],
        "tipo": "html_only",
        "max_items": 25,
        # CMS propio: clases de portada confirmadas en DOM
        "selectores": {
            "titular": ".c-highlight__item a, .c-ranking__link, .c-now-home__title-link, h2 a, h3 a",
            "resumen": "p",
        },
        # Patrón URL: /seccion/slug_XXXXXXXX_XX.html
        "html_url_regex": r"https://www\.atlanticohoy\.com/[\w-]+/[\w-]+_\d+_\d+\.html",
    },
    # ── Medios insulares ─────────────────────────────────────────────────────
    "eltime": {
        "nombre":  "El Time",
        "color":   "#d4a017",
        "url":     "https://eltime.es/",
        "rss": [],
        "tipo": "html_only",   # RSS existe pero devuelve feed vacío
        "max_items": 25,
        # Joomla 2.5/3.x — IceTheme Newsy 3 + mod_raxo_allmode
        "selectores": {
            "titular": "h4 a, div.allmode_title a",
            "resumen": "div.allmode_introtext p, div.allmode_introtext",
        },
        # Patrón Joomla SEF: /categoria/ID-slug.html
        "html_url_regex": r"https://eltime\.es/.+/\d+-[\w-]+\.html",
    },
    "gomeraverde": {
        "nombre":  "Gomera Verde",
        "color":   "#388e3c",
        "url":     "https://gomeraverde.es/",
        "rss": [
            "https://gomeraverde.es/coverrss",
        ],
        "tipo": "rss+html",
        "max_items": 25,
        # folioePress CMS (CodeIgniter)
        "selectores": {
            "titular": "h1.title a",
            "resumen": "div.newsbody > p",
        },
        # Patrón: /art/{id}/{slug}
        "html_url_regex": r"https://gomeraverde\.es/art/\d+/[\w-]+",
    },
    "lancelotdigital": {
        "nombre":  "Lancelot Digital",
        "color":   "#bf360c",
        "url":     "https://www.lancelotdigital.com/",
        "rss": [
            "https://www.lancelotdigital.com/?format=feed&type=rss",
        ],
        "tipo": "rss+html",
        "max_items": 25,
        # Joomla 4.x/5.x — GavicK Reporter + mod_news_pro_gk5
        "selectores": {
            "titular": "h3.nspHeader a, a.mod-articles-category-title",
            "resumen": "h4.nspText",
        },
        # Patrón: /{categoria}/{slug}
        "html_url_regex": r"https://www\.lancelotdigital\.com/[\w-]+/[\w-]+",
        "html_url_excludes": ["/component/", "/component/banners/"],
    },
    "elhierrohoy": {
        "nombre":  "El Hierro Hoy",
        "color":   "#5d4037",
        "url":     "https://elhierrohoy.es/",
        "rss": [
            "https://elhierrohoy.es/feed/",
        ],
        "tipo": "rss+html",
        "max_items": 20,
        # WordPress + Elementor Pro (Hello Elementor theme)
        "selectores": {
            "titular": ".elementor-widget-theme-post-title h1.elementor-heading-title a",
            "resumen": ".elementor-widget-theme-post-excerpt",
        },
        # Patrón WP: /{slug}/
        "html_url_regex": r"https://elhierrohoy\.es/[\w-]+/",
        "html_url_excludes": ["/category/", "/tag/", "/author/", "/page/", "/?columnas="],
    },
    "lavozdefuerteventura": {
        "nombre":  "La Voz de Fuerteventura",
        "color":   "#f9a825",
        "url":     "https://www.lavozdefuerteventura.com/",
        "rss": [
            "https://www.lavozdefuerteventura.com/rss/",
        ],
        "tipo": "rss+html",
        "max_items": 25,
        # OpenNemas CMS
        "selectores": {
            "titular": "h2.title a, div.data-title a",
            "resumen": "div.summary, div.subtitle",
        },
        # Patrón: /articulo/{cat}/{slug}/{timestamp+id}.html
        "html_url_regex": r"https://www\.lavozdefuerteventura\.com/articulo/[\w-]+/[\w-]+/\d+\.html",
    },
}

# ── Temáticas y diccionarios de palabras clave ────────────────────────────────
# Cada tema tiene palabras clave (título + cuerpo) que activan la clasificación.
# Orden importa: la primera coincidencia con mayor score gana.

TEMAS = {
    "migracion": {
        "label":  "Migración",
        "color":  "#1565c0",
        "keywords": [
            # --- términos nucleares ---
            "migrante", "migrantes", "migración", "migratorio", "migratorios",
            "inmigrante", "inmigrantes", "inmigración",
            "patera", "pateras", "cayuco", "cayucos",
            # --- menores y acogida migratoria ---
            "mena", "menas", "menor extranjero", "menores no acompañados",
            "acogida de migrantes", "acogida humanitaria", "centro de internamiento",
            # --- rutas y travesías ---
            "ruta canaria", "ruta atlántica", "travesía migratoria", "naufragio",
            "lancha neumática", "embarcación migrantes",
            # --- política migratoria ---
            "frontex", "repatriación", "regularización", "solicitante de asilo",
            "refugiado", "refugiados", "cupo migratorio", "reparto migrantes",
            "crisis migratoria", "flujo migratorio", "llegada de migrantes",
            "rescate marítimo", "salvamento marítimo",
        ],
        "peso_titulo": 3,
    },
    "economia": {
        "label":  "Economía",
        "color":  "#2e7d32",
        "keywords": [
            # --- indicadores macro ---
            "pib", "producto interior bruto", "inflación", "ipc",
            "recesión", "crecimiento económico", "actividad económica",
            # --- empleo y mercado laboral ---
            "tasa de paro", "tasa de desempleo", "tasa de empleo",
            "desempleo", "empleo", "epa", "afiliación seguridad social",
            "convenio colectivo", "negociación colectiva", "sindicato",
            "salario mínimo", "subida salarial", "reforma laboral",
            # --- comercio y tejido empresarial ---
            "exportación canaria", "importación canaria", "balanza comercial",
            "zona especial canaria", "zec", "zona franca",
            "rie", "régimen económico fiscal", "ref",
            "autónomo", "autónomos", "pyme", "cierre de empresa",
            "concurso de acreedores", "ere", "erte",
        ],
        "peso_titulo": 3,
    },
    "presupuestos": {
        "label":  "Presupuestos",
        "color":  "#e65100",
        "keywords": [
            # --- presupuestos públicos ---
            "presupuesto", "presupuestos", "presupuestos generales",
            "ley de presupuestos", "pge", "presupuesto autonómico",
            "partida presupuestaria", "crédito extraordinario",
            # --- gasto e inversión pública ---
            "gasto público", "inversión pública", "inversión estatal",
            "dotación presupuestaria", "ejecución presupuestaria",
            # --- fiscalidad ---
            "hacienda canaria", "agencia tributaria", "recaudación fiscal",
            "impuesto canario", "igic", "tributo", "aiem",
            "deuda pública", "déficit público", "superávit",
            # --- financiación territorial ---
            "financiación autonómica", "convenio de carreteras",
            "subvención pública", "fondos europeos", "fondos next generation",
            "transferencia estatal", "enmienda presupuestaria",
        ],
        "peso_titulo": 3,
    },
    "violencia_genero": {
        "label":  "Violencia de género",
        "color":  "#880e4f",
        "keywords": [
            # --- términos nucleares ---
            "violencia de género", "violencia machista", "violencia contra la mujer",
            "feminicidio", "femicidio", "mujer asesinada",
            # --- formas de violencia ---
            "maltrato machista", "maltratador", "agresor machista",
            "agresión sexual", "violación", "violador",
            "acoso sexual", "sumisión química",
            # --- protección y respuesta institucional ---
            "orden de alejamiento", "orden de protección",
            "punto violeta", "pacto de estado violencia",
            "casa de acogida víctimas", "víctima de género",
            "denuncia por maltrato", "denuncia por violencia de género",
            # --- conceptos asociados ---
            "misoginia", "machismo", "control coercitivo",
        ],
        "peso_titulo": 4,
    },
    "politica": {
        "label":  "Política",
        "color":  "#4a148c",
        "keywords": [
            # --- instituciones canarias ---
            "parlamento canario", "gobierno de canarias", "gobierno canario",
            "cabildo insular", "cabildo de tenerife", "cabildo de gran canaria",
            "consejería", "diputado del común",
            # --- partidos y actores ---
            "coalición canaria", "nueva canarias", "psoe canarias",
            "pp canarias", "podemos canarias", "drago", "asamblea socialista",
            # --- actividad parlamentaria ---
            "pleno parlamentario", "pleno del cabildo", "pleno municipal",
            "moción de censura", "proposición de ley", "decreto ley",
            "elecciones canarias", "elecciones municipales", "votación parlamentaria",
            "pacto de gobierno", "investidura", "oposición parlamentaria",
            # --- competencias y estatuto ---
            "estatuto de autonomía", "transferencia competencial",
            "régimen especial canario",
        ],
        "peso_titulo": 2,
    },
    "medio_ambiente": {
        "label":  "Medio ambiente",
        "color":  "#1b5e20",
        "keywords": [
            # --- cambio climático y emisiones ---
            "cambio climático", "calentamiento global", "emisiones co2",
            "huella de carbono", "descarbonización", "gases de efecto invernadero",
            # --- contaminación y residuos ---
            "contaminación ambiental", "vertido ilegal", "vertido al mar",
            "residuos urbanos", "reciclaje", "planta de residuos",
            "contaminación atmosférica", "microplástico",
            # --- energía ---
            "energía renovable", "energía fotovoltaica", "energía eólica",
            "parque eólico", "planta solar", "transición energética",
            # --- biodiversidad y espacios naturales ---
            "biodiversidad", "especie protegida", "especie invasora",
            "parque natural", "parque nacional", "reserva de la biosfera",
            "red natura 2000", "posidonia",
            # --- emergencias ambientales ---
            "incendio forestal", "sequía", "desertificación",
        ],
        "peso_titulo": 2,
    },
    "vivienda": {
        "label":  "Vivienda",
        "color":  "#f57f17",
        "keywords": [
            # --- acceso a vivienda ---
            "precio de la vivienda", "acceso a la vivienda", "burbuja inmobiliaria",
            "vivienda asequible", "primera vivienda", "compraventa de vivienda",
            # --- alquiler ---
            "alquiler", "precio del alquiler", "subida del alquiler",
            "arrendamiento", "inquilino", "bono alquiler joven",
            "alquiler vacacional", "vivienda vacacional",
            # --- vivienda pública y social ---
            "vivienda social", "vivienda pública", "vivienda protegida",
            "parque de vivienda", "promoción de vivienda",
            "ley de vivienda", "plan de vivienda",
            # --- problemas habitacionales ---
            "desahucio", "lanzamiento judicial", "okupación",
            "sinhogarismo", "emergencia habitacional",
            # --- urbanismo vinculado ---
            "suelo urbanizable", "plan general de ordenación",
            "hipoteca", "mercado inmobiliario",
        ],
        "peso_titulo": 3,
    },
    "sanidad": {
        "label":  "Sanidad",
        "color":  "#008591",
        "keywords": [
            # --- sistema sanitario canario ---
            "servicio canario de salud", "scs", "sanidad canaria",
            "hospital", "hospital universitario", "centro de salud",
            "atención primaria", "urgencias hospitalarias",
            # --- personal sanitario ---
            "personal sanitario", "médico de familia", "enfermería",
            "huelga médicos", "huelga sanitaria", "plaza mir",
            "médico especialista", "déficit de médicos",
            # --- listas de espera y gestión ---
            "lista de espera", "lista de espera quirúrgica",
            "saturación de urgencias", "cama hospitalaria",
            "ambulancia", "ambulatorio",
            # --- salud pública ---
            "vacunación", "campaña de vacunación", "epidemia", "brote",
            "alerta sanitaria", "oncología", "quirófano",
        ],
        "peso_titulo": 3,
    },
    "salud_mental": {
        "label":  "Salud mental",
        "color":  "#d28aff",
        "keywords": [
            # --- términos nucleares ---
            "salud mental", "trastorno mental", "enfermedad mental",
            "crisis de salud mental",
            # --- trastornos específicos ---
            "depresión", "ansiedad", "trastorno bipolar",
            "trastorno alimentario", "anorexia", "bulimia",
            "trastorno obsesivo", "esquizofrenia",
            # --- suicidio ---
            "suicidio", "conducta suicida", "prevención del suicidio",
            "ideación suicida", "teléfono de la esperanza",
            # --- atención y profesionales ---
            "psiquiatría", "psicólogo", "psicología clínica",
            "unidad de salud mental", "atención psicológica",
            # --- adicciones ---
            "drogodependencia", "ludopatía", "adicción al juego",
            "centro de adicciones",
            # --- estrés y bienestar ---
            "burnout", "estrés postraumático",
        ],
        "peso_titulo": 4,
    },
    "turismo": {
        "label":  "Turismo",
        "color":  "#0277bd",
        "keywords": [
            # --- términos nucleares ---
            "turismo", "turistas", "turista", "turístico", "turística",
            "sector turístico", "industria turística",
            # --- alojamiento ---
            "hotel", "hotelero", "ocupación hotelera", "pernoctación",
            "planta alojativa", "resort", "apartamento turístico",
            # --- volumen y datos ---
            "llegada de turistas", "visitantes", "cruceristas",
            "gasto turístico", "estancia media",
            # --- modelo turístico ---
            "masificación turística", "turismo de masas", "turismofobia",
            "moratoria turística", "ecotasa", "tasa turística",
            "turismo sostenible", "turismo rural",
            # --- instituciones y promoción ---
            "promotur", "patronato de turismo", "turespaña",
            "tour operador", "destino turístico",
        ],
        "peso_titulo": 3,
    },
    "dependencia_discapacidad": {
        "label":  "Dependencia y Discapacidad",
        "color":  "#0ea5e9",
        "keywords": [
            # --- dependencia ---
            "ley de dependencia", "grado de dependencia",
            "persona dependiente", "persona mayor dependiente",
            "reconocimiento de dependencia", "prestación por dependencia",
            "saad", "sistema de dependencia",
            # --- discapacidad ---
            "discapacidad", "persona con discapacidad",
            "diversidad funcional", "certificado de discapacidad",
            "grado de discapacidad", "discapacidad intelectual",
            # --- cuidados ---
            "cuidador familiar", "cuidadora", "ayuda a domicilio",
            "asistencia personal", "teleasistencia",
            # --- centros y recursos ---
            "residencia de mayores", "centro de día",
            "centro ocupacional", "imserso",
            # --- accesibilidad ---
            "accesibilidad", "barrera arquitectónica",
            "silla de ruedas", "lengua de signos",
        ],
        "peso_titulo": 3,
    },
    "justicia": {
        "label":  "Justicia",
        "color":  "#37474f",
        "keywords": [
            # --- sistema judicial ---
            "tribunal superior de justicia", "tsjc", "audiencia provincial",
            "juzgado", "juez", "jueza", "magistrado", "magistrada",
            "fiscalía", "fiscal", "ministerio fiscal",
            # --- proceso judicial ---
            "sentencia", "sentencia firme", "juicio oral", "vista oral",
            "instrucción judicial", "auto judicial", "recurso de apelación",
            "recurso de casación", "causa penal", "procedimiento judicial",
            # --- delitos y condenas ---
            "condena", "absolución", "imputado", "investigado",
            "acusado", "pena de prisión", "delito", "estafa",
            "corrupción judicial", "prevaricación", "blanqueo de capitales",
            "trama corrupta", "caso judicial",
            # --- justicia y acceso ---
            "asistencia jurídica gratuita", "turno de oficio",
            "colapso judicial", "atasco judicial",
            "justicia restaurativa", "mediación judicial",
        ],
        "peso_titulo": 3,
    },
    "diversidad": {
        "label":  "Diversidad",
        "color":  "#7b1fa2",
        "keywords": [
            # --- diversidad sexual y de género ---
            "lgtbi", "lgtbiq", "lgbtq", "orgullo lgtbi",
            "homosexual", "homosexualidad", "lesbiana", "bisexual",
            "transexual", "transgénero", "persona trans",
            "identidad de género", "orientación sexual",
            "matrimonio igualitario", "ley trans",
            "homofobia", "transfobia", "lgtbifobia", "delito de odio",
            # --- diversidad étnica y cultural ---
            "diversidad cultural", "multiculturalidad", "interculturalidad",
            "racismo", "xenofobia", "discriminación racial",
            "pueblo gitano", "comunidad gitana", "etnia",
            "antirracismo", "discurso de odio",
            # --- inclusión ---
            "inclusión social", "inclusión educativa",
            "no discriminación", "ley de igualdad de trato",
        ],
        "peso_titulo": 3,
    },
    "cuidados": {
        "label":  "Cuidados",
        "color":  "#ef6c00",
        "keywords": [
            # --- crianza y conciliación ---
            "crianza", "maternidad", "paternidad",
            "permiso de maternidad", "permiso de paternidad",
            "permiso parental", "baja maternal", "baja paternal",
            "conciliación laboral", "conciliación familiar",
            "corresponsabilidad", "corresponsabilidad familiar",
            # --- cuidados de larga duración ---
            "cuidados de larga duración", "cuidado de mayores",
            "cuidado de dependientes", "cuidador no profesional",
            "cuidadora informal", "sobrecarga del cuidador",
            "respiro familiar", "servicio de respiro",
            # --- infancia ---
            "escuela infantil", "guardería", "educación infantil",
            "plaza de guardería", "cheque guardería",
            # --- economía de los cuidados ---
            "economía de los cuidados", "trabajo no remunerado",
            "trabajo doméstico", "empleada de hogar",
            "sistema de cuidados", "derecho al cuidado",
            "crisis de los cuidados", "profesionalización de los cuidados",
        ],
        "peso_titulo": 3,
    },
    "igualdad": {
        "label":  "Igualdad",
        "color":  "#ad1457",
        "keywords": [
            # --- igualdad de género ---
            "igualdad de género", "igualdad entre hombres y mujeres",
            "brecha de género", "brecha salarial", "techo de cristal",
            "paridad", "cuota de género", "plan de igualdad",
            "perspectiva de género", "transversalidad de género",
            "feminismo", "empoderamiento femenino",
            "instituto de la mujer", "instituto canario de igualdad",
            "ley de igualdad", "ley orgánica de igualdad",
            # --- igualdad material y social ---
            "desigualdad social", "desigualdad económica",
            "pobreza", "tasa de pobreza", "exclusión social",
            "riesgo de pobreza", "pobreza infantil", "pobreza energética",
            "renta mínima", "ingreso mínimo vital", "prestación canaria de inserción",
            "índice de gini", "redistribución",
            # --- derechos e instituciones ---
            "derechos sociales", "justicia social",
            "servicios sociales", "política social",
        ],
        "peso_titulo": 3,
    },
}

# ── Configuración del scraper ─────────────────────────────────────────────────
SCRAPER = {
    # Rango de espera entre peticiones (segundos) — se elige aleatoriamente
    "delay_min": 1.5,
    "delay_max": 5.0,
    # Probabilidad (0-1) de insertar una pausa larga ("el usuario se distrae")
    "pausa_larga_prob": 0.12,
    # Rango de duración de la pausa larga (segundos)
    "pausa_larga_rango": (8, 22),
    # Timeout por petición (segundos)
    "timeout": 15,
    # Máximo de reintentos ante error 5xx o timeout
    "max_reintentos": 3,
    # Máximo de noticias a guardar por medio y ejecución
    "max_items_por_medio": 50,
    # Días que se conserva el caché HTML
    "cache_ttl_dias": 7,
    # robots.txt desactivado: monitoreo académico con 1 ejecución/día,
    # menos tráfico que un lector humano
    "respetar_robots": False,
}

# Pool de User-Agents realistas (navegadores actuales, distintos SO)
USER_AGENTS = [
    # Chrome en Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Chrome en macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Firefox en Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    # Firefox en macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Safari en macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    # Edge en Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    # Chrome en Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# ── Supabase ──────────────────────────────────────────────────────────────────
# La contraseña se lee de la variable de entorno SUPABASE_PASSWORD.
# En GitHub Actions se inyecta como secret; en local puedes definirla
# en un fichero .env o dejarla como fallback aquí (solo para desarrollo).
SUPABASE = {
    "host":     os.getenv("SUPABASE_HOST", "aws-1-eu-west-1.pooler.supabase.com"),
    "port":     int(os.getenv("SUPABASE_PORT", "5432")),
    "dbname":   os.getenv("SUPABASE_DBNAME", "postgres"),
    "user":     os.getenv("SUPABASE_USER", "postgres.kdpsjutsgvghdtzoskkg"),
    "password": os.getenv("SUPABASE_PASSWORD", ""),
    "sslmode":  os.getenv("SUPABASE_SSLMODE", "require"),
    "schema":   os.getenv("SUPABASE_SCHEMA", "medios"),
}

# ── Stopwords en español (complementan las de spacy/nltk) ────────────────────
STOPWORDS_EXTRA = {
    "canarias", "canario", "canaria", "isla", "islas", "tenerife",
    "gran", "palmas", "lanzarote", "fuerteventura", "gomera", "hierro",
    "palma", "año", "años", "día", "días", "vez", "veces", "hoy",
    "ayer", "mañana", "según", "tras", "ante", "bajo", "sobre",
    "parte", "través", "cabo", "junto",
}
