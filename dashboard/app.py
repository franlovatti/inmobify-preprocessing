import io
import os
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from apify_client import ApifyClient

st.set_page_config(
    page_title="Inmobify Rosario — Inteligencia Comercial",
    page_icon="🏢",
    layout="wide",
)

# ------------------------------------------------------------------------------
# CARGA DE DATOS VIA APIFY SDK (R1) CON FALLBACK LOCAL
@st.cache_data(ttl=600)
def cargar_datos() -> pd.DataFrame:
    token = ""
    if "APIFY_TOKEN" in st.secrets:
        token = str(st.secrets["APIFY_TOKEN"]).strip()
    elif os.getenv("APIFY_TOKEN"):
        token = os.getenv("APIFY_TOKEN").strip()

    if not token:
        st.error(f"No se encontró la clave APIFY_TOKEN. Claves detectadas: {list(st.secrets.keys())}")
        st.stop()

    try:
        client = ApifyClient(token)
        stores = client.key_value_stores().list().items
        store_match = next((s for s in stores if getattr(s, "name", None) == "inmobify-storage"), None)

        if not store_match:
            st.error("Autenticación OK, pero no se encontró el Key-Value Store 'inmobify-storage'.")
            st.stop()

        rec = client.key_value_store(store_match.id).get_record("dataset_inmobiliario_completo_rosario.csv")
        val = rec.get("value") if isinstance(rec, dict) else getattr(rec, "value", None)

        if not val:
            st.error("No se encontró 'dataset_inmobiliario_completo_rosario.csv' dentro de 'inmobify-storage'.")
            st.stop()

        text = val.decode("utf-8") if isinstance(val, bytes) else str(val)
        return pd.read_csv(io.StringIO(text))

    except Exception as e:
        st.error(f"Fallo al conectar con Apify ({type(e).__name__}: {e}).")
        st.stop()


df = cargar_datos()

# ------------------------------------------------------------------------------
# SIDEBAR — FILTROS INTERACTIVOS
# ------------------------------------------------------------------------------
st.sidebar.title("🏢 Inmobify Rosario")
st.sidebar.caption("Valuación y entorno comercial geoespacial")

tipos = st.sidebar.multiselect(
    "Tipo de inmueble",
    options=sorted(df["tipo_inmueble"].dropna().unique()),
    default=sorted(df["tipo_inmueble"].dropna().unique()),
)
barrios_disp = sorted(df["barrio"].dropna().unique())
barrios = st.sidebar.multiselect("Barrios (vacío = todos)", options=barrios_disp, default=[])

rango_sup = st.sidebar.slider(
    "Superficie (m²)",
    min_value=int(df["superficie_m2"].min()),
    max_value=int(df["superficie_m2"].max()),
    value=(int(df["superficie_m2"].min()), int(df["superficie_m2"].max())),
)

df_f = df[
    (df["tipo_inmueble"].isin(tipos))
    & (df["superficie_m2"].between(rango_sup[0], rango_sup[1]))
].copy()
if barrios:
    df_f = df_f[df_f["barrio"].isin(barrios)]

# ------------------------------------------------------------------------------
# ENCABEZADO Y KPIs EJECUTIVOS
# ------------------------------------------------------------------------------
st.title("🏢 Inmobify — Radar Comercial e Inmobiliario de Rosario")
st.markdown(
    "Análisis de alquileres comerciales cruzado con **densidad y tráfico de reseñas (200m / 350m)** "
    "y distancia a polos comerciales (*Monumento, Pichincha, Pellegrini*)."
)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Propiedades analizadas", f"{len(df_f):,}")
k2.metric("Mediana Alquiler (USD)", f"USD {df_f['precio_usd'].median():,.0f}")
k3.metric("Mediana USD / m²", f"USD {df_f['precio_m2_usd'].median():.2f}")
oportunidades = (df_f["indice_precio_relativo_barrio"] <= 0.85).sum()
k4.metric("Oportunidades (<85% barrio)", f"{oportunidades}", f"{oportunidades/max(len(df_f),1)*100:.0f}% del filtro")

st.divider()

# ------------------------------------------------------------------------------
# PESTAÑAS PRINCIPALES
# ------------------------------------------------------------------------------
tab_mapa, tab_eda, tab_corr, tab_datos = st.tabs([
    "🗺️ Mapa Geoespacial",
    "📊 Análisis por Barrio y Segmento",
    "🔬 Correlaciones y Elasticidad",
    "📋 Explorador de Oportunidades",
])

