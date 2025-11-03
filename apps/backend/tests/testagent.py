import sys
import os

# Asegura que el import funciona desde el repo raíz
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent import run_single_agent_workflow

def main():
    # Ejemplo de tarea: diseño de un filtro pasa banda simple
    example_task = (
        "Diseña una PSU 24V/3A aislada con PFC"
    )

    print("=== Ejecutando agente con ejemplo de tarea ===")
    result = run_single_agent_workflow(example_task)
    print("\n=== Resultado Agente ===")
    print(result)

if __name__ == "__main__":
    main()
