import streamlit as st
import numpy as np
import plotly.graph_objects as go
from scipy.constants import c, pi
import sys
import os
import yaml
from pathlib import Path

# --- PATH & IMPORT SETUP ---
ROOT_DIR = Path(__file__).parent
LIBS_DIR = ROOT_DIR / "libs"
if str(LIBS_DIR) not in sys.path:
    sys.path.append(str(LIBS_DIR))

try:
    from src.ris_server_controller import RISConfig, RISServerController
    from src.scenario_runner import RISScenarioRunner
    from surpRISe.components.ris import RIS
except ImportError as e:
    st.error(f"Critical Import Error: {e}")
    st.stop()

# --- PAGE CONFIG ---
st.set_page_config(page_title="RIS Command Center", page_icon="📡", layout="wide")

# --- SESSION STATE ---
if 'controller' not in st.session_state: st.session_state['controller'] = RISServerController()
if 'connected' not in st.session_state: st.session_state['connected'] = False
if 'logs' not in st.session_state: st.session_state['logs'] = []
if 'loaded_yaml' not in st.session_state: st.session_state['loaded_yaml'] = None

# --- HELPER LOGGING ---
def log_message(msg):
    st.session_state['logs'].append(msg)
    if len(st.session_state['logs']) > 50: st.session_state['logs'].pop(0)

# --- SIDEBAR ---
st.sidebar.title("RIS Connection")
st.sidebar.markdown(f"**Status:** {'🟢 CONNECTED' if st.session_state['connected'] else '🔴 DISCONNECTED'}")
c1, c2 = st.sidebar.columns(2)
if c1.button("Connect", disabled=st.session_state['connected']):
    try:
        st.session_state['controller'].connect()
        st.session_state['connected'] = True
        st.toast("Connected!")
    except Exception as e: st.error(str(e))
if c2.button("Disconnect", disabled=not st.session_state['connected']):
    try:
        st.session_state['controller'].disconnect()
        st.session_state['connected'] = False
        st.toast("Disconnected!")
    except Exception as e: st.error(str(e))

st.sidebar.markdown("---")

# --- TABS ---
tab_manual, tab_scenario, tab_viz = st.tabs(["🎛️ Manual Control", "📝 Scenario Manager", "📊 3D Visualization"])

# ==========================================
# TAB 1: MANUAL CONTROL (REDISEÑADO)
# ==========================================
with tab_manual:
    st.header("Manual Configuration")
    
    # Columnas reorganizadas
    col_ris, col_sys, col_opt = st.columns(3)
    
    with col_ris:
        st.subheader("1. RIS Parameters")
        # Parámetros visuales de la RIS
        man_ris_center = [
            st.number_input("RIS X", 0.0, key="m_rx"),
            st.number_input("RIS Y", 0.0, key="m_ry"),
            st.number_input("RIS Z", 0.0, key="m_rz")
        ]
        man_boresight = st.selectbox("Boresight", ["x", "y", "z"], index=0, key="m_bore")
        st.info("Geometry fixed: 40x40 elements")

    with col_sys:
        st.subheader("2. System & TX/RX")
        man_freq = st.number_input("Frequency (GHz)", 28.5, step=0.1)
        man_bits = st.number_input("Bits", min_value=1, max_value=8, value=1)
        
        st.caption("Positions (m):")
        man_tx = [st.number_input("TX X", 5.0), st.number_input("TX Y", -5.0), st.number_input("TX Z", 0.0)]
        man_rx = [st.number_input("RX X", 10.0), st.number_input("RX Y", 5.0), st.number_input("RX Z", 0.0)]

    with col_opt:
        st.subheader("3. Optimization Config")
        # Opciones que irán a 'params'
        man_conf_mode = st.selectbox("Config Mode", ["optimize", "zeros", "ones", "random", "no_change"])
        man_apply_to = st.selectbox("Apply To", ["both", "v", "h"])
        man_wave_model = st.selectbox("Wave Model", ["spherical", "plane"])
        man_optimizer = st.selectbox("Optimizer", ["direct_disc", "grid_search", "chen_alg1", "iterative"])

    st.divider()
    
    if st.button("🚀 Execute Manual Command", type="primary", use_container_width=True):
        if not st.session_state['connected']:
            st.error("Connect first!")
        else:
            with st.spinner("Executing..."):
                try:
                    runner = RISScenarioRunner(st.session_state['controller'])
                    
                    # 1. Construir entorno temporal
                    freq_hz = man_freq * 1e9
                    n_states = 2**man_bits
                    # Diccionarios autogenerados para manual
                    p_dict = {i: (i * 2 * pi / n_states) for i in range(n_states)}
                    a_dict = {i: 0.9 for i in range(n_states)}
                    
                    env_config = {
                        "ris_params": {
                            "center": man_ris_center,
                            "boresight": man_boresight,
                            "frequency_hz": freq_hz,
                            "num_bits": man_bits,
                            "ncol": 40, "nrow": 40,
                            "phase_shifts_dict": p_dict,
                            "att_dict": a_dict
                        },
                        "defaults": {"tx_gain": 15, "rx_gain": 15}
                    }
                    
                    # 2. Construir paso (Empaquetando params como pediste)
                    step_config = {
                        "action": "configure",
                        "params": {
                            "conf_mode": man_conf_mode,
                            "apply_to": man_apply_to,
                            "wave_model": man_wave_model,
                            "optimizer": man_optimizer,
                            "tx_pos": man_tx,
                            "rx_pos": man_rx
                        }
                    }
                    
                    runner.load_config({"environment": env_config})
                    runner.run_step(step_config, log_callback=log_message)
                    st.success("Command Sent!")
                except Exception as e:
                    st.error(f"Error: {e}")

