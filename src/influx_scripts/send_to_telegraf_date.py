#!/usr/bin/env python3
import json
import sys
import socket
from pathlib import Path
import hashlib

PORT = 8094
MEASUREMENT = "test_runs_ris"


# ============================================================
#  Load JSON config
# ============================================================
def load_config(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"No existe el fichero: {path}")

    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    required = [
        "ris_position", "tx_position", "rx_position",
        "command_info", "bit_pattern",
        "timestamp_start", "timestamp_end"
    ]
    for field in required:
        if field not in cfg:
            raise ValueError(f"Falta el campo '{field}' en el JSON")

    # 3D positions
    for name in ["ris_position", "tx_position", "rx_position"]:
        vec = cfg[name]
        if not isinstance(vec, list) or len(vec) != 3:
            raise ValueError(f"'{name}' debe ser una lista de 3 números")

    # bit_pattern list of 3200 bits
    bitlist = cfg["bit_pattern"]
    if (not isinstance(bitlist, list)
        or len(bitlist) != 3200
        or any(b not in (0,1) for b in bitlist)):
        raise ValueError("'bit_pattern' debe ser una lista de 3200 bits 0/1")

    # Convert list -> binary string
    bit_pattern_str = "".join(str(b) for b in bitlist)

    # Convert bits -> hex (800 hex chars)
    bit_pattern_hex = hex(int(bit_pattern_str, 2))[2:].zfill(800)

    # timestamps
    def as_float(x, name):
        try:
            return float(x)
        except:
            raise ValueError(f"'{name}' debe ser float convertible")

    #timestamp_start = as_float(cfg["timestamp_start"], "timestamp_start")
    #timestamp_end   = as_float(cfg["timestamp_end"], "timestamp_end")
    timestamp_start = cfg["timestamp_start"]
    timestamp_end   = cfg["timestamp_end"]

    # expand vec
    def expand(v):
        return {"x": float(v[0]), "y": float(v[1]), "z": float(v[2])}

    ris = expand(cfg["ris_position"])
    tx  = expand(cfg["tx_position"])
    rx  = expand(cfg["rx_position"])

    return {
        "ris_position_x": ris["x"],
        "ris_position_y": ris["y"],
        "ris_position_z": ris["z"],
        "tx_position_x": tx["x"],
        "tx_position_y": tx["y"],
        "tx_position_z": tx["z"],
        "rx_position_x": rx["x"],
        "rx_position_y": rx["y"],
        "rx_position_z": rx["z"],
        "command_info": cfg["command_info"],    # TAG
        "bit_pattern_hex": bit_pattern_hex,     # FIELD (hex)
        "ts_start": timestamp_start,
        "ts_end": timestamp_end,
    }


# ============================================================
#  Escapes for InfluxDB LP
# ============================================================
def escape_tag(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
         .replace(" ", "\\ ")
         .replace(",", "\\,")
         .replace("=", "\\=")
    )

def escape_field_string(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
         .replace('"', '\\"')
    )


# ============================================================
#  build run_id (useful tag for grouping)
# ============================================================
def build_run_id(data):
    src = (
        f"{data['timestamp_start']}-{data['timestamp_end']}-"
        f"{data['ris_position_x']}-{data['ris_position_y']}-{data['ris_position_z']}-"
        f"{len(data['bit_pattern_hex'])}"
    )
    return hashlib.sha1(src.encode()).hexdigest()[:12]


# ============================================================
#  Build Influx Line Protocol string
# ============================================================
def format_line_protocol(data, run_id=0):
    # TAGS
    tags = (
        #f"run_id={escape_tag(run_id)},"
        f'command_info="{escape_tag(data["command_info"])}"'
    )

    # FIELDS
    fields = []
    for k, v in data.items():
        if k == "command_info":   # ya lo pusimos como tag
            continue
        if isinstance(v, str):
            fields.append(f'{k}="{escape_field_string(v)}"')
        else:
            fields.append(f"{k}={v}")

    return f"{MEASUREMENT},{tags} " + ",".join(fields)


# ============================================================
#  Send UDP
# ============================================================
def send_udp(ip, line, debug=False):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 262144)

    payload = (line + "\n").encode("utf-8")

    if debug:
        pkt_len = len(payload)
        print(f"[DEBUG] Payload len = {pkt_len} bytes")
        print(f"[DEBUG] Estimated full IP packet = {pkt_len + 28} bytes")

    sock.sendto(payload, (ip, PORT))
    sock.close()


# ============================================================
#  Main
# ============================================================
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python3 send_to_telegraf.py <config.json> <ip_telegraf> [--debug]")
        sys.exit(1)

    config_path = sys.argv[1]
    telegraf_ip = sys.argv[2]
    debug = ("--debug" in sys.argv)

    try:
        data = load_config(config_path)

        #run_id = build_run_id(data)
        line = format_line_protocol(data)

        print("Línea LP generada:\n")
        print(line)
        print()

        send_udp(telegraf_ip, line, debug=debug)

        print(f"Enviado a Telegraf (UDP) → {telegraf_ip}:{PORT}")
        #print(f"run_id={run_id}")

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(2)
