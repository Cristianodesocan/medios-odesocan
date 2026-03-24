"""
dashboard.py — Dashboard interactivo conectado a Supabase.

Uso:
    python dashboard.py

Variables opcionales:
    DASH_HOST=127.0.0.1
    DASH_PORT=8050
    DASH_DEBUG=0
"""

from __future__ import annotations

import base64
import io
import json
import os
from datetime import timedelta
from pathlib import Path
from typing import Any

import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from collections import Counter
import psycopg2
import spacy
from dash import Dash, Input, Output, State, callback, dash_table, dcc, html
from dotenv import load_dotenv

MPLCONFIGDIR = Path(__file__).resolve().parent / ".cache" / "matplotlib"
MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPLCONFIGDIR))

from wordcloud import WordCloud

def _cargar_modelo_spacy():
    for modelo in ("es_core_news_md", "es_core_news_sm"):
        try:
            return spacy.load(modelo, disable=["parser", "ner"])
        except OSError:
            continue
    return None


_NLP = _cargar_modelo_spacy()

from config import BASE_DIR, MEDIOS, STOPWORDS_EXTRA, SUPABASE, TEMAS

load_dotenv(BASE_DIR / ".env")

FONT_SANS  = '"Inter", "Avenir Next", "Segoe UI", sans-serif'
FONT_SERIF = '"Iowan Old Style", "Palatino Linotype", Georgia, serif'
BG_PAGE    = "#f7f6f2"
BG_PANEL   = "#ffffff"
BG_CHART   = "#fafaf8"
INK        = "#111827"
MUTED      = "#6b7280"
ACCENT     = "#059669"
ACCENT_SOFT = "#d1fae5"
WARN       = "#b45309"
GRID       = "#f3f4f6"
BORDER     = "#e5e7eb"

MEDIOS_COLORES = {medio: cfg["color"] for medio, cfg in MEDIOS.items()}
TEMAS_COLORES = {tema: cfg["color"] for tema, cfg in TEMAS.items()}


def _supabase_cfg() -> dict[str, Any]:
    return {
        "host": os.getenv("SUPABASE_HOST", SUPABASE["host"]),
        "port": int(os.getenv("SUPABASE_PORT", SUPABASE["port"])),
        "dbname": os.getenv("SUPABASE_DBNAME", SUPABASE["dbname"]),
        "user": os.getenv("SUPABASE_USER", SUPABASE["user"]),
        "password": os.getenv("SUPABASE_PASSWORD", SUPABASE["password"]),
        "sslmode": os.getenv("SUPABASE_SSLMODE", SUPABASE["sslmode"]),
        "schema": os.getenv("SUPABASE_SCHEMA", SUPABASE["schema"]),
    }


def _conexion_supabase() -> psycopg2.extensions.connection:
    cfg = _supabase_cfg()
    return psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        dbname=cfg["dbname"],
        user=cfg["user"],
        password=cfg["password"],
        sslmode=cfg["sslmode"],
    )


def _normalizar_temas(valor: Any) -> list[str]:
    if valor is None:
        return []
    if isinstance(valor, list):
        return [str(v).strip() for v in valor if str(v).strip()]
    if isinstance(valor, tuple):
        return [str(v).strip() for v in valor if str(v).strip()]
    if isinstance(valor, str):
        texto = valor.strip()
        if not texto or texto.lower() in {"null", "none", "na"}:
            return []
        if texto.startswith("{") and texto.endswith("}"):
            return [parte.strip().strip('"') for parte in texto[1:-1].split(",") if parte.strip()]
        try:
            data = json.loads(texto)
        except json.JSONDecodeError:
            return [texto]
        return _normalizar_temas(data)
    return []


def _nombre_medio(medio: str) -> str:
    return MEDIOS.get(medio, {}).get("nombre", medio.replace("_", " ").title())


def _nombre_tema(tema: str) -> str:
    return TEMAS.get(tema, {}).get("label", tema.replace("_", " ").title())


def _color_medio(medio: str) -> str:
    return MEDIOS_COLORES.get(medio, ACCENT)


def _color_tema(tema: str) -> str:
    return TEMAS_COLORES.get(tema, WARN)