# ==========================================
# TAB 2: SCENARIO MANAGER
# ==========================================
with tab_scenario:
    st.header("Dynamic Test Scenarios")
    
    c_load, c_edit = st.columns([1, 3])
    with c_load:
        uploaded_file = st.file_uploader("Upload YAML", type="yaml")
        if uploaded_file:
            try:
                st.session_state['loaded_yaml'] = yaml.safe_load(uploaded_file)
                st.toast("YAML Loaded")
            except: st.error("Bad YAML")
            
    with c_edit:
        st.subheader("Visual Editor")
        # Definimos las columnas visuales (flat) que luego empaquetaremos
        default_data = [
            {"step": "Init", "action": "power_on", "delay_after": 2, "conf_mode": None, "apply_to": None},
            {"step": "Test Zeros", "action": "configure", "conf_mode": "zeros", "apply_to": "both", "delay_after": 5},
            {"step": "Optimization", "action": "configure", "conf_mode": "optimize", "apply_to": "v", "delay_after": 5},
            {"step": "End", "action": "power_off", "delay_after": 0, "conf_mode": None, "apply_to": None},
        ]
        
        # Si cargamos YAML, intentamos aplanar la estructura params para mostrarla en la tabla
        if st.session_state['loaded_yaml']:
            raw_timeline = st.session_state['loaded_yaml'].get('timeline', [])
            flattened_timeline = []
            for step in raw_timeline:
                flat_step = step.copy()
                # Extraer params a nivel raiz para la UI
                if 'params' in flat_step:
                    p = flat_step.pop('params')
                    flat_step.update(p) # Mueve conf_mode, apply_to, etc. arriba
                flattened_timeline.append(flat_step)
            current_data = flattened_timeline
        else:
            current_data = default_data

        edited_df = st.data_editor(
            current_data,
            num_rows="dynamic",
            column_config={
                "action": st.column_config.SelectboxColumn(options=["power_on", "power_off", "configure"]),
                "conf_mode": st.column_config.SelectboxColumn(options=["zeros", "ones", "random", "optimize"]),
                "apply_to": st.column_config.SelectboxColumn(options=["both", "v", "h"]),
                "wave_model": st.column_config.SelectboxColumn(options=["spherical", "plane"]),
            },
            use_container_width=True
        )

    st.divider()
    
    if st.button("▶️ Run Scenario Sequence", type="primary"):
        if not st.session_state['connected']:
            st.error("Connect first!")
        else:
            st.session_state['logs'] = []
            runner = RISScenarioRunner(st.session_state['controller'])
            
            # Reconstruir estructura anidada 'params' desde la tabla plana
            final_timeline = []
            for row in edited_df:
                clean_step = {"step": row.get("step"), "action": row.get("action"), "delay_after": row.get("delay_after")}
                
                if row.get("action") == "configure":
                    # Empaquetar todo lo demás en params
                    params_dict = {}
                    # Campos específicos que queremos en params
                    for key in ["conf_mode", "apply_to", "wave_model", "optimizer", "tx_pos", "rx_pos"]:
                        if key in row and row[key] is not None:
                            params_dict[key] = row[key]
                    
                    # Defaults para optimización si no se especificaron en la UI (limitación de tabla)
                    if params_dict.get("conf_mode") == "optimize":
                        if "tx_pos" not in params_dict: params_dict["tx_pos"] = [0, -5, 2]
                        if "rx_pos" not in params_dict: params_dict["rx_pos"] = [0, 5, 2]
                    
                    clean_step["params"] = params_dict
                
                final_timeline.append(clean_step)

            # Configuración del entorno (YAML o Defaults UI)
            if st.session_state['loaded_yaml'] and uploaded_file:
                # Usar el environment del YAML cargado
                full_config = {"environment": st.session_state['loaded_yaml']['environment'], "timeline": final_timeline}
            else:
                # Environment mínimo por defecto
                full_config = {
                    "environment": {
                        "ris_params": {
                            "center": [0,0,0], "boresight": "x", "ncol": 40, "nrow": 40,
                            "frequency_hz": 28.5e9, "num_bits": 1
                        },
                        "defaults": {"tx_gain": 15, "rx_gain": 15}
                    },
                    "timeline": final_timeline
                }

            try:
                runner.load_config(full_config)
                prog = st.progress(0)
                for i, step in enumerate(final_timeline):
                    runner.run_step(step, log_callback=log_message)
                    prog.progress((i+1)/len(final_timeline))
                st.success("Scenario Completed")
            except Exception as e:
                st.error(f"Run Error: {e}")
                log_message(f"ERR: {e}")
                
    with st.expander("Live Logs", expanded=True):
        for l in st.session_state['logs']: st.text(l)

