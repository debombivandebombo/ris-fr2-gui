import pandas as pd
import numpy as np
from influxdb_client import InfluxDBClient
from dateutil import parser as dateparser
from datetime import datetime, timedelta

import warnings
from influxdb_client.client.warnings import MissingPivotFunction

warnings.simplefilter("ignore", MissingPivotFunction)

# ----------------------------------------------------
# CONFIGURACIÓN
# ----------------------------------------------------
URL = "http://10.0.26.12:8086"
TOKEN = "ipYA7lIdtg_WKo6DXeUkwcc8gnRChPWamxl1DKteVjW-zBbUT9HEUKRZc_JkN2_36WKtJwA6L2tdktGA_sd4Bw=="
ORG = "xrlab"
BUCKET = "xrlab_onWheels"

# Ventana de agregación
WINDOW_SECONDS = 5

client = InfluxDBClient(url=URL, token=TOKEN, org=ORG)
query_api = client.query_api()

# ----------------------------------------------------
# Función utilitaria: convierte epoch o RFC3339
# ----------------------------------------------------
def to_datetime(value):
    """Convierte un valor de timestamp a datetime."""
    if isinstance(value, (int, float)):
        # Epoch en segundos
        return datetime.utcfromtimestamp(value)
    if isinstance(value, str):
        return dateparser.parse(value)
    raise ValueError("Formato de timestamp no reconocido:", value)


# ----------------------------------------------------
# 1) LEER TODOS LOS TEST RUNS Y PIVOTAR
# ----------------------------------------------------
query_test_runs = f"""
from(bucket: "{BUCKET}")
  |> range(start: -10y)
  |> filter(fn: (r) => r._measurement == "test_runs_ris")
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["_time", "ts_start", "ts_end", "command_info", "bit_pattern_hex",
                    "ris_position_x","ris_position_y","ris_position_z",
                    "rx_position_x","rx_position_y","rx_position_z",
                    "tx_position_x","tx_position_y","tx_position_z"])

"""

runs = query_api.query_data_frame(query_test_runs)

# Si vienen varias tablas de pandas, concatenarlas:
if isinstance(runs, list):
    runs = pd.concat(runs, ignore_index=True)

print("Test runs encontrados:")
print(runs)

# ----------------------------------------------------
# 2) PROCESAR CADA TEST RUN
# ----------------------------------------------------

master_rows = []   # acumulamos todas las filas finales

