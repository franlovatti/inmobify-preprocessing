import pandas as pd

def generar_tablas_eda(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    # Hoja 1: Resumen por Barrio y Tipo con diversidad comercial y distancia a polos
    csv1_barrios = (
        df.groupby(["barrio", "tipo_inmueble"], as_index=False)
        .agg(
            cantidad_inmuebles=("posting_id", "count"),
            alquiler_promedio_usd=("precio_usd", "mean"),
            alquiler_mediana_usd=("precio_usd", "median"),
            alquiler_promedio_ars=("precio_ars", "mean"),
            precio_m2_promedio_usd=("precio_m2_usd", "mean"),
            precio_m2_mediana_usd=("precio_m2_usd", "median"),
            superficie_promedio_m2=("superficie_m2", "mean"),
            densidad_comercial_200m_prom=("densidad_comercial_200m", "mean"),
            diversidad_rubros_200m_prom=("diversidad_rubros_200m", "mean"),
            dist_polo_mas_cercano_m_prom=("dist_polo_mas_cercano_m", "mean"),
        )
        .sort_values(by="cantidad_inmuebles", ascending=False)
        .round(2)
    )

    # Hoja 2: Mapa enriquecido y diagnóstico relativo contra su propio barrio
    csv2_mapa = df[[
        "posting_id", "barrio", "ciudad", "tipo_inmueble",
        "superficie_m2", "precio_usd", "precio_ars", "precio_m2_usd",
        "precio_m2_mediana_barrio", "indice_precio_relativo_barrio", "posicion_mercado_barrio",
        "densidad_comercial_200m", "diversidad_rubros_200m", "trafico_resenas_200m",
        "ratio_densidad_200_350", "dist_polo_mas_cercano_m",
    ]].copy()
    csv2_mapa["coordenadas_geo"] = df["lat"].astype(str) + "," + df["lon"].astype(str)
    csv2_mapa["entorno_comercial"] = pd.cut(
        csv2_mapa["densidad_comercial_200m"],
        bins=[-1, 4, 15, 30, 999],
        labels=["1. Bajo tránsito (<5)", "2. Tránsito medio (5-15)", "3. Corredor comercial (16-30)", "4. Polo Prime (>30)"],
    )

    # Hoja 3: Segmentación por Entorno Comercial y Rango de Superficie
    df_seg = df.copy()
    df_seg["rango_superficie"] = pd.cut(
        df_seg["superficie_m2"],
        bins=[0, 50, 120, 300, 2500],
        labels=["1. Chico (10-50 m²)", "2. Mediano (51-120 m²)", "3. Grande (121-300 m²)", "4. Gran Superficie (>300 m²)"],
    )
    df_seg["entorno_comercial"] = csv2_mapa["entorno_comercial"]

    csv3_segmentos = (
        df_seg.groupby(["tipo_inmueble", "entorno_comercial", "rango_superficie"], observed=True, as_index=False)
        .agg(
            cantidad=("posting_id", "count"),
            precio_promedio_usd=("precio_usd", "mean"),
            precio_m2_usd=("precio_m2_usd", "mean"),
            diversidad_rubros_prom=("diversidad_rubros_200m", "mean"),
            resenas_promedio_200m=("trafico_resenas_200m", "mean"),
        )
        .round(2)
    )

    return csv1_barrios, csv2_mapa, csv3_segmentos