# ==========================================
# TAB 3: VISUALIZATION
# ==========================================
with tab_viz:
    st.header("3D Visualization")
    st.info("Visualizing configuration from Manual Control tab.")
    
    # 1. Setup Scene
    fig = go.Figure()

    # 2. RIS Physics & Dimensions for Visualization
    # Recalculamos dimensiones visuales basadas en la frecuencia manual
    lam_vis = c / (man_freq * 1e9)
    dx_vis = 0.45 * lam_vis
    
    # Dimensiones reales (40x40 elementos)
    w_real = 40 * dx_vis
    h_real = 40 * dx_vis
    
    # Factor de escala visual (para que la RIS se vea bien en una escena de metros)
    SCALE = 5.0 
    w_vis = w_real * SCALE
    h_vis = h_real * SCALE
    depth = 0.1 * max(w_vis, h_vis) # Grosor arbitrario visual
    
    # 3. Orientación según Boresight
    # Definimos dimensiones de la caja [Largo X, Largo Y, Largo Z]
    if man_boresight == 'x':
        box_dim = [depth, w_vis, h_vis]
        bs_vec = np.array([1, 0, 0])
    elif man_boresight == 'y':
        box_dim = [w_vis, depth, h_vis]
        bs_vec = np.array([0, 1, 0])
    else: # z
        box_dim = [w_vis, h_vis, depth]
        bs_vec = np.array([0, 0, 1])

    # 4. Calcular vértices del cubo centrado en man_ris_center
    cx, cy, cz = man_ris_center
    lx, ly, lz = box_dim[0], box_dim[1], box_dim[2]
    
    # Límites
    x_min, x_max = cx - lx/2, cx + lx/2
    y_min, y_max = cy - ly/2, cy + ly/2
    z_min, z_max = cz - lz/2, cz + lz/2
    
    # 8 Vértices del cubo
    x_cube = [x_min, x_min, x_max, x_max, x_min, x_min, x_max, x_max]
    y_cube = [y_min, y_max, y_max, y_min, y_min, y_max, y_max, y_min]
    z_cube = [z_min, z_min, z_min, z_min, z_max, z_max, z_max, z_max]
    
    # Índices para Mesh3d
    i = [7, 0, 0, 0, 4, 4, 6, 6, 4, 0, 3, 2]
    j = [3, 4, 1, 2, 5, 6, 5, 2, 0, 1, 6, 3]
    k = [0, 7, 2, 3, 6, 7, 1, 1, 5, 5, 7, 6]

    # Dibujar RIS
    fig.add_trace(go.Mesh3d(
        x=x_cube, y=y_cube, z=z_cube,
        i=i, j=j, k=k,
        color='blue', opacity=0.3, name='RIS', flatshading=True
    ))

    # 5. Dibujar TX y RX (Usando variables corregidas: man_tx, man_rx)
    fig.add_trace(go.Scatter3d(
        x=[man_tx[0]], y=[man_tx[1]], z=[man_tx[2]],
        mode='markers+text', marker=dict(size=6, color='green'),
        text=["TX"], textposition="top center", name='TX'
    ))
    
    fig.add_trace(go.Scatter3d(
        x=[man_rx[0]], y=[man_rx[1]], z=[man_rx[2]],
        mode='markers+text', marker=dict(size=6, color='red'),
        text=["RX"], textposition="top center", name='RX'
    ))

    # 6. Flechas y Vectores (Helper Function)
    def add_arrow(fig, start, vector, color, name, scale=1.0):
        norm = np.linalg.norm(vector)
        if norm == 0: return
        u, v, w = vector / norm
        end = start + (vector / norm) * scale
        
        # Línea
        fig.add_trace(go.Scatter3d(
            x=[start[0], end[0]], y=[start[1], end[1]], z=[start[2], end[2]],
            mode='lines', line=dict(color=color, width=4), showlegend=False
        ))
        # Cono
        fig.add_trace(go.Cone(
            x=[end[0]], y=[end[1]], z=[end[2]],
            u=[u], v=[v], w=[w],
            sizemode="absolute", sizeref=0.5, anchor="tip",
            showscale=False, colorscale=[[0, color], [1, color]], name=name
        ))

    # Flecha Boresight (Normal de la RIS)
    ris_pos_arr = np.array(man_ris_center)
    add_arrow(fig, ris_pos_arr, bs_vec, 'orange', 'Normal', scale=1.5)
    
    # Flecha TX -> RIS
    tx_vec = ris_pos_arr - np.array(man_tx)
    add_arrow(fig, np.array(man_tx), tx_vec, 'green', 'TX Dir', scale=2.0)
    
    # Flecha RX -> RIS (visualmente inversa para ver el path completo)
    rx_vec = ris_pos_arr - np.array(man_rx)
    # Dibujamos línea punteada para el path
    fig.add_trace(go.Scatter3d(
        x=[man_tx[0], man_ris_center[0], man_rx[0]],
        y=[man_tx[1], man_ris_center[1], man_rx[1]],
        z=[man_tx[2], man_ris_center[2], man_rx[2]],
        mode='lines', line=dict(color='gray', dash='dash'), name='Path'
    ))

    # 7. Layout final
    fig.update_layout(
        scene=dict(
            xaxis=dict(title='X (m)', range=[-10, 10]),
            yaxis=dict(title='Y (m)', range=[-10, 10]),
            zaxis=dict(title='Z (m)', range=[-1, 10]),
            aspectmode='data' # Mantiene proporciones reales 1:1:1
        ),
        margin=dict(r=0, l=0, b=0, t=0),
        height=600
    )
    
    st.plotly_chart(fig, use_container_width=True)