for idx, run in runs.iterrows():

    run_id = run["_time"]
    start = to_datetime(run["ts_start"])
    end   = to_datetime(run["ts_end"])

    print(f"\nProcesando test run {run_id} ({start} → {end})")

    # ------------------------------------------------
    # 2A) Generar las marcas de tiempo cada 5 s
    # ------------------------------------------------
    timestamps = pd.date_range(start=start, end=end, freq=f"{WINDOW_SECONDS}s")

    df_base = pd.DataFrame({"timestamp": timestamps})
    df_base["run_id"] = run_id

    # Añadimos tags y fields del test run como columnas
    for col in runs.columns:
        if col not in ["_time", "timestamp_start", "timestamp_end", "result", "table"]:
            df_base[col] = run[col]

    # ------------------------------------------------
    # 2B) Obtener datos RSRP y RSRQ
    # ------------------------------------------------
    query_rsrp_rsrq = f"""
from(bucket: "{BUCKET}")
  |> range(start: {start.isoformat()}, stop: {end.isoformat()})
  |> filter(fn: (r) => r._measurement == "radio_quality_mdm")
  |> filter(fn: (r) => r._field == "RSRP" or r._field == "RSRQ")
  |> keep(columns: ["_time","_field","_value"])
  |> sort(columns: ["_time"])
"""

    df_rsr = query_api.query_data_frame(query_rsrp_rsrq)
    if isinstance(df_rsr, list):
        df_rsr = pd.concat(df_rsr, ignore_index=True)
    #JPOprint(df_rsr)

    if not df_rsr.empty:
        df_rsr.rename(columns={"_time": "timestamp"}, inplace=True)
        df_rsr["timestamp"] = pd.to_datetime(df_rsr["timestamp"])

        # Reorganizamos a columnas RSRP / RSRQ
        df_rsr = df_rsr.pivot(index="timestamp", columns="_field", values="_value")

        # Resample 5s con media
        df_rsr = df_rsr.resample(f"{WINDOW_SECONDS}s").mean().ffill().bfill()
    #JPOprint(df_rsr)

    # ------------------------------------------------
    # 2C1) Obtener bytes_recv + derivada no negativa
    # ------------------------------------------------
    query_net = f"""
from(bucket: "{BUCKET}")
  |> range(start: {start.isoformat()}, stop: {end.isoformat()})
  |> filter(fn: (r) => r._measurement == "net")
  |> filter(fn: (r) => r.host == "Rod-core-sa5")
  |> filter(fn: (r) => r.interface == "slicetun1")
  |> filter(fn: (r) => r._field == "bytes_recv")
  |> keep(columns: ["_time","_value"])
"""

    df_net = query_api.query_data_frame(query_net)
    #JPOprint(df_net)
    if isinstance(df_net, list):
        df_net = pd.concat(df_net, ignore_index=True)
    #JPOprint(df_net)

    df_net_bps_recv = df_net # Por si no hay datos, que quede vacío pero definido y 
                             # que no de error al hacer el join
    if not df_net.empty:
        df_net.rename(columns={"_time": "timestamp", "_value": "bytes_recv"}, inplace=True)
        df_net["timestamp"] = pd.to_datetime(df_net["timestamp"])
        df_net = df_net.sort_values("timestamp").set_index("timestamp")

        # Derivada NO NEGATIVA y conversion a bitrate en bps
        delta_bytes = df_net["bytes_recv"].diff().clip(lower=0)
        delta_t = df_net.index.to_series().diff().dt.total_seconds()
        inst_bps = (delta_bytes / delta_t).fillna(0) * 8

        # Media cada {WINDOW_SECONDS}s
        df_net_bps_recv = (
            inst_bps
            .resample(f"{WINDOW_SECONDS}s")
            .mean()
            .ffill()
            .bfill()
            .to_frame("bytes_recv_bps")
        )
    #JPOprint(df_net_bps_recv)

    # ------------------------------------------------
    # 2C2) Obtener bytes_sent + derivada no negativa
    # ------------------------------------------------
    query_net = f"""
from(bucket: "{BUCKET}")
  |> range(start: {start.isoformat()}, stop: {end.isoformat()})
  |> filter(fn: (r) => r._measurement == "net")
  |> filter(fn: (r) => r.host == "Rod-core-sa5")
  |> filter(fn: (r) => r.interface == "slicetun1")
  |> filter(fn: (r) => r._field == "bytes_sent")
  |> keep(columns: ["_time","_value"])
"""

    df_net = query_api.query_data_frame(query_net)
    #JPOprint(df_net)
    if isinstance(df_net, list):
        df_net = pd.concat(df_net, ignore_index=True)
    #JPOprint(df_net)

    df_net_bps_sent = df_net # Por si no hay datos, que quede vacío pero definido y 
                             # que no de error al hacer el join
    if not df_net.empty:
        df_net.rename(columns={"_time": "timestamp", "_value": "bytes_sent"}, inplace=True)
        df_net["timestamp"] = pd.to_datetime(df_net["timestamp"])
        df_net = df_net.sort_values("timestamp").set_index("timestamp")

        # Derivada NO NEGATIVA y conversion a bitrate en bps
        delta_bytes = df_net["bytes_sent"].diff().clip(lower=0)
        delta_t = df_net.index.to_series().diff().dt.total_seconds()
        inst_bps = (delta_bytes / delta_t).fillna(0) * 8

        # Media cada {WINDOW_SECONDS}s
        df_net_bps_sent = (
            inst_bps
            .resample(f"{WINDOW_SECONDS}s")
            .mean()
            .ffill()
            .bfill()
            .to_frame("bytes_sent_bps")
        )
    #JPOprint(df_net_bps_sent)

    # ------------------------------------------------
    # 2D) Mezclar todo en df_base
    # ------------------------------------------------
    df_final = df_base.set_index("timestamp")

    if not df_rsr.empty:
        df_final = df_final.join(df_rsr, how="left")

    if not df_net_bps_recv.empty:
        df_final = df_final.join(df_net_bps_recv, how="left")

    if not df_net_bps_sent.empty:
        df_final = df_final.join(df_net_bps_sent, how="left")

    master_rows.append(df_final.reset_index())
#JPOprint(df_final)

# ----------------------------------------------------
# 3) CONCATENAR TODO Y EXPORTAR CSV
# ----------------------------------------------------
df_all = pd.concat(master_rows, ignore_index=True)

output_csv = "test_runs_data.csv"
df_all.to_csv(output_csv, sep=';', index=False)

print(f"\nCSV generado: {output_csv}")
print(df_all.head(20))
