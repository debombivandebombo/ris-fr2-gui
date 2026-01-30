import socket
import json
from dataclasses import dataclass
import numpy as np

@dataclass
class RISConfig:
    state_matrix_v: np.ndarray  # Vertical polarization state matrix (i.e. 40x40)
    state_matrix_h: np.ndarray  # Horizontal polarization state matrix (i.e. 40x40)

class RISServerController:
    def __init__(self, ip="127.0.0.1", port=17000):
        self.addr = (ip, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def connect(self):
        self._send_command("ON")

    def disconnect(self):
        self._send_command("OFF")

    def apply_config(self, config: RISConfig):
        v_flat = config.state_matrix_v[::-1, :].T.flatten().astype(int)
        h_flat = config.state_matrix_h[::-1, :].T.flatten().astype(int)

        gw_pattern = [0] * (v_flat.size + h_flat.size)
        gw_pattern[0::2] = v_flat.tolist()
        gw_pattern[1::2] = h_flat.tolist()

        # Apply the config to the RIS
        self._send_command("SET_CONFIG", gw_pattern)

    def _send_command(self, cmd, data=None):
        msg = {"cmd": cmd, "data": data}
        self.sock.sendto(json.dumps(msg).encode('utf-8'), self.addr)