def cargar_noticias() -> pd.DataFrame:
    cfg = _supabase_cfg()
    query = f"""
        SELECT
            url,
            url_hash,
            medio,
            titulo,
            resumen,
            texto_full,
            fecha_pub,
            fecha_scrap,
            fuente,
            temas
        FROM {cfg["schema"]}.noticias
        ORDER BY fecha_scrap DESC NULLS LAST, fecha_pub DESC NULLS LAST
    """

    with _conexion_supabase() as conn:
        df = pd.read_sql_query(query, conn)

    if df.empty:
        return df

    df["fecha_pub"] = pd.to_datetime(df["fecha_pub"], errors="coerce", utc=True)
    df["fecha_scrap"] = pd.to_datetime(df["fecha_scrap"], errors="coerce", utc=True)
    df["fecha_base"] = df["fecha_pub"].fillna(df["fecha_scrap"])
    df["fecha_dia"] = df["fecha_base"].dt.tz_convert(None).dt.date
    df["temas_lista"] = df["temas"].apply(_normalizar_temas)
    df["tema_principal"] = df["temas_lista"].apply(lambda temas: temas[0] if temas else "sin_tema")
    df["medio_label"] = df["medio"].apply(_nombre_medio)
    df["tema_label"] = df["tema_principal"].apply(_nombre_tema)
    return df


def _filtro_df(
    df: pd.DataFrame,
    medios: list[str] | None,
    temas: list[str] | None,
    start_date: str | None,
    end_date: str | None,
    busqueda: str | None,
) -> pd.DataFrame:
    filtrado = df.copy()

    if medios:
        filtrado = filtrado[filtrado["medio"].isin(medios)]

    if temas:
        filtrado = filtrado[
            filtrado["temas_lista"].apply(lambda items: any(tema in items for tema in temas))
        ]

    if start_date:
        filtrado = filtrado[filtrado["fecha_dia"] >= pd.to_datetime(start_date).date()]
    if end_date:
        filtrado = filtrado[filtrado["fecha_dia"] <= pd.to_datetime(end_date).date()]

    if busqueda:
        patron = busqueda.strip().lower()
        if patron:
            columnas = (
                filtrado["titulo"].fillna("")
                + " "
                + filtrado["resumen"].fillna("")
                + " "
                + filtrado["texto_full"].fillna("")
            ).str.lower()
            filtrado = filtrado[columnas.str.contains(patron, regex=False)]

    return filtrado.sort_values("fecha_base", ascending=False)


def _fig_vacia(titulo: str):
    fig = px.scatter(title=titulo)
    fig.update_traces(marker={"opacity": 0})
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor=BG_PANEL,
        plot_bgcolor=BG_CHART,
        font={"family": FONT_SANS, "color": INK},
        xaxis={"visible": False},
        yaxis={"visible": False},
        annotations=[
            {
                "text": "Sin datos con los filtros actuales",
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"size": 16, "color": MUTED},
            }
        ],
        margin={"l": 20, "r": 20, "t": 60, "b": 20},
    )
    return fig


def _maquetar_fig(fig, titulo: str):
    fig.update_layout(
        title={
            "text": titulo,
            "x": 0.0,
            "xanchor": "left",
            "pad": {"l": 20, "t": 8},
            "font": {"size": 15, "family": FONT_SANS, "color": INK},
        },
        template="plotly_white",
        paper_bgcolor=BG_PANEL,
        plot_bgcolor=BG_CHART,
        font={"family": FONT_SANS, "size": 12, "color": INK},
        margin={"l": 20, "r": 20, "t": 54, "b": 20},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "x": 0,
            "font": {"size": 11},
            "bgcolor": "rgba(0,0,0,0)",
            "itemsizing": "constant",
        },
        hoverlabel={
            "bgcolor": "#ffffff",
            "bordercolor": BORDER,
            "font": {"family": FONT_SANS, "size": 12, "color": INK},
            "namelength": -1,
        },
    )
    fig.update_xaxes(
        showgrid=True, gridcolor=GRID, gridwidth=1,
        zeroline=False, tickfont={"size": 10.5}, linecolor=BORDER,
    )
    fig.update_yaxes(
        showgrid=True, gridcolor=GRID, gridwidth=1,
        zeroline=False, tickfont={"size": 10.5}, linecolor=BORDER,
    )
    return fig


def grafico_timeline(df: pd.DataFrame):
    if df.empty:
        return _fig_vacia("Volumen diario")

    serie = (
        df.groupby(["fecha_dia", "medio_label"], as_index=False)
        .size()
        .rename(columns={"size": "noticias"})
    )
    fig = px.line(
        serie,
        x="fecha_dia",
        y="noticias",
        color="medio_label",
        markers=True,
        color_discrete_map={_nombre_medio(k): v for k, v in MEDIOS_COLORES.items()},
    )
    fig.update_traces(line={"width": 2}, marker={"size": 5})
    return _maquetar_fig(fig, "Publicaciones por día")


