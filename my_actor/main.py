import io
import pandas as pd
from apify import Actor
import asyncio

from src.limpieza import limpiar_zonaprop, limpiar_comercios
from src.features import construir_features_modelo, construir_features_eda
from src.eda_tablas import generar_tablas_eda

async def main():
    async with Actor:
        actor_input = await Actor.get_input() or {}
        store_name = actor_input.get("kv_store_name", "inmobify-storage")
        key_zp_raw = actor_input.get("key_zonaprop_raw", "raw_zonaprop_rosario.csv")
        key_gm_raw = actor_input.get("key_comercios_raw", "maestro_comercios_rosario.csv")
        tipo_cambio_usd = float(actor_input.get("tipo_cambio_usd", 1600.0))

        await Actor.set_status_message("Abriendo Key-Value Store y cargando datasets crudos...")
        Actor.log.info(f"Conectando a Key-Value Store '{store_name}'...")
        store = await Actor.open_key_value_store(name=store_name)

        raw_zp_text = await store.get_value(key_zp_raw)
        raw_gm_text = await store.get_value(key_gm_raw)

        if not raw_zp_text or not raw_gm_text:
            raise ValueError(
                f"Faltan archivos de entrada en '{store_name}': '{key_zp_raw}' o '{key_gm_raw}'."
            )

        df_zp_raw = pd.read_csv(io.StringIO(raw_zp_text), low_memory=False)
        df_gm_raw = pd.read_csv(io.StringIO(raw_gm_text), low_memory=False)
        Actor.log.info(f"Crudos leídos por SDK -> Zonaprop: {len(df_zp_raw)} | Comercios: {len(df_gm_raw)}")

        await Actor.set_status_message("Limpiando datos y ejecutando Feature Engineering...")
        df_zp_limpio = limpiar_zonaprop(df_zp_raw, tipo_cambio_usd=tipo_cambio_usd)
        df_gm_limpio = limpiar_comercios(df_gm_raw)
        df_features = construir_features_modelo(df_zp_limpio, df_gm_limpio)
        df_dataset_final = construir_features_eda(df_features)
        Actor.log.info(f"Feature Engineering completado -> {len(df_dataset_final)} filas, {df_dataset_final.shape[1]} columnas.")

        await Actor.set_status_message("Generando tablas agregadas EDA para Looker Studio...")
        csv1_barrios, csv2_mapa, csv3_segmentos = generar_tablas_eda(df_dataset_final)

        await Actor.set_status_message("Guardando dataset limpio y tablas EDA en Key-Value Store...")
        await store.set_value("dataset_inmobiliario_completo_rosario.csv", df_dataset_final.to_csv(index=False))
        await store.set_value("maestro_comercios_limpio.csv", df_gm_limpio.to_csv(index=False))
        await store.set_value("eda_csv1_resumen_barrios.csv", csv1_barrios.to_csv(index=False))
        await store.set_value("eda_csv2_mapa_propiedades.csv", csv2_mapa.to_csv(index=False))
        await store.set_value("eda_csv3_segmentos_densidad.csv", csv3_segmentos.to_csv(index=False))

        await Actor.push_data({
            "status": "SUCCESS",
            "kv_store": store_name,
            "registros_limpios": len(df_dataset_final),
            "columnas_totales": int(df_dataset_final.shape[1]),
            "filas_eda_barrios": len(csv1_barrios),
            "filas_eda_mapa": len(csv2_mapa),
            "filas_eda_segmentos": len(csv3_segmentos),
        })
        await Actor.set_status_message("Preprocesamiento, Feature Engineering y EDA finalizados con éxito.")

if __name__ == "__main__":
    asyncio.run(main())