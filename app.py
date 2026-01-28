import streamlit as st
import numpy as np
import plotly.graph_objects as go
from scipy.constants import c, pi
import sys
import os

# Add the libs directory to path if needed, though uv should handle installs
sys.path.append(os.path.abspath("libs"))

from surpRISe.components.ris import RIS
from surpRISe.components.antenna import Antenna
from surpRISe.channels.tx2ris2rx.tang_general_channel import tang_general_channel
from ris_server_controller import RISConfig, RISServerController

# Page Configuration
st.set_page_config(
    page_title="RIS Control",
    page_icon="📡",
    layout="wide"
)

# --- Session State Initialization ---
if 'controller' not in st.session_state:
    st.session_state['controller'] = RISServerController()

if 'connected' not in st.session_state:
    st.session_state['connected'] = False

if 'ris_config_status' not in st.session_state:
    st.session_state['ris_config_status'] = "Not Configured"

# --- Sidebar Controls ---
st.sidebar.title("RIS Control Panel")

# Connection Control
st.sidebar.subheader("Connection")
col1, col2 = st.sidebar.columns(2)

def connect_ris():
    try:
        st.session_state['controller'].connect()
        st.session_state['connected'] = True
        st.toast("Connected to RIS Server", icon="✅")
    except Exception as e:
        st.error(f"Failed to connect: {e}")

def disconnect_ris():
    try:
        st.session_state['controller'].disconnect()
        st.session_state['connected'] = False
        st.toast("Disconnected from RIS Server", icon="❌")
    except Exception as e:
        st.error(f"Failed to disconnect: {e}")

with col1:
    if st.button("Connect", disabled=st.session_state['connected'], type="primary"):
        connect_ris()

with col2:
    if st.button("Disconnect", disabled=not st.session_state['connected']):
        disconnect_ris()

# Status Indicator
status_color = "green" if st.session_state['connected'] else "red"
status_text = "CONNECTED" if st.session_state['connected'] else "DISCONNECTED"
st.sidebar.markdown(f"Status: <span style='color:{status_color}; font-weight:bold'>{status_text}</span>", unsafe_allow_html=True)

st.sidebar.markdown("---")

# Parameters
st.sidebar.header("Configuration")

# RIS Parameters
with st.sidebar.expander("RIS Parameters", expanded=True):
    ris_center_x = st.number_input("Center X (m)", value=0.0, step=0.1, key="ris_x")
    ris_center_y = st.number_input("Center Y (m)", value=0.0, step=0.1, key="ris_y")
    ris_center_z = st.number_input("Center Z (m)", value=0.0, step=0.1, key="ris_z")
    
    col_dim1, col_dim2 = st.columns(2)
    # Fixed Dimensions
    ris_ncol = 40
    ris_nrow = 40
    st.info(f"RIS Dimensions: {ris_ncol} x {ris_nrow}")

    # Boresight Selection
    ris_boresight = st.selectbox("RIS Boresight Axis", ["x", "y", "z"], index=0)
    
    # Constants for RIS (Fixed or Advanced?)
    # For now, let's keep some fixed or derived as per the example
    FC = 28e9  # Frequency 28 GHz (Example default)
    LAMBDA = c / FC
    
    # Adding Frequency control just in case
    fc_ghz = st.number_input("Frequency (GHz)", value=28.0, step=0.1)
    FC = fc_ghz * 1e9
    LAMBDA = c / FC
    
    ris_dx = 0.45 * LAMBDA # Default from example
    ris_dy = 0.45 * LAMBDA

# TX Parameters
with st.sidebar.expander("TX Parameters", expanded=False):
    tx_x = st.number_input("TX X (m)", value=3.0, step=0.1, key="tx_x")
    tx_y = st.number_input("TX Y (m)", value=-3.0, step=0.1, key="tx_y")
    tx_z = st.number_input("TX Z (m)", value=0.0, step=0.1, key="tx_z")
    tx_gain = st.number_input("TX Gain (dBi)", value=16.0, step=1.0, key="tx_gain")

# RX Parameters
with st.sidebar.expander("RX Parameters", expanded=False):
    rx_x = st.number_input("RX X (m)", value=3.0, step=0.1, key="rx_x")
    rx_y = st.number_input("RX Y (m)", value=3.0, step=0.1, key="rx_y")
    rx_z = st.number_input("RX Z (m)", value=0.0, step=0.1, key="rx_z")
    rx_gain = st.number_input("RX Gain (dBi)", value=16.0, step=1.0, key="rx_gain")

