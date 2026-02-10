# Justfile for RIS Control Project

# Muestra los comandos disponibles (Default)
default:
    @just --list

# Lanza la interfaz web de Streamlit
gui:
    uv run streamlit run app2.py

# Ejecuta un escenario YAML específico desde la terminal
# Uso: just run scenarios/test_complex.yaml
run file:
    uv run python run_scenario.py {{file}}

# Ejecuta el test rápido de 1 bit por defecto
test:
    uv run python run_scenario.py scenarios/test_1bit.yaml

# Instala dependencias nuevas y sincroniza
sync:
    uv sync