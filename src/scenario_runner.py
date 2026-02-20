import time
import yaml
import json
import socket
import numpy as np
from datetime import datetime, timezone
from scipy.constants import c, pi
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from pathlib import Path

# Imports del proyecto
from .ris_server_controller import RISServerController, RISConfig
from surpRISe.components.ris import RIS
from surpRISe.components.antenna import Antenna
from surpRISe.channels.tx2ris2rx.tang_general_channel import tang_general_channel
from surpRISe.utils.utils import sph2cart

class RISScenarioRunner:
    def __init__(self, 
                 controller: RISServerController, 
                 enable_json_log: bool = False,
                 influx_ip: Optional[str] = None):
        
        self.controller = controller
        self.ris_obj = None
        self.env_config = {}
        self.stop_flag = False
        
        # Logging Config
        self.enable_json_log = enable_json_log
        self.influx_ip = influx_ip
        self.influx_port = 8094
        self.measurement_name = "test_runs_ris"
        
        self.log_file_path = None
        
        # Iniciar log local solo si está habilitado
        if self.enable_json_log:
            self._init_local_logging()

    def _init_local_logging(self):
        """Prepara el archivo de log local."""
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file_path = logs_dir / f"ris_session_{timestamp}.jsonl"

    def load_config(self, config_data: Dict[str, Any]):
        self.env_config = config_data['environment']
        self._init_ris_object()

    def _init_ris_object(self):
        p = self.env_config['ris_params']
        defaults = self.env_config.get('defaults', {})
        
        freq = float(p.get('frequency_hz', 28.5e9))
        lambda_val = c / freq
        
        d_h = p.get('delta_h', lambda_val / 2.0)
        d_v = p.get('delta_v', lambda_val / 2.0)
        dx = p.get('dx', 0.45 * lambda_val)
        dy = p.get('dy', 0.45 * lambda_val)

        num_bits = p.get('num_bits', 1)
        
        if 'phase_shifts_dict' not in p:
            n_states = 2**num_bits
            p['phase_shifts_dict'] = {i: (i * 2 * pi / n_states) for i in range(n_states)}
            
        if 'att_dict' not in p:
            n_states = 2**num_bits
            p['att_dict'] = {i: 0.9 for i in range(n_states)}

        self.ris_obj = RIS(
            center=p.get('center', [0, 0, 0]),
            boresight=p.get('boresight', 'x'),
            fc=freq,
            Ncol=p['ncol'],
            Nrow=p['nrow'],
            delta_h=d_h,
            delta_v=d_v,
            dx=dx,
            dy=dy,
            phase_shifts_dict=p['phase_shifts_dict'],
            att_dict=p['att_dict'],
            name=p.get('name', "RIS_Main")
        )

    # --- EXECUTION METHODS ---

    def run_step(self, step_data: Dict[str, Any], log_callback=None):
        if self.stop_flag: return

        action = step_data.get('action')
        step_name = step_data.get('step', 'Unnamed Step')
        
        if log_callback:
            log_callback(f"Running: {step_name} [{action}]")

        if action == "power_on":
            self.controller.connect()
            time.sleep(step_data.get('delay_after', 0))
            
        elif action == "power_off":
            self.controller.disconnect()
            
        elif action == "configure":
            self._handle_configure(step_data, log_callback)
            
        elif action == "sweep":
            self._handle_sweep(step_data, log_callback)

    def _get_geometry(self, params):
        env_defaults = self.env_config.get('defaults', {})
        def_tx = env_defaults.get('tx_pos', [0, -5, 2])
        def_rx = env_defaults.get('rx_pos', [0, 5, 2])
        tx_pos = params.get('tx_pos', def_tx)
        rx_pos = params.get('rx_pos', def_rx)
        return tx_pos, rx_pos

    def _get_iso_timestamp(self):
        """Genera timestamp RFC 3339 explícito en UTC con precisión de microsegundos."""
        # datetime.now(timezone.utc) asegura que es UTC+0 consciente.
        # .isoformat() genera: '2026-02-12T20:30:45.123456+00:00'
        # .replace() cambia el offset por la 'Z' militar/Zulu.
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _handle_configure(self, step_data, log_callback):
        params = step_data.get('params', {})
        delay = step_data.get('delay_after', 0)
        
        tx_pos, rx_pos = self._get_geometry(params)
        
        run_params = params.copy()
        run_params['tx_pos'] = tx_pos
        run_params['rx_pos'] = rx_pos

        # Capturar timestamp como STRING ISO (ZULU)
        t_start = self._get_iso_timestamp()
        ris_config_obj = self._apply_single_config(run_params, log_callback)
        if delay > 0: time.sleep(delay)
        t_end = self._get_iso_timestamp()

        self._process_logging(
            step_info=step_data,
            ris_config=ris_config_obj,
            tx_pos=tx_pos,
            rx_pos=rx_pos,
            t_start=t_start,
            t_end=t_end
        )

    def _handle_sweep(self, step_data, log_callback):
        params = step_data.get('params', {})
        
        start_ang = params.get('start_angle', -45)
        stop_ang = params.get('stop_angle', 45)
        step_ang = params.get('step_angle', 5)
        dwell = params.get('dwell_time', 0.5)
        
        if step_ang == 0: angles = [start_ang]
        else: angles = np.arange(start_ang, stop_ang + 0.0001, step_ang)

        target_type = params.get('sweep_target', 'rx') 
        dist = params.get('distance', 5.0)
        axis = params.get('axis', 'azimuth')
        
        env_tx, env_rx = self._get_geometry({})
        default_fixed_pos = env_tx if target_type == 'rx' else env_rx
        fixed_pos_cartesian = params.get('fixed_pos', default_fixed_pos)
        
        default_fixed_ang = 90.0 if axis == 'azimuth' else 0.0
        fixed_angle = params.get('fixed_angle', default_fixed_ang)

        if log_callback:
            log_callback(f"  > Starting Sweep: {len(angles)} points.")

        for angle_val in angles:
            if axis == 'azimuth':
                az, el = angle_val, fixed_angle
            else:
                az, el = fixed_angle, angle_val
                
            sph_input = np.array([[dist, az, el]])
            cart_pos = sph2cart(sph_input)[0].tolist()
            
            sweep_point_params = params.copy()
            if target_type == 'rx':
                tx_pos_now = fixed_pos_cartesian
                rx_pos_now = cart_pos
            else:
                tx_pos_now = cart_pos
                rx_pos_now = fixed_pos_cartesian
                
            sweep_point_params['tx_pos'] = tx_pos_now
            sweep_point_params['rx_pos'] = rx_pos_now
            
            t_start = self._get_iso_timestamp()
            ris_config_obj = self._apply_single_config(sweep_point_params, None)
            if log_callback:
                log_callback(f"    >> Swept {axis}={angle_val:.1f}°, cart dist rx: {np.round(cart_pos,5)}, cart dist tx {default_fixed_pos}")
            time.sleep(dwell)
            t_end = self._get_iso_timestamp()
            
            point_info = {
                "parent_step": step_data.get('step'),
                "sweep_angle": float(angle_val),
                "axis": axis,
                "virtual_coords": [float(x) for x in cart_pos]
            }
            
            self._process_logging(
                step_info=point_info,
                ris_config=ris_config_obj,
                tx_pos=tx_pos_now,
                rx_pos=rx_pos_now,
                t_start=t_start,
                t_end=t_end
            )

    def _apply_single_config(self, params, log_callback):
        conf_mode = params.get('conf_mode', 'zeros')
        apply_vh = params.get('apply_to', 'both')
        
        rows = self.env_config['ris_params']['nrow']
        cols = self.env_config['ris_params']['ncol']
        num_bits = self.env_config['ris_params'].get('num_bits', 1)
        max_state = (2 ** num_bits)
        
        pattern = np.zeros((rows, cols), dtype=int)

        if conf_mode == "zeros":
            pattern = np.zeros((rows, cols), dtype=int)
        elif conf_mode == "ones":
            pattern = np.ones((rows, cols), dtype=int)
        elif conf_mode == "random":
            pattern = np.random.randint(0, max_state, size=(rows, cols))
        elif conf_mode == "optimize":
            if log_callback: log_callback("  Calculating surpRISe optimization...")
            pattern = self._calculate_optimization(params)

        patron_v = pattern if apply_vh in ['v', 'both'] else np.zeros((rows, cols))
        patron_h = pattern if apply_vh in ['h', 'both'] else np.zeros((rows, cols))
        
        config = RISConfig(state_matrix_v=patron_v, state_matrix_h=patron_h)
        self.controller.apply_config(config)
        return config

    def _calculate_optimization(self, params):
        defaults = self.env_config.get('defaults', {})
        tx_pos = params.get('tx_pos', [0, -5, 2]) 
        rx_pos = params.get('rx_pos', [0, 5, 2])
        w_model = params.get('wave_model', defaults.get('wave_model', 'spherical'))
        
        tx = Antenna(position=tx_pos, gain_dbi=defaults.get('tx_gain', 15))
        rx = Antenna(position=rx_pos, gain_dbi=defaults.get('rx_gain', 15))
        
        ris_center = self.env_config['ris_params'].get('center', [0,0,0])
        tx.point_to(ris_center)
        rx.point_to(ris_center)
        
        ch = tang_general_channel()
        ch.optimize(
            optimizer=params.get('optimizer', 'direct_disc'),
            mode="disc",
            wave_model=w_model,
            tx_antenna=tx,
            rx_antenna=rx,
            ris=self.ris_obj
        )
        return self.ris_obj.get_all_state_indices()
        
    # --- LOGGING & INFLUX INTEGRATION ---

    def _process_logging(self, step_info, ris_config: RISConfig, tx_pos, rx_pos, t_start, t_end):
        """Orquesta el guardado local y el envío a Influx."""
        
        # 1. Preparar datos crudos (Raw Data)
        v_flat = ris_config.state_matrix_v[::-1, :].T.flatten().astype(int)
        h_flat = ris_config.state_matrix_h[::-1, :].T.flatten().astype(int)
        full_pattern = [0] * (v_flat.size + h_flat.size)
        full_pattern[0::2] = v_flat.tolist()
        full_pattern[1::2] = h_flat.tolist()
        
        ris_center = self.env_config['ris_params'].get('center', [0,0,0])

        record = {
            "timestamp_start": t_start,
            "timestamp_end": t_end,
            "ris_position": ris_center,
            "tx_position": [float(x) for x in tx_pos],
            "rx_position": [float(x) for x in rx_pos],
            "command_info": json.dumps(step_info), # JSON stringified
            "bit_pattern": full_pattern
        }
        
        # 2. Guardar Local (JSONL) - SOLO SI ESTÁ HABILITADO
        if self.enable_json_log and self.log_file_path:
            try:
                with open(self.log_file_path, 'a') as f:
                    f.write(json.dumps(record) + "\n")
            except Exception as e:
                print(f"⚠️ Error writing to local log: {e}")
                
        # 3. Enviar a Influx (UDP) - SOLO SI HAY IP
        if self.influx_ip:
            self._send_to_influx(record)

    def _send_to_influx(self, record):
        """Replica la lógica de send_to_telegraf_date.py integrada aquí."""
        try:
            # ----------------------------------------------------
            # A. Procesar Datos para Influx (Flattening y Hex)
            # ----------------------------------------------------
            
            # Helper para expandir vectores
            def expand(name, v):
                return {f"{name}_x": float(v[0]), f"{name}_y": float(v[1]), f"{name}_z": float(v[2])}

            # Construir diccionario plano de fields
            data_fields = {}
            data_fields.update(expand("ris_position", record["ris_position"]))
            data_fields.update(expand("tx_position", record["tx_position"]))
            data_fields.update(expand("rx_position", record["rx_position"]))

            # Convertir Bit Pattern a Hexadecimal
            bitlist = record["bit_pattern"]
            bit_pattern_str = "".join(str(b) for b in bitlist)
            # 3200 bits -> hex string (800 chars)
            bit_pattern_hex = hex(int(bit_pattern_str, 2))[2:].zfill(800)
            
            # Añadir restos de fields (USANDO NOMBRES DE send_to_telegraf_date.py)
            data_fields["bit_pattern_hex"] = bit_pattern_hex
            data_fields["ts_start"] = record["timestamp_start"] # Nombre cambiado
            data_fields["ts_end"] = record["timestamp_end"]     # Nombre cambiado

            # ----------------------------------------------------
            # B. Helpers de Escape (Line Protocol)
            # ----------------------------------------------------
            def escape_tag(s: str) -> str:
                return str(s).replace("\\", "\\\\").replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")

            def escape_field_string(s: str) -> str:
                return str(s).replace("\\", "\\\\").replace('"', '\\"')

            # ----------------------------------------------------
            # C. Construir Line Protocol String
            # ----------------------------------------------------
            # TAGS
            # command_info se usa como TAG
            cmd_info = record["command_info"]
            tags = f'command_info="{escape_tag(cmd_info)}"'

            # FIELDS
            fields_list = []
            for k, v in data_fields.items():
                if isinstance(v, str):
                    fields_list.append(f'{k}="{escape_field_string(v)}"')
                else:
                    fields_list.append(f"{k}={v}")

            line = f"{self.measurement_name},{tags} " + ",".join(fields_list)
            
            # ----------------------------------------------------
            # D. Enviar UDP
            # ----------------------------------------------------
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 262144)
            
            payload = (line + "\n").encode("utf-8")
            sock.sendto(payload, (self.influx_ip, self.influx_port))
            sock.close()
            
        except Exception as e:
            print(f"⚠️ Failed to send to InfluxDB: {e}")