# Optimization Mode
st.sidebar.subheader("Optimization Settings")
apply_vh = st.sidebar.selectbox("Polarization Mode", ["h", "v", "both"], index=0)
wave_model = st.sidebar.selectbox("Wave Model", ["spherical", "plane"], index=0)
optimizer = st.sidebar.selectbox("Optimizer", ["direct_disc", "grid_search", "chen_alg1", "1d_search", "iterative"], index=0)


# --- Calculation & Application Logic ---
def apply_configuration():
    if not st.session_state['connected']:
        st.error("Please connect to the RIS Server first.")
        return

    with st.spinner("Calculating optimization..."):
        try:
            # 1. Instantiate Objects
            # TX
            tx_pos = [tx_x, tx_y, tx_z]
            tx = Antenna(position=tx_pos, gain_dbi=tx_gain)
            ris_center = [ris_center_x, ris_center_y, ris_center_z]
            tx.point_to(ris_center)

            # RIS
            # Fixed params from example
            RIS_DELTA_H = LAMBDA / 2
            RIS_DELTA_V = LAMBDA / 2
            RIS_PHASE_DICT = {"0": 0, "1": pi}
            RIS_ATT_DICT = {"0": 0.9, "1": 0.9}

            ris = RIS(
                center=ris_center, boresight=ris_boresight, 
                Ncol=ris_ncol, Nrow=ris_nrow, fc=FC,
                delta_h=RIS_DELTA_H, delta_v=RIS_DELTA_V, 
                dx=ris_dx, dy=ris_dy,
                phase_shifts_dict=RIS_PHASE_DICT, att_dict=RIS_ATT_DICT
            )

            # RX
            rx_pos = [rx_x, rx_y, rx_z]
            rx = Antenna(position=rx_pos, gain_dbi=rx_gain)
            rx.point_to(ris_center) # Enforce pointing to RIS
            
            # Channel & Optimization
            ch = tang_general_channel()
            ch.optimize(
                optimizer=optimizer, 
                mode="disc", 
                wave_model=wave_model,
                tx_antenna=tx, 
                rx_antenna=rx, 
                ris=ris
            )

            opt_pattern = ris.get_all_state_indices()

            # Prepare Pattern
            if apply_vh == 'v':
                patron_v = opt_pattern
                patron_h = np.zeros_like(patron_v)
            elif apply_vh == 'h':
                patron_h = opt_pattern
                patron_v = np.zeros_like(patron_h)
            else: # both
                patron_v = opt_pattern
                patron_h = opt_pattern

            # Apply to Controller
            st.session_state['controller'].apply_config(RISConfig(
                state_matrix_v=patron_v, 
                state_matrix_h=patron_h
            ))
            
            st.session_state['ris_config_status'] = "Applied Successfully"
            st.toast("Configuration Applied!", icon="🚀")
            
        except Exception as e:
            st.error(f"Error applying config: {e}")
            st.session_state['ris_config_status'] = "Error"

st.sidebar.markdown("---")
if st.sidebar.button("Apply Configuration", type="primary"):
    apply_configuration()

# --- Main Area: 3D Visualization ---
st.title("RIS Environment Visualization")

