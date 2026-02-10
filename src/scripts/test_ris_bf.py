import socket
import json
import time
import numpy as np
from ris_server_controller import RISServerController, RISConfig
from surpRISe.components.ris import RIS
from surpRISe.components.antenna import Antenna
from surpRISe.channels.tx2ris2rx.tang_general_channel import tang_general_channel
from scipy.constants import c
from surpRISe.utils.utils import sph2cart

def main():
    controller = RISServerController(ip="127.0.0.1", port=17000)
    controller.connect()
    time.sleep(1)
    
    ch = tang_general_channel()

    my_ris = get_global_ris()
    my_tx = get_global_tx()

    # controller.apply_random_config()
    # print(f"random config applied")

    scan_point = [2, -1, -0.2]
    print(scan_point)
    calc_and_apply_ris_config(my_tx, my_ris, ch, controller, scan_point, apply_vh='h')

    # az_range = np.arange(0, 35, 1)
    # r_dist = 2.2
    # for az in az_range:
    #     scan_point = sph2cart(r_dist, az, 90)[0]
    #     calc_and_apply_ris_config(my_tx, my_ris, ch, controller, scan_point, apply_vh='h')
    #     print(az)
    #     time.sleep(3)

    # r_dist = 2.2
    # az_range = np.arange(0, 35, 1)
    # el_range = np.arange(85, 95, 1)
    # for el in el_range:
    #     for az in az_range:
    #         scan_point = sph2cart(r_dist, az, el)[0]
    #         calc_and_apply_ris_config(my_tx, my_ris, ch, controller, scan_point, apply_vh='h')
    #         print(el)
    #         time.sleep(3)
    
    # 4. Apagar la RIS
    input("Presiona Enter para apagar la RIS...")
    controller.disconnect()

def calc_and_apply_ris_config(my_tx, my_ris, ch, controller, scan_point, apply_vh='h'):

    ch.optimize(
        optimizer="direct_disc", 
        mode="disc", 
        wave_model="spherical",
        tx_antenna=my_tx, 
        rx_antenna=Antenna(position=scan_point, gain_dbi=0), 
        ris=my_ris
    )

    # ch.plot_path_gain_2d_map(tx_antenna=my_tx,
    #     rx_antenna=Antenna(position=scan_point, gain_dbi=16),
    #     ris=my_ris,
    #     ax1lim=[-3,3],
    #     ax2lim=[-3,3],
    #     Nax1=100,
    #     Nax2=100,
    #     plane = "xy",
    #     vmin= -100,
    #     vmax= -20)
        
    # 2. Retrieve the optimized pattern (indices 0/1)
    opt_pattern = my_ris.get_all_state_indices()

    if apply_vh == 'v':
        patron_v = opt_pattern
        patron_h = np.zeros_like(patron_v)
    elif apply_vh == 'h':
        patron_h = opt_pattern
        patron_v = np.zeros_like(patron_h)
    else:
        patron_v = opt_pattern
        patron_h = opt_pattern

    controller.apply_config(RISConfig(
        state_matrix_v=patron_v, 
        state_matrix_h=patron_h, 
        mode="disc")
    )
    print("      -> Patrón enviado al servidor.")

if __name__ == "__main__":
    main()