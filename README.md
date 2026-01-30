# RIS Control GUI

This project provides a professional Streamlit-based Web GUI to control the GreenerWave Reconfigurable Intelligent Surface (RIS). It supports manual control, 3D visualization, and automated test sequences via YAML configuration.

## Features

* **Manual Control:** Real-time configuration of frequency, bit resolution, and beamforming optimization modes.
* **Scenario Manager:** Define complex testing sequences (timelines) using YAML files or the built-in visual editor.
* **3D Visualization:** Visual feedback of the RIS, Transmitter (TX), and Receiver (RX) geometry.
* **Modular Architecture:** Logic separated into `src/` and external libraries in `libs/`.

## Prerequisites

- [uv](https://github.com/astral-sh/uv) (for dependency management)
- Python 3.10+
- **RIS Hardware Server:** A running instance of the `gw-ris-fr2-sandbox` server.

## Project Structure

```text
gw-ris-fr2-gui/
├── app2.py                    # Main Entry Point (Streamlit)
├── pyproject.toml             # Dependencies
├── src/                       # Source Code
│   ├── ris_server_controller.py   # Socket communication
│   └── scenario_runner.py         # Logic for executing test steps
├── libs/                      # External/Private Libraries
│   └── surpRISe/                  # Optimization Core
└── scenarios/                 # YAML Test Configurations
    └── test_example.yaml
```

## Installation

This project is managed by `uv`. Sync the dependencies:

```bash
uv sync
```

## Usage

### 1. Start the RIS Server

You need the hardware controller server running first to accept commands. Navigate to your sandbox project folder and run:

```bash
cd ../gw-ris-fr2-sandbox
uv run python ris_hardware_server.py
```

### 2. Launch the GUI

In this project folder (`gw-ris-fr2-gui`), launch the Streamlit app:

```bash
# Note: Use app2.py (or rename it to app.py if preferred)
uv run streamlit run app2.py
```

## Scenario Manager & Automated Tests
The Scenario Manager tab allows you to execute sequences of actions automatically. You can define these sequences using the visual table editor in the UI or by uploading a YAML configuration file.

**How to use YAML Configuration**

To define reproducible tests, create a `.yaml` file in the `scenarios/` folder. The file consists of two main sections: `environment` and `timeline`.

1. Environment Section
Defines the physical setup and immutable parameters of the RIS for the test session.

```yaml
environment:
  ris_params:
    name: "RIS_Lab_Setup"
    center: [0.0, 0.0, 0.0]  # RIS Center [x, y, z]
    boresight: "x"           # Normal vector direction ('x', 'y', or 'z')
    ncol: 40                 # Number of columns
    nrow: 40                 # Number of rows
    frequency_hz: 28.5e9     # Operating Frequency
    num_bits: 1              # Resolution (e.g., 1 bit = 2 states)
    
    # (Optional) Physics Overrides
    # dx: 0.005
    # dy: 0.005
    
  defaults:
    tx_gain: 16
    rx_gain: 16
    wave_model: "spherical"
```

2. Timeline Section

Defines the sequence of steps to execute.

- **action:** Can be power_on, power_off, or configure.

- **params:** Required for configure action. Contains optimization settings and geometry.

```yaml
timeline:
  - step: "Initialization"
    action: "power_on"
    delay_after: 2

  - step: "Baseline Measurement"
    action: "configure"
    params:
      conf_mode: "zeros"     # Options: zeros, ones, random, optimize
      apply_to: "both"       # Options: v, h, both
    delay_after: 5

  - step: "User A Optimization"
    action: "configure"
    params:
      conf_mode: "optimize"
      apply_to: "v"
      optimizer: "grid_search"
      wave_model: "plane"
      # Dynamic geometry for this step
      tx_pos: [-3.0, -3.0, 1.0]
      rx_pos: [3.0, 3.0, 1.0]
    delay_after: 10

  - step: "Shutdown"
    action: "power_off"
```

**Using the UI Editor**

If you don't upload a YAML file, you can use the interactive table in the Scenario Manager tab to add steps manually.

- Note: The UI editor is simplified. For complex geometries (changing TX/RX positions per step), using a YAML file is recommended.