# Plotly 3D Scene
def create_3d_scene():
    fig = go.Figure()

    # RIS Representation (Box)
    # Dimensions
    ris_width_real = ris_ncol * ris_dx
    ris_height_real = ris_nrow * ris_dx
    
    # Visual Scaling (RIS is physically small ~20cm, so we scale it up for visibility in the 10m scene)
    VISUAL_SCALE = 5.0 
    
    w_vis = ris_width_real * VISUAL_SCALE
    h_vis = ris_height_real * VISUAL_SCALE
    
    # Visual Depth (arbitrary small value to look like a box)
    depth = 0.3 * max(w_vis, h_vis)
    
    # Determine Box Dimensions based on Boresight
    # Boresight is the 'normal' to the face. The face is the main RIS surface.
    # If Boresight X: Depth is along X. Face is Y-Z (Width, Height).
    # If Boresight Y: Depth is along Y. Face is X-Z.
    # If Boresight Z: Depth is along Z. Face is X-Y.
    
    if ris_boresight == 'x':
        dx_box = depth
        dy_box = w_vis
        dz_box = h_vis
    elif ris_boresight == 'y':
        dx_box = w_vis
        dy_box = depth
        dz_box = h_vis
    else: # z
        dx_box = w_vis
        dy_box = h_vis
        dz_box = depth

    # Define the 8 corners of the cube relative to center
    x_min, x_max = ris_center_x - dx_box/2, ris_center_x + dx_box/2
    y_min, y_max = ris_center_y - dy_box/2, ris_center_y + dy_box/2
    z_min, z_max = ris_center_z - dz_box/2, ris_center_z + dz_box/2

    # Plotly Mesh3d Cube
    # 8 vertices
    x = [x_min, x_min, x_max, x_max, x_min, x_min, x_max, x_max]
    y = [y_min, y_max, y_max, y_min, y_min, y_max, y_max, y_min]
    z = [z_min, z_min, z_min, z_min, z_max, z_max, z_max, z_max]
    
    # Index for triangles (standard cube triangulation)
    i = [7, 0, 0, 0, 4, 4, 6, 6, 4, 0, 3, 2]
    j = [3, 4, 1, 2, 5, 6, 5, 2, 0, 1, 6, 3]
    k = [0, 7, 2, 3, 6, 7, 1, 1, 5, 5, 7, 6]

    fig.add_trace(go.Mesh3d(
        x=x, y=y, z=z,
        i=i, j=j, k=k,
        color='blue',
        opacity=0.5,
        name='RIS',
        flatshading=True
    ))
    
    # RIS Center Point
    fig.add_trace(go.Scatter3d(
        x=[ris_center_x], y=[ris_center_y], z=[ris_center_z],
        mode='markers', marker=dict(size=5, color='blue'),
        name='RIS Center'
    ))

    # TX Position
    fig.add_trace(go.Scatter3d(
        x=[tx_x], y=[tx_y], z=[tx_z],
        mode='markers+text', marker=dict(size=8, color='green'),
        text=["TX"], textposition="top center",
        name='TX'
    ))

    # RX Position
    fig.add_trace(go.Scatter3d(
        x=[rx_x], y=[rx_y], z=[rx_z],
        mode='markers+text', marker=dict(size=8, color='red'),
        text=["RX"], textposition="top center",
        name='RX'
    ))

    # Lines TX -> RIS -> RX (Visual Aid)
    fig.add_trace(go.Scatter3d(
        x=[tx_x, ris_center_x, rx_x],
        y=[tx_y, ris_center_y, rx_y],
        z=[tx_z, ris_center_z, rx_z],
        mode='lines', line=dict(color='gray', dash='dash', width=2),
        name='Path'
    ))

    # Layout
    fig.update_layout(
        scene=dict(
            xaxis=dict(title='X (m)', range=[-5, 5]),
            yaxis=dict(title='Y (m)', range=[-5, 5]),
            zaxis=dict(title='Z (m)', range=[-5, 5]),
            aspectmode='manual',
            aspectratio=dict(x=1, y=1, z=1)
        ),
        margin=dict(r=0, l=0, b=0, t=0),
        height=600,
    )

    # --- Arrow Helper ---
    def add_arrow(fig, start, vector, color, name, scale=1.0):
        # Normalize vector
        norm = np.linalg.norm(vector)
        if norm == 0: return
        u, v, w = vector / norm
        
        # Scale length
        length = scale
        end = start + (vector / norm) * length
        
        fig.add_trace(go.Scatter3d(
            x=[start[0], end[0]],
            y=[start[1], end[1]],
            z=[start[2], end[2]],
            mode='lines',
            line=dict(color=color, width=5),
            name=name,
            showlegend=False
        ))
        
        # Cone for tip
        fig.add_trace(go.Cone(
            x=[end[0]], y=[end[1]], z=[end[2]],
            u=[u], v=[v], w=[w],
            sizemode="absolute",
            sizeref=0.2, # Cone size
            showscale=False,
            anchor="tip",
            colorscale=[[0, color], [1, color]],
            name=name
        ))

    # --- Add Arrows ---
    
    # RIS Boresight Arrow
    # Vector depends on boresight axis
    if ris_boresight == 'x':
        bs_vec = np.array([1, 0, 0])
    elif ris_boresight == 'y':
        bs_vec = np.array([0, 1, 0])
    else:
        bs_vec = np.array([0, 0, 1])
        
    add_arrow(fig, np.array([ris_center_x, ris_center_y, ris_center_z]), bs_vec, 'orange', 'RIS Boresight', scale=1.0)
    
    # TX Pointing Arrow (to RIS Center)
    tx_pos = np.array([tx_x, tx_y, tx_z])
    ris_pos = np.array([ris_center_x, ris_center_y, ris_center_z])
    tx_vec = ris_pos - tx_pos
    add_arrow(fig, tx_pos, tx_vec, 'green', 'TX Direction', scale=1.5) # Short arrow indicating direction
    
    # RX Pointing Arrow (to RIS Center)
    rx_pos = np.array([rx_x, rx_y, rx_z])
    rx_vec = ris_pos - rx_pos
    add_arrow(fig, rx_pos, rx_vec, 'red', 'RX Direction', scale=1.5)


    return fig

st.plotly_chart(create_3d_scene(), use_container_width=True)

# Debug Info / Logs (Optional)
st.subheader("System Status")
st.info(f"RIS Config Status: {st.session_state['ris_config_status']}")