def grafico_medios(df: pd.DataFrame):
    if df.empty:
        return _fig_vacia("Medios")

    medios = (
        df.groupby(["medio", "medio_label"], as_index=False)
        .size()
        .rename(columns={"size": "noticias"})
        .sort_values("noticias", ascending=True)
    )
    fig = px.bar(
        medios,
        x="noticias",
        y="medio_label",
        orientation="h",
        color="medio",
        color_discrete_map=MEDIOS_COLORES,
        text="noticias",
    )
    fig.update_traces(textposition="outside", textfont={"size": 11}, marker={"line": {"width": 0}})
    fig.update_layout(showlegend=False)
    return _maquetar_fig(fig, "Noticias por cabecera")


def grafico_temas(df: pd.DataFrame):
    if df.empty:
        return _fig_vacia("Temas")

    temas = (
        df.explode("temas_lista")
        .dropna(subset=["temas_lista"])
        .rename(columns={"temas_lista": "tema"})
    )
    if temas.empty:
        return _fig_vacia("Temas")

    temas["tema_label"] = temas["tema"].apply(_nombre_tema)
    resumen = (
        temas.groupby(["tema", "tema_label"], as_index=False)
        .size()
        .rename(columns={"size": "noticias"})
        .sort_values("noticias", ascending=False)
        .head(10)
        .sort_values("noticias", ascending=True)
    )
    fig = px.bar(
        resumen,
        x="noticias",
        y="tema_label",
        orientation="h",
        color="tema",
        color_discrete_map=TEMAS_COLORES,
        text="noticias",
    )
    fig.update_traces(textposition="outside", textfont={"size": 11}, marker={"line": {"width": 0}})
    fig.update_layout(showlegend=False)
    return _maquetar_fig(fig, "Distribución temática")


def grafico_heatmap(df: pd.DataFrame):
    if df.empty:
        return _fig_vacia("Cruce")

    temas = (
        df.explode("temas_lista")
        .dropna(subset=["temas_lista"])
        .rename(columns={"temas_lista": "tema"})
    )
    if temas.empty:
        return _fig_vacia("Cruce")

    tabla = pd.crosstab(
        temas["tema"].apply(_nombre_tema),
        temas["medio"].apply(_nombre_medio),
    )
    if tabla.empty:
        return _fig_vacia("Cruce")

    fig = px.imshow(
        tabla,
        text_auto=True,
        aspect="auto",
        color_continuous_scale=["#f0fdf9", "#6ee7b7", "#059669"],
    )
    fig.update_traces(textfont={"size": 11, "family": FONT_SANS})
    fig.update_layout(coloraxis_showscale=False)
    return _maquetar_fig(fig, "Intensidad temática por cabecera")


def _extraer_verbos_sustantivos(texto: str) -> str:
    """Devuelve solo los lemas de verbos y sustantivos del texto.
    Si el modelo spaCy no está disponible, devuelve cadena vacía."""
    if _NLP is None:
        return ""
    doc = _NLP(texto[:60_000])
    tokens = [
        token.lemma_.lower()
        for token in doc
        if token.pos_ in {"NOUN", "VERB"}
        and token.morph.get("PronType") == []
        and not token.is_stop
        and not token.is_punct
        and len(token.lemma_) > 2
        and token.lemma_.lower() not in STOPWORDS_EXTRA
    ]
    return " ".join(tokens)


