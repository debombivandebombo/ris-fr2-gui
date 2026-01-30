import time
import yaml
import numpy as np
from scipy.constants import c, pi
from dataclasses import dataclass
from typing import List, Dict, Any

# Imports relativos asumiendo que está en src/
from .ris_server_controller import RISServerController, RISConfig

# Imports de tu librería (ajusta si la ruta cambia)
import sys
import os
# Aseguramos que libs está en el path si se ejecuta desde aquí
# (Normalmente esto lo maneja app.py, pero por seguridad)
from surpRISe.components.ris import RIS
from surpRISe.components.antenna import Antenna
from surpRISe.channels.tx2ris2rx.tang_general_channel import tang_general_channel

class RISScenarioRunner:
    def __init__(self, controller: RISServerController):
        self.controller = controller
        self.ris_obj = None
        self.env_config = {}
        self.stop_flag = False

    def load_config(self, config_data: Dict[str, Any]):
        """Carga la configuración del entorno."""
        self.env_config = config_data['environment']
        self._init_ris_object()

    def _init_ris_object(self):
        """Instancia el objeto RIS de surpRISe."""
        p = self.env_config['ris_params']
        
        # Frecuencia y Lambda
        freq = float(p.get('frequency_hz', 28.5e9))
        lambda_val = c / freq
        
        # Element spacing & size (defaults calculados si no existen)
        d_h = p.get('delta_h', lambda_val / 2.0)
        d_v = p.get('delta_v', lambda_val / 2.0)
        dx = p.get('dx', 0.45 * lambda_val)
        dy = p.get('dy', 0.45 * lambda_val)

        # Generación de diccionarios por defecto si no vienen en el YAML
        # Asumimos 1 bit por defecto si no se indica num_bits
        num_bits = p.get('num_bits', 1)
        
        if 'phase_shifts_dict' not in p:
            n_states = 2**num_bits
            # Genera fases equiespaciadas: 0, pi para 1 bit
            p['phase_shifts_dict'] = {i: (i * 2 * pi / n_states) for i in range(n_states)}
            
        if 'att_dict' not in p:
            n_states = 2**num_bits
            # Asume 0.9 para todos los estados por defecto
            p['att_dict'] = {i: 0.9 for i in range(n_states)}

        # Instanciación estricta según tu clase
        self.ris_obj = RIS(
            center=p.get('center', [0, 0, 0]),
            boresight=p.get('boresight', 'x'), # Default 'x' como pediste
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

    def run_step(self, step_data: Dict[str, Any], log_callback=None):
        """Ejecuta un paso del timeline."""
        if self.stop_flag:
            return

        action = step_data.get('action')
        step_name = step_data.get('step', 'Unnamed Step')
        
        if log_callback:
            log_callback(f"Running: {step_name} [{action}]")

        if action == "power_on":
            self.controller.connect()
            
        elif action == "power_off":
            self.controller.disconnect()
            
        elif action == "configure":
            self._handle_configure(step_data, log_callback)

        # Delay
        delay = step_data.get('delay_after', 0)
        if delay > 0:
            if log_callback:
                log_callback(f"  Waiting {delay}s...")
            time.sleep(delay)

    def _handle_configure(self, step_data, log_callback):
        # AHORA EXTRAEMOS TODO DE 'params'
        params = step_data.get('params', {})
        
        conf_mode = params.get('conf_mode', 'zeros') # Default safe
        apply_vh = params.get('apply_to', 'both')
        
        # Info de la RIS
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
            if log_callback:
                log_callback("  Calculating surpRISe optimization...")
            pattern = self._calculate_optimization(params)

        # Lógica de polarización
        patron_v = pattern if apply_vh in ['v', 'both'] else np.zeros((rows, cols))
        patron_h = pattern if apply_vh in ['h', 'both'] else np.zeros((rows, cols))
        
        config = RISConfig(state_matrix_v=patron_v, state_matrix_h=patron_h)
        self.controller.apply_config(config)

    def _calculate_optimization(self, params):
        defaults = self.env_config['defaults']
        
        # Recuperar posiciones (Obligatorias en params para optimize)
        # Si no están, intentamos usar defaults o fallar controladamente
        tx_pos = params.get('tx_pos', [0, -5, 2]) 
        rx_pos = params.get('rx_pos', [0, 5, 2])
        
        # Wave model ahora viene en params
        w_model = params.get('wave_model', defaults.get('wave_model', 'spherical'))
        
        # Instanciar Antenas
        tx = Antenna(position=tx_pos, gain_dbi=defaults['tx_gain'])
        rx = Antenna(position=rx_pos, gain_dbi=defaults['rx_gain'])
        
        # Apuntar al centro de la RIS
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