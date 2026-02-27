import argparse
import yaml
import sys
import time
from pathlib import Path
import subprocess
import platform

# --- 1. CONFIGURATION OF PATHS ---
ROOT_DIR = Path(__file__).parent
LIBS_DIR = ROOT_DIR / "libs"

if str(LIBS_DIR) not in sys.path:
    sys.path.append(str(LIBS_DIR))

try:
    from src.ris_server_controller import RISServerController
    from src.scenario_runner import RISScenarioRunner
except ImportError as e:
    print(f"❌ Critical error of import: {e}")
    sys.exit(1)

# --- 2. LOGGING FUNCTION ---
def console_log(message: str):
    """Simple callback to print to terminal with timestamp."""
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

# --- 3. MAIN LOGIC ---
def main():
    parser = argparse.ArgumentParser(description="CLI RIS scenario executor")
    parser.add_argument("file", type=str, help="YAML file path of the scenario")
    
    # Connection args
    parser.add_argument("--ip", type=str, default="127.0.0.1", help="IP of the RIS server")
    parser.add_argument("--port", type=int, default=17000, help="Port of the RIS server")
    
    # Logging args
    parser.add_argument("--json", action="store_true", help="Enable local JSONL logging (Default: Disabled)")
    
    # Influx args (Default: None/Disabled)
    parser.add_argument("--influx", type=str, default=None, help="IP of InfluxDB/Telegraf to send metrics via UDP")

    args = parser.parse_args()
    yaml_path = Path(args.file)

    if not yaml_path.exists():
        print(f"❌ The file does not exist: {yaml_path}")
        sys.exit(1)

    print(f"🚀 Starting CLI scenario executor")
    print(f"📂 Loading scenario: {yaml_path.name}")
    
    # Log Status Feedback
    if args.json:
        print(f"💾 Local Logging: ENABLED (logs/ folder)")
    else:
        print(f"💾 Local Logging: DISABLED")

    if args.influx:
        print(f"📡 InfluxDB Sending: ENABLED ({args.influx}:8094)")

        # Determinamos el parámetro según el sistema operativo (-n en Windows, -c en resto)
        param = "-n" if platform.system().lower() == "windows" else "-c"
        command = ["ping", param, "1", args.influx]
        
        # Ejecutamos el ping de forma silenciosa
        ping_check = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if ping_check.returncode != 0:
            print(f"❌ Test parado: La IP de InfluxDB ({args.influx}) no responde al ping.")
            sys.exit(1)
    else:
        print(f"📡 InfluxDB Sending: DISABLED")

    print(f"🔌 Connecting to RIS {args.ip}:{args.port}...")

    # Instantiate Controller
    controller = RISServerController(ip=args.ip, port=args.port)
    
    # Instantiate Runner with logging preferences
    runner = RISScenarioRunner(
        controller, 
        enable_json_log=args.json,
        influx_ip=args.influx
    )

    try:
        with open(yaml_path, 'r') as f:
            config_data = yaml.safe_load(f)

        runner.load_config(config_data)
        timeline = config_data.get('timeline', [])
        total_steps = len(timeline)
        
        print(f"📋 Steps detected: {total_steps}\n")
        print("-" * 40)

        for i, step in enumerate(timeline):
            step_num = i + 1
            print(f"🔹 Step {step_num}/{total_steps}")
            runner.run_step(step, log_callback=console_log)
            print("-" * 40)

        print("\n✅ Sequence completed successfully.")

    except KeyboardInterrupt:
        print("\n🛑 Execution interrupted by user.")
        controller.disconnect()
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        controller.disconnect()
        sys.exit(1)

if __name__ == "__main__":
    main()

    # Examples of usage (Bash):
    # 1. Basic command
    # uv run python run_scenario.py scenarios/test_1bit.yaml

    # 2a. Custom IP and port for FR2 !
    # uv run python run_scenario.py scenarios/test_1.yaml --ip 127.0.0.1 --port 17000

    # 2b. Custom IP and port for FR1 !
    # uv run python run_scenario.py scenarios/test_fr1.yaml --ip 127.0.0.1 --port 18000

    # 3. Enable influx connection and JSONL logging
    # uv run python run_scenario.py scenarios/test.yaml --influx 10.0.26.5 --json