def generar_nube(df: pd.DataFrame):
    if df.empty:
        return None

    muestra = df.head(200)
    texto_crudo = " ".join(
        (
            muestra["titulo"].fillna("")
            + " "
            + muestra["texto_full"].fillna("")
        ).tolist()
    )
    if not texto_crudo.strip():
        return None

    texto = _extraer_verbos_sustantivos(texto_crudo)
    if not texto.strip():
        return None

    tokens = texto.split()
    total = len(tokens)
    conteo = Counter(tokens)

    W, H = 1100, 420

    # Paleta de colores propia: verde esmeralda → azul → índigo → ámbar
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list(
        "dash", ["#065f46", "#059669", "#0891b2", "#6366f1", "#b45309"]
    )

    wc = WordCloud(
        width=W,
        height=H,
        background_color=BG_PANEL,
        colormap=cmap,
        stopwords=set(STOPWORDS_EXTRA),
        collocations=False,
        max_words=100,
        prefer_horizontal=0.82,
        margin=4,
    ).generate(texto)

    # Renderizar PNG y codificar en base64
    buf = io.BytesIO()
    wc.to_image().save(buf, format="PNG")
    img_b64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    # Posiciones y metadatos de cada palabra para el hover
    hover_items = []
    for (word, _), font_size, (row, col), *_ in wc.layout_:
        n = conteo.get(word, 0)
        pct = n / total * 100
        hover_items.append({
            "word": word,
            "x": col / W,
            "y": 1 - row / H,
            "size": font_size,
            "hover": (
                f"<b>{word}</b><br>"
                f"Apariciones: {n}<br>"
                f"Frecuencia: {pct:.2f} %"
            ),
        })

    fig = go.Figure()

    # Imagen WordCloud como fondo (sin solapes, renderizado correcto)
    fig.add_layout_image(
        source=img_b64,
        xref="x", yref="y",
        x=0, y=1,
        sizex=1, sizey=1,
        sizing="stretch",
        layer="below",
        opacity=1,
    )

    # Marcadores invisibles sobre cada palabra para disparar el hover
    fig.add_trace(go.Scatter(
        x=[w["x"] for w in hover_items],
        y=[w["y"] for w in hover_items],
        mode="markers",
        marker={
            "size":    [max(20, w["size"] * 0.55) for w in hover_items],
            "opacity": 0,
            "color":   "rgba(0,0,0,0)",
        },
        hovertext=[w["hover"] for w in hover_items],
        hoverinfo="text",
        showlegend=False,
    ))

    fig.update_layout(
        xaxis={"visible": False, "range": [0, 1], "fixedrange": True},
        yaxis={"visible": False, "range": [0, 1], "fixedrange": True},
        paper_bgcolor=BG_PANEL,
        plot_bgcolor=BG_PANEL,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        hovermode="closest",
        hoverlabel={
            "bgcolor": "#ffffff",
            "bordercolor": BORDER,
            "font": {"family": FONT_SANS, "size": 13, "color": INK},
            "namelength": 0,
        },
        showlegend=False,
    )
    return fig


def tabla_noticias(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []

    vista = df.copy().head(50)
    vista["fecha"] = vista["fecha_base"].dt.tz_convert(None).dt.strftime("%Y-%m-%d %H:%M")
    vista["temas_view"] = vista["temas_lista"].apply(
        lambda temas: ", ".join(_nombre_tema(t) for t in temas) if temas else "Sin tema"
    )
    vista["link"] = vista.apply(
        lambda row: f"[Abrir noticia]({row['url']})",
        axis=1,
    )
    return vista[
        ["fecha", "medio_label", "titulo", "temas_view", "fuente", "link"]
    ].rename(
        columns={
            "medio_label": "medio",
            "temas_view": "temas",
        }
    ).to_dict("records")


def tarjeta_kpi(titulo: str, valor: str, detalle: str, color: str) -> dbc.Card:
    return dbc.Card(
        [
            html.Div(style={"height": "3px", "background": color, "borderRadius": "14px 14px 0 0"}),
            dbc.CardBody(
                [
                    html.Div(
                        titulo,
                        style={
                            "fontSize": "0.74rem",
                            "color": MUTED,
                            "textTransform": "uppercase",
                            "letterSpacing": "0.1em",
                            "fontWeight": 700,
                            "marginBottom": "0.6rem",
                        },
                    ),
                    html.Div(
                        valor,
                        style={
                            "fontFamily": FONT_SERIF,
                            "fontSize": "2.8rem",
                            "color": INK,
                            "lineHeight": 1,
                            "fontWeight": 400,
                            "marginBottom": "0.45rem",
                        },
                    ),
                    html.Div(
                        detalle,
                        style={
                            "fontSize": "0.78rem",
                            "color": color,
                            "fontWeight": 500,
                        },
                    ),
                ],
                style={"padding": "1rem 1.2rem 1.1rem"},
            ),
        ],
        className="kpi-card",
    )


_LABEL_STYLE = {
    "fontSize": "0.7rem",
    "fontWeight": 700,
    "textTransform": "uppercase",
    "letterSpacing": "0.08em",
    "color": MUTED,
    "marginBottom": "0.3rem",
    "display": "block",
}

def _card_body(children, padding="1.25rem"):
    return dbc.Card(
        dbc.CardBody(children, style={"padding": padding}),
        className="panel-card",
    )

def _section(label: str, *children):
    return html.Div(
        [html.Div(label, className="section-label"), *children],
    )

app = Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
    ],
    title="Panel de medios",
)
server = app.server

