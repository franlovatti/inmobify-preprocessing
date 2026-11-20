import ast
import numpy as np
import pandas as pd


def _obtener_serie(df: pd.DataFrame, rutas: list[str], default=np.nan) -> pd.Series:
    """Busca la columna por cualquiera de sus rutas ('a/b/c' o 'a.b.c') o navega diccionarios anidados."""
    for ruta in rutas:
        if ruta in df.columns:
            return df[ruta]

    # Si viene como columna diccionario sin aplanar (ej. 'posting_location')
    partes = rutas[0].split("/")
    if partes[0] in df.columns:
        def extraer(val):
            if isinstance(val, str):
                try:
                    val = ast.literal_eval(val)
                except Exception:
                    return default
            cur = val
            for p in partes[1:]:
                if isinstance(cur, dict):
                    cur = cur.get(p, default)
                else:
                    return default
            return cur
        return df[partes[0]].apply(extraer)

    return pd.Series(default, index=df.index)


def parse_price_info(val):
    if pd.isna(val):
        return np.nan, np.nan, np.nan
    try:
        data = ast.literal_eval(val) if isinstance(val, str) else val
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            op = data[0].get("operation_type", {}).get("name", np.nan)
            prices = data[0].get("prices", [])
            if len(prices) > 0 and isinstance(prices[0], dict):
                return op, prices[0].get("amount", np.nan), prices[0].get("currency", np.nan)
    except Exception:
        pass
    return np.nan, np.nan, np.nan


def limpiar_zonaprop(df_zp_raw: pd.DataFrame, tipo_cambio_usd: float = 1600.0) -> pd.DataFrame:
    col_precios = _obtener_serie(df_zp_raw, ["price_operation_types"])
    parsed = col_precios.apply(parse_price_info)

    s_lat = _obtener_serie(df_zp_raw, [
        "posting_location/posting_geolocation/geolocation/latitude",
        "posting_location.posting_geolocation.geolocation.latitude",
        "lat",
    ])
    s_lon = _obtener_serie(df_zp_raw, [
        "posting_location/posting_geolocation/geolocation/longitude",
        "posting_location.posting_geolocation.geolocation.longitude",
        "lon",
    ])
    s_barrio = _obtener_serie(df_zp_raw, [
        "posting_location/location/name",
        "posting_location.location.name",
        "barrio",
    ])
    s_ciudad = _obtener_serie(df_zp_raw, [
        "posting_location/location/parent/name",
        "posting_location.location.parent.name",
        "ciudad",
    ])
    s_tipo = _obtener_serie(df_zp_raw, [
        "real_estate_type/name",
        "real_estate_type.name",
        "tipo_inmueble",
    ])
    s_exp = _obtener_serie(df_zp_raw, [
        "expenses/amount",
        "expenses.amount",
        "expensas_ars",
    ], default=0)
    s_sup = _obtener_serie(df_zp_raw, [
        "main_features/c_f_t100/value",
        "main_features.c_f_t100.value",
        "superficie_m2",
    ])

    zp_clean = pd.DataFrame({
        "posting_id": df_zp_raw.get("posting_id", pd.Series(range(len(df_zp_raw)), index=df_zp_raw.index)),
        "lat": pd.to_numeric(s_lat, errors="coerce"),
        "lon": pd.to_numeric(s_lon, errors="coerce"),
        "barrio": s_barrio,
        "ciudad": s_ciudad,
        "tipo_inmueble": s_tipo,
        "tipo_operacion": [x[0] for x in parsed],
        "precio_crudo": pd.to_numeric([x[1] for x in parsed], errors="coerce"),
        "moneda": [x[2] for x in parsed],
        "expensas_ars": pd.to_numeric(s_exp, errors="coerce").fillna(0),
        "superficie_m2": pd.to_numeric(s_sup, errors="coerce"),
    }).drop_duplicates(subset=["posting_id"])

    zp_clean = zp_clean.dropna(subset=["lat", "lon", "precio_crudo", "superficie_m2", "moneda", "tipo_operacion"])
    zp_clean = zp_clean[
        (zp_clean["lat"].between(-33.05, -32.70))
        & (zp_clean["lon"].between(-60.95, -60.60))
        & (zp_clean["tipo_operacion"] == "Alquiler")
        & (zp_clean["superficie_m2"].between(10, 2000))
    ].copy()

    es_pesos = zp_clean["moneda"].isin(["$", "ARS"])
    zp_clean["precio_usd"] = np.where(es_pesos, zp_clean["precio_crudo"] / tipo_cambio_usd, zp_clean["precio_crudo"])
    zp_clean["precio_ars"] = np.where(~es_pesos, zp_clean["precio_crudo"] * tipo_cambio_usd, zp_clean["precio_crudo"])

    zp_clean = zp_clean[
        (zp_clean["precio_usd"] > 20) & (zp_clean["precio_ars"] <= zp_clean["precio_ars"].quantile(0.98))
    ].copy()
    zp_clean["precio_m2_usd"] = (zp_clean["precio_usd"] / zp_clean["superficie_m2"]).round(2)
    return zp_clean


def limpiar_comercios(df_gm_raw: pd.DataFrame) -> pd.DataFrame:
    if {"lat", "lon", "resenas"}.issubset(df_gm_raw.columns):
        df = df_gm_raw.copy()
        df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
        df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
        df["resenas"] = pd.to_numeric(df["resenas"], errors="coerce").fillna(0)
        return df.dropna(subset=["lat", "lon"])

    if "permanentlyClosed" in df_gm_raw.columns:
        df_gm_raw = df_gm_raw[df_gm_raw["permanentlyClosed"] != True]

    s_lat = _obtener_serie(df_gm_raw, ["location/lat", "location.lat", "lat"])
    s_lon = _obtener_serie(df_gm_raw, ["location/lng", "location.lng", "lon"])
    s_res = _obtener_serie(df_gm_raw, ["reviewsCount", "resenas"], default=0)

    gm_clean = pd.DataFrame({
        "placeId": df_gm_raw.get("placeId", pd.Series(range(len(df_gm_raw)), index=df_gm_raw.index)),
        "lat": pd.to_numeric(s_lat, errors="coerce"),
        "lon": pd.to_numeric(s_lon, errors="coerce"),
        "nombre": _obtener_serie(df_gm_raw, ["title", "nombre"], default="Comercio"),
        "rubro": _obtener_serie(df_gm_raw, ["categoryName", "rubro"], default="Comercio"),
        "resenas": pd.to_numeric(s_res, errors="coerce").fillna(0),
    }).dropna(subset=["lat", "lon"])

    return gm_clean.drop_duplicates(subset=["placeId"], keep="last")