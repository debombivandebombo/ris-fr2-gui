# RIS Control GUI

This project provides a Streamlit-based Web GUI to control the GreenerWave Reconfigurable Intelligent Surface (RIS) and visualize the setup in 3D.

## Prerequisites

- [uv](https://github.com/astral-sh/uv) (for dependency management)
- Python 3.10+

## Installation

This project is managed by `uv`. Sync the dependencies:

```bash
uv sync
```

## Usage

### 1. Start the RIS Server

You need the hardware controller server running first.
Navigate to your `gw-ris-fr2-sandbox` project folder and run:

```bash
cd ../gw-ris-fr2-sandbox
uv run python ris_hardware_server.py
```

### 2. Launch the GUI

In this project folder (`gw-ris-fr2-gui`), launch the Streamlit app:

```bash
streamlit run app.py
```

*Note: If you are not in an activated virtual environment, use `uv run streamlit run app.py`.*
