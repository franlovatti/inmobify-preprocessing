import ast
import numpy as np
import pandas as pd

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
    parsed = df_zp_raw["price_operation_types"].apply(parse_price_info)

    zp_clean = pd.DataFrame({
        "posting_id": df_zp_raw.get("posting_id", pd.Series(range(len(df_zp_raw)))),
        "lat": pd.to_numeric(df_zp_raw["posting_location/posting_geolocation/geolocation/latitude"], errors="coerce"),
        "lon": pd.to_numeric(df_zp_raw["posting_location/posting_geolocation/geolocation/longitude"], errors="coerce"),
        "barrio": df_zp_raw["posting_location/location/name"],
        "ciudad": df_zp_raw["posting_location/location/parent/name"],
        "tipo_inmueble": df_zp_raw["real_estate_type/name"],
        "tipo_operacion": [x[0] for x in parsed],
        "precio_crudo": pd.to_numeric([x[1] for x in parsed], errors="coerce"),
        "moneda": [x[2] for x in parsed],
        "expensas_ars": pd.to_numeric(df_zp_raw.get("expenses/amount", 0), errors="coerce").fillna(0),
        "superficie_m2": pd.to_numeric(df_zp_raw["main_features/c_f_t100/value"], errors="coerce"),
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

    gm_clean = pd.DataFrame({
        "placeId": df_gm_raw.get("placeId", pd.Series(range(len(df_gm_raw)))),
        "lat": pd.to_numeric(df_gm_raw["location/lat"], errors="coerce"),
        "lon": pd.to_numeric(df_gm_raw["location/lng"], errors="coerce"),
        "nombre": df_gm_raw.get("title", "Comercio"),
        "rubro": df_gm_raw.get("categoryName", "Comercio"),
        "resenas": pd.to_numeric(df_gm_raw["reviewsCount"], errors="coerce").fillna(0),
    }).dropna(subset=["lat", "lon"])

    return gm_clean.drop_duplicates(subset=["placeId"], keep="last")