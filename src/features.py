import numpy as np
import pandas as pd

POLOS_ROSARIO = {
    "monumento": (-32.9477, -60.6305),
    "pichincha": (-32.9367, -60.6534),
    "pellegrini": (-32.9566, -60.6436),
}

def haversine_m(lat1: float, lon1: float, lat2_arr: np.ndarray, lon2_arr: np.ndarray) -> np.ndarray:
    r = 6371000.0
    lat1_r, lon1_r = np.radians(lat1), np.radians(lon1)
    lat2_r, lon2_r = np.radians(lat2_arr), np.radians(lon2_arr)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    return r * 2 * np.arcsin(np.sqrt(a))

def construir_features_modelo(df_propiedades: pd.DataFrame, df_comercios: pd.DataFrame) -> pd.DataFrame:
    """Genera todas las variables independientes (espaciales, comerciales y estructurales)
    que usan tanto el EDA/entrenamiento como el Actor de inferencia."""
    df_out = df_propiedades.copy()
    gm_lat = df_comercios["lat"].values
    gm_lon = df_comercios["lon"].values
    gm_res = df_comercios["resenas"].values
    gm_rub = df_comercios["rubro"].fillna("Otros").values if "rubro" in df_comercios.columns else np.array(["Comercio"] * len(df_comercios))

    dens200, res200, div200, dens350, res350 = [], [], [], [], []
    for _, row in df_out.iterrows():
        d = haversine_m(row["lat"], row["lon"], gm_lat, gm_lon)
        m200 = d <= 200
        m350 = d <= 350
        dens200.append(int(m200.sum()))
        res200.append(float(gm_res[m200].sum()))
        div200.append(int(len(set(gm_rub[m200]))))
        dens350.append(int(m350.sum()))
        res350.append(float(gm_res[m350].sum()))

    df_out["densidad_comercial_200m"] = dens200
    df_out["trafico_resenas_200m"] = res200
    df_out["diversidad_rubros_200m"] = div200
    df_out["densidad_comercial_350m"] = dens350
    df_out["trafico_resenas_350m"] = res350
    df_out["resenas_por_comercio_350m"] = (
        df_out["trafico_resenas_350m"] / (df_out["densidad_comercial_350m"] + 1)
    ).round(1)

    # Ratios de concentración comercial y transformaciones logarítmicas
    df_out["ratio_densidad_200_350"] = (
        df_out["densidad_comercial_200m"] / (df_out["densidad_comercial_350m"] + 1)
    ).round(3)
    df_out["intensidad_resenas_200m"] = (
        df_out["trafico_resenas_200m"] / (df_out["densidad_comercial_200m"] + 1)
    ).round(1)
    df_out["log_trafico_resenas_200m"] = np.log1p(df_out["trafico_resenas_200m"]).round(3)

    # Distancias radiales a los 3 polos comerciales de Rosario
    lats = df_out["lat"].values
    lons = df_out["lon"].values
    for nombre, (p_lat, p_lon) in POLOS_ROSARIO.items():
        df_out[f"dist_{nombre}_m"] = haversine_m(p_lat, p_lon, lats, lons).round(1)

    df_out["dist_polo_mas_cercano_m"] = df_out[
        ["dist_monumento_m", "dist_pichincha_m", "dist_pellegrini_m"]
    ].min(axis=1)

    # Variables estructurales del inmueble
    expensas = pd.to_numeric(df_out.get("expensas_ars", 0), errors="coerce").fillna(0)
    df_out["log_superficie_m2"] = np.log1p(df_out["superficie_m2"]).round(3)
    df_out["es_gran_superficie"] = (df_out["superficie_m2"] > 200).astype(int)
    df_out["tiene_expensas"] = (expensas > 0).astype(int)

    return df_out

def construir_features_eda(df_enriquecido: pd.DataFrame) -> pd.DataFrame:
    """Agrega variables comparativas de mercado (usan precio_m2_usd) exclusivas para EDA y Looker Studio."""
    df_eda = df_enriquecido.copy()
    mediana_barrio = df_eda.groupby(["barrio", "tipo_inmueble"])["precio_m2_usd"].transform("median")
    df_eda["precio_m2_mediana_barrio"] = mediana_barrio.round(2)
    df_eda["indice_precio_relativo_barrio"] = (df_eda["precio_m2_usd"] / mediana_barrio).round(2)
    df_eda["posicion_mercado_barrio"] = pd.cut(
        df_eda["indice_precio_relativo_barrio"],
        bins=[0, 0.85, 1.15, 999],
        labels=["1. Oportunidad (<85% mediana)", "2. En rango de barrio (85-115%)", "3. Premium / Sobre mediana (>115%)"],
    )
    return df_eda