# ── Helpers de tabla ──────────────────────────────────────────────────────────
_TABLE_STYLE = dash_table.DataTable(
    id="news-table",
    columns=[
        {"name": "Fecha",   "id": "fecha"},
        {"name": "Medio",   "id": "medio"},
        {"name": "Titular", "id": "titulo"},
        {"name": "Temas",   "id": "temas"},
        {"name": "Fuente",  "id": "fuente"},
        {"name": "Enlace",  "id": "link", "presentation": "markdown"},
    ],
    page_size=10,
    sort_action="native",
    style_as_list_view=True,
    style_table={"overflowX": "auto", "overflowY": "auto", "maxHeight": "420px"},
    markdown_options={"link_target": "_blank"},
    style_header={
        "backgroundColor": "#f9fafb",
        "border": "none",
        "borderBottom": f"2px solid {BORDER}",
        "fontWeight": 700,
        "fontFamily": FONT_SANS,
        "fontSize": "0.68rem",
        "textTransform": "uppercase",
        "letterSpacing": "0.08em",
        "color": MUTED,
        "padding": "0.55rem 0.85rem",
        "position": "sticky",
        "top": 0,
    },
    style_cell={
        "backgroundColor": BG_PANEL,
        "color": INK,
        "border": "none",
        "borderBottom": f"1px solid {GRID}",
        "padding": "0.55rem 0.85rem",
        "textAlign": "left",
        "fontFamily": FONT_SANS,
        "fontSize": "0.82rem",
        "whiteSpace": "normal",
        "height": "auto",
        "lineHeight": "1.5",
    },
    style_cell_conditional=[
        {"if": {"column_id": "fecha"},   "width": "115px", "minWidth": "115px"},
        {"if": {"column_id": "medio"},   "width": "100px", "minWidth": "100px"},
        {"if": {"column_id": "fuente"},  "width": "60px",  "minWidth": "60px"},
        {"if": {"column_id": "link"},    "width": "80px",  "minWidth": "80px"},
    ],
    style_data_conditional=[
        {"if": {"state": "active"}, "backgroundColor": ACCENT_SOFT, "border": "none"},
        {"if": {"row_index": "odd"}, "backgroundColor": "#fafaf8"},
    ],
)

_GRAPH_CFG = {"displayModeBar": False, "responsive": True}

