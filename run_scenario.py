import argparse
import yaml
import sys
import time
from pathlib import Path

# --- 1. CONFIGURATION OF PATHS (Same as app2.py) ---
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
    # Define command line arguments
    parser = argparse.ArgumentParser(
        description="CLI RIS scenario executor"
    )
    parser.add_argument(
        "file", 
        type=str, 
        help="YAML file path of the scenario"
    )
    parser.add_argument(
        "--ip", 
        type=str, 
        default="127.0.0.1", 
        help="IP of the RIS server (Default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", 
        type=int, 
        default=17000, 
        help="Port of the RIS server (Default: 17000)"
    )

    args = parser.parse_args()
    yaml_path = Path(args.file)

    # Basic validations
    if not yaml_path.exists():
        print(f"❌ The file does not exist: {yaml_path}")
        sys.exit(1)

    print(f"🚀 Starting CLI scenario executor")
    print(f"📂 Loading scenario: {yaml_path.name}")
    print(f"🔌 Connecting to {args.ip}:{args.port}...")

    # Instantiate Controller
    controller = RISServerController(ip=args.ip, port=args.port)
    
    # Instantiate Runner
    runner = RISScenarioRunner(controller)

    try:
        # Cargar YAML
        with open(yaml_path, 'r') as f:
            config_data = yaml.safe_load(f)

        # Cargar configuración en el Runner
        runner.load_config(config_data)
        
        timeline = config_data.get('timeline', [])
        total_steps = len(timeline)
        
        print(f"📋 Steps detected: {total_steps}\n")
        print("-" * 40)

        # Execution loop
        for i, step in enumerate(timeline):
            # Simple text progress bar
            step_num = i + 1
            print(f"🔹 Step {step_num}/{total_steps}")
            
            # Run step passing 'print' (or our wrapper function) as callback
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

    # 2. Custom IP and port
    # uv run python run_scenario.py scenarios/test_1bit.yaml --ip 192.168.1.50 --port 8080