with tab_mapa:
    st.subheader("Distribución Geográfica y Posición respecto a la Mediana Barrial")
    fig_map = px.scatter_mapbox(
        df_f,
        lat="lat",
        lon="lon",
        color="posicion_mercado_barrio",
        size="superficie_m2",
        size_max=22,
        zoom=12,
        center={"lat": -32.947, "lon": -60.650},
        mapbox_style="carto-positron",
        color_discrete_map={
            "1. Oportunidad (<85% mediana)": "#2a9d8f",
            "2. En rango de barrio (85-115%)": "#457b9d",
            "3. Premium / Sobre mediana (>115%)": "#e63946",
        },
        hover_name="barrio",
        hover_data={
            "tipo_inmueble": True,
            "superficie_m2": ":.0f",
            "precio_usd": ":,.0f",
            "precio_m2_usd": ":.2f",
            "densidad_comercial_200m": True,
            "diversidad_rubros_200m": True,
            "trafico_resenas_200m": ":,.0f",
            "lat": False,
            "lon": False,
        },
        height=560,
    )
    fig_map.update_layout(margin={"r": 0, "t": 10, "l": 0, "b": 0})
    st.plotly_chart(fig_map, use_container_width=True)

with tab_eda:
    c1, c2 = st.columns(2)
    with c1:
        top_b = df_f["barrio"].value_counts().head(10).index
        fig_box = px.box(
            df_f[df_f["barrio"].isin(top_b)],
            x="precio_m2_usd",
            y="barrio",
            color="tipo_inmueble",
            category_orders={"barrio": list(top_b)},
            title="Dispersión de USD/m² en los 10 Barrios Principales",
            labels={"precio_m2_usd": "USD / m²", "barrio": ""},
        )
        st.plotly_chart(fig_box, use_container_width=True)

    with c2:
        fig_hist = px.histogram(
            df_f,
            x="precio_usd",
            color="tipo_inmueble",
            nbins=30,
            barmode="overlay",
            opacity=0.75,
            title="Distribución de Alquiler Mensual (USD)",
            labels={"precio_usd": "Alquiler Mensual (USD)"},
        )
        st.plotly_chart(fig_hist, use_container_width=True)

with tab_corr:
    c1, c2 = st.columns([1.2, 1])
    with c1:
        cols_num = [
            "precio_usd", "precio_m2_usd", "log_superficie_m2",
            "tiene_expensas", "densidad_comercial_200m", "diversidad_rubros_200m",
            "log_trafico_resenas_200m", "ratio_densidad_200_350", "dist_polo_mas_cercano_m",
        ]
        corr = df_f[cols_num].corr().round(2)
        fig_heat = px.imshow(
            corr,
            text_auto=True,
            color_continuous_scale="RdBu_r",
            zmin=-1,
            zmax=1,
            title="Matriz de Correlación Interactiva (Pearson)",
        )
        st.plotly_chart(fig_heat, use_container_width=True)

    with c2:
        df_plot = df_f.copy()
        df_plot["log_precio_usd"] = np.log1p(df_plot["precio_usd"])
        fig_reg = px.scatter(
            df_plot,
            x="log_superficie_m2",
            y="log_precio_usd",
            color="tipo_inmueble",
            trendline="ols",
            title="Elasticidad Log-Log: Superficie vs Alquiler (r = 0.77)",
            labels={"log_superficie_m2": "log(Superficie m² + 1)", "log_precio_usd": "log(Precio USD + 1)"},
        )
        st.plotly_chart(fig_reg, use_container_width=True)

with tab_datos:
    st.subheader("Listado Priorizado por Índice Relativo al Barrio")
    cols_tabla = [
        "posting_id", "barrio", "tipo_inmueble", "superficie_m2",
        "precio_usd", "precio_m2_usd", "precio_m2_mediana_barrio",
        "indice_precio_relativo_barrio", "posicion_mercado_barrio",
        "densidad_comercial_200m", "diversidad_rubros_200m", "dist_polo_mas_cercano_m",
    ]
    st.dataframe(
        df_f[cols_tabla].sort_values("indice_precio_relativo_barrio"),
        use_container_width=True,
        hide_index=True,
    )