app.layout = html.Div(
    [
        dcc.Store(id="news-store"),
        dcc.Interval(id="startup-refresh", interval=250, n_intervals=0, max_intervals=1),

        # ── Topbar ────────────────────────────────────────────────────────────
        html.Div(
            [
                html.Div(
                    [
                        html.Div(className="topbar-dot"),
                        html.Span("Observatorio de Medios", className="topbar-name"),
                        html.Div(className="topbar-sep"),
                        html.Span("Seguimiento de prensa", className="topbar-title"),
                    ],
                    className="topbar-brand",
                ),
                dbc.Button(
                    "↻  Actualizar",
                    id="refresh-button",
                    n_clicks=0,
                    className="btn-refresh",
                ),
            ],
            className="topbar",
        ),

        # ── Contenido principal ───────────────────────────────────────────────
        dbc.Container(
            [
                # ── Status ────────────────────────────────────────────────────
                html.Div(
                    id="refresh-status",
                    className="status-banner",
                    style={"marginTop": "1.25rem"},
                ),

                # ── Filtros ───────────────────────────────────────────────────
                html.Div(
                    dbc.Card(
                        dbc.CardBody(
                            dbc.Row(
                                [
                                    dbc.Col(
                                        [
                                            html.Label("Medio", style=_LABEL_STYLE),
                                            dcc.Dropdown(id="medio-filter", multi=True, placeholder="Todos"),
                                        ],
                                        md=3,
                                    ),
                                    dbc.Col(
                                        [
                                            html.Label("Tema", style=_LABEL_STYLE),
                                            dcc.Dropdown(id="tema-filter", multi=True, placeholder="Todos"),
                                        ],
                                        md=3,
                                    ),
                                    dbc.Col(
                                        [
                                            html.Label("Fechas", style=_LABEL_STYLE),
                                            dcc.DatePickerRange(
                                                id="date-filter",
                                                display_format="DD/MM/YY",
                                                minimum_nights=0,
                                                clearable=True,
                                                style={"width": "100%"},
                                            ),
                                        ],
                                        md=4,
                                    ),
                                    dbc.Col(
                                        [
                                            html.Label("Buscar", style=_LABEL_STYLE),
                                            dbc.Input(
                                                id="text-filter",
                                                placeholder="Titular, resumen…",
                                                debounce=True,
                                            ),
                                        ],
                                        md=2,
                                    ),
                                ],
                                className="g-3 align-items-end",
                            ),
                            style={"padding": "1rem 1.25rem"},
                        ),
                        className="filter-card",
                    ),
                    style={"marginBottom": "1.25rem"},
                ),

                # ── KPIs ──────────────────────────────────────────────────────
                html.Div(id="kpi-row", style={"marginBottom": "1.25rem"}),

                # ── Gráficos fila 1 ───────────────────────────────────────────
                _section(
                    "Actividad editorial",
                    dbc.Row(
                        [
                            dbc.Col(
                                dbc.Card(
                                    dbc.CardBody(
                                        dcc.Loading(
                                            dcc.Graph(id="timeline-chart", config=_GRAPH_CFG, style={"height": "340px"}),
                                            type="circle", color=ACCENT,
                                        ),
                                        style={"padding": "0.5rem 0.5rem 0.25rem"},
                                    ),
                                    className="panel-card",
                                ),
                                lg=8,
                            ),
                            dbc.Col(
                                dbc.Card(
                                    dbc.CardBody(
                                        dcc.Loading(
                                            dcc.Graph(id="medio-chart", config=_GRAPH_CFG, style={"height": "340px"}),
                                            type="circle", color=ACCENT,
                                        ),
                                        style={"padding": "0.5rem 0.5rem 0.25rem"},
                                    ),
                                    className="panel-card",
                                ),
                                lg=4,
                            ),
                        ],
                        className="g-3",
                    ),
                ),

                # ── Gráficos fila 2 ───────────────────────────────────────────
                _section(
                    "Análisis temático",
                    dbc.Row(
                        [
                            dbc.Col(
                                dbc.Card(
                                    dbc.CardBody(
                                        dcc.Loading(
                                            dcc.Graph(id="tema-chart", config=_GRAPH_CFG, style={"height": "380px"}),
                                            type="circle", color=ACCENT,
                                        ),
                                        style={"padding": "0.5rem 0.5rem 0.25rem"},
                                    ),
                                    className="panel-card",
                                ),
                                lg=5,
                            ),
                            dbc.Col(
                                dbc.Card(
                                    dbc.CardBody(
                                        dcc.Loading(
                                            dcc.Graph(id="heatmap-chart", config=_GRAPH_CFG, style={"height": "380px"}),
                                            type="circle", color=ACCENT,
                                        ),
                                        style={"padding": "0.5rem 0.5rem 0.25rem"},
                                    ),
                                    className="panel-card",
                                ),
                                lg=7,
                            ),
                        ],
                        className="g-3",
                    ),
                ),

                # ── Nube + Tabla ──────────────────────────────────────────────
                _section(
                    "Léxico y archivo",
                    dbc.Row(
                        [
                            dbc.Col(
                                dbc.Card(
                                    dbc.CardBody(
                                        [
                                            html.Div(
                                                [
                                                    html.Span("Nube de palabras", className="card-title-main"),
                                                    html.Span("titulares y texto completo · verbos y sustantivos", className="card-title-badge"),
                                                ],
                                                className="card-title-row",
                                            ),
                                            dcc.Loading(
                                                [
                                                    dcc.Graph(
                                                        id="wordcloud-image",
                                                        config={"displayModeBar": False},
                                                        style={"height": "340px"},
                                                    ),
                                                    html.Div(id="wordcloud-empty", style={"color": MUTED, "fontSize": "0.82rem", "marginTop": "0.5rem"}),
                                                ],
                                                type="circle", color=ACCENT,
                                            ),
                                        ],
                                        style={"padding": "1.1rem 1.25rem"},
                                    ),
                                    className="panel-card",
                                ),
                                lg=5,
                            ),
                            dbc.Col(
                                dbc.Card(
                                    dbc.CardBody(
                                        [
                                            html.Div(
                                                [
                                                    html.Span("Noticias recientes", className="card-title-main"),
                                                    html.Span("últimas 50", className="card-title-badge"),
                                                ],
                                                className="card-title-row",
                                            ),
                                            dcc.Loading(
                                                _TABLE_STYLE,
                                                type="circle", color=ACCENT,
                                            ),
                                        ],
                                        style={"padding": "1.1rem 1.25rem"},
                                    ),
                                    className="panel-card",
                                ),
                                lg=7,
                            ),
                        ],
                        className="g-3",
                    ),
                ),

                # ── Footer ────────────────────────────────────────────────────
                html.Div(
                    f"Observatorio de medios · {pd.Timestamp.now().year}",
                    style={
                        "textAlign": "center",
                        "fontSize": "0.72rem",
                        "color": "#d1d5db",
                        "padding": "2.5rem 0 1rem",
                        "letterSpacing": "0.06em",
                    },
                ),
            ],
            fluid=True,
            style={"padding": "0 1.5rem"},
        ),
    ],
    style={
        "minHeight": "100vh",
        "background": BG_PAGE,
        "fontFamily": FONT_SANS,
        "color": INK,
    },
)


