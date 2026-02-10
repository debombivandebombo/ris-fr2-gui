import socket
import json
import time
import numpy as np
from ris_server_controller import RISServerController, RISConfig

def main():
    print("--- Test de Conexión: Bridge UDP para la RIS ---")
    
    # 1. Instanciar el controlador físico (el cual usa UDP hacia el puerto 17000)
    # Asegúrate de que el servidor 'ris_hardware_server.py' esté corriendo en otra terminal con Python 3.8
    controller = RISServerController(ip="127.0.0.1", port=17000)

    try:
        # 2. Intentar encender la RIS remotamente
        print("[1/3] Enviando comando de encendido (ON)...")
        controller.connect()
        time.sleep(1)

        # 3. Crear y enviar un patrón de prueba (40x40 para cada polarización)
        print("[2/3] Generando patrón de tablero de ajedrez (Checkerboard)...")
        
        # Creamos dos matrices 40x40 con un patrón alternante
        checker_v = np.indices((40, 40)).sum(axis=0) % 2
        checker_h = (checker_v + 1) % 2 # Inverso para la otra polarización

        controller.apply_config(RISConfig(
            state_matrix_v=checker_v, 
            state_matrix_h=checker_h)
        )
        print("      -> Patrón enviado al servidor.")
        
        time.sleep(2)

        # 4. Apagar la RIS
        print("[3/3] Enviando comando de apagado (OFF)...")
        controller.disconnect()
        
        print("\n✅ Test completado con éxito. Si el servidor 3.8 no mostró errores, la comunicación es correcta.")

    except Exception as e:
        print(f"\n❌ Error durante el test: {e}")
        print("Asegúrate de que 'ris_hardware_server.py' esté ejecutándose en un proceso de Python 3.8.")

if __name__ == "__main__":
    main()