@callback(
    Output("news-store", "data"),
    Output("refresh-status", "children"),
    Input("startup-refresh", "n_intervals"),
    Input("refresh-button", "n_clicks"),
    prevent_initial_call=False,
)
def refrescar_datos(_startup: int, _clicks: int):
    try:
        df = cargar_noticias()
    except Exception as exc:
        return [], f"✗  No se pudo cargar Supabase: {exc}"

    total = len(df)
    ultima = df["fecha_scrap"].max() if total else None
    marca = (
        ultima.tz_convert(None).strftime("%Y-%m-%d %H:%M")
        if isinstance(ultima, pd.Timestamp) and not pd.isna(ultima)
        else "sin marca temporal"
    )
    payload = df.copy()
    for columna in ["fecha_pub", "fecha_scrap", "fecha_base"]:
        payload[columna] = payload[columna].apply(
            lambda valor: valor.isoformat() if isinstance(valor, pd.Timestamp) and not pd.isna(valor) else None
        )
    payload["fecha_dia"] = payload["fecha_dia"].apply(
        lambda valor: valor.isoformat() if pd.notna(valor) else None
    )
    msg = f"✓  {total} noticias cargadas  ·  Último scrape: {marca}"
    return payload.to_dict("records"), msg


@callback(
    Output("medio-filter", "options"),
    Output("tema-filter", "options"),
    Output("date-filter", "min_date_allowed"),
    Output("date-filter", "max_date_allowed"),
    Output("date-filter", "start_date"),
    Output("date-filter", "end_date"),
    Input("news-store", "data"),
    State("date-filter", "start_date"),
    State("date-filter", "end_date"),
)
def preparar_filtros(data: list[dict[str, Any]], start_date: str | None, end_date: str | None):
    df = pd.DataFrame(data)
    if df.empty or "fecha_dia" not in df:
        return [], [], None, None, None, None

    df["fecha_dia"] = pd.to_datetime(df["fecha_dia"]).dt.date
    df["temas_lista"] = df["temas_lista"].apply(_normalizar_temas)

    medios = sorted(df["medio"].dropna().unique())
    temas = sorted({tema for lista in df["temas_lista"] for tema in lista})
    min_date = df["fecha_dia"].min()
    max_date = df["fecha_dia"].max()

    default_start = max(min_date, max_date - timedelta(days=30))
    selected_start = pd.to_datetime(start_date).date() if start_date else default_start
    selected_end = pd.to_datetime(end_date).date() if end_date else max_date

    if selected_start < min_date or selected_start > max_date:
        selected_start = default_start
    if selected_end < min_date or selected_end > max_date:
        selected_end = max_date

    return (
        [{"label": _nombre_medio(m), "value": m} for m in medios],
        [{"label": _nombre_tema(t), "value": t} for t in temas],
        min_date,
        max_date,
        selected_start,
        selected_end,
    )


@callback(
    Output("kpi-row", "children"),
    Output("timeline-chart", "figure"),
    Output("medio-chart", "figure"),
    Output("tema-chart", "figure"),
    Output("heatmap-chart", "figure"),
    Output("news-table", "data"),
    Input("news-store", "data"),
    Input("medio-filter", "value"),
    Input("tema-filter", "value"),
    Input("date-filter", "start_date"),
    Input("date-filter", "end_date"),
    Input("text-filter", "value"),
)
def actualizar_dashboard(
    data: list[dict[str, Any]],
    medios: list[str] | None,
    temas: list[str] | None,
    start_date: str | None,
    end_date: str | None,
    busqueda: str | None,
):
    df = pd.DataFrame(data)
    if df.empty or "fecha_base" not in df:
        vacia = _fig_vacia("Sin datos")
        return (
            dbc.Row([dbc.Col(tarjeta_kpi("Noticias", "0", "Sin registros cargados", ACCENT), md=3)]),
            vacia,
            vacia,
            vacia,
            vacia,
            [],
        )

    df["fecha_pub"] = pd.to_datetime(df["fecha_pub"], errors="coerce", utc=True)
    df["fecha_scrap"] = pd.to_datetime(df["fecha_scrap"], errors="coerce", utc=True)
    df["fecha_base"] = pd.to_datetime(df["fecha_base"], errors="coerce", utc=True)
    df["fecha_dia"] = pd.to_datetime(df["fecha_dia"]).dt.date
    df["temas_lista"] = df["temas_lista"].apply(_normalizar_temas)

    filtrado = _filtro_df(df, medios, temas, start_date, end_date, busqueda)

    total = len(filtrado)
    medios_activos = filtrado["medio"].nunique()
    ultima = filtrado["fecha_scrap"].max()
    temas_exploded = filtrado.explode("temas_lista").dropna(subset=["temas_lista"])
    tema_top = (
        temas_exploded["temas_lista"].value_counts().index[0]
        if not temas_exploded.empty
        else "sin_tema"
    )
    tema_total = (
        int(temas_exploded["temas_lista"].value_counts().iloc[0])
        if not temas_exploded.empty
        else 0
    )
    fuentes = filtrado["fuente"].value_counts()

    kpis = dbc.Row(
        [
            dbc.Col(
                tarjeta_kpi(
                    "Noticias filtradas",
                    f"{total}",
                    f"{fuentes.get('rss', 0)} RSS / {fuentes.get('html', 0)} HTML",
                    ACCENT,
                ),
                md=3,
            ),
            dbc.Col(
                tarjeta_kpi(
                    "Medios activos",
                    f"{medios_activos}",
                    "Cantidad de cabeceras con resultados",
                    "#b45309",
                ),
                md=3,
            ),
            dbc.Col(
                tarjeta_kpi(
                    "Tema líder",
                    _nombre_tema(tema_top),
                    f"{tema_total} noticias asociadas",
                    _color_tema(tema_top),
                ),
                md=3,
            ),
            dbc.Col(
                tarjeta_kpi(
                    "Último scrape",
                    ultima.tz_convert(None).strftime("%Y-%m-%d") if isinstance(ultima, pd.Timestamp) and not pd.isna(ultima) else "-",
                    ultima.tz_convert(None).strftime("%H:%M") if isinstance(ultima, pd.Timestamp) and not pd.isna(ultima) else "Sin marca",
                    "#7c3aed",
                ),
                md=3,
            ),
        ],
        className="g-4",
    )

    return (
        kpis,
        grafico_timeline(filtrado),
        grafico_medios(filtrado),
        grafico_temas(filtrado),
        grafico_heatmap(filtrado),
        tabla_noticias(filtrado),
    )


@callback(
    Output("wordcloud-image", "figure"),
    Output("wordcloud-empty", "children"),
    Input("news-store", "data"),
    Input("medio-filter", "value"),
    Input("tema-filter", "value"),
    Input("date-filter", "start_date"),
    Input("date-filter", "end_date"),
    Input("text-filter", "value"),
)
def actualizar_nube(
    data: list[dict[str, Any]],
    medios: list[str] | None,
    temas: list[str] | None,
    start_date: str | None,
    end_date: str | None,
    busqueda: str | None,
):
    df = pd.DataFrame(data)
    if df.empty or "fecha_base" not in df:
        return None, "No hay datos para generar la nube."
    if _NLP is None:
        return None, "Instala es_core_news_md o es_core_news_sm para filtrar la nube por verbos y sustantivos."

    df["fecha_base"] = pd.to_datetime(df["fecha_base"], errors="coerce", utc=True)
    df["fecha_dia"] = pd.to_datetime(df["fecha_dia"]).dt.date
    df["temas_lista"] = df["temas_lista"].apply(_normalizar_temas)

    filtrado = _filtro_df(df, medios, temas, start_date, end_date, busqueda)
    nube = generar_nube(filtrado)
    if not nube:
        return None, "No hay suficiente texto para la nube de palabras."
    return nube, ""


if __name__ == "__main__":
    host = os.getenv("DASH_HOST", "127.0.0.1")
    port = int(os.getenv("DASH_PORT", "8050"))
    debug = os.getenv("DASH_DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug)
